from unittest.mock import patch

from tests.support.app_test_case import AppTestCase, app_module


class ProcessFlowRouteTests(AppTestCase):
    def test_process_data_endpoint(self):
        scenarios = [
            {
                "name": "process_data_happy_path",
                "payload": {"params": {"param1": "arthaslav", "param2": "3"}},
                "credentials": {"instagram_login": "insta", "instagram_password": "secret"},
                "extract_result": {
                    "new_posts_found": 2,
                    "posts_loaded": 2,
                    "comments_collected": 11,
                    "saved_files": ["one.csv"],
                },
                "load_result": {"rows_loaded": 11, "files_processed": 1},
                "expected_status": 200,
                "assertions": lambda response, mocked_load: (
                    self.assertTrue(response.get_json()["success"]),
                    self.assertEqual(response.get_json()["result"]["rows_loaded_to_db"], 11),
                    mocked_load.assert_called_once_with(dry_run=False),
                ),
            },
            {
                "name": "process_data_skips_when_no_new_posts",
                "payload": {"params": {"param1": "arthaslav", "param2": "3"}},
                "credentials": {"instagram_login": "insta", "instagram_password": "secret"},
                "extract_result": {"new_posts_found": 0},
                "load_result": {"rows_loaded": 999, "files_processed": 9},
                "expected_status": 200,
                "assertions": lambda response, mocked_load: (
                    self.assertIn("No new posts found", response.get_json()["result"]["message"]),
                    mocked_load.assert_not_called(),
                ),
            },
            {
                "name": "process_data_rejects_missing_instagram_credentials",
                "payload": {"params": {"param1": "arthaslav", "param2": "3"}},
                "credentials": {"instagram_login": "", "instagram_password": ""},
                "extract_result": {},
                "load_result": {},
                "expected_status": 400,
                "assertions": lambda response, mocked_load: (
                    self.assertEqual(
                        response.get_json()["error"],
                        "Instagram credentials are missing for the logged in user.",
                    ),
                    mocked_load.assert_not_called(),
                ),
            },
        ]

        for scenario in scenarios:
            with self.subTest(scenario["name"]):
                self.client = self.app.test_client()
                self.set_access_cookie("alice")
                with patch.object(
                    app_module,
                    "fetch_user_instagram_credentials",
                    return_value=scenario["credentials"],
                ), patch.object(
                    app_module, "fetch_existing_post_hrefs", return_value=["href-1"]
                ), patch.object(
                    app_module, "extract_data", return_value=scenario["extract_result"]
                ), patch.object(
                    app_module, "load_to_db", return_value=scenario["load_result"]
                ) as mocked_load:
                    response = self.client.post(
                        "/process-data",
                        json=scenario["payload"],
                        headers=self.make_json_headers(csrf="access"),
                    )

                self.assertEqual(response.status_code, scenario["expected_status"])
                scenario["assertions"](response, mocked_load)

    def test_process_data_endpoint_validates_request_payload(self):
        scenarios = [
            {
                "name": "missing_params_object",
                "payload": {},
                "expected_error": "No parameters provided.",
            },
            {
                "name": "blank_target_page",
                "payload": {"params": {"param1": "   ", "param2": "3"}},
                "expected_error": "Target page is required.",
            },
            {
                "name": "missing_number_of_posts",
                "payload": {"params": {"param1": "arthaslav"}},
                "expected_error": "Number of posts is required.",
            },
            {
                "name": "non_integer_number_of_posts",
                "payload": {"params": {"param1": "arthaslav", "param2": "abc"}},
                "expected_error": "Number of posts must be an integer.",
            },
            {
                "name": "non_positive_number_of_posts",
                "payload": {"params": {"param1": "arthaslav", "param2": "0"}},
                "expected_error": "Number of posts must be greater than zero.",
            },
        ]

        for scenario in scenarios:
            with self.subTest(scenario["name"]):
                self.client = self.app.test_client()
                self.set_access_cookie("alice")
                with patch.object(
                    app_module,
                    "fetch_user_instagram_credentials",
                    return_value={"instagram_login": "insta", "instagram_password": "secret"},
                ) as mocked_credentials, patch.object(
                    app_module, "fetch_existing_post_hrefs"
                ) as mocked_existing, patch.object(
                    app_module, "extract_data"
                ) as mocked_extract, patch.object(
                    app_module, "load_to_db"
                ) as mocked_load:
                    response = self.client.post(
                        "/process-data",
                        json=scenario["payload"],
                        headers=self.make_json_headers(csrf="access"),
                    )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()["error"], scenario["expected_error"])
                mocked_credentials.assert_not_called()
                mocked_existing.assert_not_called()
                mocked_extract.assert_not_called()
                mocked_load.assert_not_called()

    def test_process_data_requires_csrf_header(self):
        self.set_access_cookie("alice")

        response = self.client.post(
            "/process-data",
            json={"params": {"param1": "arthaslav", "param2": "3"}},
            headers={"Accept": "application/json"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "Missing CSRF token")
        self.assertEqual(response.get_json()["action"], "logout")

    def test_enrich_comments_endpoint(self):
        scenarios = [
            {
                "name": "enrich_comments_success",
                "side_effect": lambda **kwargs: {
                    "mode": kwargs["mode"],
                    "selected": kwargs["page_name"],
                    "processed": 3,
                },
                "expected_status": 200,
                "assertions": lambda response: self.assertTrue(response.get_json()["success"]),
            },
            {
                "name": "enrich_comments_handles_backend_failure",
                "side_effect": RuntimeError("boom"),
                "expected_status": 500,
                "assertions": lambda response: self.assertEqual(response.get_json()["error"], "boom"),
            },
        ]

        for scenario in scenarios:
            with self.subTest(scenario["name"]):
                self.client = self.app.test_client()
                self.set_access_cookie("alice")
                enrich_patch = patch.object(app_module, "enrich_comments", side_effect=scenario["side_effect"])
                if scenario["expected_status"] == 500:
                    with enrich_patch as mocked_enrich, patch.object(app_module.logger, "exception"):
                        response = self.client.post(
                            "/enrich-comments",
                            json={"mode": "page_name", "page_name": "arthaslav"},
                            headers=self.make_json_headers(csrf="access"),
                        )
                        mocked_enrich.assert_called_once()
                else:
                    with enrich_patch:
                        response = self.client.post(
                            "/enrich-comments",
                            json={"mode": "page_name", "page_name": "arthaslav"},
                            headers=self.make_json_headers(csrf="access"),
                        )

                self.assertEqual(response.status_code, scenario["expected_status"])
                scenario["assertions"](response)

    def test_page_analysis_endpoint(self):
        scenarios = [
            {
                "name": "page_analysis_success",
                "side_effect": lambda **kwargs: {
                    "selection_type": kwargs["selection_type"],
                    "selection_value": kwargs["selection_value"],
                    "summary": {"total_comments": 4, "distinct_posts": 2},
                },
                "expected_status": 200,
                "assertions": lambda response: self.assertEqual(
                    response.get_json()["result"]["summary"]["distinct_posts"], 2
                ),
            },
            {
                "name": "page_analysis_handles_backend_failure",
                "side_effect": RuntimeError("analysis failed"),
                "expected_status": 500,
                "assertions": lambda response: self.assertEqual(
                    response.get_json()["error"], "analysis failed"
                ),
            },
        ]

        for scenario in scenarios:
            with self.subTest(scenario["name"]):
                self.client = self.app.test_client()
                self.set_access_cookie("alice")
                analysis_patch = patch.object(app_module, "build_page_analysis", side_effect=scenario["side_effect"])
                if scenario["expected_status"] == 500:
                    with analysis_patch as mocked_analysis, patch.object(app_module.logger, "exception"):
                        response = self.client.post(
                            "/page-analysis",
                            json={"selection_type": "page_id", "selection_value": "arthaslav"},
                            headers=self.make_json_headers(csrf="access"),
                        )
                        mocked_analysis.assert_called_once()
                else:
                    with analysis_patch:
                        response = self.client.post(
                            "/page-analysis",
                            json={"selection_type": "page_id", "selection_value": "arthaslav"},
                            headers=self.make_json_headers(csrf="access"),
                        )

                self.assertEqual(response.status_code, scenario["expected_status"])
                scenario["assertions"](response)

    def test_advanced_analysis_preview(self):
        scenarios = [
            {
                "name": "preview_success",
                "preview_result": {"rows": [{"CommentHash": "1"}], "total": 1},
                "rows_result": [{"CommentHash": "1"}],
                "analysis_result": {"summary": {"total_comments": 1}},
                "expected_status": 200,
                "assertions": lambda response: self.assertEqual(
                    response.get_json()["analysis"]["summary"]["total_comments"], 1
                ),
            },
            {
                "name": "preview_handles_backend_failure",
                "preview_result": RuntimeError("preview failed"),
                "rows_result": [],
                "analysis_result": {},
                "expected_status": 500,
                "assertions": lambda response: self.assertEqual(
                    response.get_json()["error"], "preview failed"
                ),
            },
        ]

        for scenario in scenarios:
            with self.subTest(scenario["name"]):
                self.client = self.app.test_client()
                self.set_access_cookie("alice")
                if isinstance(scenario["preview_result"], Exception):
                    preview_patch = patch.object(
                        app_module, "fetch_enriched_comment_preview", side_effect=scenario["preview_result"]
                    )
                else:
                    preview_patch = patch.object(
                        app_module, "fetch_enriched_comment_preview", return_value=scenario["preview_result"]
                    )

                rows_patch = patch.object(app_module, "fetch_enriched_comment_rows", return_value=scenario["rows_result"])
                build_patch = patch.object(app_module, "build_analysis_from_rows", return_value=scenario["analysis_result"])
                if scenario["expected_status"] == 500:
                    with preview_patch as mocked_preview, rows_patch, build_patch, patch.object(app_module.logger, "exception"):
                        response = self.client.post(
                            "/api/advanced-analysis/preview",
                            json={"page_ids": ["arthaslav"]},
                            headers=self.make_json_headers(csrf="access"),
                        )
                        mocked_preview.assert_called_once()
                else:
                    with preview_patch, rows_patch, build_patch:
                        response = self.client.post(
                            "/api/advanced-analysis/preview",
                            json={"page_ids": ["arthaslav"]},
                            headers=self.make_json_headers(csrf="access"),
                        )

                self.assertEqual(response.status_code, scenario["expected_status"])
                scenario["assertions"](response)

    def test_advanced_analysis_analyze(self):
        scenarios = [
            {
                "name": "analyze_success",
                "rows_result": [{"CommentHash": "1"}],
                "analysis_result": {"summary": {"total_comments": 1}},
                "expected_status": 200,
                "assertions": lambda response: self.assertEqual(
                    response.get_json()["analysis"]["summary"]["total_comments"], 1
                ),
            },
            {
                "name": "analyze_handles_backend_failure",
                "rows_result": RuntimeError("rows failed"),
                "analysis_result": {},
                "expected_status": 500,
                "assertions": lambda response: self.assertEqual(
                    response.get_json()["error"], "rows failed"
                ),
            },
        ]

        for scenario in scenarios:
            with self.subTest(scenario["name"]):
                self.client = self.app.test_client()
                self.set_access_cookie("alice")
                if isinstance(scenario["rows_result"], Exception):
                    rows_patch = patch.object(
                        app_module, "fetch_enriched_comment_rows", side_effect=scenario["rows_result"]
                    )
                else:
                    rows_patch = patch.object(
                        app_module, "fetch_enriched_comment_rows", return_value=scenario["rows_result"]
                    )

                build_patch = patch.object(app_module, "build_analysis_from_rows", return_value=scenario["analysis_result"])
                if scenario["expected_status"] == 500:
                    with rows_patch as mocked_rows, build_patch, patch.object(app_module.logger, "exception"):
                        response = self.client.post(
                            "/api/advanced-analysis/analyze",
                            json={"page_ids": ["arthaslav"]},
                            headers=self.make_json_headers(csrf="access"),
                        )
                        mocked_rows.assert_called_once()
                else:
                    with rows_patch, build_patch:
                        response = self.client.post(
                            "/api/advanced-analysis/analyze",
                            json={"page_ids": ["arthaslav"]},
                            headers=self.make_json_headers(csrf="access"),
                        )

                self.assertEqual(response.status_code, scenario["expected_status"])
                scenario["assertions"](response)
