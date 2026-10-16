from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from forge_database import Database, mysql_connection_factory
from credit_system.config import CreditDatabaseConfig
from credit_system.store import MySQLCreditStore
from webgal_backend.asset_library import AssetLibrary


class Connection:
    def __init__(self, fail=None):
        self.events = []
        self.fail = fail or set()
        self.value = object()

    def event(self, name):
        self.events.append(name)
        if name in self.fail:
            raise RuntimeError(name)

    def begin(self): self.event("begin")
    def commit(self): self.event("commit")
    def rollback(self): self.event("rollback")
    def close(self): self.event("close")

    @contextmanager
    def cursor(self):
        self.event("cursor")
        try:
            yield self.value
        finally:
            self.event("cursor_close")


def test_success_commits_after_cursor_cleanup_then_closes():
    connection = Connection()
    with Database(lambda: connection).transaction() as cursor:
        assert cursor is connection.value
        connection.event("work")
    assert connection.events == ["begin", "cursor", "work", "cursor_close", "commit", "close"]


@pytest.mark.parametrize("stage", ["begin", "cursor", "cursor_close", "commit"])
def test_failures_roll_back_and_close(stage):
    connection = Connection({stage})
    with pytest.raises(RuntimeError, match=stage):
        with Database(lambda: connection).transaction():
            pass
    assert "commit" not in connection.events or stage == "commit"
    assert connection.events[-2:] == ["rollback", "close"]


@pytest.mark.parametrize("error", [ValueError("business"), KeyboardInterrupt()])
def test_aborted_business_work_is_rolled_back(error):
    connection = Connection()
    with pytest.raises(type(error)) as caught:
        with Database(lambda: connection).transaction():
            raise error
    assert caught.value is error
    assert "commit" not in connection.events
    assert connection.events[-2:] == ["rollback", "close"]


def test_cleanup_failures_do_not_hide_the_original_business_error():
    connection = Connection({"rollback", "close"})
    error = ValueError("business")
    with pytest.raises(ValueError) as caught:
        with Database(lambda: connection).transaction():
            raise error
    assert caught.value is error
    assert len(error.__notes__) == 2
    assert connection.events[-2:] == ["rollback", "close"]


def test_connection_failures_do_not_enter_a_transaction():
    def fail(): raise OSError("connect")
    with pytest.raises(OSError, match="connect"):
        with Database(fail).transaction():
            pytest.fail("Connection creation failed")


def test_mysql_factory_preserves_database_settings_without_eager_connection(monkeypatch):
    import pymysql
    from pymysql.cursors import DictCursor
    calls = []
    connection = object()
    monkeypatch.setattr(pymysql, "connect", lambda **kwargs: calls.append(kwargs) or connection)
    config = CreditDatabaseConfig(host="localhost", port=3306, user="test", password="test-only", database="isolated")
    connect = mysql_connection_factory(config)
    assert calls == []
    assert connect() is connection
    assert calls == [{"cursorclass": DictCursor, **config.connect_kwargs()}]
    assert calls[0]["autocommit"] is False
    assert calls[0]["init_command"] == "SET time_zone = '+00:00'"


def test_credit_store_and_asset_library_delegate_to_the_same_transaction_layer(monkeypatch):
    calls = []
    connection = Connection()
    original = Database.transaction
    def transaction(self):
        calls.append(self)
        return original(self)
    monkeypatch.setattr(Database, "transaction", transaction)
    store = MySQLCreditStore(lambda: connection)
    library = object.__new__(AssetLibrary)
    library._database = Database(lambda: connection)
    with store.transaction(): pass
    with store._transaction(): pass
    with library._transaction(): pass
    assert len(calls) == 3
    assert connection.events.count("commit") == 3


def test_http_database_entry_uses_existing_application_configuration(monkeypatch):
    from webgal_backend import database
    connection = Connection()
    config = SimpleNamespace(connect_kwargs=lambda: {})
    monkeypatch.setattr(database.CreditDatabaseConfig, "from_env", lambda: config)
    monkeypatch.setattr(database, "mysql_connection_factory", lambda value: (lambda: connection) if value is config else pytest.fail("Wrong config"))
    with database.database_transaction(): pass
    assert connection.events[-2:] == ["commit", "close"]
