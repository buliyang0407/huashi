import json
import tempfile
import unittest
from pathlib import Path

from scripts.fetch_face_library import FacePhoto, library_filename, write_metadata


class FaceLibraryFetchTest(unittest.TestCase):
    def test_library_filename_keeps_chinese_name_visible(self):
        photo = FacePhoto(
            person_name="刘亦菲",
            english_name="Liu Yifei",
            wikidata_id="Q283203",
            file_title="File:Liu Yifei 2016.jpg",
            image_url="https://example.com/Liu.jpg",
            source_page="https://commons.wikimedia.org/wiki/File:Liu_Yifei_2016.jpg",
            width=1800,
            height=2400,
            author="Example",
            license_short_name="CC BY-SA 4.0",
            license_url="https://creativecommons.org/licenses/by-sa/4.0/",
        )

        self.assertEqual(library_filename(photo, 3), "刘亦菲_03_Liu_Yifei_2016.jpg")

    def test_write_metadata_records_source_license_and_people(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photo = FacePhoto(
                person_name="刘亦菲",
                english_name="Liu Yifei",
                wikidata_id="Q283203",
                file_title="File:Liu Yifei 2016.jpg",
                image_url="https://example.com/Liu.jpg",
                source_page="https://commons.wikimedia.org/wiki/File:Liu_Yifei_2016.jpg",
                width=1800,
                height=2400,
                author="Example",
                license_short_name="CC BY-SA 4.0",
                license_url="https://creativecommons.org/licenses/by-sa/4.0/",
            )

            write_metadata(root, [photo])

            data = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(data["people"][0]["person_name"], "刘亦菲")
            self.assertEqual(data["people"][0]["photos"][0]["source_page"], photo.source_page)
            self.assertEqual(data["people"][0]["photos"][0]["license_short_name"], "CC BY-SA 4.0")


if __name__ == "__main__":
    unittest.main()
