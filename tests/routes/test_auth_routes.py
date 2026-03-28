import hashlib
from datetime import timedelta
from unittest.mock import patch

from flask import jsonify
from flask_jwt_extended import create_access_token

from tests.support.app_test_case import AppTestCase, app_module


class AuthRouteTests(AppTestCase):
    def test_login_route(self):
        password_hash = hashlib.sha256("secret".encode()).hexdigest()
        scenarios = [
            {
                "name": "get_login_page_resets_session",
                "method": "GET",
                "path": "/login?next=/login",
                "fetch_user_result": None,
                "payload": None,
                "expected_status": 200,
                "assertions": lambda response: (
                    self.assertIn(b"<h1>Login</h1>", response.data),
                    self.assertIn("access_token_cookie=;", " ".join(response.headers.getlist("Set-Cookie"))),
                    self.assertIn("refresh_token_cookie=;", " ".join(response.headers.getlist("Set-Cookie"))),
                ),
            },
            {
                "name": "post_login_success_sets_tokens",
                "method": "POST",
                "path": "/login",
                "fetch_user_result": (password_hash,),
                "payload": {"username": "alice", "password": "secret"},
                "expected_status": 200,
                "assertions": lambda response: (
                    self.assertEqual(response.get_json()["message"], "Login successful"),
                    self.assertIn("access_token_cookie=", " ".join(response.headers.getlist("Set-Cookie"))),
                    self.assertIn("refresh_token_cookie=", " ".join(response.headers.getlist("Set-Cookie"))),
                ),
            },
            {
                "name": "post_login_rejects_bad_password",
                "method": "POST",
                "path": "/login",
                "fetch_user_result": (password_hash,),
                "payload": {"username": "alice", "password": "wrong"},
                "expected_status": 401,
                "assertions": lambda response: self.assertEqual(
                    response.get_json()["error"], "Invalid username or password"
                ),
            },
            {
                "name": "post_login_handles_unknown_user",
                "method": "POST",
                "path": "/login",
                "fetch_user_result": None,
                "payload": {"username": "alice", "password": "secret"},
                "expected_status": 404,
                "assertions": lambda response: self.assertEqual(
                    response.get_json()["error"], "User not found"
                ),
            },
        ]

        for scenario in scenarios:
            with self.subTest(scenario["name"]), patch.object(
                app_module, "fetch_user", return_value=scenario["fetch_user_result"]
            ):
                if scenario["method"] == "GET":
                    response = self.client.get(scenario["path"])
                else:
                    response = self.client.post(scenario["path"], json=scenario["payload"])

                self.assertEqual(response.status_code, scenario["expected_status"])
                scenario["assertions"](response)

    def test_refresh_route(self):
        scenarios = [
            {
                "name": "refresh_requires_cookie",
                "prepare": lambda: None,
                "expected_status": 401,
                "assertions": lambda response: self.assertEqual(
                    response.get_json()["error"], "Missing token"
                ),
            },
            {
                "name": "refresh_rotates_access_token",
                "prepare": lambda: self.set_refresh_cookie("alice"),
                "expected_status": 200,
                "assertions": lambda response: (
                    self.assertEqual(response.get_json()["message"], "Token refreshed successfully"),
                    self.assertIn("access_token_cookie=", " ".join(response.headers.getlist("Set-Cookie"))),
                ),
            },
        ]

        for scenario in scenarios:
            with self.subTest(scenario["name"]):
                self.client = self.app.test_client()
                scenario["prepare"]()
                response = self.client.post("/refresh", headers={"Accept": "application/json"})
                self.assertEqual(response.status_code, scenario["expected_status"])
                scenario["assertions"](response)

    def test_logout_route(self):
        response = self.client.post("/logout")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["message"], "Logout successful")
        self.assertIn("access_token_cookie=;", " ".join(response.headers.getlist("Set-Cookie")))

    def test_user_info_route(self):
        scenarios = [
            {
                "name": "user_info_requires_auth",
                "prepare": lambda: None,
                "expected_status": 401,
                "assertions": lambda response: self.assertEqual(
                    response.get_json()["action"], "redirect_to_login"
                ),
            },
            {
                "name": "user_info_returns_identity",
                "prepare": lambda: self.set_access_cookie("alice"),
                "expected_status": 200,
                "assertions": lambda response: self.assertEqual(
                    response.get_json(), {"username": "alice", "email": "email@example.com"}
                ),
            },
        ]

        for scenario in scenarios:
            with self.subTest(scenario["name"]):
                self.client = self.app.test_client()
                scenario["prepare"]()
                response = self.client.get("/user-info", headers={"Accept": "application/json"})
                self.assertEqual(response.status_code, scenario["expected_status"])
                scenario["assertions"](response)

    def test_auth_error_handlers_and_static_proxy(self):
        scenarios = []

        scenarios.append(("missing_token_redirects_html", self.app.test_client(), None, "/user-info", {}, 302, "/login?next=/user-info"))

        invalid_client = self.app.test_client()
        invalid_client.set_cookie("access_token_cookie", "not-a-jwt", path="/")
        scenarios.append(("invalid_token_returns_json", invalid_client, None, "/user-info", {"Accept": "application/json"}, 401, "logout"))

        expired_client = self.app.test_client()
        with self.app.app_context():
            expired_token = create_access_token(identity="alice", expires_delta=timedelta(seconds=-1))
        expired_client.set_cookie("access_token_cookie", expired_token, path="/")
        scenarios.append(("expired_token_returns_refresh_action", expired_client, None, "/user-info", {"Accept": "application/json"}, 401, "refresh"))

        static_anon_client = self.app.test_client()
        scenarios.append(("static_proxy_requires_auth", static_anon_client, None, "/static/assets/js/main.js", {"Accept": "application/json"}, 401, "redirect_to_login"))

        static_auth_client = self.app.test_client()
        with self.app.app_context():
            access_token = create_access_token(identity="alice")
        static_auth_client.set_cookie("access_token_cookie", access_token, path="/")
        scenarios.append(("static_proxy_serves_when_authenticated", static_auth_client, "served", "/static/assets/js/main.js", {}, 200, "served"))

        for name, client, send_result, path, headers, expected_status, expected_marker in scenarios:
            with self.subTest(name):
                if send_result is not None:
                    with patch.object(app_module, "send_from_directory", return_value=send_result):
                        response = client.get(path, headers=headers)
                else:
                    response = client.get(path, headers=headers)

                self.assertEqual(response.status_code, expected_status)
                if expected_status == 302:
                    self.assertIn(expected_marker, response.headers["Location"])
                elif path.startswith("/static/") and expected_status == 200:
                    self.assertEqual(response.get_data(as_text=True), expected_marker)
                else:
                    self.assertEqual(response.get_json()["action"], expected_marker)

    def test_signup_route(self):
        captured = {}

        def fake_insert_new_user(username, email, password_hash, instagram_login, instagram_password):
            captured["call"] = (
                username,
                email,
                password_hash,
                instagram_login,
                instagram_password,
            )
            return jsonify({"message": "created"}), 201

        scenarios = [
            {
                "name": "get_signup_page",
                "payload": None,
                "expected_status": 200,
                "assertions": lambda response: self.assertIn(b"<form", response.data),
            },
            {
                "name": "post_signup_rejects_missing_fields",
                "payload": {"username": "alice"},
                "expected_status": 400,
                "assertions": lambda response: self.assertEqual(
                    response.get_json()["error"], "All fields are required"
                ),
            },
            {
                "name": "post_signup_hashes_password_and_delegates",
                "payload": {
                    "username": "alice",
                    "password": "secret",
                    "email": "a@example.com",
                    "instagram_login": "insta",
                    "instagram_password": "insta-secret",
                },
                "expected_status": 201,
                "assertions": lambda response: (
                    self.assertEqual(response.get_json()["message"], "created"),
                    self.assertEqual(
                        captured["call"],
                        (
                            "alice",
                            "a@example.com",
                            hashlib.sha256("secret".encode()).hexdigest(),
                            "insta",
                            "insta-secret",
                        ),
                    ),
                ),
            },
        ]

        with patch.object(app_module, "insert_new_user", side_effect=fake_insert_new_user):
            for scenario in scenarios:
                with self.subTest(scenario["name"]):
                    if scenario["payload"] is None:
                        response = self.client.get("/signup")
                    else:
                        response = self.client.post("/signup", json=scenario["payload"])

                    self.assertEqual(response.status_code, scenario["expected_status"])
                    scenario["assertions"](response)
