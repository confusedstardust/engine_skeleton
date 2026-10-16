"""Shared database infrastructure, independent of assets, credits and HTTP routes."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator, Protocol

ConnectionFactory = Callable[[], Any]


class DatabaseConfig(Protocol):
    def connect_kwargs(self) -> dict[str, object]: ...


class DatabaseDependencyError(RuntimeError):
    pass


def mysql_connection_factory(
    config: DatabaseConfig,
    *,
    dependency_error: type[RuntimeError] = DatabaseDependencyError,
) -> ConnectionFactory:
    def connect():
        try:
            import pymysql
            from pymysql.cursors import DictCursor
        except ImportError as exc:  # pragma: no cover - installation problem
            raise dependency_error("PyMySQL is required; install project requirements") from exc
        return pymysql.connect(cursorclass=DictCursor, **config.connect_kwargs())
    return connect


class Database:
    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        connection = self._connection_factory()
        failure: BaseException | None = None
        try:
            connection.begin()
            with connection.cursor() as cursor:
                yield cursor
            connection.commit()
        except BaseException as exc:
            failure = exc
            try:
                connection.rollback()
            except Exception as rollback_error:
                exc.add_note(f"Database rollback also failed ({type(rollback_error).__name__})")
            raise
        finally:
            try:
                connection.close()
            except Exception as close_error:
                if failure is None:
                    raise
                failure.add_note(f"Database close also failed ({type(close_error).__name__})")
