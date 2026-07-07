"""Unit tests for widget token refresh."""

import json

import pytest

from app.widget_auth.jwt import WidgetTokenError, decode_widget_token
from app.widget_auth.models import WidgetInitRequest
from app.widget_auth.service import WidgetAuthError, WidgetAuthService


def _registry(status: str = "active") -> str:
    return json.dumps(
        [
            {
                "widgetId": "widget-1",
                "publishableKey": "pk_test",
                "organizationId": "org-1",
                "companyName": "Example Enterprise",
                "allowedOrigins": ["https://company.com"],
                "status": status,
            }
        ]
    )


def _service(monkeypatch, status: str = "active") -> WidgetAuthService:
    from app.widget_auth import service as service_module

    monkeypatch.setattr(service_module.settings, "WIDGET_REGISTRY_JSON", _registry(status))
    monkeypatch.setattr(service_module.settings, "WIDGET_JWT_SECRET", "test-secret")
    monkeypatch.setattr(service_module.settings, "WIDGET_JWT_TTL_SECONDS", 900)
    return WidgetAuthService()


def test_refresh_issues_new_token_for_same_session(monkeypatch) -> None:
    service = _service(monkeypatch)
    initial = service.initialize(
        WidgetInitRequest(widgetId="widget-1", publishableKey="pk_test", origin="https://company.com"),
        "cid",
        "203.0.113.10",
    )
    initial_claims = decode_widget_token(initial.token)

    refreshed = service.refresh(initial.token, "cid", "https://company.com")

    refreshed_claims = decode_widget_token(refreshed.token)
    assert refreshed_claims["sessionId"] == initial_claims["sessionId"]
    assert refreshed_claims["jti"] != initial_claims["jti"]


def test_refresh_revokes_previous_token(monkeypatch) -> None:
    service = _service(monkeypatch)
    initial = service.initialize(
        WidgetInitRequest(widgetId="widget-1", publishableKey="pk_test", origin="https://company.com"),
        "cid",
        "203.0.113.10",
    )

    service.refresh(initial.token, "cid", "https://company.com")

    with pytest.raises(WidgetTokenError):
        decode_widget_token(initial.token)


def test_refresh_rejects_origin_mismatch(monkeypatch) -> None:
    service = _service(monkeypatch)
    initial = service.initialize(
        WidgetInitRequest(widgetId="widget-1", publishableKey="pk_test", origin="https://company.com"),
        "cid",
        "203.0.113.10",
    )

    with pytest.raises(WidgetAuthError):
        service.refresh(initial.token, "cid", "https://evil.example")


def test_refresh_rejects_disabled_widget(monkeypatch) -> None:
    service = _service(monkeypatch)
    initial = service.initialize(
        WidgetInitRequest(widgetId="widget-1", publishableKey="pk_test", origin="https://company.com"),
        "cid",
        "203.0.113.10",
    )

    from app.widget_auth import service as service_module

    monkeypatch.setattr(service_module.settings, "WIDGET_REGISTRY_JSON", _registry("disabled"))
    service.reload()

    with pytest.raises(WidgetAuthError):
        service.refresh(initial.token, "cid", "https://company.com")
