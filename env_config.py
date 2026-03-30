import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


def load_dotenv(dotenv_path=None, override=False):
    path = Path(dotenv_path) if dotenv_path else PROJECT_ROOT / ".env"
    if not path.exists():
        return False

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        if override or key not in os.environ:
            os.environ[key] = value

    return True


def get_bool_env(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def get_app_environment():
    raw_value = os.environ.get("APP_ENV") or os.environ.get("FLASK_ENV") or "development"
    normalized = raw_value.strip().lower()
    aliases = {
        "prod": "production",
        "development": "development",
        "dev": "development",
        "local": "development",
        "staging": "staging",
        "test": "test",
        "testing": "test",
        "production": "production",
    }
    return aliases.get(normalized, normalized or "development")


def get_cookie_samesite(default="Lax"):
    value = os.environ.get("JWT_COOKIE_SAMESITE")
    if value is None:
        return default

    normalized = value.strip().lower()
    options = {
        "strict": "Strict",
        "lax": "Lax",
        "none": "None",
    }
    return options.get(normalized, default)


def get_int_env(name, default):
    value = os.environ.get(name)
    if value is None:
        return default

    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return default


def get_list_env(name, default=None):
    value = os.environ.get(name)
    if value is None:
        return list(default or [])

    items = [item.strip() for item in value.split(",")]
    return [item for item in items if item]
