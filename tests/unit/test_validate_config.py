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
    monkeypatch.setattr(settings, "RETRIEVAL_RRF_K", 60)
    monkeypatch.setattr(settings, "RETRIEVAL_MAX_RESULTS_PER_PARENT", 2)
    monkeypatch.setattr(settings, "RETRIEVAL_NEIGHBOR_LIMIT", 2)
    monkeypatch.setattr(settings, "RETRIEVAL_PROMOTION_MIN_SAME_SECTION_RATE", 0.85)
    monkeypatch.setattr(settings, "RETRIEVAL_PROMOTION_MIN_EVIDENCE_OVERLAP", 0.70)
    monkeypatch.setattr(settings, "RETRIEVAL_PROMOTION_MAX_LATENCY_MS", 1500.0)
    monkeypatch.setattr(settings, "AUDIT_FIREHOSE_ENABLED", False)
    monkeypatch.setattr(settings, "SUPPORT_EMAIL_ENABLED", False)
    monkeypatch.setattr(settings, "SUPPORT_ROUTES_JSON", {})
    monkeypatch.setattr(settings, "SUPPORT_DEFAULT_ROUTE_JSON", {})
    monkeypatch.setattr(settings, "SECURITY_PROFILE", "standard")
    monkeypatch.setattr(settings, "ADMIN_INGESTION_QUEUE_ENABLED", True)
    monkeypatch.setattr(settings, "ADMIN_INGESTION_QUEUE_URL", "ingestion-queue")
    monkeypatch.setattr(settings, "ADMIN_INGESTION_DLQ_URL", "ingestion-dlq")
    monkeypatch.setattr(settings, "ADMIN_INGESTION_STAGED_PUBLISH_ENABLED", True)
    monkeypatch.setattr(settings, "ADMIN_INGESTION_GENERATION_POINTER_ENABLED", True)


def test_valid_production_configuration_passes(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    assert validate() == []


def test_production_requires_atomic_ingestion(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "ADMIN_INGESTION_STAGED_PUBLISH_ENABLED", False)

    assert (
        "ADMIN_INGESTION_STAGED_PUBLISH_ENABLED (must be enabled in production)"
        in validate()
    )


def test_unknown_configuration_mode_is_rejected(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "RETRIEVAL_PROVIDER", "experimental_provider")

    failures = validate()

    assert (
        "RETRIEVAL_PROVIDER (must be one of: bedrock, opensearch_section)"
        in failures
    )


def test_production_rejects_draft_guardrail_version(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "BEDROCK_GUARDRAIL_VERSION", "DRAFT")

    failures = validate()

    assert "BEDROCK_GUARDRAIL_VERSION (DRAFT is not allowed in production)" in failures


def test_retrieval_experiment_limits_are_validated(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "RETRIEVAL_RRF_K", 0)
    monkeypatch.setattr(settings, "RETRIEVAL_MAX_RESULTS_PER_PARENT", 0)
    monkeypatch.setattr(settings, "RETRIEVAL_NEIGHBOR_LIMIT", -1)
    monkeypatch.setattr(settings, "RETRIEVAL_PROMOTION_MIN_SAME_SECTION_RATE", 1.1)
    monkeypatch.setattr(settings, "RETRIEVAL_PROMOTION_MIN_EVIDENCE_OVERLAP", -0.1)
    monkeypatch.setattr(settings, "RETRIEVAL_PROMOTION_MAX_LATENCY_MS", 0)

    failures = validate()

    assert "RETRIEVAL_RRF_K (must be greater than 0)" in failures
    assert "RETRIEVAL_MAX_RESULTS_PER_PARENT (must be greater than 0)" in failures
    assert "RETRIEVAL_NEIGHBOR_LIMIT (must not be negative)" in failures
    assert "RETRIEVAL_PROMOTION_MIN_SAME_SECTION_RATE (must be between 0 and 1)" in failures
    assert "RETRIEVAL_PROMOTION_MIN_EVIDENCE_OVERLAP (must be between 0 and 1)" in failures
    assert "RETRIEVAL_PROMOTION_MAX_LATENCY_MS (must be greater than 0)" in failures


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


def test_semantic_cache_requires_safe_configuration(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_THRESHOLD", 1.1)
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_MIN_SCORE_MARGIN", -0.1)
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_MAX_CANDIDATES", 0)
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_EMBED_MODEL_ID", "")

    failures = validate()

    assert "SEMANTIC_CACHE_THRESHOLD (must be between 0 and 1)" in failures
    assert "SEMANTIC_CACHE_MIN_SCORE_MARGIN (must be at least 0 and less than 1)" in failures
    assert "SEMANTIC_CACHE_MAX_CANDIDATES (must be greater than 0)" in failures
    assert "SEMANTIC_CACHE_EMBED_MODEL_ID" in failures


def test_semantic_cache_live_and_shadow_modes_are_mutually_exclusive(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_SHADOW_ENABLED", True)

    failures = validate()

    assert (
        "SEMANTIC_CACHE_ENABLED and SEMANTIC_CACHE_SHADOW_ENABLED (choose only one mode)"
        in failures
    )


def test_model_routing_rejects_invalid_mode(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "MODEL_ROUTING_MODE", "automatic")

    assert "MODEL_ROUTING_MODE (must be off, shadow, or live)" in validate()


def test_model_routing_requires_distinct_models(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "MODEL_ROUTING_MODE", "shadow")
    monkeypatch.setattr(settings, "BEDROCK_FAST_MODEL_ID", "same-model")
    monkeypatch.setattr(settings, "BEDROCK_COMPLEX_MODEL_ID", "same-model")

    assert "BEDROCK_FAST_MODEL_ID and BEDROCK_COMPLEX_MODEL_ID (must differ)" in validate()


def test_live_model_routing_requires_evidence_gate(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "MODEL_ROUTING_MODE", "live")
    monkeypatch.setattr(settings, "BEDROCK_FAST_MODEL_ID", "fast-model")
    monkeypatch.setattr(settings, "BEDROCK_COMPLEX_MODEL_ID", "complex-model")
    monkeypatch.setattr(settings, "EVIDENCE_GATED_OUTPUT_ENABLED", False)

    assert "EVIDENCE_GATED_OUTPUT_ENABLED (must be true for live model routing)" in validate()


def test_model_routing_rejects_negative_dashboard_pricing(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "MODEL_ROUTING_FAST_INPUT_USD_PER_MILLION", -1.0)

    assert (
        "MODEL_ROUTING_FAST_INPUT_USD_PER_MILLION (must not be negative)" in validate()
    )
