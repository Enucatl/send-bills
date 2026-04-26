import importlib
import sys

import pytest
from django.core.exceptions import ImproperlyConfigured


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


def test_production_requires_database_url(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-secret")
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "example.com")
    monkeypatch.setenv("CSRF_TRUSTED_ORIGINS", "https://example.com")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    sys.modules.pop("send_bills.project.settings.production", None)

    with pytest.raises(ImproperlyConfigured):
        importlib.import_module("send_bills.project.settings.production")
