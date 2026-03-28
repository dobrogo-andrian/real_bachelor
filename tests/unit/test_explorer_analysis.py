import unittest
from collections import Counter
from datetime import datetime
from unittest.mock import patch

from static.backend import explorer_analysis as analysis_module
from tests.fixtures.enriched_rows import analysis_rows
from tests.support.fake_db import FakeConnection, FakeCursor


class ExplorerAnalysisTests(unittest.TestCase):
    def test_normalize_datetime(self):
        value = datetime(2024, 1, 1, 10, 0, 0)
        self.assertEqual(analysis_module._normalize_datetime(value), value)
        self.assertEqual(
            analysis_module._normalize_datetime("2024-01-01 10:00:00"),
            value,
        )
        self.assertIsNone(analysis_module._normalize_datetime("invalid"))

    def test_normalize_text(self):
        self.assertEqual(analysis_module._normalize_text(None), "")
        self.assertEqual(analysis_module._normalize_text("  hello  "), "hello")

    def test_build_post_key(self):
        self.assertEqual(
            analysis_module._build_post_key(" page ", " Name ", datetime(2024, 1, 1, 10, 0, 0)),
            "page|Name|2024-01-01 10:00:00",
        )
        self.assertEqual(
            analysis_module._build_post_key("page", "Name", "raw"),
            "page|Name|raw",
        )

    def test_pick_post_href(self):
        rows = [{"PostHref": "   "}, {"PostHref": "https://instagram.com/p/1"}]
        self.assertEqual(analysis_module._pick_post_href(rows), "https://instagram.com/p/1")
        self.assertEqual(analysis_module._pick_post_href([]), "")

    def test_safe_percentage(self):
        self.assertEqual(analysis_module._safe_percentage(1, 3), 33.33)
        self.assertEqual(analysis_module._safe_percentage(1, 0), 0.0)

    def test_safe_average(self):
        self.assertEqual(analysis_module._safe_average([1, 2, 2]), 1.67)
        self.assertEqual(analysis_module._safe_average([]), 0.0)

    def test_compute_percentile(self):
        self.assertEqual(analysis_module._compute_percentile([], 0.9), 0)
        self.assertEqual(analysis_module._compute_percentile([5], 0.9), 5)
        self.assertEqual(analysis_module._compute_percentile([1, 3, 5], 0.5), 3.0)

    def test_build_adaptive_histogram_bins(self):
        bins = analysis_module._build_adaptive_histogram_bins([1, 1, 2, 5, 8, 13])

        self.assertTrue(any(bucket["label"] == "1-1" and bucket["value"] == 2 for bucket in bins))
        self.assertTrue(any(bucket["label"].endswith("+") and bucket["value"] == 1 for bucket in bins))
        self.assertEqual(analysis_module._build_adaptive_histogram_bins([]), [])

    def test_fetch_enriched_comments_for_page(self):
        cursor = FakeCursor(
            fetchall_values=[("hash-1", "Page", "page-id")],
            description=[("CommentHash",), ("PageName",), ("PageID",)],
        )
        conn = FakeConnection(cursor)

        with patch.object(analysis_module.db_connection, "get_db_connection", return_value=conn):
            rows = analysis_module.fetch_enriched_comments_for_page("page_id", "page-id")

        with self.assertRaisesRegex(ValueError, "selection_type"):
            analysis_module.fetch_enriched_comments_for_page("bad", "value")

        self.assertEqual(rows, [{"CommentHash": "hash-1", "PageName": "Page", "PageID": "page-id"}])
        self.assertTrue(cursor.closed)
        self.assertTrue(conn.close_called)

    def test_build_chart_visibility(self):
        rows = [
            {"PageID": "page-a", "PageName": "A"},
            {"PageID": "page-a", "PageName": "A"},
        ]
        language_counts = Counter({"en": 2})
        sentiment_counts = Counter({"positive": 2})
        ordered_posts = [("p1", [{}])]

        visibility = analysis_module._build_chart_visibility({}, rows, language_counts, sentiment_counts, ordered_posts)

        self.assertFalse(visibility["visible"]["comments_by_post"])
        self.assertFalse(visibility["visible"]["comments_by_language"])
        self.assertIn("single_language_scope", visibility["reasons"])
        self.assertEqual(visibility["meta"]["distinct_pages"], 1)

    def test_build_analysis_from_rows(self):
        rows = analysis_rows()

        anchor_map = {
            "page-id|Page|2024-01-01 10:00:00": "positive",
            "page-id|Page|2024-01-02 10:00:00": "negative",
        }

        with patch.object(analysis_module.db_connection, "fetch_post_anchor_sentiments", return_value=anchor_map):
            result = analysis_module.build_analysis_from_rows(
                rows,
                selection_type="page_id",
                selection_value="page-id",
                filters={"page_id": "page-id"},
            )

        empty = analysis_module.build_analysis_from_rows([], selection_type="page_id", selection_value="page-id")

        self.assertEqual(result["summary"]["total_comments"], 4)
        self.assertEqual(result["summary"]["distinct_posts"], 2)
        self.assertEqual(result["summary"]["positive_share"], 50.0)
        self.assertEqual(len(result["language_breakdown"]), 2)
        self.assertEqual(len(result["post_breakdown"]), 2)
        self.assertEqual(result["sample_comments"][0]["comment"], "Great job team")
        self.assertTrue(result["chart_visibility"]["visible"]["comments_by_post"])
        self.assertTrue(any(item["label"] == "en" for item in result["charts"]["comments_by_language"]))
        self.assertEqual(empty["summary"], None)
        self.assertEqual(empty["charts"], {})

    def test_build_page_analysis(self):
        rows = [{"CommentHash": "c1"}]
        analysis = {"summary": {"total_comments": 1}}

        with patch.object(analysis_module, "fetch_enriched_comments_for_page", return_value=rows) as mocked_fetch, patch.object(
            analysis_module, "build_analysis_from_rows", return_value=analysis
        ) as mocked_build:
            result = analysis_module.build_page_analysis("page_id", "page-id")

        self.assertEqual(result, analysis)
        mocked_fetch.assert_called_once_with("page_id", "page-id")
        mocked_build.assert_called_once_with(
            rows,
            selection_type="page_id",
            selection_value="page-id",
            filters={"page_id": "page-id"},
        )


if __name__ == "__main__":
    unittest.main()
