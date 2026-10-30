"""Durable RunPod queue behavior, using only isolated SQLite and fake transport."""
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from huashi.service import HuashiService
from huashi.storage import HuashiStore
from huashi.runpod import RunPodClient, RunPodError, RunPodSubmissionUnknown
from tests.test_runpod import FakeRunPod

TEXT='runpod-noctq-v4-text-to-image'
EDIT='runpod-noctq-v4-lora-single-image-edit'

class QueueTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=HuashiStore(self.root/'db.sqlite');self.store.initialize()
        self.service=HuashiService(self.root,self.store,object())
    def task(self,prompt='test',app=TEXT):
        files={}
        if app==EDIT:
            b=io.BytesIO();Image.new('RGB',(64,64),'white').save(b,'PNG')
            files={'input_image1':{'filename':'original.png','content':b.getvalue()}}
        return self.service.create_task_from_form(app,{'input_prompt':prompt,'input_seed':'0','input_width':'512','input_height':'512','input_lora_strength':'0.75'},files,start_background=False)
    def run_one(self,fake=None):
        with patch.object(RunPodClient,'from_workflow',return_value=fake or FakeRunPod()):
            return self.service.task_queue.run_once()
    def test_fifo_across_workflows_and_independent_inputs(self):
        a=self.task('first');b=self.task('second',EDIT);c=self.task('third')
        self.run_one();self.assertEqual(self.store.get_task(a['id'])['status'],'success')
        self.assertEqual(self.store.get_task(b['id'])['status'],'queued');self.run_one()
        saved=self.store.get_task(b['id']);self.assertEqual(saved['input_payload']['values']['lora_strength'],'0.75')
        self.assertEqual(saved['input_payload']['values']['seed'],'0');self.assertTrue((self.root/saved['input_path']).exists())
        self.assertEqual([t['id'] for t in self.service.task_queue.snapshot()['pending']],[c['id']])
    def test_pause_survives_restart_and_only_delays_next_job(self):
        a=self.task();self.task('next');self.service.task_queue.set_paused(True)
        self.assertFalse(self.run_one());self.assertEqual(self.store.get_task(a['id'])['status'],'queued')
        other=HuashiService(self.root,self.store,object());self.assertTrue(other.task_queue.snapshot()['paused'])
        other.task_queue.set_paused(False);self.run_one();self.assertEqual(self.store.get_task(a['id'])['status'],'success')
    def test_cancel_keeps_history_upload_and_other_tasks(self):
        a=self.task(app=EDIT);b=self.task();self.service.task_queue.cancel(a['id'])
        self.assertEqual(self.store.get_task(a['id'])['status'],'cancelled');self.assertTrue((self.root/a['input_path']).exists())
        self.run_one();self.assertEqual(self.store.get_task(b['id'])['status'],'success')
        with self.assertRaises(ValueError):self.service.task_queue.cancel(b['id'])
    def test_restart_recovers_unsubmitted_waiting_tasks(self):
        a=self.task();other=HuashiService(self.root,self.store,object());other.task_queue.recover()
        with patch.object(RunPodClient,'from_workflow',return_value=FakeRunPod()):other.task_queue.run_once()
        self.assertEqual(self.store.get_task(a['id'])['status'],'success')
    def test_restart_known_job_polls_without_submit_even_while_paused(self):
        a=self.task();self.store.update_task(a['id'],status='running',stage='remote_running',runpod_job_id='job_123',remote_submission_state='submitted')
        self.service.task_queue.set_paused(True);self.service.task_queue.recover();fake=FakeRunPod();self.run_one(fake)
        self.assertEqual(fake.calls,['wait']);self.assertEqual(self.store.get_task(a['id'])['status'],'success')
    def test_unknown_submission_blocks_following_tasks_and_retry(self):
        a=self.task();b=self.task('next');self.run_one(FakeRunPod(submit_unknown=True));fake=FakeRunPod()
        self.assertFalse(self.run_one(fake));self.assertEqual(fake.calls,[])
        self.assertEqual(self.service.task_queue.snapshot()['blocked'][0]['id'],a['id'])
        self.assertEqual(self.store.get_task(b['id'])['status'],'queued')
        with self.assertRaises(ValueError):self.service.retry_task(a['id'],start_background=False)
        self.assertEqual(len(self.store.list_tasks()),2)
    def test_restart_at_ambiguous_boundary_never_resubmits(self):
        a=self.task();self.store.update_task(a['id'],status='running',stage='submitting',remote_submission_state='unknown')
        self.service.task_queue.recover();fake=FakeRunPod();self.assertFalse(self.run_one(fake));self.assertEqual(fake.calls,[])
        self.assertEqual(self.store.get_task(a['id'])['stage'],'submission_unknown')
    def test_poll_timeout_holds_slot_until_same_job_is_resolved(self):
        a=self.task();b=self.task('next')
        class Timeout(FakeRunPod):
            def wait(self,*args,**kw):raise RunPodError('网络超时')
        self.run_one(Timeout());self.assertEqual(self.store.get_task(a['id'])['status'],'running')
        self.assertEqual(self.store.get_task(b['id'])['status'],'queued')
        fake=FakeRunPod();self.run_one(fake);self.assertEqual(fake.calls,['wait'])
        self.assertEqual(self.store.get_task(a['id'])['status'],'success')
    def test_terminal_remote_failure_advances_without_resubmit(self):
        a=self.task();b=self.task('next')
        class Failure(FakeRunPod):
            def wait(self,job,on_status,**kw):on_status('FAILED');raise RunPodError('RunPod FAILED')
        self.run_one(Failure());self.assertEqual(self.store.get_task(a['id'])['status'],'failed')
        self.run_one();self.assertEqual(self.store.get_task(b['id'])['status'],'success')
    def test_preflight_failure_can_advance_without_gpu_submission(self):
        a=self.task();b=self.task();self.run_one(FakeRunPod(preflight_error=True));self.run_one()
        self.assertEqual(self.store.get_task(a['id'])['remote_submission_state'],'not_submitted');self.assertEqual(self.store.get_task(b['id'])['status'],'success')
    def test_two_dispatchers_never_overlap_and_pause_does_not_interrupt(self):
        a=self.task();b=self.task();entered=threading.Event();release=threading.Event();errors=[]
        class Slow(FakeRunPod):
            def wait(self,*args,**kw):entered.set();release.wait(5);return super().wait(*args,**kw)
        fake=Slow();other=HuashiService(self.root,self.store,object())
        def run():
            try:self.service.task_queue.run_once()
            except Exception as exc:errors.append(exc)
        with patch.object(RunPodClient,'from_workflow',return_value=fake):
            thread=threading.Thread(target=run);thread.start()
            try:
                self.assertTrue(entered.wait(3));self.service.task_queue.set_paused(True)
                self.assertFalse(other.task_queue.run_once())
                with self.assertRaises(ValueError):self.service.task_queue.cancel(a['id'])
                with self.assertRaises(ValueError):self.service.delete_task(a['id'])
            finally:release.set();thread.join(5)
        self.assertFalse(errors);self.assertEqual(fake.calls.count('submit'),1)
        self.assertFalse(self.run_one());self.assertEqual(self.store.get_task(b['id'])['status'],'queued')
    def test_input_save_failure_is_retained_but_never_dispatched(self):
        original=Path.write_bytes
        def broken(path,data):
            if 'uploads' in path.parts:raise OSError('disk failed')
            return original(path,data)
        with patch.object(Path,'write_bytes',broken):
            with self.assertRaises(ValueError):self.task(app=EDIT)
        saved=self.store.list_tasks()[0]
        self.assertEqual(saved['status'],'failed')
        self.assertEqual(saved['stage'],'input_save_failed')
        self.assertFalse(self.service.task_queue.snapshot()['pending'])

    def test_repeated_admission_does_not_duplicate_orders(self):
        a=self.task();self.service.task_queue.enqueue(a['id']);self.service.task_queue.enqueue(a['id'])
        self.assertEqual(len(self.service.task_queue.snapshot()['pending']),1)
        fake=FakeRunPod();self.run_one(fake);self.run_one(fake);self.assertEqual(fake.calls.count('submit'),1)

    def test_parallel_admissions_are_complete_before_dispatch(self):
        errors=[]
        def submit(i):
            try:self.task('order '+str(i))
            except Exception as exc:errors.append(exc)
        threads=[threading.Thread(target=submit,args=(i,)) for i in range(8)]
        for t in threads:t.start()
        for t in threads:t.join(5)
        self.assertEqual(errors,[])
        pending=self.service.task_queue.snapshot()['pending'];self.assertEqual(len(pending),8)
        self.assertEqual(len({t['queue_sequence'] for t in pending}),8)
        self.assertTrue(all(t['input_payload']['values']['prompt'].startswith('order ') for t in pending))

    def test_resume_does_not_bypass_unknown_hold(self):
        self.task();self.task();self.run_one(FakeRunPod(submit_unknown=True))
        self.service.task_queue.set_paused(False);fake=FakeRunPod();self.assertFalse(self.run_one(fake));self.assertEqual(fake.calls,[])

    def test_historical_rows_and_files_are_unchanged_by_initialization(self):
        a=self.task();self.run_one();before=self.store.get_task(a['id']);path=self.root/before['outputs'][0]['path'];original=path.read_bytes()
        self.store.initialize();HuashiService(self.root,self.store,object()).task_queue.recover()
        self.assertEqual(self.store.get_task(a['id']),before);self.assertEqual(path.read_bytes(),original)

if __name__=='__main__':unittest.main()
