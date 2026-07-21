"""Tests for environment-aware startup configuration validation."""

from config import settings
from scripts.validate_config import validate


def _configure_valid_production(monkeypatch) -> None:
    for name in settings.REQUIRED_VALUES:
        monkeypatch.setattr(settings, name, "configured")
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "production-admin-secret")
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
    monkeypatch.setattr(settings, "AUDIT_FIREHOSE_ENABLED", False)
    monkeypatch.setattr(settings, "SUPPORT_EMAIL_ENABLED", False)


def test_valid_production_configuration_passes(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)

    assert validate() == []


def test_production_rejects_development_auth_and_missing_retrieval_config(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "dev-admin-key")
    monkeypatch.setattr(settings, "WIDGET_JWT_SECRET", "dev-only-change-before-production")
    monkeypatch.setattr(settings, "WIDGET_AUTH_REQUIRED", False)
    monkeypatch.setattr(settings, "OPENSEARCH_ENDPOINT", "")

    failures = validate()

    assert "ADMIN_API_KEY (development value is not allowed)" in failures
    assert "WIDGET_JWT_SECRET (development value is not allowed)" in failures
    assert "WIDGET_AUTH_REQUIRED (must be true in production)" in failures
    assert "OPENSEARCH_ENDPOINT" in failures


def test_support_email_requires_sender_and_routes_in_production(monkeypatch) -> None:
    _configure_valid_production(monkeypatch)
    monkeypatch.setattr(settings, "SUPPORT_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "SUPPORT_EMAIL_FROM", "")
    monkeypatch.setattr(settings, "SUPPORT_ROUTES_JSON", {})

    failures = validate()

    assert "SUPPORT_EMAIL_FROM" in failures
    assert "SUPPORT_ROUTES_JSON" in failures
