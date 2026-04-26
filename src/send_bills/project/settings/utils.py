from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote


def read_env_or_file(name: str, default: str | None = None) -> str | None:
    file_name = os.environ.get(f"{name}_FILE")
    if file_name:
        return Path(file_name).read_text(encoding="utf-8").rstrip("\r\n")
    return os.environ.get(name, default)


def build_database_url() -> str | None:
    direct_url = read_env_or_file("DATABASE_URL")
    if direct_url:
        return direct_url

    database_name = os.environ.get("DATABASE_NAME")
    database_user = os.environ.get("DATABASE_USER")
    database_host = os.environ.get("DATABASE_HOST")
    if not database_name or not database_user or not database_host:
        return None

    database_port = os.environ.get("DATABASE_PORT", "5432")
    database_password = read_env_or_file("DATABASE_PASSWORD")

    auth = quote(database_user)
    if database_password is not None:
        auth = f"{auth}:{quote(database_password)}"

    return f"postgres://{auth}@{database_host}:{database_port}/{database_name}"
