"""Tests for operations portal administrator authentication."""

import pytest
from fastapi import HTTPException

from config import settings
from services import admin_auth


def test_explicitly_enabled_api_key_is_accepted(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ADMIN_AUTH_MODE", "api_key")
    monkeypatch.setattr(settings, "ADMIN_AUTH_ALLOW_API_KEY", True)
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key")

    principal = admin_auth.require_admin_identity(x_admin_key="test-admin-key", authorization="")

    assert principal["auth_method"] == "api_key"


def test_api_key_is_rejected_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ADMIN_AUTH_MODE", "cognito")
    monkeypatch.setattr(settings, "ADMIN_AUTH_ALLOW_API_KEY", False)
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key")

    with pytest.raises(HTTPException) as exc_info:
        admin_auth.require_admin_identity(x_admin_key="test-admin-key", authorization="")

    assert exc_info.value.status_code == 401


def test_bearer_token_uses_cognito_validation(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ADMIN_AUTH_MODE", "cognito")
    monkeypatch.setattr(settings, "ADMIN_AUTH_ALLOW_API_KEY", False)
    monkeypatch.setattr(admin_auth, "_decode_cognito_access_token", lambda token: {"sub": token})

    principal = admin_auth.require_admin_identity(authorization="Bearer signed-token", x_admin_key="")

    assert principal == {"sub": "signed-token"}
