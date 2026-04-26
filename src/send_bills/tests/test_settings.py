import importlib
import sys

import pytest
from django.core.exceptions import ImproperlyConfigured

from send_bills.project.settings.utils import read_env_or_file


def test_read_env_or_file_prefers_secret_file(tmp_path, monkeypatch):
    secret_file = tmp_path / "secret"
    secret_file.write_text("file-value\n", encoding="utf-8")
    monkeypatch.setenv("EXAMPLE_SECRET_FILE", str(secret_file))
    monkeypatch.setenv("EXAMPLE_SECRET", "env-value")

    assert read_env_or_file("EXAMPLE_SECRET") == "file-value"


def test_read_env_or_file_falls_back_to_env(monkeypatch):
    monkeypatch.delenv("EXAMPLE_SECRET_FILE", raising=False)
    monkeypatch.setenv("EXAMPLE_SECRET", "env-value")

    assert read_env_or_file("EXAMPLE_SECRET") == "env-value"


def test_email_use_tls_parser(monkeypatch):
    monkeypatch.setenv("DJANGO_EMAIL_USE_TLS", "False")
    from send_bills.project.settings import base

    importlib.reload(base)
    assert base.EMAIL_USE_TLS is False

    monkeypatch.setenv("DJANGO_EMAIL_USE_TLS", "true")
    importlib.reload(base)
    assert base.EMAIL_USE_TLS is True


def test_email_port_uses_django_email_port(monkeypatch):
    monkeypatch.setenv("DJANGO_EMAIL_PORT", "2525")
    from send_bills.project.settings import base

    importlib.reload(base)
    assert base.EMAIL_PORT == 2525


def test_base_builds_database_url_from_parts(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_NAME", "tmp.sqlite3")
    monkeypatch.setenv("DATABASE_USER", "sqlite")
    monkeypatch.setenv("DATABASE_HOST", "localhost")
    monkeypatch.setenv("DATABASE_PASSWORD_FILE", str(tmp_path / "password"))
    (tmp_path / "password").write_text("secret\n", encoding="utf-8")
    from send_bills.project.settings import base

    importlib.reload(base)
    assert base.DATABASES["default"]["NAME"] == "tmp.sqlite3"
    assert base.DATABASES["default"]["PASSWORD"] == "secret"


def test_production_requires_database_configuration(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-secret")
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "example.com")
    monkeypatch.setenv("CSRF_TRUSTED_ORIGINS", "https://example.com")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    sys.modules.pop("send_bills.project.settings.production", None)

    with pytest.raises(ImproperlyConfigured):
        importlib.import_module("send_bills.project.settings.production")


def test_production_reads_secret_files(monkeypatch, tmp_path):
    secret_key = tmp_path / "django_secret_key"
    database_password = tmp_path / "database_password"
    secret_key.write_text("file-secret\n", encoding="utf-8")
    database_password.write_text("file-password\n", encoding="utf-8")

    monkeypatch.setenv("DJANGO_SECRET_KEY_FILE", str(secret_key))
    monkeypatch.setenv("DATABASE_HOST", "db")
    monkeypatch.setenv("DATABASE_NAME", "bills")
    monkeypatch.setenv("DATABASE_USER", "bills")
    monkeypatch.setenv("DATABASE_PASSWORD_FILE", str(database_password))
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "example.com")
    monkeypatch.setenv("CSRF_TRUSTED_ORIGINS", "https://example.com")
    sys.modules.pop("send_bills.project.settings.production", None)

    production = importlib.import_module("send_bills.project.settings.production")

    assert production.SECRET_KEY == "file-secret"
    assert production.DATABASES["default"]["PASSWORD"] == "file-password"
