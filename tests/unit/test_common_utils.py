import os
import tempfile
import unittest

from static.backend.common_utils import extract_sort_key, get_next_filename


class CommonUtilsTests(unittest.TestCase):
    def test_get_next_filename(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = os.path.join(temp_dir, "exports")
            os.makedirs(target_dir, exist_ok=True)

            for filename in [
                "comments_1.csv",
                "comments_2.csv",
                "comments_invalid.csv",
                "other_9.csv",
                "comments_7.txt",
            ]:
                open(os.path.join(target_dir, filename), "w", encoding="utf-8").close()

            next_filename = get_next_filename("comments", target_dir)
            missing_dir_filename = get_next_filename("fresh", os.path.join(temp_dir, "new_exports"))

            self.assertEqual(next_filename, os.path.join(target_dir, "comments_3.csv"))
            self.assertTrue(os.path.isdir(os.path.join(temp_dir, "new_exports")))
            self.assertEqual(
                missing_dir_filename,
                os.path.join(temp_dir, "new_exports", "fresh_1.csv"),
            )

    def test_extract_sort_key(self):
        scenarios = {
            "arthaslav_10.csv": ("arthaslav_", 10),
            "ARTHASLAV_2.csv": ("arthaslav_", 2),
            "summary.csv": ("summary", -1),
            "batch099.csv": ("batch", 99),
        }

        for filename, expected in scenarios.items():
            with self.subTest(filename=filename):
                self.assertEqual(extract_sort_key(filename), expected)


if __name__ == "__main__":
    unittest.main()
