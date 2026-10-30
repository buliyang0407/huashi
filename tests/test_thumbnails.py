from pathlib import Path
import tempfile
import unittest

from huashi.thumbnails import ThumbnailError, ThumbnailService


class ThumbnailServiceTest(unittest.TestCase):
    def test_rejects_paths_outside_data_root(self):
        service = ThumbnailService(Path("/tmp/huashi-data"))

        with self.assertRaises(ThumbnailError):
            service.source_path("../secret.png")

    def test_builds_stable_url_with_encoded_relative_path(self):
        service = ThumbnailService(Path("/tmp/huashi-data"))

        url = service.url_for("cache/task id/output 1.png", size=480, version="123-456")

        self.assertEqual(url, "/thumbs/480/cache%2Ftask%20id%2Foutput%201.png?v=123-456")

    def test_generates_thumbnail_when_pillow_is_available(self):
        try:
            from PIL import Image
        except ModuleNotFoundError:
            self.skipTest("Pillow is not installed in this Python environment")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "cache" / "task" / "large.png"
            source.parent.mkdir(parents=True)
            Image.new("RGB", (1600, 1200), "red").save(source)

            service = ThumbnailService(root)
            thumb = service.ensure("cache/task/large.png", size=480)

            self.assertTrue(thumb.exists())
            self.assertIn(root / "thumbnails", thumb.parents)
            with Image.open(thumb) as generated:
                self.assertLessEqual(max(generated.size), 480)


if __name__ == "__main__":
    unittest.main()
