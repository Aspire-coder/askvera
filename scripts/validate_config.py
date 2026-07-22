"""Fail-fast startup configuration validator."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings

PLACEHOLDER_PREFIX = "REPLACE_WITH"
DEVELOPMENT_SECRETS = {"dev-admin-key", "dev-only-change-before-production"}


def _is_missing(value: object) -> bool:
    return value in (None, "") or (isinstance(value, str) and value.startswith(PLACEHOLDER_PREFIX))


def _require(missing: list[str], name: str) -> None:
    if _is_missing(getattr(settings, name, "")):
        missing.append(name)


def validate() -> list[str]:
    """Return missing or placeholder required setting names."""
    missing: list[str] = []
    for name in settings.REQUIRED_VALUES:
        _require(missing, name)

    if settings.APP_ENV != "production":
        return missing

    for name in (
        "WIDGET_JWT_SECRET",
        "BEDROCK_MODEL_ARN",
        "BEDROCK_GUARDRAIL_ID",
        "BEDROCK_GUARDRAIL_VERSION",
        "SQS_FEEDBACK_QUEUE_URL",
    ):
        _require(missing, name)

    if settings.ADMIN_AUTH_MODE not in {"cognito", "api_key", "either"}:
        missing.append("ADMIN_AUTH_MODE (must be cognito, api_key, or either)")
    if settings.ADMIN_AUTH_MODE in {"cognito", "either"}:
        for name in ("ADMIN_COGNITO_USER_POOL_ID", "ADMIN_COGNITO_CLIENT_ID"):
            _require(missing, name)
    if settings.ADMIN_AUTH_MODE in {"api_key", "either"}:
        _require(missing, "ADMIN_API_KEY")
        if settings.ADMIN_API_KEY in DEVELOPMENT_SECRETS:
            missing.append("ADMIN_API_KEY (development value is not allowed)")
    if settings.ADMIN_AUTH_MODE == "cognito" and settings.ADMIN_AUTH_ALLOW_API_KEY:
        missing.append("ADMIN_AUTH_ALLOW_API_KEY (must be false for cognito-only production auth)")
    if settings.WIDGET_JWT_SECRET in DEVELOPMENT_SECRETS:
        missing.append("WIDGET_JWT_SECRET (development value is not allowed)")
    if not settings.WIDGET_AUTH_REQUIRED:
        missing.append("WIDGET_AUTH_REQUIRED (must be true in production)")
    if settings.WIDGET_ALLOW_LOCALHOST_ORIGINS:
        missing.append("WIDGET_ALLOW_LOCALHOST_ORIGINS (must be false in production)")
    if settings.CHAT_MEMORY_BACKEND != "postgres":
        missing.append("CHAT_MEMORY_BACKEND (must be postgres in production)")
    if not settings.SHARED_SECURITY_STATE_ENABLED or not settings.SHARED_SECURITY_STATE_REQUIRED:
        missing.append("SHARED_SECURITY_STATE_REQUIRED (must be enabled in production)")

    if settings.RETRIEVAL_PROVIDER == "opensearch_section":
        _require(missing, "OPENSEARCH_ENDPOINT")
        _require(missing, "OPENSEARCH_INDEX")
    if settings.AUDIT_FIREHOSE_ENABLED:
        _require(missing, "AUDIT_FIREHOSE_STREAM")
    if settings.SUPPORT_EMAIL_ENABLED:
        _require(missing, "SUPPORT_EMAIL_FROM")
        has_market_routes = any(
            isinstance(route, dict) and route.get("department") and route.get("email")
            for route in settings.SUPPORT_ROUTES_JSON.values()
        ) if isinstance(settings.SUPPORT_ROUTES_JSON, dict) else False
        default_route = settings.SUPPORT_DEFAULT_ROUTE_JSON
        has_default_route = (
            isinstance(default_route, dict)
            and default_route.get("department")
            and default_route.get("email")
        )
        if not has_market_routes and not has_default_route:
            missing.append("SUPPORT_ROUTES_JSON or SUPPORT_DEFAULT_ROUTE_JSON")
    return missing


def main() -> int:
    """Print validation result and return a process exit code."""
    missing = validate()
    if missing:
        print("AskVera configuration is incomplete. Configure these values through the environment or SSM:")
        for name in missing:
            print(f"- {name}")
        return 1
    print("AskVera configuration is complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
