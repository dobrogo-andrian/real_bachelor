import hashlib
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from unittest.mock import patch

import pandas as pd

from static.backend import load_to_db as load_module
from tests.fixtures.comments_rows import load_to_db_input_rows
from tests.fixtures.csv_samples import load_to_db_csv_rows
from tests.support.fake_db import FakeConnection


class LoadToDbTests(unittest.TestCase):
    def test_validate_columns(self):
        valid_df = pd.DataFrame({"Comment": ["hi"], "Time": ["2024-01-01"], "Likes": [1]})
        invalid_df = pd.DataFrame({"Comment": ["hi"], "Likes": [1]})

        load_module.validate_columns(valid_df)

        with self.assertRaisesRegex(ValueError, "Missing required columns"):
            load_module.validate_columns(invalid_df)

    def test_derive_page_id(self):
        scenarios = {
            "arthaslav_10.csv": "arthaslav",
            "ArthaSlav_1.CSV": "ArthaSlav",
            "page-export.csv": "page-export",
        }

        for filename, expected in scenarios.items():
            with self.subTest(filename=filename):
                self.assertEqual(load_module.derive_page_id(filename), expected)

    def test_normalize_hash_value(self):
        timestamp = pd.Timestamp("2024-01-02 03:04:05")
        scenarios = [
            (None, ""),
            (float("nan"), ""),
            (timestamp, "2024-01-02T03:04:05"),
            ("  text  ", "text"),
        ]

        for value, expected in scenarios:
            with self.subTest(value=repr(value)):
                self.assertEqual(load_module.normalize_hash_value(value), expected)

    def test_compute_comment_hash(self):
        expected = hashlib.sha256(
            "arthaslav|https://instagram.com/p/1|2024-01-02T03:04:05|Great post".encode("utf-8")
        ).hexdigest()

        result = load_module.compute_comment_hash(
            "arthaslav",
            "https://instagram.com/p/1",
            datetime(2024, 1, 2, 3, 4, 5),
            "Great post",
        )

        result_with_whitespace = load_module.compute_comment_hash(
            " arthaslav ",
            "https://instagram.com/p/1",
            pd.Timestamp("2024-01-02 03:04:05"),
            "Great post",
        )

        self.assertEqual(result, expected)
        self.assertEqual(result_with_whitespace, expected)

    def test_prepare_rows(self):
        dataframe = pd.DataFrame(load_to_db_input_rows())
        post_time = datetime(2024, 1, 1, 8, 0, 0)
        load_time = datetime(2024, 1, 1, 12, 0, 0)

        rows = load_module.prepare_rows(
            dataframe,
            page_id="arthaslav",
            post_href="https://instagram.com/p/1",
            post_time=post_time,
            load_time=load_time,
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["PageName"], "unknown")
        self.assertEqual(rows[0]["PageID"], "arthaslav")
        self.assertEqual(rows[0]["CommentLikes"], 5)
        self.assertEqual(rows[0]["CommentTime"], datetime(2024, 1, 1, 9, 10, 11))
        self.assertEqual(rows[1]["PageName"], "Custom Page")
        self.assertEqual(rows[1]["PageID"], "custom-page-id")
        self.assertEqual(rows[1]["CommentLikes"], 0)
        self.assertIsNone(rows[1]["CommentTime"])
        self.assertEqual(rows[0]["PostTime"], post_time)
        self.assertEqual(rows[0]["LoadTime"], load_time)

    def test_insert_rows(self):
        fake_connection = FakeConnection()
        rows = [
            {
                "CommentHash": "hash-1",
                "PageName": "Page",
                "PageID": "page-id",
                "PostHref": "href",
                "PostTime": datetime(2024, 1, 1, 10, 0, 0),
                "Comment": "Hello",
                "CommentTime": datetime(2024, 1, 1, 10, 5, 0),
                "CommentLikes": 4,
                "LoadTime": datetime(2024, 1, 1, 11, 0, 0),
            }
        ]

        inserted_count = load_module.insert_rows(fake_connection, rows)
        empty_inserted_count = load_module.insert_rows(fake_connection, [])

        self.assertEqual(inserted_count, 1)
        self.assertEqual(empty_inserted_count, 0)
        self.assertTrue(fake_connection.cursor_instance.fast_executemany)
        self.assertIn("MERGE [dbo].[Comments]", fake_connection.cursor_instance.executemany_sql)
        self.assertEqual(fake_connection.cursor_instance.executemany_params[0][0], "hash-1")
        self.assertTrue(fake_connection.commit_called)

    def test_iter_csv_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            os.makedirs(os.path.join(temp_dir, "nested"), exist_ok=True)
            for relative_path in ["a.csv", "nested\\b.CSV", "nested\\ignore.txt"]:
                with open(os.path.join(temp_dir, relative_path), "w", encoding="utf-8") as handle:
                    handle.write("data")

            found_files = sorted(
                os.path.relpath(path, temp_dir).replace("\\", "/")
                for path in load_module.iter_csv_files(temp_dir)
            )

        self.assertEqual(found_files, ["a.csv", "nested/b.CSV"])

    def test_load_to_db(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_one = os.path.join(temp_dir, "arthaslav_2.csv")
            file_two = os.path.join(temp_dir, "arthaslav_10.csv")
            csv_rows = load_to_db_csv_rows()
            pd.DataFrame([csv_rows[0]]).to_csv(file_one, index=False)
            pd.DataFrame([csv_rows[1]]).to_csv(file_two, index=False)

            fake_connection = FakeConnection()
            inserted_batches = []

            def fake_insert_rows(conn, rows):
                inserted_batches.append((conn, rows))
                return len(rows)

            with self.subTest("dry_run_counts_rows_without_db_connection"):
                with redirect_stdout(io.StringIO()):
                    dry_run_result = load_module.load_to_db(input_folder=temp_dir, dry_run=True)
                self.assertEqual(
                    dry_run_result,
                    {
                        "files_processed": 2,
                        "rows_loaded": 2,
                        "input_files_found": 2,
                        "dry_run": True,
                    },
                )

            with self.subTest("non_dry_run_uses_db_connection_and_closes_it"), patch.object(
                load_module.db_connection, "get_db_connection", return_value=fake_connection
            ), patch.object(load_module, "insert_rows", side_effect=fake_insert_rows):
                with redirect_stdout(io.StringIO()):
                    load_result = load_module.load_to_db(input_folder=temp_dir, dry_run=False)

                self.assertEqual(
                    load_result,
                    {
                        "files_processed": 2,
                        "rows_loaded": 2,
                        "input_files_found": 2,
                        "dry_run": False,
                    },
                )
                self.assertEqual(len(inserted_batches), 2)
                self.assertIs(inserted_batches[0][0], fake_connection)
                self.assertEqual(inserted_batches[0][1][0]["Comment"], "First")
                self.assertEqual(inserted_batches[1][1][0]["Comment"], "Second")
                self.assertTrue(fake_connection.close_called)

            with self.subTest("missing_or_empty_input_folder_raises"):
                with self.assertRaisesRegex(FileNotFoundError, "Input folder not found"):
                    load_module.load_to_db(input_folder=os.path.join(temp_dir, "missing"), dry_run=True)

                empty_dir = os.path.join(temp_dir, "empty")
                os.makedirs(empty_dir, exist_ok=True)
                with self.assertRaisesRegex(FileNotFoundError, "No CSV files found under"):
                    with redirect_stdout(io.StringIO()):
                        load_module.load_to_db(input_folder=empty_dir, dry_run=True)


if __name__ == "__main__":
    unittest.main()
