from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator
from urllib.parse import parse_qs, unquote, urlsplit

from .config import settings


class DatabaseUnavailable(RuntimeError):
    pass


def _pymysql():
    try:
        import pymysql
    except ImportError as exc:
        raise DatabaseUnavailable("database access requires PyMySQL; install project requirements") from exc
    return pymysql


def connect_kwargs(database_url: str) -> dict[str, Any]:
    parsed = urlsplit(database_url)
    if parsed.scheme not in {"mysql", "mysql+pymysql"}:
        raise DatabaseUnavailable("NARRATIVEOS_DATABASE_URL must use mysql:// or mysql+pymysql://")
    database = parsed.path.lstrip("/")
    if not parsed.hostname or not database:
        raise DatabaseUnavailable("NARRATIVEOS_DATABASE_URL must include host and database")
    query = parse_qs(parsed.query)
    return {
        "host": parsed.hostname,
        "port": parsed.port or 3306,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "database": unquote(database),
        "charset": query.get("charset", ["utf8mb4"])[0],
        "autocommit": False,
        "cursorclass": _pymysql().cursors.DictCursor,
        "connect_timeout": 5,
        "read_timeout": 15,
        "write_timeout": 15,
    }


@contextmanager
def database_connection() -> Iterator[Any]:
    if not settings.database_url:
        raise DatabaseUnavailable("NARRATIVEOS_DATABASE_URL is not configured")
    connection = _pymysql().connect(**connect_kwargs(settings.database_url))
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET time_zone = '+00:00'")
        yield connection
    finally:
        connection.close()
