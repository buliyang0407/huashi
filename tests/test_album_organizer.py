import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from huashi.storage import HuashiStore


class AlbumOrganizerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = HuashiStore(self.root / 'db.sqlite')
        self.store.initialize()
        self.folder = self.store.create_album_folder('礼服参考')
        self.items = [self.store.save_album_upload('works', 'albums/a.png', 'A'), self.store.save_album_upload('works', 'albums/b.png', 'B')]

    def organizer(self):
        self.assertIsNotNone(importlib.util.find_spec('huashi.album_organizer'), 'Safe album move adapter is not implemented')
        from huashi.album_organizer import AlbumOrganizer
        return AlbumOrganizer(self.store, self.root / 'backups')

    def moves(self):
        return [{'item_id': i['id'], 'from_folder_id': 'works', 'to_folder_id': self.folder['id']} for i in self.items]

    def test_preview_is_read_only(self):
        before = self.store.db_path.read_bytes()
        result = self.organizer().preview(self.moves())
        self.assertEqual(len(result['moves']), 2)
        self.assertEqual(before, self.store.db_path.read_bytes())
        self.assertFalse((self.root / 'backups').exists())

    def test_apply_and_receipt_undo_preserve_paths_ids_and_original_positions(self):
        before = [self.store.get_album_item(i['id']) for i in self.items]
        result = self.organizer().apply(self.moves())
        receipt = json.loads((self.root / 'backups' / result['receipt']).read_text())
        self.assertEqual(result['moved'], 2)
        self.assertEqual({self.store.get_album_item(i['id'])['folder_id'] for i in self.items}, {self.folder['id']})
        self.organizer().apply(receipt['undo'])
        for i in before:
            after = self.store.get_album_item(i['id'])
            self.assertEqual((after['id'], after['file_path'], after['position'], after['folder_id']), (i['id'], i['file_path'], i['position'], i['folder_id']))

    def test_invalid_destination_is_atomic(self):
        moves = self.moves()
        moves[1]['to_folder_id'] = '__faces__'
        with self.assertRaises(ValueError):
            self.organizer().apply(moves)
        self.assertEqual({self.store.get_album_item(i['id'])['folder_id'] for i in self.items}, {'works'})

    def test_stale_source_and_duplicate_ids_are_rejected(self):
        self.store.move_album_item(self.items[0]['id'], self.folder['id'])
        with self.assertRaises(ValueError):
            self.organizer().apply(self.moves())
        self.assertEqual(self.store.get_album_item(self.items[1]['id'])['folder_id'], 'works')
        with self.assertRaises(ValueError):
            self.organizer().preview([self.moves()[1], self.moves()[1]])

    def test_deleted_or_virtual_source_cannot_be_moved(self):
        self.store.soft_delete_album_item(self.items[0]['id'])
        with self.assertRaises(ValueError):
            self.organizer().apply(self.moves())

    def test_failure_during_second_update_rolls_back_every_item(self):
        with self.store.connect() as conn:
            conn.execute("CREATE TRIGGER fail_move BEFORE UPDATE OF folder_id ON album_items WHEN OLD.id='" + self.items[1]['id'] + "' BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.organizer().apply(self.moves())
        self.assertEqual({self.store.get_album_item(i['id'])['folder_id'] for i in self.items}, {'works'})
        receipts=list((self.root/'backups').glob('*.json'))
        self.assertEqual(json.loads(receipts[0].read_text())['state'], 'prepared')

    def test_batch_limit_and_implicit_source_are_rejected(self):
        for moves in [[], [{}], self.moves() * 101, [{'item_id': self.items[0]['id'], 'to_folder_id': self.folder['id']}]]:
            with self.assertRaises(ValueError):
                self.organizer().preview(moves)


if __name__ == '__main__':
    unittest.main()
