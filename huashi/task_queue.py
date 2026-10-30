"""Small durable serial dispatcher for RunPod. No cloud submission outside the service."""
from __future__ import annotations

import fcntl
import threading
from contextlib import contextmanager
from pathlib import Path
from .storage import utc_now

TERMINAL_REMOTE = {'COMPLETED', 'FAILED', 'CANCELLED', 'TIMED_OUT'}


def initialize_queue(conn):
    # Additive tables only: original task records, payloads and works are untouched.
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS runpod_queue (
          sequence INTEGER PRIMARY KEY AUTOINCREMENT,
          task_id TEXT NOT NULL UNIQUE,
          state TEXT NOT NULL DEFAULT 'waiting',
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runpod_queue_control (
          id INTEGER PRIMARY KEY CHECK (id = 1),
          paused INTEGER NOT NULL DEFAULT 0
        );
        INSERT OR IGNORE INTO runpod_queue_control(id, paused) VALUES (1, 0);
    ''')


class RunPodQueue:
    def __init__(self, service):
        self.service = service
        self.store = service.store
        self.lock_path = Path(service.data_root) / 'tmp' / 'runpod-queue.lock'
        self._thread_lock = threading.Lock()
        self._thread = None
        self._wake = threading.Event()
        self._stop = threading.Event()

    @contextmanager
    def _lease(self):
        # Survives competing threads/processes, released by the OS on process death.
        with self.lock_path.open('a') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def enqueue(self, task_id):
        with self.store.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('INSERT OR IGNORE INTO runpod_queue(task_id,created_at) VALUES (?,?)', (task_id, utc_now()))
            conn.execute("UPDATE tasks SET stage='queue_waiting',updated_at=? WHERE id=? AND status='queued'", (utc_now(), task_id))

    def _reconcile(self, conn):
        # Adopt only existing unfinished records; historical successes/failures stay intact.
        conn.execute('''INSERT OR IGNORE INTO runpod_queue(task_id,state,created_at)
          SELECT id, CASE WHEN status='running' OR runpod_job_id IS NOT NULL AND runpod_job_id!='' THEN 'active' ELSE 'waiting' END, created_at
          FROM tasks WHERE provider='runpod' AND status IN ('queued','running') AND stage!='saving_inputs'
          ORDER BY created_at,rowid''')
        rows = conn.execute('''SELECT q.task_id,t.status,t.stage,t.runpod_job_id,t.remote_submission_state
          FROM runpod_queue q JOIN tasks t ON t.id=q.task_id WHERE q.state IN ('waiting','active','blocked')''').fetchall()
        for row in rows:
            tid = row['task_id']
            if row['remote_submission_state'] == 'unknown' and not row['runpod_job_id']:
                if row['status'] != 'failed' or row['stage'] != 'submission_unknown':
                    conn.execute("UPDATE tasks SET status='failed',stage='submission_unknown',error=?,completed_at=?,updated_at=? WHERE id=?", ('远端提交结果未知；队列已停止派单，请联系维护核对 RunPod，未自动重投。', utc_now(), utc_now(), tid))
                conn.execute("UPDATE runpod_queue SET state='blocked' WHERE task_id=?", (tid,))
            elif row['status'] in {'success', 'failed', 'cancelled'}:
                conn.execute("UPDATE runpod_queue SET state='finished' WHERE task_id=?", (tid,))
            elif row['runpod_job_id']:
                conn.execute("UPDATE runpod_queue SET state='active' WHERE task_id=?", (tid,))
            elif row['status'] == 'running':
                # Died before POST boundary; the complete persisted input can be submitted safely.
                conn.execute("UPDATE tasks SET status='queued',stage='queue_waiting',updated_at=? WHERE id=?", (utc_now(), tid))
                conn.execute("UPDATE runpod_queue SET state='waiting' WHERE task_id=?", (tid,))

    def recover(self):
        with self._lease() as owned:
            if owned:
                with self.store.connect() as conn:
                    conn.execute('BEGIN IMMEDIATE')
                    self._reconcile(conn)

    def run_once(self):
        """Process at most one task while holding the cross-process execution lease."""
        with self._lease() as owned:
            if not owned:
                return False
            with self.store.connect() as conn:
                conn.execute('BEGIN IMMEDIATE')
                self._reconcile(conn)
                # Known jobs must be polled even when manual pause/another unknown job holds new submissions.
                row = conn.execute("SELECT task_id FROM runpod_queue WHERE state='active' ORDER BY sequence LIMIT 1").fetchone()
                if row is None:
                    paused = conn.execute('SELECT paused FROM runpod_queue_control WHERE id=1').fetchone()[0]
                    blocked = conn.execute("SELECT 1 FROM runpod_queue WHERE state='blocked' LIMIT 1").fetchone()
                    if paused or blocked:
                        return False
                    row = conn.execute("SELECT task_id FROM runpod_queue WHERE state='waiting' ORDER BY sequence LIMIT 1").fetchone()
                if row is None:
                    return False
                tid = row[0]
                conn.execute("UPDATE runpod_queue SET state='active' WHERE task_id=?", (tid,))
                conn.execute("UPDATE tasks SET status='running',updated_at=? WHERE id=?", (utc_now(), tid))
            try:
                self.service.process_task(tid)
            except Exception:
                # Never expose exception strings (may contain payloads/secrets), and preserve the POST boundary.
                task = self.store.get_task(tid)
                if task.get('runpod_job_id'):
                    self.store.update_task(tid, status='running', stage='recovery_wait', error='结果查询暂时中断，将继续查询原任务。')
                else:
                    self.store.update_task(tid, status='failed', stage='failed', error='任务处理失败，请查看设定后手动处理。', completed_at=utc_now())
            task = self.store.get_task(tid)
            with self.store.connect() as conn:
                conn.execute('BEGIN IMMEDIATE')
                self._reconcile(conn)
            return task['status'] in {'success', 'failed', 'cancelled'}

    def start(self):
        with self._thread_lock:
            self._wake.set()
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name='runpod-queue', daemon=True)
            self._thread.start()

    def _loop(self):
        # Keep one idle lightweight thread. Wakes promptly on new orders and controls.
        while not self._stop.is_set():
            self._wake.clear()
            try:
                finished = self.run_once()
            except Exception:
                finished = False
            if not finished:
                self._wake.wait(10)

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=2)

    def set_paused(self, paused):
        with self.store.connect() as conn:
            conn.execute('UPDATE runpod_queue_control SET paused=? WHERE id=1', (int(bool(paused)),))
        self._wake.set()

    def cancel(self, task_id):
        with self.store.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('''SELECT q.state,t.status,t.remote_submission_state,t.runpod_job_id
              FROM runpod_queue q JOIN tasks t ON t.id=q.task_id WHERE q.task_id=?''', (task_id,)).fetchone()
            if not row or row['state'] != 'waiting' or row['status'] != 'queued' or row['remote_submission_state'] != 'not_submitted' or row['runpod_job_id']:
                raise ValueError('只能取消尚未开始的排队任务；正在生成的任务继续保留。')
            conn.execute("UPDATE runpod_queue SET state='finished' WHERE task_id=?", (task_id,))
            conn.execute("UPDATE tasks SET status='cancelled',stage='cancelled',completed_at=?,updated_at=?,error=NULL WHERE id=?", (utc_now(), utc_now(), task_id))
        self._wake.set()

    def snapshot(self):
        with self.store.connect() as conn:
            paused = bool(conn.execute('SELECT paused FROM runpod_queue_control WHERE id=1').fetchone()[0])
            rows = conn.execute('''SELECT q.sequence,q.task_id,q.state FROM runpod_queue q
              JOIN tasks t ON t.id=q.task_id WHERE q.state IN ('waiting','active','blocked') ORDER BY q.sequence''').fetchall()
        result = {'paused': paused, 'active': [], 'pending': [], 'blocked': [], 'completed': []}
        for row in rows:
            task = self.service.get_task(row['task_id'])
            # A response may race a completion. Do not show stale queue entries as running.
            if row['state'] != 'blocked' and task['status'] not in {'queued', 'running'}:
                continue
            task['queue_sequence'] = row['sequence']
            key = {'waiting':'pending', 'active':'active', 'blocked':'blocked'}[row['state']]
            result[key].append(task)
        result['completed'] = [self.service.task_summary(t) for t in self.store.list_tasks() if t['provider']=='runpod' and t['status']=='success'][:12]
        result['completed_count'] = sum(t['provider']=='runpod' and t['status']=='success' for t in self.store.list_tasks())
        return result
