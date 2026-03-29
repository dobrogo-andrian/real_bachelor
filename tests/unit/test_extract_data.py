import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, TimeoutException

from static.backend import extract_data as extract_module
from tests.support.fake_selenium import FakeDriver, FakeElement, FakeWebDriverWait


class ExtractDataTests(unittest.TestCase):
    def test_human_pause(self):
        with patch.object(extract_module.random, "uniform", return_value=0.42) as mocked_uniform, patch.object(
            extract_module.time, "sleep"
        ) as mocked_sleep:
            extract_module.human_pause(0.1, 0.9)

        mocked_uniform.assert_called_once_with(0.1, 0.9)
        mocked_sleep.assert_called_once_with(0.42)

    def test_wait_for_document_ready(self):
        driver = FakeDriver()
        with patch.object(extract_module, "WebDriverWait", FakeWebDriverWait):
            extract_module.wait_for_document_ready(driver, timeout=7)

        self.assertTrue(driver.executed_scripts)

    def test_wait_for_any_element(self):
        visible = FakeElement(displayed=True)
        stale = FakeElement(displayed=StaleElementReferenceException())
        driver = FakeDriver()
        driver.find_map = {
            ("xpath", "//first"): [stale],
            ("css selector", ".second"): [visible],
        }
        selectors = [("xpath", "//first"), ("css selector", ".second")]

        with patch.object(extract_module, "WebDriverWait", FakeWebDriverWait):
            result = extract_module.wait_for_any_element(driver, selectors, timeout=5)

        self.assertIs(result, visible)

    def test_wait_for_comment_surface(self):
        driver = FakeDriver()
        with patch.object(extract_module, "wait_for_any_element", side_effect=[FakeElement(), TimeoutException("x")]):
            found = extract_module.wait_for_comment_surface(driver, timeout=3)
            missing = extract_module.wait_for_comment_surface(driver, timeout=3)

        self.assertIsInstance(found, FakeElement)
        self.assertIsNone(missing)

    def test_retry_on_stale(self):
        attempts = {"count": 0}

        def flaky_action():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise StaleElementReferenceException()
            return "ok"

        with patch.object(extract_module, "human_pause") as mocked_pause, redirect_stdout(io.StringIO()):
            result = extract_module.retry_on_stale(flaky_action, "retrying", retries=2)

        self.assertEqual(result, "ok")
        self.assertEqual(attempts["count"], 3)
        self.assertEqual(mocked_pause.call_count, 2)

    def test_delete_previos_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            working_dir = os.getcwd()
            os.chdir(temp_dir)
            try:
                target_dir = os.path.join(temp_dir, "unprocessed_data")
                os.makedirs(os.path.join(target_dir, "nested"), exist_ok=True)
                with open(os.path.join(target_dir, "old.csv"), "w", encoding="utf-8") as handle:
                    handle.write("data")
                with open(os.path.join(target_dir, "nested", "inside.csv"), "w", encoding="utf-8") as handle:
                    handle.write("data")

                with redirect_stdout(io.StringIO()):
                    extract_module.delete_previos_files()

                self.assertTrue(os.path.isdir(target_dir))
                self.assertEqual(os.listdir(target_dir), [])
            finally:
                os.chdir(working_dir)

    def test_setup_driver(self):
        fake_options_instance = MagicMock()
        fake_driver = FakeDriver()

        with patch.object(extract_module, "Options", return_value=fake_options_instance), patch.object(
            extract_module.webdriver, "Chrome", return_value=fake_driver
        ) as mocked_chrome, patch.dict(os.environ, {"CHROMEDRIVER_PATH": "C:\\chromedriver.exe"}, clear=False):
            driver = extract_module.setup_driver()

        self.assertIs(driver, fake_driver)
        mocked_chrome.assert_called_once()
        self.assertFalse(hasattr(fake_driver, "cdp_command"))

    def test_setup_driver_headless(self):
        fake_options_instance = MagicMock()
        fake_driver = FakeDriver()

        with patch.object(extract_module, "Options", return_value=fake_options_instance), patch.object(
            extract_module.webdriver, "Chrome", return_value=fake_driver
        ), patch.dict(os.environ, {"CHROMEDRIVER_PATH": "C:\\chromedriver.exe"}, clear=False):
            extract_module.setup_driver(headless=True)

        fake_options_instance.add_argument.assert_any_call("--headless=new")

    def test_login_to_instagram(self):
        username_field = FakeElement()
        password_field = FakeElement()
        login_button = FakeElement()
        driver = FakeDriver()

        def fake_wait_for_document_ready(current_driver, timeout=12):
            return current_driver

        def fake_webdriver_wait(current_driver, timeout):
            class _Wait:
                def until(self, condition):
                    result = condition(current_driver)
                    if not result:
                        raise TimeoutException("timed out")
                    current_driver.current_url = "https://www.instagram.com/home/"
                    return result

            return _Wait()

        def fake_find_elements(by=None, value=None):
            if value == "username":
                return [username_field]
            if value == "password":
                return [password_field]
            if value == "//button[@type='submit']":
                return [login_button]
            return []

        driver.find_elements = fake_find_elements

        with patch.object(extract_module, "wait_for_document_ready", side_effect=fake_wait_for_document_ready), patch.object(
            extract_module, "WebDriverWait", side_effect=fake_webdriver_wait
        ), patch.object(extract_module, "human_pause"), redirect_stdout(io.StringIO()):
            success = extract_module.login_to_instagram(driver, "alice", "secret")

        self.assertTrue(success)
        self.assertIn("https://www.instagram.com/accounts/login/", driver.got_urls)
        self.assertEqual(username_field.sent_keys, ["alice"])
        self.assertEqual(password_field.sent_keys[0], "secret")

    def test_save_cookies(self):
        driver = FakeDriver()

        with patch.object(extract_module, "store_user_instagram_cookies") as mocked_store, redirect_stdout(
            io.StringIO()
        ):
            extract_module.save_cookies(driver, app_username="alice", instagram_username="insta")

        mocked_store.assert_called_once()
        self.assertEqual(mocked_store.call_args.args[0], "alice")
        stored_payload = mocked_store.call_args.args[1]
        self.assertEqual(
            json.loads(stored_payload),
            {
                "app_username": "alice",
                "cookies": [{"name": "sessionid", "value": "abc"}],
                "instagram_username": "insta",
                "version": 1,
            },
        )

    def test_load_cookies(self):
        driver = FakeDriver()

        with patch.object(extract_module, "fetch_user_instagram_cookies", return_value=None), redirect_stdout(
            io.StringIO()
        ):
            self.assertFalse(extract_module.load_cookies(driver, app_username="alice", instagram_username="insta"))

        payload = json.dumps(
            {
                "version": 1,
                "app_username": "alice",
                "instagram_username": "insta",
                "cookies": [{"name": "sessionid", "value": "abc"}],
            }
        )
        with patch.object(extract_module, "fetch_user_instagram_cookies", return_value=payload), redirect_stdout(
            io.StringIO()
        ):
            loaded = extract_module.load_cookies(driver, app_username="alice", instagram_username="insta")

        self.assertTrue(loaded)
        self.assertEqual(driver.cookies_added, [{"name": "sessionid", "value": "abc"}])

    def test_load_cookies_clears_invalid_payload(self):
        driver = FakeDriver()

        with patch.object(extract_module, "fetch_user_instagram_cookies", return_value="{"), patch.object(
            extract_module, "clear_user_instagram_cookies"
        ) as mocked_clear, redirect_stdout(io.StringIO()):
            loaded = extract_module.load_cookies(driver, app_username="alice", instagram_username="insta")

        self.assertFalse(loaded)
        mocked_clear.assert_called_once_with("alice")

    def test_detect_instagram_restriction(self):
        driver = FakeDriver()
        driver.page_source = "Ми маємо підозру, що у вашому обліковому записі виконуються автоматичні дії"

        restriction = extract_module.detect_instagram_restriction(driver)

        self.assertEqual(restriction, "Instagram flagged the session for suspected automation.")

    def test_wait_for_manual_instagram_login_detects_completed_login(self):
        driver = FakeDriver()
        driver.current_url = "https://www.instagram.com/arthaslav/"

        with patch.object(extract_module, "wait_for_profile_content"):
            success, reason = extract_module.wait_for_manual_instagram_login(driver, timeout=1, poll_interval=0)

        self.assertTrue(success)
        self.assertIsNone(reason)

    def test_wait_for_manual_instagram_login_detects_restriction(self):
        driver = FakeDriver()
        driver.page_source = "automated actions"

        with patch.object(extract_module.time, "sleep"):
            success, reason = extract_module.wait_for_manual_instagram_login(driver, timeout=1, poll_interval=0)

        self.assertFalse(success)
        self.assertIn("suspected automation", reason)

    def test_get_scroll_wait_profile(self):
        driver = FakeDriver()
        scroll_container = SimpleNamespace()

        container_height, load_timeout, poll_interval, settle_delay = extract_module.get_scroll_wait_profile(
            driver, scroll_container
        )

        self.assertEqual(container_height, 660)
        self.assertTrue(1.2 <= load_timeout <= 3.2)
        self.assertTrue(0.2 <= poll_interval <= 0.45)
        self.assertTrue(0.45 <= settle_delay <= 1.4)

    def test_try_scroll_page(self):
        driver = FakeDriver()
        scroll_container = SimpleNamespace(scroll_heights=[100, 150, 150])
        time_values = iter([0.0, 0.0, 0.005, 0.02, 0.03, 0.03, 0.035, 0.05])

        with patch.object(extract_module, "get_scroll_wait_profile", return_value=(500, 0.01, 0.01, 0.01)), patch.object(
            extract_module.random, "uniform", side_effect=lambda a, b: min(a, b)
        ), patch.object(extract_module.time, "sleep"), patch.object(
            extract_module.time, "time", side_effect=lambda: next(time_values)
        ), redirect_stdout(io.StringIO()):
            exhausted = extract_module.try_scroll_page(driver, scroll_container, limit_scrolling=False)

        with patch.object(extract_module, "get_scroll_wait_profile", return_value=(500, 0.01, 0.01, 0.01)), patch.object(
            extract_module.random, "uniform", side_effect=lambda a, b: min(a, b)
        ), patch.object(extract_module.time, "sleep"), patch.object(
            extract_module.time, "time", side_effect=[0, 0, 0.02]
        ), redirect_stdout(io.StringIO()):
            stopped = extract_module.try_scroll_page(
                driver,
                SimpleNamespace(scroll_heights=[100]),
                stop_scroll_callback=lambda: True,
            )

        self.assertFalse(exhausted)
        self.assertFalse(stopped)
        self.assertTrue(driver.executed_scripts)

    def test_collect_comments_and_likes(self):
        comment_span = FakeElement(text="Great post")
        time_element = FakeElement(attributes={"datetime": "2024-01-01T10:00:00"})
        like_span = FakeElement(text="12 likes")
        container = FakeElement(
            nested={
                ("xpath", ".//span"): [like_span],
                ("xpath", ".//time[@datetime]"): time_element,
            }
        )
        comment_span.nested = {
            (
                "xpath",
                "ancestor::div[.//time[@datetime] and .//span[contains(translate(., 'LIKE', 'like'), 'like')]][1]",
            ): container
        }
        driver = FakeDriver()
        driver.find_map = {
            ("xpath", ".//div[@style='display: inline;']/span[@dir='auto']"): [comment_span],
            ("xpath", "//time[@datetime]"): [time_element],
        }

        with redirect_stdout(io.StringIO()):
            result = extract_module.collect_comments_and_likes(driver)

        self.assertEqual(result, [("Great post", "2024-01-01T10:00:00", 12)])

    def test_click_view_all_comments(self):
        button = FakeElement()
        with patch.object(extract_module, "WebDriverWait", return_value=SimpleNamespace(until=lambda condition: button)), patch.object(
            extract_module.EC, "element_to_be_clickable", return_value=lambda driver: button
        ), redirect_stdout(io.StringIO()):
            success = extract_module.click_view_all_comments(FakeDriver())

        with patch.object(extract_module, "WebDriverWait", return_value=SimpleNamespace(until=lambda condition: (_ for _ in ()).throw(TimeoutException("x")))), patch.object(
            extract_module.EC, "element_to_be_clickable", return_value=lambda driver: False
        ), redirect_stdout(io.StringIO()):
            missing = extract_module.click_view_all_comments(FakeDriver())

        self.assertTrue(success)
        self.assertTrue(button.clicked)
        self.assertFalse(missing)

    def test_click_reels_comment_button(self):
        button = FakeElement()

        def fake_wait(*args, **kwargs):
            class _Wait:
                def until(self, condition):
                    return button

            return _Wait()

        with patch.object(extract_module, "WebDriverWait", side_effect=fake_wait), patch.object(
            extract_module.EC, "element_to_be_clickable", return_value=lambda driver: button
        ), redirect_stdout(io.StringIO()):
            clicked = extract_module.click_reels_comment_button(FakeDriver())

        self.assertTrue(clicked)
        self.assertTrue(button.clicked)

    def test_click_more_button(self):
        button = FakeElement()
        driver = FakeDriver()
        driver.find_element = lambda by=None, value=None: button

        with redirect_stdout(io.StringIO()):
            clicked = extract_module.click_more_button(driver)

        driver.find_element = lambda by=None, value=None: (_ for _ in ()).throw(NoSuchElementException())
        with redirect_stdout(io.StringIO()):
            missing = extract_module.click_more_button(driver)

        self.assertTrue(clicked)
        self.assertTrue(button.clicked)
        self.assertFalse(missing)

    def test_save_comments(self):
        driver = FakeDriver()
        fake_dataframe = MagicMock()
        fake_pd = SimpleNamespace(DataFrame=MagicMock(return_value=fake_dataframe))

        with patch.object(extract_module, "wait_for_post_content"), patch.object(
            extract_module, "human_pause"
        ), patch.object(extract_module, "retry_on_stale"), patch.object(
            extract_module, "scroll_and_load_comments"
        ), patch.object(
            extract_module, "collect_comments_and_likes", return_value=[("Nice", "2024-01-01T10:00:00", 3)]
        ), patch.object(
            extract_module, "get_next_filename", return_value="unprocessed_data/comments1/arthaslav_1.csv"
        ), patch.object(
            extract_module, "pd", fake_pd
        ), redirect_stdout(io.StringIO()):
            result = extract_module.save_comments(
                driver,
                "https://instagram.com/p/1",
                "arthaslav",
                "Artha Slav",
            )

        self.assertEqual(result["comments_collected"], 1)
        self.assertEqual(result["output_path"], "unprocessed_data/comments1/arthaslav_1.csv")
        fake_dataframe.insert.assert_any_call(0, "PageName", "Artha Slav")
        fake_dataframe.to_csv.assert_called_once()

    def test_find_scroll_elements_by_scroll_properties(self):
        driver = FakeDriver()
        large = SimpleNamespace(scroll_height=200, client_height=50)
        small = SimpleNamespace(scroll_height=100, client_height=70)
        flat = SimpleNamespace(scroll_height=30, client_height=30)
        driver.find_map = {("tag name", "div"): [flat, small, large]}

        with patch.object(extract_module, "wait_for_document_ready"), patch.object(
            extract_module, "human_pause"
        ), patch.object(extract_module, "try_press_cancel_button"), redirect_stdout(io.StringIO()):
            result = extract_module.find_scroll_elements_by_scroll_properties(driver, "div")

        self.assertEqual(result, [large, small])

    def test_find_scroll_element_by_scroll_properties(self):
        first = object()
        second = object()
        with patch.object(extract_module, "find_scroll_elements_by_scroll_properties", return_value=[first, second]):
            result = extract_module.find_scroll_element_by_scroll_properties(FakeDriver(), "div")

        self.assertIs(result, first)

    def test_collect_all_hrefs(self):
        anchors = [
            FakeElement(attributes={"href": "https://www.instagram.com/arthaslav/p/1"}),
            FakeElement(attributes={"href": "https://www.instagram.com/arthaslav/p/1"}),
            FakeElement(attributes={"href": "https://www.instagram.com/arthaslav/p/2"}),
            FakeElement(attributes={"href": "https://www.instagram.com/arthaslav/p/skip"}),
        ]
        container = FakeElement(nested={("tag name", "a"): anchors})

        with redirect_stdout(io.StringIO()):
            hrefs = extract_module.collect_all_hrefs(
                container,
                "arthaslav",
                5,
                skip_hrefs={"https://www.instagram.com/p/skip"},
            )

        self.assertEqual(hrefs, ["https://www.instagram.com/p/1", "https://www.instagram.com/p/2"])

    def test_get_page_name(self):
        element = FakeElement(text="Artha Slav")
        wait_calls = {"count": 0}

        def fake_wait(*args, **kwargs):
            class _Wait:
                def until(self, condition):
                    wait_calls["count"] += 1
                    if wait_calls["count"] == 1:
                        raise TimeoutException("miss")
                    return element

            return _Wait()

        with patch.object(extract_module, "WebDriverWait", side_effect=fake_wait), patch.object(
            extract_module.EC, "presence_of_element_located", return_value=lambda driver: element
        ):
            page_name = extract_module.get_page_name(FakeDriver())

        self.assertEqual(page_name, "Artha Slav")

    def test_load_all_posts(self):
        driver = FakeDriver()
        container = FakeElement()
        driver.find_map = {("xpath", extract_module.POST_CONTAINER_XPATH): [container]}
        collected_sequences = [["https://www.instagram.com/p/1"], ["https://www.instagram.com/p/1", "https://www.instagram.com/p/2"]]

        def fake_collect_all_hrefs(*args, **kwargs):
            return collected_sequences.pop(0)

        with patch.object(extract_module, "wait_for_profile_content"), patch.object(
            extract_module, "human_pause"
        ), patch.object(
            extract_module, "get_page_name", return_value="Artha Slav"
        ), patch.object(
            extract_module, "find_scroll_element_by_scroll_properties", return_value=object()
        ), patch.object(
            extract_module, "collect_all_hrefs", side_effect=fake_collect_all_hrefs
        ), patch.object(
            extract_module, "try_scroll_page", return_value=True
        ), redirect_stdout(io.StringIO()):
            hrefs, page_name = extract_module.load_all_posts(driver, "arthaslav", 2, existing_post_hrefs={"skip"})

        self.assertEqual(hrefs, ["https://www.instagram.com/p/1", "https://www.instagram.com/p/2"])
        self.assertEqual(page_name, "Artha Slav")

    def test_extract_data(self):
        fake_driver = FakeDriver()

        with patch.object(extract_module, "delete_previos_files"), patch.object(
            extract_module, "setup_driver", return_value=fake_driver
        ), patch.object(
            extract_module, "human_pause"
        ), patch.object(
            extract_module, "wait_for_document_ready"
        ), patch.object(
            extract_module, "load_cookies", return_value=False
        ), patch.object(
            extract_module, "wait_for_manual_instagram_login", return_value=(True, None)
        ), patch.object(
            extract_module, "save_cookies"
        ), patch.object(
            extract_module, "load_all_posts", return_value=(["https://www.instagram.com/p/1"], "Artha Slav")
        ), patch.object(
            extract_module,
            "save_comments",
            return_value={"output_path": "unprocessed_data/comments1/arthaslav_1.csv", "comments_collected": 4},
        ), redirect_stdout(io.StringIO()):
            result = extract_module.extract_data(
                "alice",
                "secret",
                "arthaslav",
                1,
                existing_post_hrefs={"https://www.instagram.com/p/existing"},
                app_username="app-alice",
            )

        self.assertEqual(result["target_page"], "arthaslav")
        self.assertEqual(result["posts_requested"], 1)
        self.assertEqual(result["new_posts_found"], 1)
        self.assertEqual(result["posts_loaded"], 1)
        self.assertEqual(result["comments_collected"], 4)
        self.assertEqual(result["saved_files"], ["unprocessed_data/comments1/arthaslav_1.csv"])
        self.assertTrue(fake_driver.refreshed)
        self.assertTrue(fake_driver.quit_called)

    def test_extract_data_aborts_when_instagram_flags_automation(self):
        fake_driver = FakeDriver()
        fake_driver.page_source = "automated actions"

        with patch.object(extract_module, "delete_previos_files"), patch.object(
            extract_module, "setup_driver", return_value=fake_driver
        ), patch.object(
            extract_module, "human_pause"
        ), patch.object(
            extract_module, "wait_for_document_ready"
        ), redirect_stdout(io.StringIO()):
            result = extract_module.extract_data(
                "alice",
                "secret",
                "arthaslav",
                1,
                app_username="app-alice",
            )

        self.assertEqual(result["posts_loaded"], 0)
        self.assertIn("suspected automation", result["aborted_reason"])
        self.assertTrue(fake_driver.quit_called)

    def test_extract_data_aborts_headless_session_only_when_cookies_missing(self):
        fake_driver = FakeDriver()

        with patch.object(extract_module, "delete_previos_files"), patch.object(
            extract_module, "setup_driver", return_value=fake_driver
        ), patch.object(
            extract_module, "human_pause"
        ), patch.object(
            extract_module, "wait_for_document_ready"
        ), patch.object(
            extract_module, "load_cookies", return_value=False
        ), redirect_stdout(io.StringIO()):
            result = extract_module.extract_data(
                "alice",
                "secret",
                "arthaslav",
                1,
                app_username="app-alice",
                headless_session_only=True,
            )

        self.assertIn("Headless extraction requires a valid stored Instagram session", result["aborted_reason"])
        self.assertTrue(fake_driver.quit_called)


if __name__ == "__main__":
    unittest.main()
