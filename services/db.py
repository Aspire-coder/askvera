"""PostgreSQL connection and schema setup for ASK Vera."""

import json
from typing import Any
from urllib.parse import quote_plus

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from services.aws_clients import get_aws_clients
from utils.exceptions import AwsServiceError
from utils.logging import get_logger

LOGGER = get_logger("services.db")
_engine: Engine | None = None


def _read_rds_secret(correlation_id: str) -> dict[str, Any]:
    """Fetch RDS credentials from AWS Secrets Manager using the instance role."""
    try:
        response = get_aws_clients().secretsmanager.get_secret_value(SecretId=settings.RDS_SECRET_ARN)
    except (BotoCoreError, ClientError) as exc:
        LOGGER.exception("rds_secret_read_failed", correlation_id=correlation_id)
        raise AwsServiceError("RDS secret could not be read from Secrets Manager.") from exc
    return json.loads(response["SecretString"])


def _build_database_url(secret: dict[str, Any]) -> str:
    """Build a SQLAlchemy PostgreSQL URL from an AWS RDS secret payload."""
    username = quote_plus(str(secret["username"]))
    password = quote_plus(str(secret["password"]))
    host = secret["host"]
    port = secret.get("port", 5432)
    database = secret.get("dbname") or secret.get("database") or "postgres"
    return f"postgresql+psycopg://{username}:{password}@{host}:{port}/{database}"


def init_db(correlation_id: str = "startup") -> Engine:
    """Initialise the PostgreSQL engine and create required tables."""
    global _engine
    secret = _read_rds_secret(correlation_id)
    _engine = create_engine(
        _build_database_url(secret),
        pool_size=settings.POSTGRES_POOL_SIZE,
        max_overflow=settings.POSTGRES_MAX_OVERFLOW,
        pool_pre_ping=True,
        connect_args={"connect_timeout": settings.POSTGRES_CONNECT_TIMEOUT_SECONDS},
    )
    create_schema(correlation_id)
    LOGGER.info("postgres_initialized", correlation_id=correlation_id, db_identifier=settings.RDS_DB_IDENTIFIER)
    return _engine


def get_engine() -> Engine:
    """Return the initialised PostgreSQL engine."""
    if _engine is None:
        return init_db()
    return _engine


def create_schema(correlation_id: str = "startup") -> None:
    """Create session and consent tables if they do not exist."""
    try:
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS chat_sessions (
                        session_id TEXT PRIMARY KEY,
                        messages JSONB NOT NULL DEFAULT '[]'::jsonb,
                        expires_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS consent_log (
                        id BIGSERIAL PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        country TEXT NOT NULL,
                        lang TEXT NOT NULL,
                        accepted_at TIMESTAMPTZ NOT NULL,
                        version TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
    except SQLAlchemyError as exc:
        LOGGER.exception("postgres_schema_failed", correlation_id=correlation_id)
        raise AwsServiceError("PostgreSQL schema setup failed.") from exc


def close_db(correlation_id: str = "shutdown") -> None:
    """Dispose PostgreSQL connections during graceful shutdown."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None
        LOGGER.info("postgres_closed", correlation_id=correlation_id)
