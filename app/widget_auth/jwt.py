"""Small HS256 JWT helper for widget sessions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from time import time
from typing import Any

from config import settings
from utils.exceptions import AskVeraError


class WidgetTokenError(AskVeraError):
    """Raised when a widget JWT is missing, invalid, or expired."""

    status_code = 401
    error_code = "WIDGET_AUTH_REQUIRED"

    def __init__(self, message: str = "A valid widget session token is required.") -> None:
        super().__init__(message)


class WidgetTokenRevokedError(WidgetTokenError):
    """Raised when a token has been explicitly revoked."""

    def __init__(self) -> None:
        super().__init__("Widget session token has been revoked.")


_REVOKED_TOKEN_IDS: set[str] = set()


def revoke_widget_token_id(jti: str) -> None:
    """Revoke a widget token ID for the current process."""
    if jti:
        _REVOKED_TOKEN_IDS.add(jti)


def is_widget_token_revoked(jti: str | None) -> bool:
    """Return True when a widget token ID is revoked."""
    return bool(jti and jti in _REVOKED_TOKEN_IDS)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(f"{data}{padding}".encode("ascii"))


def _sign(message: str) -> str:
    digest = hmac.new(settings.WIDGET_JWT_SECRET.encode("utf-8"), message.encode("ascii"), hashlib.sha256).digest()
    return _b64url_encode(digest)


def encode_widget_token(claims: dict[str, Any]) -> str:
    """Encode claims as a compact HS256 JWT."""
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    encoded_payload = _b64url_encode(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}"
    return f"{signing_input}.{_sign(signing_input)}"


def decode_widget_token(token: str) -> dict[str, Any]:
    """Decode and validate a compact HS256 JWT."""
    try:
        encoded_header, encoded_payload, signature = token.split(".", 2)
    except ValueError as exc:
        raise WidgetTokenError() from exc

    signing_input = f"{encoded_header}.{encoded_payload}"
    expected_signature = _sign(signing_input)
    if not hmac.compare_digest(signature, expected_signature):
        raise WidgetTokenError()

    try:
        header = json.loads(_b64url_decode(encoded_header))
        payload = json.loads(_b64url_decode(encoded_payload))
    except (json.JSONDecodeError, ValueError) as exc:
        raise WidgetTokenError() from exc

    if header.get("alg") != "HS256":
        raise WidgetTokenError()

    if payload.get("iss") != settings.WIDGET_JWT_ISSUER:
        raise WidgetTokenError("Widget token issuer is invalid.")

    if payload.get("aud") != settings.WIDGET_JWT_AUDIENCE:
        raise WidgetTokenError("Widget token audience is invalid.")

    if payload.get("sub") != "widget-session":
        raise WidgetTokenError("Widget token subject is invalid.")

    if is_widget_token_revoked(payload.get("jti")):
        raise WidgetTokenRevokedError()

    now = int(time())
    skew = settings.WIDGET_JWT_CLOCK_SKEW_SECONDS
    if int(payload.get("nbf", 0)) > now + skew:
        raise WidgetTokenError("Widget token is not valid yet.")

    if int(payload.get("iat", 0)) > now + skew:
        raise WidgetTokenError("Widget token issued-at time is invalid.")

    if int(payload.get("exp", 0)) <= now - skew:
        raise WidgetTokenError()

    return payload
