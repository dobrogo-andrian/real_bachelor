import importlib
import logging
import os
import sys
import types
from contextlib import contextmanager
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _ensure_package(name, path):
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module
    return module


@contextmanager
def _temporary_backend_stubs():
    _ensure_package("static", PROJECT_ROOT / "static")
    _ensure_package("static.backend", PROJECT_ROOT / "static" / "backend")
    target_modules = [
        "static.backend.extract_data",
        "static.backend.load_to_db",
        "static.backend.enrich_comments",
        "static.backend.explorer_analysis",
        "static.backend.db_connection",
    ]
    original_modules = {name: sys.modules.get(name) for name in target_modules}

    extract_data_module = types.ModuleType("static.backend.extract_data")
    extract_data_module.extract_data = lambda *args, **kwargs: {}
    sys.modules["static.backend.extract_data"] = extract_data_module

    load_to_db_module = types.ModuleType("static.backend.load_to_db")
    load_to_db_module.load_to_db = lambda *args, **kwargs: {}
    sys.modules["static.backend.load_to_db"] = load_to_db_module

    enrich_comments_module = types.ModuleType("static.backend.enrich_comments")
    enrich_comments_module.enrich_comments = lambda *args, **kwargs: {}
    sys.modules["static.backend.enrich_comments"] = enrich_comments_module

    explorer_analysis_module = types.ModuleType("static.backend.explorer_analysis")
    explorer_analysis_module.build_page_analysis = lambda *args, **kwargs: {}
    explorer_analysis_module.build_analysis_from_rows = lambda *args, **kwargs: {}
    sys.modules["static.backend.explorer_analysis"] = explorer_analysis_module

    db_connection_module = types.ModuleType("static.backend.db_connection")
    db_connection_module.insert_new_user = lambda *args, **kwargs: None
    db_connection_module.fetch_user = lambda *args, **kwargs: None
    db_connection_module.fetch_user_profile = lambda *args, **kwargs: None
    db_connection_module.fetch_account_statistics = lambda *args, **kwargs: {}
    db_connection_module.update_user_password_hash = lambda *args, **kwargs: None
    db_connection_module.update_user_instagram_credentials = lambda *args, **kwargs: None
    db_connection_module.set_user_email_verified = lambda *args, **kwargs: None
    db_connection_module.fetch_user_instagram_credentials = lambda *args, **kwargs: None
    db_connection_module.fetch_user_instagram_cookies = lambda *args, **kwargs: None
    db_connection_module.store_user_instagram_cookies = lambda *args, **kwargs: None
    db_connection_module.clear_user_instagram_cookies = lambda *args, **kwargs: None
    db_connection_module.fetch_distinct_comment_dimensions = (
        lambda *args, **kwargs: {"page_names": [], "page_ids": []}
    )
    db_connection_module.fetch_existing_post_hrefs = lambda *args, **kwargs: []
    db_connection_module.fetch_advanced_comment_dimensions = (
        lambda *args, **kwargs: {
            "page_names": [],
            "page_ids": [],
            "sources": [],
            "languages": [],
            "sentiments": [],
            "ranges": {},
        }
    )
    db_connection_module.fetch_enriched_comment_preview = (
        lambda *args, **kwargs: {"rows": [], "total": 0}
    )
    db_connection_module.fetch_enriched_comment_rows = lambda *args, **kwargs: []
    sys.modules["static.backend.db_connection"] = db_connection_module
    try:
        yield
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def load_app_module():
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")

    previous_disable_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with _temporary_backend_stubs():
            if "app" in sys.modules:
                return importlib.reload(sys.modules["app"])
            return importlib.import_module("app")
    finally:
        logging.disable(previous_disable_level)
