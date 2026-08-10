"""Cognito-backed administrator profiles and structured authorization."""

from __future__ import annotations

import re
from typing import Any, Iterable
from uuid import uuid4

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from services.aws_clients import get_aws_clients
from services.db import get_engine
from services.market_config import get_country_codes
from utils.logging import get_logger

LOGGER = get_logger("services.admin_users")

ADMIN_SECTIONS = {"flow", "knowledge", "insights", "users", "widget", "support", "audit"}
ADMIN_PERMISSIONS = {"view", "stage", "publish", "manage"}
ADMIN_ROLES = {"super_admin", "country_admin", "section_scoped", "auditor"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _scope_rows(scopes: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    normalized: set[tuple[str, str, str]] = set()
    markets = get_country_codes()
    for scope in scopes:
        market = str(scope.get("market") or "").upper()
        section = str(scope.get("section") or "").lower()
        permission = str(scope.get("permission") or "").lower()
        if market != "*" and market not in markets:
            raise ValueError(f"Unsupported market: {market}")
        if section not in ADMIN_SECTIONS:
            raise ValueError(f"Unsupported admin section: {section}")
        if permission not in ADMIN_PERMISSIONS:
            raise ValueError(f"Unsupported permission: {permission}")
        normalized.add((market, section, permission))
    return [
        {"market": market, "section": section, "permission": permission}
        for market, section, permission in sorted(normalized)
    ]


def _validate_role_scopes(role: str, scopes: list[dict[str, str]]) -> list[dict[str, str]]:
    if role == "super_admin":
        return []
    wildcard_scopes = [scope for scope in scopes if scope["market"] == "*"]
    if wildcard_scopes and role != "auditor":
        raise ValueError("Only Super Admin or an Auditor can receive all-market access.")
    if role == "country_admin" and any(scope["section"] in {"users", "widget", "audit"} for scope in scopes):
        raise ValueError("Country Admin cannot manage users, widget instances, or global audit settings.")
    if any(
        scope["section"] in {"users", "audit"} and scope["market"] != "*"
        for scope in scopes
    ):
        raise ValueError("Users and Audit permissions require all-market scope.")
    if role == "auditor":
        if any(
            scope["market"] != "*"
            or scope["section"] not in {"users", "audit"}
            or scope["permission"] != "view"
            for scope in scopes
        ):
            raise ValueError("Auditors receive all-market, read-only Users and Audit access.")
    if not scopes:
        raise ValueError("Choose at least one market and section permission.")
    return scopes


def _serialize(row: dict[str, Any], scopes: list[dict[str, str]]) -> dict[str, Any]:
    return {
        **row,
        "last_login": row["last_login"].isoformat() if row.get("last_login") else None,
        "disabled_at": row["disabled_at"].isoformat() if row.get("disabled_at") else None,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else "",
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else "",
        "scopes": scopes,
    }


def _load_scopes(connection: Any, user_ids: list[str]) -> dict[str, list[dict[str, str]]]:
    result = {user_id: [] for user_id in user_ids}
    if not user_ids:
        return result
    rows = connection.execute(
        text(
            """
            SELECT user_id, market, section, permission
            FROM admin_user_scopes
            WHERE user_id = ANY(:user_ids)
            ORDER BY market, section, permission
            """
        ),
        {"user_ids": user_ids},
    ).mappings()
    for row in rows:
        result[str(row["user_id"])].append(
            {"market": row["market"], "section": row["section"], "permission": row["permission"]}
        )
    return result


def _write_audit(connection: Any, actor_sub: str, action: str, target_id: str) -> None:
    connection.execute(
        text(
            """
            INSERT INTO admin_audit_log (
                event_id, actor_sub, action, target_type, target_id, metadata, created_at
            ) VALUES (:event_id, :actor_sub, :action, 'admin_user', :target_id, '{}'::jsonb, now())
            """
        ),
        {"event_id": str(uuid4()), "actor_sub": actor_sub, "action": action, "target_id": target_id},
    )


def record_admin_audit_event(actor_sub: str, action: str, target_id: str) -> None:
    """Record a non-content admin access event for sensitive operational actions."""
    try:
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO admin_audit_log (
                        event_id, actor_sub, action, target_type, target_id, metadata, created_at
                    ) VALUES (:event_id, :actor_sub, :action, 'operations', :target_id, '{}'::jsonb, now())
                    """
                ),
                {
                    "event_id": str(uuid4()),
                    "actor_sub": actor_sub,
                    "action": action,
                    "target_id": target_id,
                },
            )
    except SQLAlchemyError:
        LOGGER.exception("admin_audit_event_write_failed", actor_sub=actor_sub, action=action)


def _lock_admin_lifecycle(connection: Any) -> None:
    connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('askvera_admin_lifecycle'))"))


def _active_super_admins_other_than(connection: Any, user_id: str) -> int:
    return int(
        connection.execute(
            text(
                """
                SELECT COUNT(*) FROM admin_users
                WHERE role = 'super_admin' AND status = 'active' AND id <> :id
                """
            ),
            {"id": user_id},
        ).scalar_one()
    )


def _ensure_cognito_admin_group(cognito: Any, username: str) -> None:
    group = str(settings.ADMIN_COGNITO_REQUIRED_GROUP or "").strip()
    if group:
        cognito.admin_add_user_to_group(
            UserPoolId=settings.ADMIN_COGNITO_USER_POOL_ID,
            Username=username,
            GroupName=group,
        )


def _replace_scopes(connection: Any, user_id: str, scopes: list[dict[str, str]]) -> None:
    connection.execute(text("DELETE FROM admin_user_scopes WHERE user_id = :user_id"), {"user_id": user_id})
    for scope in scopes:
        connection.execute(
            text(
                """
                INSERT INTO admin_user_scopes (user_id, market, section, permission)
                VALUES (:user_id, :market, :section, :permission)
                """
            ),
            {"user_id": user_id, **scope},
        )


def list_admin_users() -> list[dict[str, Any]]:
    with get_engine().connect() as connection:
        rows = [dict(row) for row in connection.execute(text("SELECT * FROM admin_users ORDER BY email")).mappings()]
        scopes = _load_scopes(connection, [str(row["id"]) for row in rows])
    return [_serialize(row, scopes.get(str(row["id"]), [])) for row in rows]


def list_admin_audit_events(limit: int = 100) -> list[dict[str, Any]]:
    with get_engine().connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT event_id, actor_sub, action, target_type, target_id, metadata, created_at
                FROM admin_audit_log
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": max(1, min(int(limit), 200))},
        ).mappings()
        return [
            {
                **dict(row),
                "created_at": row["created_at"].isoformat() if row["created_at"] else "",
            }
            for row in rows
        ]


def get_admin_user(user_id: str) -> dict[str, Any] | None:
    with get_engine().connect() as connection:
        row = connection.execute(
            text("SELECT * FROM admin_users WHERE id = :id"),
            {"id": user_id},
        ).mappings().first()
        if not row:
            return None
        scopes = _load_scopes(connection, [user_id])[user_id]
    return _serialize(dict(row), scopes)


def sync_admin_identity(claims: dict[str, Any]) -> dict[str, Any]:
    """Sync a successfully authenticated legacy Cognito administrator into RDS."""
    subject = str(claims.get("sub") or "")
    email = str(claims.get("email") or claims.get("username") or claims.get("cognito:username") or "").lower()
    if not subject:
        raise HTTPException(status_code=403, detail="Administrator identity is incomplete.")
    if "@" not in email:
        username = str(claims.get("username") or claims.get("cognito:username") or "")
        if username:
            try:
                response = get_aws_clients().cognito_idp.admin_get_user(
                    UserPoolId=settings.ADMIN_COGNITO_USER_POOL_ID,
                    Username=username,
                )
                attributes = {
                    item["Name"]: item["Value"]
                    for item in response.get("UserAttributes", [])
                }
                email = str(attributes.get("email") or "").strip().lower()
            except (BotoCoreError, ClientError):
                LOGGER.exception("admin_identity_email_lookup_failed")
    if "@" not in email:
        raise HTTPException(status_code=403, detail="Administrator email is unavailable.")
    with get_engine().begin() as connection:
        _lock_admin_lifecycle(connection)
        row = connection.execute(
            text(
                """
                SELECT * FROM admin_users
                WHERE cognito_sub = :sub OR lower(email) = :email
                ORDER BY CASE WHEN cognito_sub = :sub THEN 0 ELSE 1 END
                LIMIT 1
                """
            ),
            {"sub": subject, "email": email},
        ).mappings().first()
        if row is None:
            user_count = int(connection.execute(text("SELECT COUNT(*) FROM admin_users")).scalar_one())
            if user_count:
                raise HTTPException(status_code=403, detail="Administrator access has not been assigned.")
            bootstrap_email = str(settings.ADMIN_BOOTSTRAP_SUPER_ADMIN_EMAIL or "").strip().lower()
            if not bootstrap_email or email != bootstrap_email:
                raise HTTPException(status_code=403, detail="Initial administrator access has not been approved.")
            user_id = str(uuid4())
            connection.execute(
                text(
                    """
                    INSERT INTO admin_users (
                        id, cognito_sub, email, role, status, last_login, created_by, created_at, updated_at
                    ) VALUES (:id, :sub, :email, 'super_admin', 'active', now(), 'cognito-sync', now(), now())
                    """
                ),
                {"id": user_id, "sub": subject, "email": email},
            )
        else:
            user_id = str(row["id"])
            if row["status"] == "disabled":
                raise HTTPException(status_code=403, detail="Administrator access is disabled.")
            connection.execute(
                text(
                    """
                    UPDATE admin_users
                    SET cognito_sub = :sub, status = 'active',
                        last_login = now(), updated_at = now()
                    WHERE id = :id
                    """
                ),
                {"id": user_id, "sub": subject},
            )
    user = get_admin_user(user_id)
    if user is None:
        raise HTTPException(status_code=403, detail="Administrator profile is unavailable.")
    return user


def build_principal(claims: dict[str, Any]) -> dict[str, Any]:
    if not settings.ADMIN_RBAC_ENABLED:
        return {
            **claims,
            "role": "super_admin",
            "status": "active",
            "scopes": [{"market": "*", "section": section, "permission": "manage"} for section in ADMIN_SECTIONS],
        }
    if claims.get("auth_method") == "api_key":
        return {**claims, "role": "super_admin", "status": "active", "scopes": []}
    return {**claims, **sync_admin_identity(claims)}


def can_access(principal: dict[str, Any], section: str, permission: str = "view", market: str = "") -> bool:
    if principal.get("status") == "disabled":
        return False
    if principal.get("role") == "super_admin":
        return True
    requested_market = market.upper() if market else ""
    for scope in principal.get("scopes") or []:
        if scope["section"] != section:
            continue
        if requested_market and scope["market"] not in {"*", requested_market}:
            continue
        granted = scope["permission"]
        if granted == "manage" or granted == permission:
            return True
        if section == "knowledge" and granted == "publish" and permission in {"view", "stage"}:
            return True
        if section == "knowledge" and granted == "stage" and permission == "view":
            return True
    return False


def accessible_markets(principal: dict[str, Any], section: str, permission: str = "view") -> set[str]:
    """Return concrete markets available to a principal for one admin section."""
    if principal.get("status") == "disabled":
        return set()
    if principal.get("role") == "super_admin":
        return set(get_country_codes())
    return {
        market
        for market in get_country_codes()
        if can_access(principal, section, permission, market)
    }


def require_admin_access(request: Request, section: str, permission: str = "view", market: str = "") -> dict[str, Any]:
    principal = getattr(request.state, "admin_identity", None) or {}
    if not can_access(principal, section, permission, market):
        raise HTTPException(status_code=403, detail="You do not have access to this admin section or market.")
    return principal


def create_admin_user(
    *,
    email: str,
    role: str,
    scopes: list[dict[str, str]],
    actor_sub: str,
) -> dict[str, Any]:
    normalized_email = email.strip().lower()
    if not EMAIL_RE.fullmatch(normalized_email):
        raise ValueError("Enter a valid email address.")
    if role not in ADMIN_ROLES:
        raise ValueError("Unsupported administrator role.")
    normalized_scopes = _validate_role_scopes(role, _scope_rows(scopes))
    user_id = str(uuid4())
    cognito = get_aws_clients().cognito_idp
    cognito_user_created = False
    try:
        response = cognito.admin_create_user(
            UserPoolId=settings.ADMIN_COGNITO_USER_POOL_ID,
            Username=normalized_email,
            UserAttributes=[
                {"Name": "email", "Value": normalized_email},
                {"Name": "email_verified", "Value": "true"},
            ],
            DesiredDeliveryMediums=["EMAIL"],
        )
        cognito_user_created = True
        _ensure_cognito_admin_group(cognito, normalized_email)
        attributes = {item["Name"]: item["Value"] for item in response.get("User", {}).get("Attributes", [])}
        subject = attributes.get("sub", "")
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO admin_users (
                        id, cognito_sub, email, role, status, created_by, created_at, updated_at
                    ) VALUES (:id, :sub, :email, :role, 'invited', :actor, now(), now())
                    """
                ),
                {"id": user_id, "sub": subject or None, "email": normalized_email, "role": role, "actor": actor_sub},
            )
            _replace_scopes(connection, user_id, normalized_scopes)
            _write_audit(connection, actor_sub, "admin_user.created", user_id)
    except (BotoCoreError, ClientError, SQLAlchemyError):
        if cognito_user_created:
            try:
                cognito.admin_delete_user(UserPoolId=settings.ADMIN_COGNITO_USER_POOL_ID, Username=normalized_email)
            except (BotoCoreError, ClientError):
                LOGGER.warning("admin_user_compensation_failed")
        LOGGER.exception("admin_user_create_failed")
        raise
    return get_admin_user(user_id) or {}


def update_admin_user(
    user_id: str,
    *,
    role: str,
    scopes: list[dict[str, str]],
    actor_sub: str,
) -> dict[str, Any]:
    if role not in ADMIN_ROLES:
        raise ValueError("Unsupported administrator role.")
    normalized_scopes = _validate_role_scopes(role, _scope_rows(scopes))
    with get_engine().begin() as connection:
        _lock_admin_lifecycle(connection)
        current = connection.execute(
            text("SELECT role, status, cognito_sub FROM admin_users WHERE id = :id FOR UPDATE"),
            {"id": user_id},
        ).mappings().first()
        if not current:
            raise KeyError(user_id)
        if current["role"] == "super_admin" and role != "super_admin":
            if str(current.get("cognito_sub") or "") == actor_sub:
                raise ValueError("You cannot remove your own Super Admin access.")
            if current["status"] == "active" and _active_super_admins_other_than(connection, user_id) == 0:
                raise ValueError("At least one active Super Admin must remain.")
        result = connection.execute(
            text("UPDATE admin_users SET role = :role, updated_at = now() WHERE id = :id"),
            {"role": role, "id": user_id},
        )
        if result.rowcount == 0:
            raise KeyError(user_id)
        _replace_scopes(connection, user_id, normalized_scopes)
        _write_audit(connection, actor_sub, "admin_user.updated", user_id)
    return get_admin_user(user_id) or {}


def set_admin_user_enabled(user_id: str, enabled: bool, actor_sub: str) -> dict[str, Any]:
    user = get_admin_user(user_id)
    if not user:
        raise KeyError(user_id)
    cognito = get_aws_clients().cognito_idp
    if enabled:
        cognito.admin_enable_user(
            UserPoolId=settings.ADMIN_COGNITO_USER_POOL_ID,
            Username=user["email"],
        )
        with get_engine().begin() as connection:
            connection.execute(
                text("UPDATE admin_users SET status = 'active', disabled_at = NULL, updated_at = now() WHERE id = :id"),
                {"id": user_id},
            )
            _write_audit(connection, actor_sub, "admin_user.enabled", user_id)
        return get_admin_user(user_id) or {}

    with get_engine().begin() as connection:
        _lock_admin_lifecycle(connection)
        current = connection.execute(
            text("SELECT role, status, cognito_sub FROM admin_users WHERE id = :id FOR UPDATE"),
            {"id": user_id},
        ).mappings().first()
        if not current:
            raise KeyError(user_id)
        if str(current.get("cognito_sub") or "") == actor_sub:
            raise ValueError("You cannot disable your own administrator account.")
        if (
            current["role"] == "super_admin"
            and current["status"] == "active"
            and _active_super_admins_other_than(connection, user_id) == 0
        ):
            raise ValueError("At least one active Super Admin must remain.")
        connection.execute(
            text("UPDATE admin_users SET status = 'disabled', disabled_at = now(), updated_at = now() WHERE id = :id"),
            {"id": user_id},
        )
        _write_audit(connection, actor_sub, "admin_user.disable_requested", user_id)
    try:
        cognito.admin_disable_user(
            UserPoolId=settings.ADMIN_COGNITO_USER_POOL_ID,
            Username=user["email"],
        )
    except (BotoCoreError, ClientError):
        with get_engine().begin() as connection:
            _write_audit(connection, actor_sub, "admin_user.disable_cognito_failed", user_id)
        raise
    with get_engine().begin() as connection:
        _write_audit(connection, actor_sub, "admin_user.disabled", user_id)
    return get_admin_user(user_id) or {}


def resend_admin_invite(user_id: str, actor_sub: str) -> dict[str, Any]:
    user = get_admin_user(user_id)
    if not user:
        raise KeyError(user_id)
    cognito = get_aws_clients().cognito_idp
    cognito.admin_create_user(
        UserPoolId=settings.ADMIN_COGNITO_USER_POOL_ID,
        Username=user["email"],
        MessageAction="RESEND",
        DesiredDeliveryMediums=["EMAIL"],
    )
    _ensure_cognito_admin_group(cognito, user["email"])
    with get_engine().begin() as connection:
        _write_audit(connection, actor_sub, "admin_user.invite_resent", user_id)
    return user
