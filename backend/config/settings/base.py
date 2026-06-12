from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

# Raiz del repositorio (dos niveles por encima de config/settings/)
ROOT_DIR = Path(__file__).resolve().parents[3]
BASE_DIR = Path(__file__).resolve().parents[2]

load_dotenv(ROOT_DIR / ".env")       # variables de frontend (VITE_*)
load_dotenv(BASE_DIR / ".env", override=True)  # variables de backend (prioridad)

# Ruta al modelo UVL — compartida entre entornos
UVL_MODEL_PATH = BASE_DIR / "agroTrain.uvl"
UVL_VERSIONS_PATH = BASE_DIR / "uvl_versions"

SECRET_KEY = NotImplemented  # cada entorno debe definir su propio SECRET_KEY

DEBUG = False

ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "drf_spectacular",
    "apps.accounts",
    "apps.configurador",
    "apps.geo",
    "apps.telemetria",
    "apps.modelos",
    "apps.common",
]

AUTH_USER_MODEL = "accounts.CustomUser"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

LANGUAGE_CODE = "es-es"
TIME_ZONE = "Europe/Madrid"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MODELS_STORAGE_PATH = BASE_DIR / "model_storage"

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_HEADERS = True
CORS_ALLOW_ALL_METHODS = True

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "EXCEPTION_HANDLER": "apps.configurador.exception_handlers.custom_exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "UPDATE_LAST_LOGIN": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "agroTrain Configurator API",
    "DESCRIPTION": "Backend Django + DRF para el configurador de sensores digitales.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
}
