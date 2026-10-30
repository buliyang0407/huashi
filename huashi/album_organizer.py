"""Classification changes only: atomic moves, source checks and undo receipts."""
from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import uuid

from .storage import utc_now


class AlbumOrganizer:
    def __init__(self, store, backup_root):
        self.store = store
        self.backup_root = Path(backup_root)

    def _validate(self, conn, moves):
        if not isinstance(moves, list) or not 1 <= len(moves) <= 200:
            raise ValueError('一次整理需要 1–200 张图片')
        seen = set()
        result = []
        for move in moves:
            if not isinstance(move, dict) or any(not isinstance(move.get(k), str) or not move[k] for k in ('item_id', 'from_folder_id', 'to_folder_id')):
                raise ValueError('每张图片需提供 ID、原分类和目标分类')
            item_id = move['item_id']
            if item_id in seen:
                raise ValueError('同一图片不能重复出现')
            seen.add(item_id)
            row = conn.execute('SELECT * FROM album_items WHERE id=? AND deleted_at IS NULL', (item_id,)).fetchone()
            if row is None or row['source_type'] in ('pose', 'face'):
                raise ValueError('图片不存在或属于只读素材库')
            if row['folder_id'] != move['from_folder_id']:
                raise ValueError('图片分类已变化，请刷新后重新整理')
            if move.get('expected_file_path', row['file_path']) != row['file_path']:
                raise ValueError('图片路径已变化，请重新核对')
            if conn.execute('SELECT id FROM album_folders WHERE id=?', (move['to_folder_id'],)).fetchone() is None:
                raise ValueError('目标分类不存在，只读素材库不能作为目标')
            position = move.get('restore_position')
            if position is not None and (isinstance(position, bool) or not isinstance(position, int)):
                raise ValueError('回退位置必须为整数')
            result.append({**move, 'title': row['title'], 'file_path': row['file_path'], 'from_position': row['position']})
        return result

    def preview(self, moves):
        with closing(self.store.connect()) as conn:
            return {'moves': self._validate(conn, moves), 'count': len(moves), 'changes_files': False}

    def _write(self, path, value):
        tmp = path.with_suffix('.tmp')
        with tmp.open('x', encoding='utf-8') as stream:
            os.chmod(tmp, 0o600)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)

    def apply(self, moves):
        with closing(self.store.connect()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            try:
                planned = self._validate(conn, moves)
                self.backup_root.mkdir(parents=True, exist_ok=True)
                name = 'album-moves-' + uuid.uuid4().hex + '.json'
                path = self.backup_root / name
                receipt = {'version': 1, 'created_at': utc_now(), 'state': 'prepared', 'moves': planned,
                           'undo': [{'item_id': i['item_id'], 'from_folder_id': i['to_folder_id'], 'to_folder_id': i['from_folder_id'], 'restore_position': i['from_position'], 'expected_file_path': i['file_path']} for i in planned]}
                self._write(path, receipt)  # A durable undo record exists before any row changes.
                for item in planned:
                    position = item.get('restore_position')
                    if position is None:
                        position = conn.execute('SELECT COALESCE(MIN(position),0) FROM album_items WHERE folder_id=?', (item['to_folder_id'],)).fetchone()[0] - 10
                    conn.execute('UPDATE album_items SET folder_id=?, position=?, updated_at=? WHERE id=?', (item['to_folder_id'], position, utc_now(), item['item_id']))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        receipt['state'] = 'committed'
        try:
            self._write(path, receipt)
        except OSError:
            # Prepared receipt still contains the complete inverse plan; never reapply blindly.
            pass
        return {'moved': len(planned), 'receipt': name, 'changes_files': False, 'moves': planned}
