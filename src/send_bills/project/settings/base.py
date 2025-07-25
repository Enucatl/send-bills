"""
Base Django settings for the send_bills project.

This file contains settings that are common to all environments.
Environment-specific settings are defined in separate files (e.g., development.py, production.py).
"""

import os
from pathlib import Path

import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# Note: We go up two levels now: from base.py -> settings -> project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# --- CORE DJANGO SETTINGS ---

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "send_bills.bills.apps.BillsConfig",
    "send_bills.api.apps.ApiConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "send_bills.project.middleware.CustomHeaderRemoteUserMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "send_bills.project.backends.CustomRemoteUserBackend",
]

REST_FRAMEWORK = {
    # Use TokenAuthentication for scripts/services and SessionAuthentication
    # for calls from a logged-in browser session.
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    # By default, require all API endpoints to be authenticated.
    "DEFAULT_PERMISSION_CLASSES": [
        # "rest_framework.permissions.IsAuthenticated",
        "rest_framework.permissions.AllowAny",
    ],
}

ROOT_URLCONF = "send_bills.project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "send_bills.project.wsgi.application"

# --- DATABASE CONFIGURATION ---
# Use DATABASE_URL from environment
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL is not None:
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=600)}

# --- INTERNATIONALIZATION ---

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Zurich"
USE_I18N = False
USE_TZ = True

# --- DEFAULT PRIMARY KEY ---

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Define where Django will collect static files in production
STATIC_ROOT = os.environ.get("DJANGO_STATIC_ROOT", "/vol/web/staticfiles")

# --- STATIC FILES ---
STATIC_URL = "static/"

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Configure email
EMAIL_BACKEND = "send_bills.project.email.EmailBackend"
EMAIL_HOST = os.environ.get("DJANGO_EMAIL_HOST")
EMAIL_PORT = int(os.environ.get("DJANGO_EMAIL_PORT", "10125"))
EMAIL_HOST_USER = os.environ.get("DJANGO_EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.environ.get("DJANGO_EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = bool(os.environ.get("DJANGO_EMAIL_USE_TLS", "True"))
EMAIL_TIMEOUT = int(os.environ.get("DJANGO_EMAIL_TIMEOUT", "60"))
EMAIL_SSL_KEYFILE = os.environ.get("DJANGO_EMAIL_SSL_KEYFILE")
EMAIL_SSL_CERTFILE = os.environ.get("DJANGO_EMAIL_SSL_CERTFILE")
EMAIL_CAFILE = os.environ.get("DJANGO_EMAIL_CAFILE")
