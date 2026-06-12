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

# Despliegue de desarrollo (no produccion): el frontend se sirve desde la IP
# publica de la VM, asi que permitimos cualquier origen. NO usar en produccion.
CORS_ALLOW_ALL_ORIGINS = True
