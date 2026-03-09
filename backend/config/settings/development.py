from __future__ import annotations

import os

from .base import *  # noqa: F401, F403
from .base import BASE_DIR

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-agrotrain-local-dev")  # type: ignore[assignment]

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:8080",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8080",
]
CORS_ALLOWED_ORIGIN_REGEXES = [r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"]
