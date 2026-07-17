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
    host = secret.get("host") or settings.RDS_HOST
    port = secret.get("port") or settings.RDS_PORT
    database = secret.get("dbname") or secret.get("database") or settings.RDS_DB_NAME
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
        connect_args={
            "connect_timeout": settings.POSTGRES_CONNECT_TIMEOUT_SECONDS,
            "sslmode": "require",
        },
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
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        expires_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        consent_accepted BOOLEAN NOT NULL DEFAULT false,
                        consent_legal_version TEXT,
                        consent_accepted_at TIMESTAMPTZ,
                        ended_at TIMESTAMPTZ,
                        end_reason TEXT
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS chat_analytics (
                        correlation_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        country TEXT NOT NULL,
                        language TEXT NOT NULL,
                        question TEXT NOT NULL,
                        answer TEXT NOT NULL,
                        topic TEXT NOT NULL DEFAULT 'General assistance',
                        confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
                        source_count INTEGER NOT NULL DEFAULT 0,
                        input_tokens INTEGER NOT NULL DEFAULT 0,
                        output_tokens INTEGER NOT NULL DEFAULT 0,
                        fallback BOOLEAN NOT NULL DEFAULT false,
                        failure_layer TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS idx_chat_analytics_filters
                    ON chat_analytics (created_at DESC, country, language)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS feedback_events (
                        event_id TEXT PRIMARY KEY,
                        correlation_id TEXT NOT NULL DEFAULT '',
                        session_id TEXT NOT NULL,
                        message_id TEXT NOT NULL,
                        rating INTEGER NOT NULL,
                        comment TEXT NOT NULL DEFAULT '',
                        request_type TEXT NOT NULL DEFAULT 'feedback',
                        country TEXT NOT NULL DEFAULT '',
                        language TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS idx_feedback_events_correlation
                    ON feedback_events (correlation_id, created_at DESC)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS ingestion_jobs (
                        job_id TEXT PRIMARY KEY,
                        filename TEXT NOT NULL,
                        country TEXT NOT NULL,
                        language TEXT NOT NULL,
                        document_type TEXT NOT NULL,
                        access_scope TEXT NOT NULL DEFAULT 'country',
                        document_version TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'queued',
                        progress INTEGER NOT NULL DEFAULT 0,
                        section_count INTEGER NOT NULL DEFAULT 0,
                        source_uri TEXT NOT NULL DEFAULT '',
                        error_message TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS knowledge_documents (
                        document_id TEXT PRIMARY KEY,
                        filename TEXT NOT NULL,
                        source_uri TEXT NOT NULL DEFAULT '',
                        country TEXT NOT NULL,
                        language TEXT NOT NULL,
                        document_type TEXT NOT NULL,
                        access_scope TEXT NOT NULL DEFAULT 'country',
                        document_version TEXT NOT NULL DEFAULT '',
                        section_count INTEGER NOT NULL DEFAULT 0,
                        content_hash TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()"))
            connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now()"))
            connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS consent_accepted BOOLEAN NOT NULL DEFAULT false"))
            connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS consent_legal_version TEXT"))
            connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS consent_accepted_at TIMESTAMPTZ"))
            connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ"))
            connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS end_reason TEXT"))
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
                        accepted BOOLEAN NOT NULL DEFAULT true,
                        correlation_id TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            connection.execute(text("ALTER TABLE consent_log ADD COLUMN IF NOT EXISTS accepted BOOLEAN NOT NULL DEFAULT true"))
            connection.execute(text("ALTER TABLE consent_log ADD COLUMN IF NOT EXISTS correlation_id TEXT"))
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS policy_sections (
                        id TEXT PRIMARY KEY,
                        source_file TEXT NOT NULL,
                        source_uri TEXT NOT NULL DEFAULT '',
                        country TEXT NOT NULL,
                        language TEXT NOT NULL,
                        document_type TEXT NOT NULL DEFAULT 'policy',
                        section_id TEXT NOT NULL,
                        section_title TEXT NOT NULL,
                        start_page INTEGER,
                        end_page INTEGER,
                        content TEXT NOT NULL,
                        search_text TEXT NOT NULL,
                        embedding JSONB,
                        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                        content_hash TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            connection.execute(text("ALTER TABLE policy_sections ADD COLUMN IF NOT EXISTS source_uri TEXT NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE policy_sections ADD COLUMN IF NOT EXISTS document_type TEXT NOT NULL DEFAULT 'policy'"))
            connection.execute(text("ALTER TABLE policy_sections ADD COLUMN IF NOT EXISTS search_text TEXT NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE policy_sections ADD COLUMN IF NOT EXISTS embedding JSONB"))
            connection.execute(text("ALTER TABLE policy_sections ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb"))
            connection.execute(text("ALTER TABLE policy_sections ADD COLUMN IF NOT EXISTS content_hash TEXT NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE policy_sections ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"))
            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS idx_policy_sections_market
                    ON policy_sections (country, language, document_type)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS idx_policy_sections_section
                    ON policy_sections (country, language, section_id)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS idx_policy_sections_search
                    ON policy_sections
                    USING GIN (to_tsvector('english', search_text))
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
