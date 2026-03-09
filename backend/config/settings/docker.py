from __future__ import annotations

import os

from .base import *  # noqa: F401, F403

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-docker-dev")

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "backend", "*"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "agrotrain"),
        "USER": os.environ.get("POSTGRES_USER", "agrotrain"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "agrotrain_dev"),
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

CORS_ALLOWED_ORIGINS = [
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]
CORS_ALLOWED_ORIGIN_REGEXES = [r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"]
