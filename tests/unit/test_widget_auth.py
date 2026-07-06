"""Unit tests for widget authentication foundation."""

import json
from time import time

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
                "allowedOrigins": ["https://example.com", "https://portal.example.com"],
                "status": status,
            }
        ]
    )


def test_widget_init_issues_short_lived_token(monkeypatch) -> None:
    from app.widget_auth import service as service_module

    monkeypatch.setattr(service_module.settings, "WIDGET_REGISTRY_JSON", _registry())
    monkeypatch.setattr(service_module.settings, "WIDGET_JWT_SECRET", "test-secret")
    monkeypatch.setattr(service_module.settings, "WIDGET_JWT_TTL_SECONDS", 900)
    service = WidgetAuthService()

    response = service.initialize(
        WidgetInitRequest(widgetId="widget-1", publishableKey="pk_test", origin="https://example.com"),
        "cid",
    )

    claims = decode_widget_token(response.token)
    assert response.expiresIn == 900
    assert claims["widgetId"] == "widget-1"
    assert claims["organizationId"] == "org-1"
    assert claims["origin"] == "https://example.com"
    assert claims["exp"] > int(time())


def test_widget_init_rejects_unapproved_origin(monkeypatch) -> None:
    from app.widget_auth import service as service_module

    monkeypatch.setattr(service_module.settings, "WIDGET_REGISTRY_JSON", _registry())
    service = WidgetAuthService()

    with pytest.raises(WidgetAuthError):
        service.initialize(
            WidgetInitRequest(widgetId="widget-1", publishableKey="pk_test", origin="https://evil.example"),
            "cid",
        )


def test_widget_init_rejects_disabled_widget(monkeypatch) -> None:
    from app.widget_auth import service as service_module

    monkeypatch.setattr(service_module.settings, "WIDGET_REGISTRY_JSON", _registry("disabled"))
    service = WidgetAuthService()

    with pytest.raises(WidgetAuthError):
        service.initialize(
            WidgetInitRequest(widgetId="widget-1", publishableKey="pk_test", origin="https://example.com"),
            "cid",
        )


def test_widget_token_rejects_tampering(monkeypatch) -> None:
    from app.widget_auth import service as service_module

    monkeypatch.setattr(service_module.settings, "WIDGET_REGISTRY_JSON", _registry())
    monkeypatch.setattr(service_module.settings, "WIDGET_JWT_SECRET", "test-secret")
    service = WidgetAuthService()
    response = service.initialize(
        WidgetInitRequest(widgetId="widget-1", publishableKey="pk_test", origin="https://example.com"),
        "cid",
    )

    tampered = f"{response.token[:-1]}x"
    with pytest.raises(WidgetTokenError):
        decode_widget_token(tampered)
