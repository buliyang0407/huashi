import tempfile
import unittest
import zipfile
from pathlib import Path

from huashi.zip_utils import UnsafeZipError, safe_extract_zip


class ZipUtilsTest(unittest.TestCase):
    def test_safe_extract_zip_extracts_nested_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = root / "result.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("images/a.png", b"png-a")
                archive.writestr("images/b.jpg", b"jpg-b")

            extracted = safe_extract_zip(zip_path, root / "out")

            self.assertEqual(extracted, ["images/a.png", "images/b.jpg"])
            self.assertEqual((root / "out" / "images" / "a.png").read_bytes(), b"png-a")
            self.assertEqual((root / "out" / "images" / "b.jpg").read_bytes(), b"jpg-b")

    def test_safe_extract_zip_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = root / "bad.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("../escape.txt", b"nope")

            with self.assertRaises(UnsafeZipError):
                safe_extract_zip(zip_path, root / "out")

            self.assertFalse((root / "escape.txt").exists())


if __name__ == "__main__":
    unittest.main()
