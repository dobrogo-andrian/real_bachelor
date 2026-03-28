import logging
import unittest

from flask_jwt_extended import create_access_token, create_refresh_token, get_csrf_token

from tests.support.app_test_loader import load_app_module


app_module = load_app_module()


class AppTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app_module.app
        cls.app.config["TESTING"] = True
        app_module.logger.setLevel(logging.ERROR)

    def setUp(self):
        self.client = self.app.test_client()
        self.access_csrf_token = None
        self.refresh_csrf_token = None

    def set_access_cookie(self, identity="alice"):
        with self.app.app_context():
            token = create_access_token(identity=identity)
            self.access_csrf_token = get_csrf_token(token)
        self.client.set_cookie("access_token_cookie", token, path="/")
        self.client.set_cookie("csrf_access_token", self.access_csrf_token, path="/")
        return self.access_csrf_token

    def set_refresh_cookie(self, identity="alice"):
        with self.app.app_context():
            token = create_refresh_token(identity=identity)
            self.refresh_csrf_token = get_csrf_token(token)
        self.client.set_cookie("refresh_token_cookie", token, path="/refresh")
        self.client.set_cookie("csrf_refresh_token", self.refresh_csrf_token, path="/refresh")
        return self.refresh_csrf_token

    def make_json_headers(self, csrf=None):
        headers = {"Accept": "application/json"}
        if csrf == "access" and self.access_csrf_token:
            headers["X-CSRF-TOKEN"] = self.access_csrf_token
        if csrf == "refresh" and self.refresh_csrf_token:
            headers["X-CSRF-TOKEN"] = self.refresh_csrf_token
        return headers
