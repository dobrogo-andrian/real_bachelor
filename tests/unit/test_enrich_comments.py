import os
import sys
import unittest
from datetime import datetime
from unittest.mock import patch

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TRANSFORMERS_NO_TF"] = "1"
os.environ["USE_TF"] = "0"

from static.backend import enrich_comments as enrich_module
from tests.fixtures.comments_rows import enrich_comment_rows
from tests.support.fake_db import FakeConnection, FakeCursor


class EnrichCommentsTests(unittest.TestCase):
    def test_normalize_unicode(self):
        self.assertEqual(enrich_module.normalize_unicode("Cafe\u0301"), "Caf\u00e9")

    def test_normalize_comment_for_analysis(self):
        self.assertEqual(
            "Hello 😡 world",
            enrich_module.normalize_comment_for_analysis("Hello  😡   world"),
        )

    def test_detect_main_language(self):
        cases = [
            ("!!!", "symbols_only", "en"),
            ("\u041f\u0440\u0438\u0432\u0456\u0442, \u0434\u0440\u0443\u0437\u0456", "uk", "uk"),
            ("\u0435\u0449\u0451 \u0441\u044b\u0440\u044b\u0435", "ru", "ru"),
            ("hello", "en", "en"),
            ("bonjour", "other", "other"),
        ]

        for comment, expected, lingua_output in cases:
            with self.subTest(comment=comment):
                with patch.object(enrich_module, "_detect_with_lingua", return_value=lingua_output):
                    self.assertEqual(enrich_module.detect_main_language(comment), expected)

        with patch.object(enrich_module, "_detect_with_lingua", side_effect=RuntimeError("fail")):
            self.assertEqual(enrich_module.detect_main_language("boom"), "other")

    def test_load_models(self):
        enrich_module.load_models.cache_clear()
        created_calls = []

        def fake_pipeline(*args, **kwargs):
            created_calls.append(kwargs)
            return "classifier"

        with patch.object(enrich_module, "pipeline", side_effect=fake_pipeline):
            first = enrich_module.load_models()
            second = enrich_module.load_models()

        self.assertIs(first, second)
        self.assertEqual(len(created_calls), 1)
        self.assertEqual(first, "classifier")
        self.assertEqual(created_calls[0]["model"], "cardiffnlp/twitter-xlm-roberta-base-sentiment")
        self.assertEqual(created_calls[0]["tokenizer"], "cardiffnlp/twitter-xlm-roberta-base-sentiment")
        self.assertTrue(created_calls[0]["truncation"])
        self.assertEqual(created_calls[0]["max_length"], 512)

    def test_analyze_sentiment(self):
        positive_classifier = lambda text: [{"label": "LABEL_2"}]
        neutral_classifier = lambda text: [{"label": "neutral"}]

        self.assertEqual(enrich_module.analyze_sentiment("good", positive_classifier), "positive")
        self.assertEqual(enrich_module.analyze_sentiment("ok", neutral_classifier), "neutral")
        self.assertEqual(enrich_module.analyze_sentiment("bad", lambda text: (_ for _ in ()).throw(RuntimeError("fail"))), "neutral")

    def test_build_comment_query(self):
        query, params = enrich_module.build_comment_query("delta")
        self.assertIn("LEFT JOIN [dbo].[EnrichedComments]", query)
        self.assertEqual(params, [])

        query, params = enrich_module.build_comment_query("page_name", page_name="Artha")
        self.assertIn("c.[PageName] = ?", query)
        self.assertEqual(params, ["Artha"])

        query, params = enrich_module.build_comment_query("page_id", page_id="artha")
        self.assertIn("c.[PageID] = ?", query)
        self.assertEqual(params, ["artha"])

        with self.assertRaisesRegex(ValueError, "page_name"):
            enrich_module.build_comment_query("page_name")

    def test_normalize_comment_payload(self):
        self.assertEqual(enrich_module.normalize_comment_payload(None), "")
        self.assertEqual(enrich_module.normalize_comment_payload("Cafe\u0301"), "Caf\u00e9")

    def test_normalize_datetime_value(self):
        value = datetime(2024, 1, 2, 3, 4, 5, 987654)
        self.assertEqual(enrich_module.normalize_datetime_value(value), datetime(2024, 1, 2, 3, 4, 5))
        self.assertIsNone(enrich_module.normalize_datetime_value(None))

    def test_build_post_group_key(self):
        row = {
            "PageID": " artha ",
            "PostHref": " href ",
            "PostTime": datetime(2024, 1, 2, 3, 4, 5, 999),
        }
        self.assertEqual(
            enrich_module.build_post_group_key(row),
            ("artha", "href", "2024-01-02 03:04:05"),
        )

    def test_assign_comment_order(self):
        rows = [
            {
                "CommentHash": "b",
                "PageID": "page",
                "PostHref": "href",
                "PostTime": datetime(2024, 1, 1, 10, 0, 0),
                "CommentTime": None,
            },
            {
                "CommentHash": "a",
                "PageID": "page",
                "PostHref": "href",
                "PostTime": datetime(2024, 1, 1, 10, 0, 0),
                "CommentTime": datetime(2024, 1, 1, 10, 1, 0),
            },
        ]

        self.assertEqual(enrich_module.assign_comment_order(rows), {"a": 1, "b": 2})

    def test_enrich_comment(self):
        with patch.object(enrich_module, "detect_main_language", return_value="en"), patch.object(
            enrich_module, "normalize_comment_for_analysis", return_value="Hello 🔥"
        ), patch.object(enrich_module, "analyze_sentiment", return_value="positive"):
            enriched = enrich_module.enrich_comment("Hello world", {"en": object()})

        with patch.object(enrich_module, "detect_main_language", return_value="fr"), patch.object(
            enrich_module, "normalize_comment_for_analysis", return_value="Bonjour"
        ), patch.object(enrich_module, "analyze_sentiment", return_value="weird"):
            fallback = enrich_module.enrich_comment("Bonjour", {})

        self.assertEqual(
            enriched,
            {"MainLanguage": "en", "NormalizedComment": "Hello 🔥", "Sentiment": "positive"},
        )
        self.assertEqual(
            fallback,
            {"MainLanguage": "other", "NormalizedComment": "Bonjour", "Sentiment": "neutral"},
        )

    def test_fetch_comment_rows(self):
        cursor = FakeCursor(
            fetchall_values=[("hash-1", "Page", "page-id")],
            description=[("CommentHash",), ("PageName",), ("PageID",)],
        )
        conn = FakeConnection(cursor)

        rows = enrich_module.fetch_comment_rows(conn, "page_id", page_id="page-id")

        self.assertEqual(rows, [{"CommentHash": "hash-1", "PageName": "Page", "PageID": "page-id"}])
        self.assertTrue(cursor.closed)

    def test_clear_enriched_scope(self):
        cursor = FakeCursor(rowcount=3)
        conn = FakeConnection(cursor)

        deleted = enrich_module.clear_enriched_scope(conn, "page_name", page_name="Artha")
        skipped = enrich_module.clear_enriched_scope(conn, "unsupported")

        self.assertEqual(deleted, 3)
        self.assertEqual(skipped, 0)
        self.assertTrue(conn.commit_called)
        self.assertTrue(cursor.closed)

    def test_prepare_enriched_rows(self):
        comment_rows = enrich_comment_rows()

        with patch.object(
            enrich_module,
            "assign_comment_order",
            return_value={"hash-1": 1, "hash-2": 2},
        ), patch.object(
            enrich_module,
            "enrich_comment",
            side_effect=[
                {"MainLanguage": "en", "NormalizedComment": "Hello", "Sentiment": "positive"},
                {"MainLanguage": "en", "NormalizedComment": "World", "Sentiment": "neutral"},
            ],
        ):
            rows = enrich_module.prepare_enriched_rows(comment_rows, {"en": object()}, source="whole_db")

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["CommentOrder"], 1)
        self.assertEqual(rows[0]["CommentLikes"], 0)
        self.assertEqual(rows[1]["CommentOrder"], 2)
        self.assertEqual(rows[1]["CommentLikes"], 3)
        self.assertEqual(rows[0]["ProcessedTime"].microsecond, 0)

    def test_upsert_enriched_rows(self):
        row = {
            "CommentHash": "hash-1",
            "PageName": "Page",
            "PageID": "page-id",
            "PostHref": "href",
            "PostTime": datetime(2024, 1, 1, 10, 0, 0),
            "Comment": "Hello",
            "CommentTime": datetime(2024, 1, 1, 10, 1, 0),
            "CommentOrder": 1,
            "CommentLikes": 0,
            "MainLanguage": "en",
            "NormalizedComment": "Hello",
            "Sentiment": "positive",
            "ProcessedTime": datetime(2024, 1, 1, 11, 0, 0),
            "Source": "delta",
        }

        cursor = FakeCursor(fetchone_values=[(0,), (1,)], rowcount=1)
        conn = FakeConnection(cursor)

        stats = enrich_module.upsert_enriched_rows(conn, [row, row], allow_updates=True)
        empty_stats = enrich_module.upsert_enriched_rows(conn, [], allow_updates=False)

        self.assertEqual(stats, {"processed": 2, "added_count": 1, "updated_count": 1})
        self.assertEqual(empty_stats, {"processed": 0, "added_count": 0, "updated_count": 0})
        self.assertTrue(cursor.fast_executemany)
        self.assertTrue(conn.commit_called)
        self.assertTrue(cursor.closed)

    def test_enrich_comments(self):
        connection = FakeConnection(FakeCursor())

        with patch.object(enrich_module.db_connection, "get_db_connection", return_value=connection), patch.object(
            enrich_module, "clear_enriched_scope", return_value=2
        ), patch.object(
            enrich_module,
            "fetch_comment_rows",
            side_effect=[
                [],
                [{"CommentHash": "hash-1", "Comment": "Hello"}],
            ],
        ), patch.object(
            enrich_module, "load_models", return_value=object()
        ), patch.object(
            enrich_module, "prepare_enriched_rows", return_value=[{"CommentHash": "hash-1"}]
        ), patch.object(
            enrich_module, "upsert_enriched_rows", return_value={"processed": 1, "added_count": 1, "updated_count": 0}
        ):
            empty_result = enrich_module.enrich_comments(mode="whole_db")
            filled_result = enrich_module.enrich_comments(mode="delta", page_id="page-id")

        with self.assertRaisesRegex(ValueError, "Unsupported mode"):
            enrich_module.enrich_comments(mode="bad")

        self.assertEqual(empty_result, {"selected": 0, "processed": 0, "deleted": 2, "mode": "whole_db"})
        self.assertEqual(filled_result["selected"], 1)
        self.assertEqual(filled_result["processed"], 1)
        self.assertEqual(filled_result["mode"], "delta")
        self.assertTrue(connection.close_called)

    def test_parse_args(self):
        with patch.object(sys, "argv", ["prog", "--mode", "page_id", "--page-id", "artha"]):
            args = enrich_module.parse_args()

        self.assertEqual(args.mode, "page_id")
        self.assertEqual(args.page_id, "artha")
        self.assertIsNone(args.page_name)


if __name__ == "__main__":
    unittest.main()
