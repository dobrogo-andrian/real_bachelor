from unittest.mock import patch

from tests.support.app_test_case import AppTestCase, app_module


class AppSmokeTests(AppTestCase):
    def test_static_assets_are_publicly_served(self):
        response = self.client.get("/static/assets/css/main.css")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"body", response.data)

    def test_app_imports_and_public_pages_render(self):
        self.assertIsNotNone(self.app)

        scenarios = [
            {"path": "/", "marker": b'id="login-state-indicator"'},
            {"path": "/test", "marker": b"<title>Test</title>"},
            {"path": "/signup", "marker": b'id="signup-form"'},
            {"path": "/login", "marker": b'id="login-form"'},
        ]

        for scenario in scenarios:
            with self.subTest(scenario["path"]):
                response = self.client.get(scenario["path"])
                self.assertEqual(response.status_code, 200)
                self.assertIn(scenario["marker"], response.data)

    def test_protected_html_routes_redirect_anonymous_users(self):
        protected_paths = ["/elements", "/extractor", "/explorer", "/advanced-analysis", "/faq"]

        for path in protected_paths:
            with self.subTest(path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/login?next=", response.headers["Location"])

    def test_protected_html_routes_render_for_authenticated_user(self):
        self.set_access_cookie("alice")

        with patch.object(
            app_module,
            "fetch_distinct_comment_dimensions",
            return_value={"page_names": ["arthaslav"], "page_ids": ["arthaslav"]},
        ), patch.object(
            app_module,
            "fetch_advanced_comment_dimensions",
            return_value={
                "page_names": ["arthaslav"],
                "page_ids": ["arthaslav"],
                "sources": ["instagram"],
                "languages": ["uk"],
                "sentiments": ["positive"],
                "ranges": {},
            },
        ):
            scenarios = [
                {"path": "/elements", "marker": b'id="content"'},
                {"path": "/extractor", "marker": b'id="start_execution"'},
                {"path": "/explorer", "marker": b'id="selection-result-title"'},
                {"path": "/advanced-analysis", "marker": b'id="summary-total-comments"'},
                {"path": "/faq", "marker": b"FAQ Reference: Comments Table Model"},
            ]

            for scenario in scenarios:
                with self.subTest(scenario["path"]):
                    response = self.client.get(scenario["path"])
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(scenario["marker"], response.data)

    def test_dimension_loading_errors_render_on_page(self):
        self.set_access_cookie("alice")

        with patch.object(
            app_module,
            "fetch_distinct_comment_dimensions",
            side_effect=RuntimeError("comments lookup failed"),
        ), patch.object(
            app_module,
            "fetch_advanced_comment_dimensions",
            side_effect=RuntimeError("advanced lookup failed"),
        ), patch.object(
            app_module.logger, "exception"
        ):
            explorer_response = self.client.get("/explorer")
            advanced_response = self.client.get("/advanced-analysis")

        self.assertEqual(explorer_response.status_code, 200)
        self.assertIn(b"Could not load page lists right now.", explorer_response.data)
        self.assertEqual(advanced_response.status_code, 200)
        self.assertIn(b"Could not load advanced-analysis filters right now.", advanced_response.data)
