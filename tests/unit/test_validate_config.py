"""Tests for environment-aware startup configuration validation."""

from config import settings
from scripts.validate_config import validate


def _configure_valid_production(monkeypatch) -> None:
    for name in settings.REQUIRED_VALUES:
        monkeypatch.setattr(settings, name, "configured")
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "AWS_ACCOUNT_ID", "123456789012")
    monkeypatch.setattr(settings, "RDS_DB_IDENTIFIER", "askvera-db")
    monkeypatch.setattr(settings, "ADMIN_AUTH_MODE", "cognito")
    monkeypatch.setattr(settings, "ADMIN_AUTH_ALLOW_API_KEY", False)
    monkeypatch.setattr(settings, "ADMIN_COGNITO_USER_POOL_ID", "us-east-1_example")
    monkeypatch.setattr(settings, "ADMIN_COGNITO_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "ADMIN_COGNITO_REQUIRED_GROUP", "AskVeraAdmins")
    monkeypatch.setattr(settings, "ADMIN_BOOTSTRAP_SUPER_ADMIN_EMAIL", "owner@example.com")
    monkeypatch.setattr(settings, "ADMIN_RBAC_ENABLED", False)
    monkeypatch.setattr(settings, "ADMIN_USER_MANAGEMENT_ENABLED", False)
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "")
    monkeypatch.setattr(settings, "WIDGET_JWT_SECRET", "production-widget-secret")
    monkeypatch.setattr(settings, "WIDGET_AUTH_REQUIRED", True)
    monkeypatch.setattr(settings, "WIDGET_ALLOW_LOCALHOST_ORIGINS", False)
    monkeypatch.setattr(settings, "CHAT_MEMORY_BACKEND", "postgres")
    monkeypatch.setattr(settings, "SHARED_SECURITY_STATE_ENABLED", True)
    monkeypatch.setattr(settings, "SHARED_SECURITY_STATE_REQUIRED", True)
    monkeypatch.setattr(settings, "BEDROCK_MODEL_ARN", "model-arn")
    monkeypatch.setattr(settings, "BEDROCK_GUARDRAIL_ID", "guardrail-id")
    monkeypatch.setattr(settings, "BEDROCK_GUARDRAIL_VERSION", "1")
    monkeypatch.setattr(settings, "SQS_FEEDBACK_QUEUE_URL", "queue-url")
    monkeypatch.setattr(settings, "RETRIEVAL_PROVIDER", "opensearch_section")
    monkeypatch.setattr(settings, "OPENSEARCH_ENDPOINT", "https://example.aoss.amazonaws.com")
    monkeypatch.setattr(settings, "OPENSEARCH_INDEX", "sections")
    monkeypatch.setattr(settings, "RETRIEVAL_SHADOW_ENABLED", False)
    monkeypatch.setattr(settings, "AUDIT_FIREHOSE_ENABLED", False)
    monkeypatch.setattr(settings, "SUPPORT_EMAIL_ENABLED", False)
    monkeypatch.setattr(settings, "SUPPORT_ROUTES_JSON", {})
    monkeypatch.setattr(settings, "SUPPORT_DEFAULT_ROUTE_JSON", {})
    monkeypatch.setattr(settings, "SECURITY_PROFILE", "standard")


def test_valid_production_configuration_passes(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)

    assert validate() == []


def test_production_restart_validation_rejects_non_production_environment(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "APP_ENV", "uat")

    failures = validate(require_production=True)

    assert "APP_ENV (must be production for a production restart)" in failures


def test_production_rejects_development_auth_and_missing_retrieval_config(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "ADMIN_AUTH_MODE", "api_key")
    monkeypatch.setattr(settings, "ADMIN_AUTH_ALLOW_API_KEY", True)
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "dev-admin-key")
    monkeypatch.setattr(settings, "WIDGET_JWT_SECRET", "dev-only-change-before-production")
    monkeypatch.setattr(settings, "WIDGET_AUTH_REQUIRED", False)
    monkeypatch.setattr(settings, "OPENSEARCH_ENDPOINT", "")

    failures = validate()

    assert "ADMIN_API_KEY (development value is not allowed)" in failures
    assert "ADMIN_AUTH_MODE (must be cognito in production)" in failures
    assert "ADMIN_AUTH_ALLOW_API_KEY (must be false in production)" in failures
    assert "WIDGET_JWT_SECRET (development value is not allowed)" in failures
    assert "WIDGET_AUTH_REQUIRED (must be true in production)" in failures
    assert "OPENSEARCH_ENDPOINT" in failures


def test_production_requires_external_resource_inventory(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "AWS_ACCOUNT_ID", "")
    monkeypatch.setattr(settings, "RDS_DB_IDENTIFIER", "")

    failures = validate()

    assert "AWS_ACCOUNT_ID" in failures
    assert "RDS_DB_IDENTIFIER" in failures


def test_bedrock_retrieval_requires_kb_and_data_source(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "RETRIEVAL_PROVIDER", "bedrock")
    monkeypatch.setattr(settings, "BEDROCK_KB_ID", "")
    monkeypatch.setattr(settings, "BEDROCK_DATA_SOURCE_ID", "")

    failures = validate()

    assert "BEDROCK_KB_ID" in failures
    assert "BEDROCK_DATA_SOURCE_ID" in failures


def test_cognito_production_requires_pool_and_client(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "ADMIN_COGNITO_USER_POOL_ID", "")
    monkeypatch.setattr(settings, "ADMIN_COGNITO_CLIENT_ID", "")

    failures = validate()

    assert "ADMIN_COGNITO_USER_POOL_ID" in failures
    assert "ADMIN_COGNITO_CLIENT_ID" in failures


def test_rbac_production_requires_explicit_bootstrap_identity(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "ADMIN_RBAC_ENABLED", True)
    monkeypatch.setattr(settings, "ADMIN_USER_MANAGEMENT_ENABLED", True)
    monkeypatch.setattr(settings, "ADMIN_COGNITO_REQUIRED_GROUP", "")
    monkeypatch.setattr(settings, "ADMIN_BOOTSTRAP_SUPER_ADMIN_EMAIL", "")

    failures = validate()

    assert "ADMIN_COGNITO_REQUIRED_GROUP" in failures
    assert "ADMIN_BOOTSTRAP_SUPER_ADMIN_EMAIL" in failures


def test_support_email_requires_sender_and_routes_in_production(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "SUPPORT_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "SUPPORT_EMAIL_FROM", "")
    monkeypatch.setattr(settings, "SUPPORT_ROUTES_JSON", {})
    monkeypatch.setattr(settings, "SUPPORT_DEFAULT_ROUTE_JSON", {})

    failures = validate()

    assert "SUPPORT_EMAIL_FROM" in failures
    assert "SUPPORT_ROUTES_JSON or SUPPORT_DEFAULT_ROUTE_JSON" in failures


def test_support_email_accepts_default_route_in_production(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "SUPPORT_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "SUPPORT_EMAIL_FROM", "askvera@example.com")
    monkeypatch.setattr(settings, "SUPPORT_ROUTES_JSON", {})
    monkeypatch.setattr(
        settings,
        "SUPPORT_DEFAULT_ROUTE_JSON",
        {"department": "Global Support", "email": "global@example.com"},
    )

    assert validate() == []


def test_shadow_retrieval_requires_a_separate_vnext_index(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "RETRIEVAL_SHADOW_ENABLED", True)
    monkeypatch.setattr(settings, "RETRIEVAL_SHADOW_SAMPLE_RATE", 0.1)
    monkeypatch.setattr(settings, "RETRIEVAL_VNEXT_PROVIDER", "opensearch_section")
    monkeypatch.setattr(settings, "OPENSEARCH_VNEXT_INDEX", "sections")

    failures = validate()

    assert "OPENSEARCH_VNEXT_INDEX (must differ from OPENSEARCH_INDEX)" in failures


def test_shadow_retrieval_accepts_safe_isolated_configuration(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "RETRIEVAL_SHADOW_ENABLED", True)
    monkeypatch.setattr(settings, "RETRIEVAL_SHADOW_SAMPLE_RATE", 0.1)
    monkeypatch.setattr(settings, "RETRIEVAL_VNEXT_PROVIDER", "opensearch_section")
    monkeypatch.setattr(settings, "OPENSEARCH_VNEXT_INDEX", "sections-vnext")

    assert validate() == []


def test_shadow_reranking_requires_a_model_arn(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "RETRIEVAL_SHADOW_ENABLED", True)
    monkeypatch.setattr(settings, "RETRIEVAL_SHADOW_SAMPLE_RATE", 0.1)
    monkeypatch.setattr(settings, "RETRIEVAL_VNEXT_PROVIDER", "opensearch_section")
    monkeypatch.setattr(settings, "OPENSEARCH_VNEXT_INDEX", "sections-vnext")
    monkeypatch.setattr(settings, "RETRIEVAL_VNEXT_RERANK_ENABLED", True)
    monkeypatch.setattr(settings, "RETRIEVAL_VNEXT_RERANK_MODEL_ARN", "")

    failures = validate()

    assert "RETRIEVAL_VNEXT_RERANK_MODEL_ARN" in failures


def test_shadow_reranking_requires_enough_candidates(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "RETRIEVAL_SHADOW_ENABLED", True)
    monkeypatch.setattr(settings, "RETRIEVAL_SHADOW_SAMPLE_RATE", 0.1)
    monkeypatch.setattr(settings, "RETRIEVAL_VNEXT_PROVIDER", "opensearch_section")
    monkeypatch.setattr(settings, "OPENSEARCH_VNEXT_INDEX", "sections-vnext")
    monkeypatch.setattr(settings, "RETRIEVAL_VNEXT_RERANK_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "RETRIEVAL_VNEXT_RERANK_MODEL_ARN",
        "arn:aws:bedrock:us-east-1::foundation-model/cohere.rerank-v3-5:0",
    )
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 10)
    monkeypatch.setattr(settings, "RETRIEVAL_VNEXT_RERANK_CANDIDATE_COUNT", 9)

    failures = validate()

    assert (
        "RETRIEVAL_VNEXT_RERANK_CANDIDATE_COUNT "
        "(must be at least OPENSEARCH_RESULT_COUNT)"
    ) in failures


def test_hardened_profile_requires_durable_security_controls(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "SECURITY_PROFILE", "hardened")
    monkeypatch.setattr(settings, "ADMIN_INGESTION_QUEUE_ENABLED", False)
    monkeypatch.setattr(settings, "ADMIN_INGESTION_STAGED_PUBLISH_ENABLED", False)
    monkeypatch.setattr(settings, "ADMIN_INGESTION_GENERATION_POINTER_ENABLED", False)
    monkeypatch.setattr(settings, "ADMIN_INGESTION_APPROVAL_METADATA_REQUIRED", False)
    monkeypatch.setattr(settings, "ADMIN_INGESTION_MALWARE_SCAN_REQUIRED", False)
    monkeypatch.setattr(settings, "ADMIN_INGESTION_QUEUE_URL", "")
    monkeypatch.setattr(settings, "ADMIN_INGESTION_DLQ_URL", "")
    monkeypatch.setattr(settings, "KNOWLEDGE_UPLOAD_BUCKET", "")
    monkeypatch.setattr(settings, "ENABLE_ALARM_NOTIFICATIONS", False)
    monkeypatch.setattr(settings, "ADMIN_DOCUMENT_PREFLIGHT_ENABLED", False)
    monkeypatch.setattr(settings, "ADMIN_ANALYTICS_REDACTED_BY_DEFAULT", False)
    monkeypatch.setattr(settings, "EVIDENCE_GATED_OUTPUT_ENABLED", False)

    failures = validate()

    assert (
        "ADMIN_INGESTION_QUEUE_ENABLED "
        "(must be enabled for the hardened security profile)"
    ) in failures
    assert "ADMIN_INGESTION_QUEUE_URL" in failures
    assert "ADMIN_INGESTION_DLQ_URL" in failures
    assert "KNOWLEDGE_UPLOAD_BUCKET" in failures
    assert (
        "ADMIN_ANALYTICS_REDACTED_BY_DEFAULT "
        "(must be enabled for the hardened security profile)"
    ) in failures
