import logging
import unittest

from flask_jwt_extended import create_access_token, create_refresh_token

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

    def set_access_cookie(self, identity="alice"):
        with self.app.app_context():
            token = create_access_token(identity=identity)
        self.client.set_cookie("access_token_cookie", token, path="/")

    def set_refresh_cookie(self, identity="alice"):
        with self.app.app_context():
            token = create_refresh_token(identity=identity)
        self.client.set_cookie("refresh_token_cookie", token, path="/refresh")
