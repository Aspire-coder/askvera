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
    """Initialise the PostgreSQL engine without mutating the schema."""
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
    if settings.DB_SCHEMA_BOOTSTRAP_ON_STARTUP:
        LOGGER.warning(
            "postgres_legacy_schema_bootstrap_enabled",
            correlation_id=correlation_id,
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
    """Compatibility bootstrap for a fresh local database.

    Production schema changes must use scripts/run_db_migrations.py.
    """
    try:
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS admin_users (
                        id TEXT PRIMARY KEY,
                        cognito_sub TEXT UNIQUE,
                        email TEXT NOT NULL UNIQUE,
                        role TEXT NOT NULL DEFAULT 'section_scoped',
                        status TEXT NOT NULL DEFAULT 'invited',
                        last_login TIMESTAMPTZ,
                        created_by TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            connection.execute(text("ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS access_review_due_at DATE"))
            connection.execute(text("ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS access_certified_at TIMESTAMPTZ"))
            connection.execute(text("ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS access_certified_by TEXT NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS invite_expires_at TIMESTAMPTZ"))
            connection.execute(text("ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS disabled_at TIMESTAMPTZ"))
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS admin_user_scopes (
                        user_id TEXT NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
                        market TEXT NOT NULL,
                        section TEXT NOT NULL,
                        permission TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        PRIMARY KEY (user_id, market, section, permission)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS admin_audit_log (
                        event_id TEXT PRIMARY KEY,
                        actor_sub TEXT NOT NULL,
                        action TEXT NOT NULL,
                        target_type TEXT NOT NULL,
                        target_id TEXT NOT NULL,
                        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS idx_admin_users_status
                    ON admin_users (status, role, updated_at DESC)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS widget_configs (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        customer TEXT NOT NULL DEFAULT '',
                        allowed_origins JSONB NOT NULL DEFAULT '[]'::jsonb,
                        markets JSONB NOT NULL DEFAULT '[]'::jsonb,
                        languages JSONB NOT NULL DEFAULT '[]'::jsonb,
                        default_market TEXT NOT NULL DEFAULT '',
                        default_language TEXT NOT NULL DEFAULT '',
                        display_name TEXT NOT NULL DEFAULT 'AskVera',
                        greeting TEXT NOT NULL DEFAULT '',
                        logo_url TEXT NOT NULL DEFAULT '',
                        accent_color TEXT NOT NULL DEFAULT '#2F7D4E',
                        position TEXT NOT NULL DEFAULT 'bottom-right',
                        legal_version TEXT NOT NULL DEFAULT '',
                        rate_limit_tier TEXT NOT NULL DEFAULT 'standard',
                        usage_cap INTEGER,
                        public_key TEXT NOT NULL UNIQUE,
                        key_version INTEGER NOT NULL DEFAULT 1,
                        status TEXT NOT NULL DEFAULT 'active',
                        created_by TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            connection.execute(text("ALTER TABLE widget_configs ADD COLUMN IF NOT EXISTS logo_url TEXT NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE widget_configs ADD COLUMN IF NOT EXISTS previous_public_key TEXT NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE widget_configs ADD COLUMN IF NOT EXISTS previous_key_expires_at TIMESTAMPTZ"))
            connection.execute(text("ALTER TABLE widget_configs ADD COLUMN IF NOT EXISTS draft_config JSONB"))
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS support_routes (
                        country TEXT PRIMARY KEY,
                        department TEXT NOT NULL,
                        email TEXT NOT NULL,
                        enabled BOOLEAN NOT NULL DEFAULT true,
                        updated_by TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            connection.execute(text("ALTER TABLE support_routes ADD COLUMN IF NOT EXISTS fallback_department TEXT NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE support_routes ADD COLUMN IF NOT EXISTS fallback_email TEXT NOT NULL DEFAULT ''"))
            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS idx_support_routes_enabled
                    ON support_routes (enabled, country)
                    """
                )
            )
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
                        traffic_source TEXT NOT NULL DEFAULT 'legacy',
                        model_route_mode TEXT NOT NULL DEFAULT '',
                        model_route_target TEXT NOT NULL DEFAULT '',
                        model_route_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
                        actual_model TEXT NOT NULL DEFAULT '',
                        generation_latency_ms INTEGER NOT NULL DEFAULT 0,
                        cache_hit BOOLEAN NOT NULL DEFAULT false,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    ALTER TABLE chat_analytics
                    ADD COLUMN IF NOT EXISTS traffic_source TEXT NOT NULL DEFAULT 'legacy'
                    """
                )
            )
            connection.execute(
                text(
                    """
                    ALTER TABLE chat_analytics
                    ALTER COLUMN traffic_source SET DEFAULT 'legacy'
                    """
                )
            )
            connection.execute(text("ALTER TABLE chat_analytics ADD COLUMN IF NOT EXISTS model_route_mode TEXT NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE chat_analytics ADD COLUMN IF NOT EXISTS model_route_target TEXT NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE chat_analytics ADD COLUMN IF NOT EXISTS model_route_reasons JSONB NOT NULL DEFAULT '[]'::jsonb"))
            connection.execute(text("ALTER TABLE chat_analytics ADD COLUMN IF NOT EXISTS actual_model TEXT NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE chat_analytics ADD COLUMN IF NOT EXISTS generation_latency_ms INTEGER NOT NULL DEFAULT 0"))
            connection.execute(text("ALTER TABLE chat_analytics ADD COLUMN IF NOT EXISTS cache_hit BOOLEAN NOT NULL DEFAULT false"))
            connection.execute(
                text(
                    """
                    UPDATE chat_analytics
                    SET traffic_source = 'legacy'
                    WHERE traffic_source = 'widget'
                      AND created_at < TIMESTAMPTZ '2026-07-22 21:46:00+00'
                    """
                )
            )
            connection.execute(
                text(
                    """
                    UPDATE chat_analytics
                    SET traffic_source = 'evaluation'
                    WHERE traffic_source <> 'evaluation' AND session_id LIKE 'csv-%'
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS idx_chat_analytics_source_filters
                    ON chat_analytics (created_at DESC, country, language, traffic_source)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS idx_chat_analytics_session_source
                    ON chat_analytics (session_id, traffic_source)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS answer_review_cases (
                        correlation_id TEXT PRIMARY KEY REFERENCES chat_analytics(correlation_id) ON DELETE CASCADE,
                        status TEXT NOT NULL DEFAULT 'open',
                        assignee_email TEXT NOT NULL DEFAULT '',
                        resolution_notes TEXT NOT NULL DEFAULT '',
                        updated_by TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        resolved_at TIMESTAMPTZ
                    )
                    """
                )
            )
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_answer_review_cases_queue ON answer_review_cases (status, assignee_email, updated_at DESC)"))
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS analytics_saved_views (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        owner_sub TEXT NOT NULL,
                        filters JSONB NOT NULL DEFAULT '{}'::jsonb,
                        schedule TEXT NOT NULL DEFAULT 'none',
                        report_email TEXT NOT NULL DEFAULT '',
                        alert_not_helpful_threshold DOUBLE PRECISION,
                        enabled BOOLEAN NOT NULL DEFAULT true,
                        last_sent_at TIMESTAMPTZ,
                        next_run_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
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
                        expected_answer TEXT,
                        expected_answer_present BOOLEAN NOT NULL DEFAULT false,
                        request_type TEXT NOT NULL DEFAULT 'feedback',
                        country TEXT NOT NULL DEFAULT '',
                        language TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            connection.execute(text("ALTER TABLE feedback_events ADD COLUMN IF NOT EXISTS expected_answer TEXT"))
            connection.execute(
                text(
                    """
                    ALTER TABLE feedback_events
                    ADD COLUMN IF NOT EXISTS expected_answer_present BOOLEAN NOT NULL DEFAULT false
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
                    CREATE TABLE IF NOT EXISTS support_requests (
                        ticket_id TEXT PRIMARY KEY,
                        correlation_id TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        message_id TEXT NOT NULL DEFAULT '',
                        country TEXT NOT NULL,
                        language TEXT NOT NULL,
                        route_name TEXT NOT NULL,
                        delivery_status TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS retrieval_shadow_comparisons (
                        correlation_id TEXT PRIMARY KEY,
                        country TEXT NOT NULL,
                        language TEXT NOT NULL,
                        primary_provider TEXT NOT NULL,
                        primary_index TEXT NOT NULL,
                        primary_pipeline_version TEXT NOT NULL,
                        primary_count INTEGER NOT NULL,
                        primary_confidence DOUBLE PRECISION NOT NULL,
                        primary_top_id TEXT NOT NULL DEFAULT '',
                        vnext_provider TEXT NOT NULL,
                        vnext_index TEXT NOT NULL,
                        vnext_pipeline_version TEXT NOT NULL,
                        vnext_count INTEGER NOT NULL,
                        vnext_confidence DOUBLE PRECISION NOT NULL,
                        vnext_top_id TEXT NOT NULL DEFAULT '',
                        top_result_matches BOOLEAN NOT NULL,
                        shared_result_count INTEGER NOT NULL,
                        result_overlap DOUBLE PRECISION NOT NULL,
                        duration_ms DOUBLE PRECISION NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS idx_retrieval_shadow_filters
                    ON retrieval_shadow_comparisons (created_at DESC, country, language)
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
                        upload_uri TEXT NOT NULL DEFAULT '',
                        content_hash TEXT NOT NULL DEFAULT '',
                        accepted_by TEXT NOT NULL DEFAULT '',
                        review_before_publish BOOLEAN NOT NULL DEFAULT false,
                        attempt_count INTEGER NOT NULL DEFAULT 0,
                        error_message TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            connection.execute(text("ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS upload_uri TEXT NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS content_hash TEXT NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS accepted_by TEXT NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS review_before_publish BOOLEAN NOT NULL DEFAULT false"))
            connection.execute(text("ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0"))
            connection.execute(text("ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS logical_document_id TEXT NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS document_owner TEXT NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS approval_reference TEXT NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS effective_date DATE"))
            connection.execute(text("ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS expiry_date DATE"))
            connection.execute(text("ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS malware_scan_status TEXT NOT NULL DEFAULT 'not_required'"))
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
                        accepted_by TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'active',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            connection.execute(text("ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS accepted_by TEXT NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS logical_document_id TEXT NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS document_owner TEXT NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS approval_reference TEXT NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS effective_date DATE"))
            connection.execute(text("ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS expiry_date DATE"))
            connection.execute(text("ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS malware_scan_status TEXT NOT NULL DEFAULT 'not_required'"))
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS market_readiness_governance (
                        country TEXT PRIMARY KEY,
                        owner_email TEXT NOT NULL DEFAULT '',
                        deadline DATE,
                        updated_by TEXT NOT NULL DEFAULT '',
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS knowledge_active_generations (
                        country TEXT NOT NULL,
                        language TEXT NOT NULL,
                        source_file TEXT NOT NULL,
                        document_type TEXT NOT NULL,
                        access_scope TEXT NOT NULL,
                        active_ingestion_id TEXT NOT NULL,
                        previous_ingestion_id TEXT NOT NULL DEFAULT '',
                        activated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        activated_by TEXT NOT NULL DEFAULT '',
                        logical_document_id TEXT NOT NULL DEFAULT '',
                        PRIMARY KEY (
                            country, language, source_file,
                            document_type, access_scope
                        )
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    ALTER TABLE knowledge_active_generations
                    ADD COLUMN IF NOT EXISTS logical_document_id
                    TEXT NOT NULL DEFAULT ''
                    """
                )
            )
            connection.execute(
                text(
                    """
                    UPDATE knowledge_active_generations
                    SET logical_document_id = concat_ws(
                        ':', lower(access_scope), upper(country), lower(language),
                        lower(document_type),
                        left(
                            COALESCE(
                                NULLIF(
                                    trim(
                                        both '-' from regexp_replace(
                                            lower(
                                                regexp_replace(
                                                    source_file,
                                                    '\\.[^.]+$',
                                                    ''
                                                )
                                            ),
                                            '[^a-z0-9]+',
                                            '-',
                                            'g'
                                        )
                                    ),
                                    ''
                                ),
                                'document'
                            ),
                            96
                        )
                    )
                    WHERE logical_document_id = ''
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_knowledge_active_generations_logical_document
                    ON knowledge_active_generations (logical_document_id)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS knowledge_document_generations (
                        ingestion_id TEXT PRIMARY KEY,
                        logical_document_id TEXT NOT NULL,
                        country TEXT NOT NULL,
                        language TEXT NOT NULL,
                        source_file TEXT NOT NULL,
                        document_type TEXT NOT NULL,
                        access_scope TEXT NOT NULL,
                        status TEXT NOT NULL,
                        activated_at TIMESTAMPTZ,
                        retired_at TIMESTAMPTZ,
                        activated_by TEXT NOT NULL DEFAULT ''
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
                    CREATE INDEX IF NOT EXISTS idx_chat_sessions_live
                    ON chat_sessions (expires_at)
                    WHERE ended_at IS NULL AND consent_accepted = true
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
                    CREATE INDEX IF NOT EXISTS idx_consent_log_session_locale
                    ON consent_log (session_id, country, lang)
                    WHERE accepted = true
                    """
                )
            )
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
