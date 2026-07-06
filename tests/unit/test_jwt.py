"""Unit tests for widget JWT security checks."""

from time import time
from uuid import uuid4

import pytest

from app.widget_auth.jwt import WidgetTokenError, decode_widget_token, encode_widget_token, revoke_widget_token_id


def _claims(**overrides):
    now = int(time())
    claims = {
        "iss": "ask-vera",
        "aud": "widget-api",
        "sub": "widget-session",
        "widgetId": "widget-1",
        "organizationId": "org-1",
        "companyName": "Example Enterprise",
        "origin": "https://company.com",
        "sessionId": "session-1",
        "jti": str(uuid4()),
        "iat": now,
        "nbf": now,
        "exp": now + 900,
    }
    claims.update(overrides)
    return claims


def test_valid_token_decodes(monkeypatch) -> None:
    from app.widget_auth import jwt as jwt_module

    monkeypatch.setattr(jwt_module.settings, "WIDGET_JWT_SECRET", "test-secret")
    token = encode_widget_token(_claims())

    decoded = decode_widget_token(token)

    assert decoded["iss"] == "ask-vera"
    assert decoded["aud"] == "widget-api"


def test_expired_token_rejected(monkeypatch) -> None:
    from app.widget_auth import jwt as jwt_module

    monkeypatch.setattr(jwt_module.settings, "WIDGET_JWT_SECRET", "test-secret")
    monkeypatch.setattr(jwt_module.settings, "WIDGET_JWT_CLOCK_SKEW_SECONDS", 0)
    token = encode_widget_token(_claims(exp=int(time()) - 1))

    with pytest.raises(WidgetTokenError):
        decode_widget_token(token)


def test_wrong_audience_rejected(monkeypatch) -> None:
    from app.widget_auth import jwt as jwt_module

    monkeypatch.setattr(jwt_module.settings, "WIDGET_JWT_SECRET", "test-secret")
    token = encode_widget_token(_claims(aud="wrong-api"))

    with pytest.raises(WidgetTokenError):
        decode_widget_token(token)


def test_wrong_issuer_rejected(monkeypatch) -> None:
    from app.widget_auth import jwt as jwt_module

    monkeypatch.setattr(jwt_module.settings, "WIDGET_JWT_SECRET", "test-secret")
    token = encode_widget_token(_claims(iss="wrong-issuer"))

    with pytest.raises(WidgetTokenError):
        decode_widget_token(token)


def test_invalid_signature_rejected(monkeypatch) -> None:
    from app.widget_auth import jwt as jwt_module

    monkeypatch.setattr(jwt_module.settings, "WIDGET_JWT_SECRET", "test-secret")
    token = encode_widget_token(_claims())

    with pytest.raises(WidgetTokenError):
        decode_widget_token(f"{token[:-1]}x")


def test_revoked_token_rejected(monkeypatch) -> None:
    from app.widget_auth import jwt as jwt_module

    monkeypatch.setattr(jwt_module.settings, "WIDGET_JWT_SECRET", "test-secret")
    claims = _claims()
    token = encode_widget_token(claims)
    revoke_widget_token_id(claims["jti"])

    with pytest.raises(WidgetTokenError):
        decode_widget_token(token)


def test_clock_skew_allows_slight_future_nbf(monkeypatch) -> None:
    from app.widget_auth import jwt as jwt_module

    monkeypatch.setattr(jwt_module.settings, "WIDGET_JWT_SECRET", "test-secret")
    monkeypatch.setattr(jwt_module.settings, "WIDGET_JWT_CLOCK_SKEW_SECONDS", 60)
    now = int(time())
    token = encode_widget_token(_claims(iat=now + 30, nbf=now + 30))

    assert decode_widget_token(token)["widgetId"] == "widget-1"
