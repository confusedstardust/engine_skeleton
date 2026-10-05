from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

from .errors import CreditConfigurationError


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise CreditConfigurationError(f"Missing required environment variable: {name}")
    return value


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise CreditConfigurationError(f"{name} must be true or false")


@dataclass(frozen=True)
class CreditDatabaseConfig:
    """MySQL connection settings; the password is excluded from repr output."""

    host: str
    port: int
    user: str
    password: str = field(repr=False)
    database: str
    connect_timeout: int = 5
    read_timeout: int = 10
    write_timeout: int = 10
    ssl_ca: str | None = None
    ssl_verify_cert: bool = True

    @classmethod
    def from_env(cls) -> "CreditDatabaseConfig":
        database_url = os.getenv("NARRATIVEOS_DATABASE_URL", "").strip()
        if database_url:
            return cls.from_url(database_url)
        try:
            port = int(os.getenv("CREDIT_DB_PORT", "3306"))
            connect_timeout = int(os.getenv("CREDIT_DB_CONNECT_TIMEOUT", "5"))
        except ValueError as exc:
            raise CreditConfigurationError("Credit database port/timeouts must be integers") from exc
        ssl_ca = os.getenv("CREDIT_DB_SSL_CA", "").strip() or None
        return cls(
            host=_required("CREDIT_DB_HOST"),
            port=port,
            user=_required("CREDIT_DB_USER"),
            password=_required("CREDIT_DB_PASSWORD"),
            database=_required("CREDIT_DB_NAME"),
            connect_timeout=connect_timeout,
            ssl_ca=ssl_ca,
            ssl_verify_cert=_bool_env("CREDIT_DB_SSL_VERIFY_CERT", True),
        )

    @classmethod
    def from_url(cls, database_url: str) -> "CreditDatabaseConfig":
        """Parse a MySQL URL without retaining or displaying the original secret."""
        try:
            parsed = urlsplit(database_url)
            port = parsed.port or 3306
            connect_timeout = int(os.getenv("CREDIT_DB_CONNECT_TIMEOUT", "5"))
        except ValueError as exc:
            raise CreditConfigurationError("Invalid NARRATIVEOS_DATABASE_URL") from exc
        if parsed.scheme not in {"mysql", "mysql+pymysql"}:
            raise CreditConfigurationError(
                "NARRATIVEOS_DATABASE_URL must use mysql:// or mysql+pymysql://"
            )
        database = unquote(parsed.path.lstrip("/"))
        if not parsed.hostname or parsed.username is None or parsed.password is None or not database:
            raise CreditConfigurationError(
                "NARRATIVEOS_DATABASE_URL must include host, user, password, and database"
            )
        if "/" in database:
            raise CreditConfigurationError("NARRATIVEOS_DATABASE_URL contains an invalid database name")
        ssl_ca = os.getenv("CREDIT_DB_SSL_CA", "").strip() or None
        return cls(
            host=parsed.hostname,
            port=port,
            user=unquote(parsed.username),
            password=unquote(parsed.password),
            database=database,
            connect_timeout=connect_timeout,
            ssl_ca=ssl_ca,
            ssl_verify_cert=_bool_env("CREDIT_DB_SSL_VERIFY_CERT", True),
        )

    def connect_kwargs(self) -> dict[str, object]:
        kwargs: dict[str, object] = {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "database": self.database,
            "charset": "utf8mb4",
            "autocommit": False,
            "connect_timeout": self.connect_timeout,
            "read_timeout": self.read_timeout,
            "write_timeout": self.write_timeout,
        }
        if self.ssl_ca:
            kwargs["ssl"] = {
                "ca": self.ssl_ca,
                "check_hostname": self.ssl_verify_cert,
            }
        return kwargs
