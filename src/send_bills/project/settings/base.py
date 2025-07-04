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
    "send_bills.bills.apps.BillsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "send_bills.project.middleware.CustomHeaderRemoteUserMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.RemoteUserBackend",
]

ROOT_URLCONF = "send_bills.project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

# --- STATIC FILES ---

STATIC_URL = "static/"

# --- DEFAULT PRIMARY KEY ---

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# get app version from environment
VERSION = os.environ.get("VERSION", "unknown")

# Define where Django will collect static files in production
STATIC_ROOT = os.environ.get("DJANGO_STATIC_ROOT", "/vol/web/staticfiles")
