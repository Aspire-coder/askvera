"""Authentication for operational admin endpoints."""

from hmac import compare_digest
from typing import Any

import jwt
from fastapi import Header, HTTPException
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError

from config import settings

_jwks_clients: dict[str, PyJWKClient] = {}


def _unauthorized(message: str = "Administrator sign-in is required.") -> HTTPException:
    return HTTPException(
        status_code=401,
        detail=message,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _issuer() -> str:
    region = str(settings.ADMIN_COGNITO_REGION or settings.AWS_REGION).strip()
    pool_id = str(settings.ADMIN_COGNITO_USER_POOL_ID or "").strip()
    if not region or not pool_id:
        raise _unauthorized("Administrator sign-in is not configured.")
    return f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"


def _jwks_client(issuer: str) -> PyJWKClient:
    client = _jwks_clients.get(issuer)
    if client is None:
        client = PyJWKClient(f"{issuer}/.well-known/jwks.json", cache_keys=True)
        _jwks_clients[issuer] = client
    return client


def _decode_cognito_access_token(token: str) -> dict[str, Any]:
    issuer = _issuer()
    client_id = str(settings.ADMIN_COGNITO_CLIENT_ID or "").strip()
    if not client_id:
        raise _unauthorized("Administrator sign-in is not configured.")
    try:
        signing_key = _jwks_client(issuer).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False, "require": ["exp", "iat", "iss", "sub", "token_use"]},
        )
    except (PyJWTError, ValueError, RuntimeError) as exc:
        raise _unauthorized("Administrator session is invalid or expired.") from exc

    if claims.get("token_use") != "access" or claims.get("client_id") != client_id:
        raise _unauthorized("Administrator session is invalid.")

    required_group = str(settings.ADMIN_COGNITO_REQUIRED_GROUP or "").strip()
    groups = claims.get("cognito:groups", [])
    if isinstance(groups, str):
        groups = [groups]
    if required_group and required_group not in groups:
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    return claims


def require_admin_identity(
    authorization: str = Header(default=""),
    x_admin_key: str = Header(default=""),
) -> dict[str, Any]:
    """Require a Cognito administrator or an explicitly enabled API key."""
    mode = str(settings.ADMIN_AUTH_MODE or "").lower()
    if mode not in {"cognito", "api_key", "either"}:
        raise HTTPException(status_code=500, detail="Administrator authentication is misconfigured.")

    if mode in {"cognito", "either"} and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        if token:
            return _decode_cognito_access_token(token)

    configured = str(settings.ADMIN_API_KEY or "")
    key_allowed = mode in {"api_key", "either"} and bool(settings.ADMIN_AUTH_ALLOW_API_KEY)
    if key_allowed and configured and x_admin_key and compare_digest(configured, x_admin_key):
        return {"sub": "api-key-operator", "auth_method": "api_key"}

    raise _unauthorized()
