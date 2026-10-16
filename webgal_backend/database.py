"""Application database entry point; transaction mechanics live in forge_database."""
from . import config as _application_config  # Initialize the existing .env/settings before standalone callers.
from credit_system.config import CreditDatabaseConfig
from forge_database import Database, mysql_connection_factory


def database_transaction():
    return Database(mysql_connection_factory(CreditDatabaseConfig.from_env())).transaction()
