from selenium.common.exceptions import NoSuchElementException, TimeoutException


class FakeElement:
    def __init__(self, text="", displayed=True, attributes=None, nested=None, click_error=None):
        self.text = text
        self._displayed = displayed
        self.attributes = attributes or {}
        self.nested = nested or {}
        self.click_error = click_error
        self.clicked = False
        self.cleared = False
        self.sent_keys = []

    def is_displayed(self):
        if isinstance(self._displayed, Exception):
            raise self._displayed
        return self._displayed

    def click(self):
        if self.click_error:
            raise self.click_error
        self.clicked = True

    def clear(self):
        self.cleared = True

    def send_keys(self, value):
        self.sent_keys.append(value)

    def find_element(self, by=None, value=None):
        key = (by, value)
        if key in self.nested:
            nested_value = self.nested[key]
            if isinstance(nested_value, Exception):
                raise nested_value
            return nested_value
        raise NoSuchElementException(f"Missing nested element for {key}")

    def find_elements(self, by=None, value=None):
        return list(self.nested.get((by, value), []))

    def get_attribute(self, name):
        return self.attributes.get(name)


class FakeDriver:
    def __init__(self):
        self.current_url = "https://www.instagram.com/"
        self.title = "Instagram"
        self.find_map = {}
        self.executed_scripts = []
        self.cookies_added = []
        self.got_urls = []
        self.refreshed = False
        self.quit_called = False

    def execute_script(self, script, *args):
        self.executed_scripts.append((script, args))
        if "return document.readyState" in script:
            return "complete"
        if "clientHeight" in script and "offsetHeight" in script:
            return 660
        if "return arguments[0].scrollHeight" in script:
            if args and hasattr(args[0], "scroll_heights") and args[0].scroll_heights:
                return args[0].scroll_heights.pop(0)
            return getattr(args[0], "scroll_height", 0) if args else 0
        if "return arguments[0].clientHeight;" in script:
            return getattr(args[0], "client_height", 0) if args else 0
        return None

    def execute_cdp_cmd(self, command, payload):
        self.cdp_command = (command, payload)

    def find_elements(self, by=None, value=None):
        return list(self.find_map.get((by, value), []))

    def find_element(self, by=None, value=None):
        elements = self.find_map.get((by, value), [])
        if not elements:
            raise NoSuchElementException(f"Missing element for {(by, value)}")
        return elements[0]

    def add_cookie(self, cookie):
        self.cookies_added.append(cookie)

    def get_cookies(self):
        return [{"name": "sessionid", "value": "abc"}]

    def get(self, url):
        self.current_url = url
        self.got_urls.append(url)

    def refresh(self):
        self.refreshed = True

    def quit(self):
        self.quit_called = True


class FakeWebDriverWait:
    def __init__(self, driver, timeout):
        self.driver = driver
        self.timeout = timeout

    def until(self, condition):
        result = condition(self.driver)
        if not result:
            raise TimeoutException("timed out")
        return result
