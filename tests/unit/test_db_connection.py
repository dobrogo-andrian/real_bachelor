import ctypes
import hashlib
import hmac
import unittest
from datetime import datetime
from unittest.mock import patch

from flask import Flask

from static.backend import db_connection as db_module
from tests.support.fake_db import FakeConnection, FakeCursor


class DbConnectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.flask_app = Flask(__name__)

    def test_normalize_filter_values(self):
        self.assertEqual(db_module._normalize_filter_values(None), [])
        self.assertEqual(db_module._normalize_filter_values("  one "), ["one"])
        self.assertEqual(db_module._normalize_filter_values([" one ", "", "two", None]), ["one", "two"])

    def test_add_in_filter(self):
        where_clauses = []
        params = []

        normalized = db_module._add_in_filter(where_clauses, params, "PageID", [" a ", "b"])
        empty = db_module._add_in_filter(where_clauses, params, "PageID", [])

        self.assertEqual(normalized, ["a", "b"])
        self.assertEqual(empty, [])
        self.assertEqual(where_clauses, ["[PageID] IN (?, ?)"])
        self.assertEqual(params, ["a", "b"])

    def test_qualify_column(self):
        self.assertEqual(db_module._qualify_column("PageID"), "[PageID]")
        self.assertEqual(db_module._qualify_column("PageID", "EC"), "EC.[PageID]")

    def test_add_in_filter_for_alias(self):
        where_clauses = []
        params = []

        normalized = db_module._add_in_filter_for_alias(where_clauses, params, "Sentiment", [" positive "], "EC")
        empty = db_module._add_in_filter_for_alias(where_clauses, params, "Sentiment", None, "EC")

        self.assertEqual(normalized, ["positive"])
        self.assertEqual(empty, [])
        self.assertEqual(where_clauses, ["EC.[Sentiment] IN (?)"])
        self.assertEqual(params, ["positive"])

    def test_add_first_comment_sentiment_filter(self):
        where_clauses = []
        params = []

        normalized = db_module._add_first_comment_sentiment_filter(
            where_clauses,
            params,
            [" positive ", "negative"],
            table_alias="EC",
        )
        empty = db_module._add_first_comment_sentiment_filter(where_clauses, params, [], table_alias="EC")

        self.assertEqual(normalized, ["positive", "negative"])
        self.assertEqual(empty, [])
        self.assertIn("EXISTS", where_clauses[0])
        self.assertIn("Anchor.[Sentiment] IN (?, ?)", where_clauses[0])
        self.assertEqual(params, ["positive", "negative"])

    def test_get_db_connection(self):
        with patch.dict(
            "os.environ",
            {
                "DB_DRIVER": "ODBC Driver 17 for SQL Server",
                "DB_SERVER": "localhost",
                "DB_NAME": "social-media-optimizer",
                "DB_USER": "social-media-optimizer",
                "DB_PASSWORD": "social-media-optimizer",
            },
            clear=False,
        ), patch.object(db_module.pyodbc, "connect", return_value="conn") as mocked_connect:
            conn = db_module.get_db_connection()

        self.assertEqual(conn, "conn")
        self.assertIn("SERVER=localhost", mocked_connect.call_args.args[0])
        self.assertIn("PWD=social-media-optimizer", mocked_connect.call_args.args[0])

    def test_bytes_to_blob(self):
        blob, buffer = db_module._bytes_to_blob(b"abc")
        empty_blob, empty_buffer = db_module._bytes_to_blob(b"")

        self.assertEqual(blob.cbData, 3)
        self.assertIsNotNone(buffer)
        self.assertEqual(empty_blob.cbData, 0)
        self.assertIsNone(empty_buffer)

    def test_protect_secret(self):
        allocated = []

        def fake_crypt_protect_data(*args):
            output_blob = args[6]._obj
            payload = (ctypes.c_byte * 3)(1, 2, 3)
            allocated.append(payload)
            output_blob.cbData = 3
            output_blob.pbData = ctypes.cast(payload, ctypes.POINTER(ctypes.c_byte))
            return True

        with patch.object(db_module, "_crypt_protect_data", side_effect=fake_crypt_protect_data), patch.object(
            db_module.ctypes, "string_at", return_value=b"\x01\x02\x03"
        ), patch.object(db_module, "_local_free") as mocked_free:
            encrypted = db_module.protect_secret("secret")
            none_value = db_module.protect_secret(None)

        self.assertEqual(encrypted, b"\x01\x02\x03")
        self.assertIsNone(none_value)
        mocked_free.assert_called_once()

    def test_unprotect_secret(self):
        allocated = []

        def fake_crypt_unprotect_data(*args):
            output_blob = args[6]._obj
            payload = "secret".encode("utf-16-le")
            buffer = (ctypes.c_byte * len(payload))(*payload)
            allocated.append(buffer)
            output_blob.cbData = len(payload)
            output_blob.pbData = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))
            return True

        with patch.object(db_module, "_crypt_unprotect_data", side_effect=fake_crypt_unprotect_data), patch.object(
            db_module, "_local_free"
        ) as mocked_free:
            plaintext = db_module.unprotect_secret(b"\x01\x02")
            none_value = db_module.unprotect_secret(None)

        self.assertEqual(plaintext, "secret")
        self.assertIsNone(none_value)
        self.assertTrue(mocked_free.called)

    def test_insert_new_user(self):
        success_cursor = FakeCursor(fetchone_values=[None])
        success_conn = FakeConnection(success_cursor)
        duplicate_cursor = FakeCursor(fetchone_values=[("exists",)])
        duplicate_conn = FakeConnection(duplicate_cursor)

        with self.flask_app.app_context():
            with patch.object(db_module, "get_db_connection", return_value=success_conn), patch.object(
                db_module, "protect_secret", side_effect=[b"login", b"password"]
            ), patch.object(db_module.pyodbc, "Binary", side_effect=lambda value: value):
                response, status = db_module.insert_new_user("alice", "a@example.com", "hash", "insta", "secret")

            with patch.object(db_module, "get_db_connection", return_value=duplicate_conn):
                duplicate_response, duplicate_status = db_module.insert_new_user(
                    "alice",
                    "a@example.com",
                    "hash",
                    "insta",
                    "secret",
                )

        self.assertEqual(status, 201)
        self.assertEqual(response.get_json()["redirect"], "/login")
        self.assertTrue(success_conn.commit_called)
        self.assertTrue(success_cursor.closed)
        self.assertTrue(success_conn.close_called)
        self.assertEqual(duplicate_status, 409)
        self.assertEqual(duplicate_response.get_json()["error"], "Username or email already exists")

    def test_insert_new_user_hides_internal_errors(self):
        failing_cursor = FakeCursor(fetchone_values=[None])
        failing_conn = FakeConnection(failing_cursor)

        with self.flask_app.app_context():
            with patch.object(db_module, "get_db_connection", return_value=failing_conn), patch.object(
                db_module, "protect_secret", side_effect=RuntimeError("dpapi failure")
            ), patch.object(db_module.logger, "exception") as mocked_exception:
                response, status = db_module.insert_new_user("alice", "a@example.com", "hash", "insta", "secret")

        self.assertEqual(status, 500)
        self.assertEqual(response.get_json()["error"], "Sign up failed. Please try again later.")
        self.assertTrue(failing_conn.rollback_called)
        self.assertTrue(failing_cursor.closed)
        self.assertTrue(failing_conn.close_called)
        mocked_exception.assert_called_once()

    def test_sign_instagram_cookie_payload(self):
        with patch.dict("os.environ", {"COOKIE_SIGNING_SECRET": "cookie-secret"}, clear=False):
            signature = db_module.sign_instagram_cookie_payload("payload")

        expected = hmac.new(b"cookie-secret", b"payload", hashlib.sha256).digest()
        self.assertEqual(signature, expected)

    def test_fetch_user(self):
        cursor = FakeCursor(fetchone_values=[("hash",)])
        conn = FakeConnection(cursor)

        with patch.object(db_module, "get_db_connection", return_value=conn):
            user = db_module.fetch_user("alice")

        self.assertEqual(user, ("hash",))
        self.assertIn("SELECT PasswordHash FROM Users", cursor.executed[0][0])
        self.assertTrue(cursor.closed)
        self.assertTrue(conn.close_called)

    def test_update_user_password_hash(self):
        cursor = FakeCursor()
        conn = FakeConnection(cursor)

        with patch.object(db_module, "get_db_connection", return_value=conn):
            db_module.update_user_password_hash("alice", "scrypt:hash")

        self.assertIn("UPDATE Users", cursor.executed[0][0])
        self.assertEqual(cursor.executed[0][1], ("scrypt:hash", "alice"))
        self.assertTrue(conn.commit_called)
        self.assertTrue(cursor.closed)
        self.assertTrue(conn.close_called)

    def test_fetch_user_instagram_credentials(self):
        cursor = FakeCursor(fetchone_values=[(b"login", b"password"), None])
        conn = FakeConnection(cursor)

        with patch.object(db_module, "get_db_connection", return_value=conn), patch.object(
            db_module, "unprotect_secret", side_effect=["insta-login", "insta-password"]
        ):
            creds = db_module.fetch_user_instagram_credentials("alice")
            missing = db_module.fetch_user_instagram_credentials("bob")

        self.assertEqual(
            creds,
            {"instagram_login": "insta-login", "instagram_password": "insta-password"},
        )
        self.assertIsNone(missing)
        self.assertTrue(conn.close_called)

    def test_fetch_user_profile(self):
        cursor = FakeCursor(
            fetchone_values=[
                (
                    "alice",
                    "alice@example.com",
                    1,
                    "2026-03-20T10:00:00",
                    "2026-03-01T10:00:00",
                    "2026-03-10T10:00:00",
                    b"login",
                    b"password",
                    "2026-03-21T10:00:00",
                )
            ]
        )
        conn = FakeConnection(cursor)

        with patch.object(db_module, "get_db_connection", return_value=conn), patch.object(
            db_module, "unprotect_secret", return_value="insta-login"
        ):
            profile = db_module.fetch_user_profile("alice")

        self.assertEqual(profile["email"], "alice@example.com")
        self.assertTrue(profile["email_verified"])
        self.assertEqual(profile["instagram_login"], "insta-login")
        self.assertTrue(profile["has_instagram_password"])
        self.assertTrue(profile["has_instagram_cookies"])

    def test_fetch_account_statistics(self):
        cursor = FakeCursor(fetchone_values=[(10,), (3,), (7,)])
        conn = FakeConnection(cursor)

        with patch.object(db_module, "get_db_connection", return_value=conn):
            stats = db_module.fetch_account_statistics()

        self.assertEqual(
            stats,
            {"total_comments": 10, "distinct_pages": 3, "enriched_comments": 7},
        )

    def test_set_user_email_verified(self):
        cursor = FakeCursor()
        conn = FakeConnection(cursor)

        with patch.object(db_module, "get_db_connection", return_value=conn):
            db_module.set_user_email_verified("alice", True)

        self.assertIn("UPDATE Users", cursor.executed[0][0])
        self.assertEqual(cursor.executed[0][1], (1, 1, "alice"))
        self.assertTrue(conn.commit_called)

    def test_update_user_instagram_credentials(self):
        cursor = FakeCursor()
        conn = FakeConnection(cursor)

        with patch.object(db_module, "get_db_connection", return_value=conn), patch.object(
            db_module, "protect_secret", side_effect=[b"login", b"password"]
        ), patch.object(db_module.pyodbc, "Binary", side_effect=lambda value: value):
            db_module.update_user_instagram_credentials("alice", "insta", "secret")

        self.assertIn("UPDATE Users", cursor.executed[0][0])
        self.assertEqual(cursor.executed[0][1], (b"login", b"password", "alice"))
        self.assertTrue(conn.commit_called)

    def test_store_user_instagram_cookies(self):
        cursor = FakeCursor()
        conn = FakeConnection(cursor)

        with patch.object(db_module, "get_db_connection", return_value=conn), patch.object(
            db_module, "protect_secret", return_value=b"encrypted"
        ), patch.object(db_module, "sign_instagram_cookie_payload", return_value=b"signed"), patch.object(
            db_module.pyodbc, "Binary", side_effect=lambda value: value
        ):
            db_module.store_user_instagram_cookies("alice", "payload")

        self.assertIn("UPDATE Users", cursor.executed[0][0])
        self.assertEqual(cursor.executed[0][1], (b"encrypted", b"signed", "alice"))
        self.assertTrue(conn.commit_called)
        self.assertTrue(cursor.closed)
        self.assertTrue(conn.close_called)

    def test_fetch_user_instagram_cookies(self):
        cursor = FakeCursor(fetchone_values=[(b"encrypted", b"signed"), None])
        conn = FakeConnection(cursor)

        with patch.object(db_module, "get_db_connection", return_value=conn), patch.object(
            db_module, "unprotect_secret", return_value="payload"
        ), patch.object(db_module, "sign_instagram_cookie_payload", return_value=b"signed"):
            payload = db_module.fetch_user_instagram_cookies("alice")
            missing = db_module.fetch_user_instagram_cookies("bob")

        self.assertEqual(payload, "payload")
        self.assertIsNone(missing)
        self.assertTrue(cursor.closed)
        self.assertTrue(conn.close_called)

    def test_fetch_user_instagram_cookies_rejects_signature_mismatch(self):
        cursor = FakeCursor(fetchone_values=[(b"encrypted", b"signed")])
        conn = FakeConnection(cursor)

        with patch.object(db_module, "get_db_connection", return_value=conn), patch.object(
            db_module, "unprotect_secret", return_value="payload"
        ), patch.object(db_module, "sign_instagram_cookie_payload", return_value=b"other-signed"):
            with self.assertRaises(ValueError):
                db_module.fetch_user_instagram_cookies("alice")

        self.assertTrue(cursor.closed)
        self.assertTrue(conn.close_called)

    def test_fetch_distinct_comment_dimensions(self):
        cursor = FakeCursor(fetchall_values=[[("Page A",), ("Page B",)], [("id-a",), ("id-b",)]])
        conn = FakeConnection(cursor)

        with patch.object(db_module, "get_db_connection", return_value=conn):
            dimensions = db_module.fetch_distinct_comment_dimensions()

        self.assertEqual(dimensions, {"page_names": ["Page A", "Page B"], "page_ids": ["id-a", "id-b"]})
        self.assertTrue(cursor.closed)

    def test_fetch_existing_post_hrefs(self):
        cursor = FakeCursor(fetchall_values=[[(" https://a ",), ("",), (None,), ("https://b",)]])
        conn = FakeConnection(cursor)

        with patch.object(db_module, "get_db_connection", return_value=conn):
            hrefs = db_module.fetch_existing_post_hrefs(" page-id ")
            empty = db_module.fetch_existing_post_hrefs(" ")

        self.assertEqual(hrefs, {"https://a", "https://b"})
        self.assertEqual(empty, set())

    def test_fetch_advanced_comment_dimensions(self):
        range_row = (
            datetime(2024, 1, 1, 10, 0, 0),
            datetime(2024, 1, 2, 10, 0, 0),
            datetime(2024, 1, 1, 11, 0, 0),
            datetime(2024, 1, 2, 11, 0, 0),
            1,
            9,
        )
        cursor = FakeCursor(
            fetchall_values=[
                [("Page",)],
                [("page-id",)],
                [("instagram",)],
                [("en",)],
                [("positive",), ("neutral",)],
            ],
            fetchone_values=[range_row],
        )
        conn = FakeConnection(cursor)

        with patch.object(db_module, "get_db_connection", return_value=conn):
            dimensions = db_module.fetch_advanced_comment_dimensions()

        self.assertEqual(dimensions["page_names"], ["Page"])
        self.assertEqual(dimensions["first_comment_sentiments"], ["positive", "neutral"])
        self.assertEqual(dimensions["ranges"]["max_comment_likes"], 9)

    def test_fetch_enriched_comment_preview(self):
        summary_row = (5, 4, 3, 2, 1.25, datetime(2024, 1, 3, 12, 0, 0))
        preview_row = (
            "hash-1",
            "Page",
            "page-id",
            "href",
            datetime(2024, 1, 1, 10, 0, 0),
            datetime(2024, 1, 1, 10, 1, 0),
            7,
            "en",
            "Hello",
            "positive",
            datetime(2024, 1, 2, 10, 0, 0),
            "delta",
        )
        cursor = FakeCursor(
            fetchone_values=[summary_row],
            fetchall_values=[[preview_row]],
            description_values=[[], [
                ("CommentHash",), ("PageName",), ("PageID",), ("PostHref",), ("PostTime",),
                ("CommentTime",), ("CommentLikes",), ("MainLanguage",),
                ("NormalizedComment",), ("Sentiment",), ("ProcessedTime",), ("Source",),
            ]],
        )
        conn = FakeConnection(cursor)
        filters = {
            "page_name": ["Page"],
            "language": ["en"],
            "first_comment_sentiment": ["positive"],
            "post_time_from": "2024-01-01 00:00:00",
            "min_likes": 1,
            "text_search": "Hel",
        }

        with patch.object(db_module, "get_db_connection", return_value=conn):
            preview = db_module.fetch_enriched_comment_preview(filters, limit=10)

        self.assertEqual(preview["summary"]["total_comments"], 5)
        self.assertEqual(preview["rows"][0]["ProcessedTime"], "2024-01-02 10:00:00")
        self.assertEqual(preview["applied_filters"]["page_name"], ["Page"])
        self.assertIn("first_comment_sentiment", preview["applied_filters"])

    def test_fetch_enriched_comment_rows(self):
        row = (
            "hash-1",
            "Page",
            "page-id",
            "href",
            datetime(2024, 1, 1, 10, 0, 0),
            datetime(2024, 1, 1, 10, 1, 0),
            7,
            "en",
            "Hello",
            "positive",
            datetime(2024, 1, 2, 10, 0, 0),
            "delta",
        )
        cursor = FakeCursor(
            fetchall_values=[[row]],
            description_values=[[
                ("CommentHash",), ("PageName",), ("PageID",), ("PostHref",), ("PostTime",),
                ("CommentTime",), ("CommentLikes",), ("MainLanguage",),
                ("NormalizedComment",), ("Sentiment",), ("ProcessedTime",), ("Source",),
            ]],
        )
        conn = FakeConnection(cursor)

        with patch.object(db_module, "get_db_connection", return_value=conn):
            rows = db_module.fetch_enriched_comment_rows({"page_id": ["page-id"], "min_likes": 2})

        self.assertEqual(rows[0]["CommentHash"], "hash-1")
        self.assertTrue(cursor.closed)

    def test_fetch_post_anchor_sentiments(self):
        post_refs = [
            {"page_id": "page-id", "page_name": "", "post_time": datetime(2024, 1, 1, 10, 0, 0)},
            {"page_id": "page-id", "page_name": "", "post_time": datetime(2024, 1, 1, 10, 0, 0)},
            {"page_id": "", "page_name": "Page", "post_time": datetime(2024, 1, 2, 10, 0, 0)},
        ]
        cursor = FakeCursor(fetchall_values=[[
            ("", "page-id", datetime(2024, 1, 1, 10, 0, 0), "Positive"),
            ("Page", "", datetime(2024, 1, 2, 10, 0, 0), ""),
        ]])
        conn = FakeConnection(cursor)

        with patch.object(db_module, "get_db_connection", return_value=conn):
            anchors = db_module.fetch_post_anchor_sentiments(post_refs)
            empty = db_module.fetch_post_anchor_sentiments([{"page_id": "", "page_name": "", "post_time": None}])

        self.assertEqual(
            anchors,
            {
                "page-id||2024-01-01 10:00:00": "positive",
                "|Page|2024-01-02 10:00:00": "unknown",
            },
        )
        self.assertEqual(empty, {})


if __name__ == "__main__":
    unittest.main()
