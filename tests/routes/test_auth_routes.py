from datetime import timedelta
from unittest.mock import patch

from flask import jsonify
from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash

from tests.support.app_test_case import AppTestCase, app_module
from tests.support.app_test_loader import load_app_module_with_env


class AuthRouteTests(AppTestCase):
    def test_runtime_security_config_uses_safe_environment_defaults(self):
        development_module = load_app_module_with_env(
            {
                "APP_ENV": "development",
                "DEBUG": None,
                "JWT_COOKIE_SECURE": None,
                "JWT_COOKIE_SAMESITE": None,
            }
        )
        self.assertEqual(development_module.app.config["APP_ENV"], "development")
        self.assertTrue(development_module.app.config["DEBUG"])
        self.assertFalse(development_module.app.config["JWT_COOKIE_SECURE"])
        self.assertEqual(development_module.app.config["JWT_COOKIE_SAMESITE"], "Lax")

        production_module = load_app_module_with_env(
            {
                "APP_ENV": "production",
                "DEBUG": None,
                "JWT_COOKIE_SECURE": None,
                "JWT_COOKIE_SAMESITE": None,
            }
        )
        self.assertEqual(production_module.app.config["APP_ENV"], "production")
        self.assertFalse(production_module.app.config["DEBUG"])
        self.assertTrue(production_module.app.config["JWT_COOKIE_SECURE"])
        self.assertEqual(production_module.app.config["JWT_COOKIE_SAMESITE"], "Lax")

    def test_login_route_applies_cookie_flags_for_each_environment(self):
        password_hash = generate_password_hash("secret", method="scrypt")
        development_module = load_app_module_with_env(
            {
                "APP_ENV": "development",
                "DEBUG": None,
                "JWT_COOKIE_SECURE": None,
                "JWT_COOKIE_SAMESITE": None,
            }
        )
        development_client = development_module.app.test_client()
        with patch.object(development_module, "fetch_user", return_value=(password_hash,)):
            response = development_client.post("/login", json={"username": "alice", "password": "secret"})

        set_cookie_headers = " ".join(response.headers.getlist("Set-Cookie"))
        self.assertIn("SameSite=Lax", set_cookie_headers)
        self.assertNotIn("Secure;", set_cookie_headers)

        production_module = load_app_module_with_env(
            {
                "APP_ENV": "production",
                "DEBUG": None,
                "JWT_COOKIE_SECURE": None,
                "JWT_COOKIE_SAMESITE": None,
            }
        )
        production_client = production_module.app.test_client()
        with patch.object(production_module, "fetch_user", return_value=(password_hash,)):
            production_response = production_client.post("/login", json={"username": "alice", "password": "secret"})

        production_cookie_headers = " ".join(production_response.headers.getlist("Set-Cookie"))
        self.assertIn("SameSite=Lax", production_cookie_headers)
        self.assertIn("Secure;", production_cookie_headers)

    def test_login_route(self):
        password_hash = generate_password_hash("secret", method="scrypt")
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
                "name": "post_login_upgrades_legacy_sha256_hash",
                "method": "POST",
                "path": "/login",
                "fetch_user_result": (app_module.hashlib.sha256("secret".encode()).hexdigest(),),
                "payload": {"username": "alice", "password": "secret"},
                "expected_status": 200,
                "assertions": lambda response: self.assertEqual(response.get_json()["message"], "Login successful"),
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
                "expected_status": 401,
                "assertions": lambda response: self.assertEqual(
                    response.get_json()["error"], "Invalid username or password"
                ),
            },
        ]

        for scenario in scenarios:
            with self.subTest(scenario["name"]), patch.object(
                app_module, "fetch_user", return_value=scenario["fetch_user_result"]
            ), patch.object(app_module, "update_user_password_hash") as mocked_upgrade:
                app_module.clear_rate_limit_state()
                if scenario["method"] == "GET":
                    response = self.client.get(scenario["path"])
                else:
                    response = self.client.post(scenario["path"], json=scenario["payload"])

                self.assertEqual(response.status_code, scenario["expected_status"])
                scenario["assertions"](response)
                if scenario["name"] == "post_login_upgrades_legacy_sha256_hash":
                    mocked_upgrade.assert_called_once()
                    self.assertTrue(mocked_upgrade.call_args.args[1].startswith("scrypt:"))
                else:
                    mocked_upgrade.assert_not_called()

    def test_login_route_uses_same_failure_behavior_for_unknown_user_and_bad_password(self):
        password_hash = generate_password_hash("secret", method="scrypt")

        with patch.object(app_module, "fetch_user", return_value=(password_hash,)):
            bad_password_response = self.client.post("/login", json={"username": "alice", "password": "wrong"})

        app_module.clear_rate_limit_state()

        with patch.object(app_module, "fetch_user", return_value=None):
            unknown_user_response = self.client.post("/login", json={"username": "missing-user", "password": "secret"})

        self.assertEqual(bad_password_response.status_code, 401)
        self.assertEqual(unknown_user_response.status_code, 401)
        self.assertEqual(
            bad_password_response.get_json()["error"],
            "Invalid username or password",
        )
        self.assertEqual(
            unknown_user_response.get_json()["error"],
            "Invalid username or password",
        )

    def test_login_route_rate_limits_repeated_attempts(self):
        self.app.config["RATE_LIMIT_LOGIN_MAX_ATTEMPTS"] = 2
        self.app.config["RATE_LIMIT_LOGIN_WINDOW_SECONDS"] = 60
        password_hash = generate_password_hash("secret", method="scrypt")

        with patch.object(app_module, "fetch_user", return_value=(password_hash,)):
            first_response = self.client.post("/login", json={"username": "alice", "password": "wrong"})
            second_response = self.client.post("/login", json={"username": "alice", "password": "wrong"})
            limited_response = self.client.post("/login", json={"username": "alice", "password": "wrong"})

        self.assertEqual(first_response.status_code, 401)
        self.assertEqual(second_response.status_code, 401)
        self.assertEqual(limited_response.status_code, 429)
        self.assertEqual(
            limited_response.get_json()["error"],
            "Too many login requests. Please retry later.",
        )
        self.assertIn("Retry-After", limited_response.headers)

    def test_login_rate_limit_does_not_trust_spoofed_forwarded_for_by_default(self):
        self.app.config["RATE_LIMIT_LOGIN_MAX_ATTEMPTS"] = 1
        self.app.config["RATE_LIMIT_LOGIN_WINDOW_SECONDS"] = 60
        password_hash = generate_password_hash("secret", method="scrypt")

        with patch.object(app_module, "fetch_user", return_value=(password_hash,)):
            first_response = self.client.post(
                "/login",
                json={"username": "alice", "password": "wrong"},
                headers={"X-Forwarded-For": "1.1.1.1"},
            )
            limited_response = self.client.post(
                "/login",
                json={"username": "alice", "password": "wrong"},
                headers={"X-Forwarded-For": "2.2.2.2"},
            )

        self.assertEqual(first_response.status_code, 401)
        self.assertEqual(limited_response.status_code, 429)
        self.assertEqual(
            limited_response.get_json()["error"],
            "Too many login requests. Please retry later.",
        )

    def test_cors_is_restricted_to_explicit_allowed_origins(self):
        cors_module = load_app_module_with_env(
            {
                "CORS_ALLOWED_ORIGINS": "http://localhost:5000,https://trusted.example",
            }
        )
        cors_client = cors_module.app.test_client()

        allowed_response = cors_client.get("/login", headers={"Origin": "https://trusted.example"})
        disallowed_response = cors_client.get("/login", headers={"Origin": "https://evil.example"})

        self.assertEqual(
            allowed_response.headers.get("Access-Control-Allow-Origin"),
            "https://trusted.example",
        )
        self.assertEqual(allowed_response.headers.get("Access-Control-Allow-Credentials"), "true")
        self.assertIsNone(disallowed_response.headers.get("Access-Control-Allow-Origin"))

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
                response = self.client.post("/refresh", headers=self.make_json_headers(csrf="refresh"))
                self.assertEqual(response.status_code, scenario["expected_status"])
                scenario["assertions"](response)

    def test_refresh_route_rejects_missing_csrf_header(self):
        self.set_refresh_cookie("alice")

        response = self.client.post("/refresh", headers={"Accept": "application/json"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "Missing CSRF token")
        self.assertEqual(response.get_json()["action"], "logout")

    def test_logout_route(self):
        self.set_access_cookie("alice")
        response = self.client.post("/logout", headers=self.make_json_headers(csrf="access"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["message"], "Logout successful")
        self.assertIn("access_token_cookie=;", " ".join(response.headers.getlist("Set-Cookie")))

    def test_logout_route_rejects_missing_csrf_header(self):
        self.set_access_cookie("alice")

        response = self.client.post("/logout", headers={"Accept": "application/json"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "Missing CSRF token")
        self.assertEqual(response.get_json()["action"], "logout")

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
                    response.get_json(), {"username": "alice", "email": "alice@example.com"}
                ),
            },
        ]

        for scenario in scenarios:
            with self.subTest(scenario["name"]):
                self.client = self.app.test_client()
                scenario["prepare"]()
                with patch.object(
                    app_module,
                    "fetch_user_profile",
                    return_value={"email": "alice@example.com"},
                ):
                    response = self.client.get("/user-info", headers={"Accept": "application/json"})
                self.assertEqual(response.status_code, scenario["expected_status"])
                scenario["assertions"](response)

    def test_account_routes(self):
        self.set_access_cookie("alice")

        profile_payload = {
            "username": "alice",
            "email": "alice@example.com",
            "email_verified": False,
            "email_verified_at": None,
            "created_at": "2026-03-01T10:00:00",
            "password_changed_at": "2026-03-10T10:00:00",
            "instagram_login": "insta",
            "has_instagram_password": True,
            "instagram_cookies_updated_at": "2026-03-20T10:00:00",
            "has_instagram_cookies": True,
        }
        stats_payload = {"total_comments": 10, "distinct_pages": 2, "enriched_comments": 7}

        with patch.object(app_module, "fetch_user_profile", return_value=profile_payload), patch.object(
            app_module, "fetch_account_statistics", return_value=stats_payload
        ):
            page_response = self.client.get("/account")
            api_response = self.client.get("/api/account", headers=self.make_json_headers(csrf="access"))

        self.assertEqual(page_response.status_code, 200)
        self.assertIn(b"Account", page_response.data)
        self.assertEqual(api_response.status_code, 200)
        self.assertEqual(api_response.get_json()["profile"]["email"], "alice@example.com")
        self.assertEqual(api_response.get_json()["stats"]["total_comments"], 10)

    def test_manual_login_hint_route(self):
        self.set_access_cookie("alice")

        with patch.object(
            app_module,
            "fetch_user_instagram_credentials",
            return_value={"instagram_login": "insta-user", "instagram_password": "secretpass"},
        ):
            response = self.client.get("/api/account/manual-login-hint", headers=self.make_json_headers(csrf="access"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"instagram_login": "insta-user", "instagram_password_hint": "s********s"},
        )

    def test_account_mutation_routes(self):
        self.set_access_cookie("alice")
        scenarios = [
            {
                "name": "change_password_success",
                "method": "POST",
                "path": "/api/account/change-password",
                "payload": {"current_password": "old-secret", "new_password": "new-secret-1"},
                "verify_result": True,
                "expected_status": 200,
                "assertions": lambda response, mocked_password, mocked_email, mocked_ig, mocked_cookies: (
                    self.assertEqual(response.get_json()["message"], "Password updated successfully."),
                    mocked_password.assert_called_once(),
                    mocked_email.assert_not_called(),
                    mocked_ig.assert_not_called(),
                    mocked_cookies.assert_not_called(),
                ),
            },
            {
                "name": "verify_email_success",
                "method": "POST",
                "path": "/api/account/verify-email",
                "payload": {"current_password": "old-secret"},
                "verify_result": True,
                "expected_status": 200,
                "assertions": lambda response, mocked_password, mocked_email, mocked_ig, mocked_cookies: (
                    self.assertEqual(response.get_json()["message"], "Email marked as verified for this local account."),
                    mocked_password.assert_not_called(),
                    mocked_email.assert_called_once_with("alice", True),
                    mocked_ig.assert_not_called(),
                    mocked_cookies.assert_not_called(),
                ),
            },
            {
                "name": "clear_instagram_cookies",
                "method": "POST",
                "path": "/api/account/instagram-cookies/clear",
                "payload": None,
                "verify_result": True,
                "expected_status": 200,
                "assertions": lambda response, mocked_password, mocked_email, mocked_ig, mocked_cookies: (
                    self.assertEqual(response.get_json()["message"], "Stored Instagram cookies cleared."),
                    mocked_password.assert_not_called(),
                    mocked_email.assert_not_called(),
                    mocked_ig.assert_not_called(),
                    mocked_cookies.assert_called_once_with("alice"),
                ),
            },
            {
                "name": "update_instagram_credentials",
                "method": "POST",
                "path": "/api/account/instagram-credentials",
                "payload": {"instagram_login": "insta-new", "instagram_password": "ig-secret"},
                "verify_result": True,
                "expected_status": 200,
                "assertions": lambda response, mocked_password, mocked_email, mocked_ig, mocked_cookies: (
                    self.assertIn("Instagram credentials updated", response.get_json()["message"]),
                    mocked_password.assert_not_called(),
                    mocked_email.assert_not_called(),
                    mocked_ig.assert_called_once_with("alice", "insta-new", "ig-secret"),
                    mocked_cookies.assert_not_called(),
                ),
            },
            {
                "name": "delete_instagram_credentials",
                "method": "DELETE",
                "path": "/api/account/instagram-credentials",
                "payload": None,
                "verify_result": True,
                "expected_status": 200,
                "assertions": lambda response, mocked_password, mocked_email, mocked_ig, mocked_cookies: (
                    self.assertIn("Instagram credentials deleted", response.get_json()["message"]),
                    mocked_password.assert_not_called(),
                    mocked_email.assert_not_called(),
                    mocked_ig.assert_called_once_with("alice", None, None),
                    mocked_cookies.assert_not_called(),
                ),
            },
            {
                "name": "change_password_rejects_wrong_current_password",
                "method": "POST",
                "path": "/api/account/change-password",
                "payload": {"current_password": "wrong", "new_password": "new-secret-1"},
                "verify_result": False,
                "expected_status": 401,
                "assertions": lambda response, mocked_password, mocked_email, mocked_ig, mocked_cookies: (
                    self.assertEqual(response.get_json()["error"], "Current password is incorrect."),
                    mocked_password.assert_not_called(),
                    mocked_email.assert_not_called(),
                    mocked_ig.assert_not_called(),
                    mocked_cookies.assert_not_called(),
                ),
            },
        ]

        for scenario in scenarios:
            with self.subTest(scenario["name"]), patch.object(
                app_module, "verify_application_password", return_value=scenario["verify_result"]
            ), patch.object(
                app_module, "update_user_password_hash"
            ) as mocked_password, patch.object(
                app_module, "set_user_email_verified"
            ) as mocked_email, patch.object(
                app_module, "update_user_instagram_credentials"
            ) as mocked_ig, patch.object(
                app_module, "clear_user_instagram_cookies"
            ) as mocked_cookies:
                if scenario["method"] == "DELETE":
                    response = self.client.delete(
                        scenario["path"],
                        headers=self.make_json_headers(csrf="access"),
                    )
                else:
                    response = self.client.post(
                        scenario["path"],
                        json=scenario["payload"],
                        headers=self.make_json_headers(csrf="access"),
                    )

                self.assertEqual(response.status_code, scenario["expected_status"])
                scenario["assertions"](response, mocked_password, mocked_email, mocked_ig, mocked_cookies)

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

        static_client = self.app.test_client()
        scenarios.append(("static_proxy_is_public", static_client, "served", "/static/assets/js/main.js", {}, 200, "served"))

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
                        captured["call"][0],
                        "alice",
                    ),
                    self.assertEqual(captured["call"][1], "a@example.com"),
                    self.assertTrue(captured["call"][2].startswith("scrypt:")),
                    self.assertEqual(captured["call"][3], "insta"),
                    self.assertEqual(captured["call"][4], "insta-secret"),
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
