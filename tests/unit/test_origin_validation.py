"""Unit tests for widget origin allowlist validation."""

import json

import pytest

from app.widget_auth.models import WidgetInitRequest
from app.widget_auth.origin_validator import is_origin_allowed, normalize_origin
from app.widget_auth.service import WidgetAuthError, WidgetAuthService


def _registry(allowed_origins: list[str], status: str = "active") -> str:
    return json.dumps(
        [
            {
                "widgetId": "widget-1",
                "publishableKey": "pk_test",
                "organizationId": "org-1",
                "companyName": "Example Enterprise",
                "allowedOrigins": allowed_origins,
                "status": status,
            }
        ]
    )


def test_exact_origin_match() -> None:
    result = is_origin_allowed("https://company.com", ["https://company.com"])

    assert result.allowed is True
    assert result.normalized_origin == "https://company.com"


def test_wildcard_origin_match() -> None:
    result = is_origin_allowed("https://portal.company.com", ["*.company.com"])

    assert result.allowed is True


def test_wildcard_does_not_match_lookalike_domain() -> None:
    result = is_origin_allowed("https://evilcompany.com", ["*.company.com"])

    assert result.allowed is False
    assert result.reason == "origin_not_allowed"


def test_wildcard_does_not_match_root_domain() -> None:
    result = is_origin_allowed("https://company.com", ["*.company.com"])

    assert result.allowed is False


def test_localhost_allowed_in_development(monkeypatch) -> None:
    from app.widget_auth import origin_validator

    monkeypatch.setattr(origin_validator.settings, "WIDGET_ALLOW_LOCALHOST_ORIGINS", True)

    result = is_origin_allowed("http://localhost:5173", ["http://localhost:5173"])

    assert result.allowed is True


def test_localhost_rejected_in_production(monkeypatch) -> None:
    from app.widget_auth import origin_validator

    monkeypatch.setattr(origin_validator.settings, "WIDGET_ALLOW_LOCALHOST_ORIGINS", False)

    result = is_origin_allowed("http://localhost:5173", ["http://localhost:5173"])

    assert result.allowed is False
    assert result.reason == "localhost_not_allowed"


def test_missing_origin_rejected() -> None:
    result = is_origin_allowed(None, ["https://company.com"])

    assert result.allowed is False
    assert result.reason == "missing_or_invalid_origin"


def test_invalid_origin_rejected() -> None:
    assert normalize_origin("javascript:alert(1)") == ""
    result = is_origin_allowed("javascript:alert(1)", ["https://company.com"])

    assert result.allowed is False
    assert result.reason == "missing_or_invalid_origin"


def test_service_rejects_disabled_widget(monkeypatch) -> None:
    from app.widget_auth import service as service_module

    monkeypatch.setattr(service_module.settings, "WIDGET_REGISTRY_JSON", _registry(["https://company.com"], "disabled"))
    service = WidgetAuthService()

    with pytest.raises(WidgetAuthError):
        service.initialize(
            WidgetInitRequest(widgetId="widget-1", publishableKey="pk_test", origin="https://company.com"),
            "cid",
            "203.0.113.10",
        )


def test_service_accepts_wildcard_origin(monkeypatch) -> None:
    from app.widget_auth import service as service_module

    monkeypatch.setattr(service_module.settings, "WIDGET_REGISTRY_JSON", _registry(["*.company.com"]))
    monkeypatch.setattr(service_module.settings, "WIDGET_JWT_SECRET", "test-secret")
    service = WidgetAuthService()

    response = service.initialize(
        WidgetInitRequest(widgetId="widget-1", publishableKey="pk_test", origin="https://portal.company.com"),
        "cid",
        "203.0.113.10",
    )

    assert response.widgetId == "widget-1"
