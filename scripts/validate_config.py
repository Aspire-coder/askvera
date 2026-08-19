"""Fail-fast startup configuration validator."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402

PLACEHOLDER_PREFIX = "REPLACE_WITH"
DEVELOPMENT_SECRETS = {"dev-admin-key", "dev-only-change-before-production"}


def _is_missing(value: object) -> bool:
    return value in (None, "") or (isinstance(value, str) and value.startswith(PLACEHOLDER_PREFIX))


def _require(missing: list[str], name: str) -> None:
    if _is_missing(getattr(settings, name, "")):
        missing.append(name)


def _validate_shadow_retrieval(missing: list[str]) -> None:
    if not settings.RETRIEVAL_SHADOW_ENABLED:
        return
    if settings.RETRIEVAL_VNEXT_PROVIDER != "opensearch_section":
        missing.append("RETRIEVAL_VNEXT_PROVIDER (must be opensearch_section for isolated shadow testing)")
    _require(missing, "OPENSEARCH_VNEXT_INDEX")
    if settings.OPENSEARCH_VNEXT_INDEX == settings.OPENSEARCH_INDEX:
        missing.append("OPENSEARCH_VNEXT_INDEX (must differ from OPENSEARCH_INDEX)")
    if not 0.0 < settings.RETRIEVAL_SHADOW_SAMPLE_RATE <= 1.0:
        missing.append("RETRIEVAL_SHADOW_SAMPLE_RATE (must be greater than 0 and at most 1)")
    if settings.RETRIEVAL_VNEXT_RERANK_ENABLED:
        _require(missing, "RETRIEVAL_VNEXT_RERANK_MODEL_ARN")
        if settings.RETRIEVAL_VNEXT_RERANK_CANDIDATE_COUNT < settings.OPENSEARCH_RESULT_COUNT:
            missing.append(
                "RETRIEVAL_VNEXT_RERANK_CANDIDATE_COUNT "
                "(must be at least OPENSEARCH_RESULT_COUNT)"
            )


def _validate_retrieval_experiments(missing: list[str]) -> None:
    """Validate opt-in retrieval controls without enabling any of them."""
    if settings.RETRIEVAL_RRF_K <= 0:
        missing.append("RETRIEVAL_RRF_K (must be greater than 0)")
    if settings.RETRIEVAL_MAX_RESULTS_PER_PARENT <= 0:
        missing.append("RETRIEVAL_MAX_RESULTS_PER_PARENT (must be greater than 0)")
    if settings.RETRIEVAL_NEIGHBOR_LIMIT < 0:
        missing.append("RETRIEVAL_NEIGHBOR_LIMIT (must not be negative)")
    for name in (
        "RETRIEVAL_PROMOTION_MIN_SAME_SECTION_RATE",
        "RETRIEVAL_PROMOTION_MIN_EVIDENCE_OVERLAP",
    ):
        value = getattr(settings, name)
        if not 0.0 <= value <= 1.0:
            missing.append(f"{name} (must be between 0 and 1)")
    if settings.RETRIEVAL_PROMOTION_MAX_LATENCY_MS <= 0:
        missing.append("RETRIEVAL_PROMOTION_MAX_LATENCY_MS (must be greater than 0)")
    if not 0.0 <= settings.BEDROCK_CONFIDENCE_EVIDENCE_MIN_CONFIDENCE <= settings.BEDROCK_MIN_CONFIDENCE:
        missing.append(
            "BEDROCK_CONFIDENCE_EVIDENCE_MIN_CONFIDENCE "
            "(must be between 0 and BEDROCK_MIN_CONFIDENCE)"
        )


def _validate_semantic_cache(missing: list[str]) -> None:
    """Validate the opt-in semantic cache without enabling it."""
    if settings.SEMANTIC_CACHE_ENABLED and settings.SEMANTIC_CACHE_SHADOW_ENABLED:
        missing.append("SEMANTIC_CACHE_ENABLED and SEMANTIC_CACHE_SHADOW_ENABLED (choose only one mode)")
    if not (settings.SEMANTIC_CACHE_ENABLED or settings.SEMANTIC_CACHE_SHADOW_ENABLED):
        return
    for name in ("REDIS_HOST", "REDIS_CACHE_NAME", "REDIS_USER", "SEMANTIC_CACHE_EMBED_MODEL_ID"):
        _require(missing, name)
    for name in (
        "SEMANTIC_CACHE_THRESHOLD",
        "SEMANTIC_CACHE_MIN_CONFIDENCE",
        "SEMANTIC_CACHE_SHADOW_MIN_ANSWER_AGREEMENT",
    ):
        if not 0.0 <= float(getattr(settings, name)) <= 1.0:
            missing.append(f"{name} (must be between 0 and 1)")
    if not 0.0 <= settings.SEMANTIC_CACHE_MIN_SCORE_MARGIN < 1.0:
        missing.append("SEMANTIC_CACHE_MIN_SCORE_MARGIN (must be at least 0 and less than 1)")
    for name in (
        "SEMANTIC_CACHE_MAX_CANDIDATES",
        "SEMANTIC_CACHE_MAX_ENTRIES",
        "SEMANTIC_CACHE_TTL_SECONDS",
        "SEMANTIC_CACHE_MAX_VECTOR_DIMENSIONS",
    ):
        if int(getattr(settings, name)) <= 0:
            missing.append(f"{name} (must be greater than 0)")


def _validate_production_auth(missing: list[str]) -> None:
    for name in (
        "WIDGET_JWT_SECRET",
        "BEDROCK_MODEL_ARN",
        "BEDROCK_GUARDRAIL_ID",
        "BEDROCK_GUARDRAIL_VERSION",
        "SQS_FEEDBACK_QUEUE_URL",
    ):
        _require(missing, name)

    if settings.ADMIN_AUTH_MODE != "cognito":
        missing.append("ADMIN_AUTH_MODE (must be cognito in production)")
    if settings.ADMIN_AUTH_MODE in {"cognito", "either"}:
        for name in ("ADMIN_COGNITO_USER_POOL_ID", "ADMIN_COGNITO_CLIENT_ID"):
            _require(missing, name)
    if settings.ADMIN_RBAC_ENABLED or settings.ADMIN_USER_MANAGEMENT_ENABLED:
        _require(missing, "ADMIN_COGNITO_REQUIRED_GROUP")
        _require(missing, "ADMIN_BOOTSTRAP_SUPER_ADMIN_EMAIL")
        bootstrap_email = str(settings.ADMIN_BOOTSTRAP_SUPER_ADMIN_EMAIL or "")
        if bootstrap_email and ("@" not in bootstrap_email or "." not in bootstrap_email.rsplit("@", 1)[-1]):
            missing.append("ADMIN_BOOTSTRAP_SUPER_ADMIN_EMAIL (must be a valid email address)")
    if settings.ADMIN_AUTH_MODE in {"api_key", "either"}:
        _require(missing, "ADMIN_API_KEY")
        if settings.ADMIN_API_KEY in DEVELOPMENT_SECRETS:
            missing.append("ADMIN_API_KEY (development value is not allowed)")
    if settings.ADMIN_AUTH_ALLOW_API_KEY:
        missing.append("ADMIN_AUTH_ALLOW_API_KEY (must be false in production)")
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


def _validate_production_integrations(missing: list[str]) -> None:
    _require(missing, "AWS_ACCOUNT_ID")
    _require(missing, "RDS_DB_IDENTIFIER")
    if settings.RETRIEVAL_PROVIDER == "opensearch_section":
        _require(missing, "OPENSEARCH_ENDPOINT")
        _require(missing, "OPENSEARCH_INDEX")
    elif settings.RETRIEVAL_PROVIDER == "bedrock":
        _require(missing, "BEDROCK_KB_ID")
        _require(missing, "BEDROCK_DATA_SOURCE_ID")
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


def _validate_hardened_profile(missing: list[str]) -> None:
    if settings.SECURITY_PROFILE != "hardened":
        return
    for name in (
        "ADMIN_RBAC_ENABLED",
        "ADMIN_USER_MANAGEMENT_ENABLED",
        "ADMIN_DOCUMENT_PREFLIGHT_ENABLED",
        "ADMIN_ANALYTICS_REDACTED_BY_DEFAULT",
        "ADMIN_TEXTRACT_OCR_ENABLED",
        "AUDIT_FIREHOSE_ENABLED",
        "EVIDENCE_GATED_OUTPUT_ENABLED",
        "ADMIN_INGESTION_QUEUE_ENABLED",
        "ADMIN_INGESTION_STAGED_PUBLISH_ENABLED",
        "ADMIN_INGESTION_GENERATION_POINTER_ENABLED",
        "ADMIN_INGESTION_APPROVAL_METADATA_REQUIRED",
        "ADMIN_INGESTION_MALWARE_SCAN_REQUIRED",
        "ENABLE_ALARM_NOTIFICATIONS",
    ):
        if not bool(getattr(settings, name, False)):
            missing.append(f"{name} (must be enabled for the hardened security profile)")
    for name in (
        "ADMIN_INGESTION_QUEUE_URL",
        "ADMIN_INGESTION_DLQ_URL",
        "KNOWLEDGE_UPLOAD_BUCKET",
        "AUDIT_FIREHOSE_STREAM",
    ):
        _require(missing, name)


def validate(*, require_production: bool = False) -> list[str]:
    """Return missing or placeholder required setting names."""
    missing: list[str] = []
    if require_production and settings.APP_ENV != "production":
        missing.append("APP_ENV (must be production for a production restart)")
    for name in settings.REQUIRED_VALUES:
        _require(missing, name)

    _validate_shadow_retrieval(missing)
    _validate_retrieval_experiments(missing)
    _validate_semantic_cache(missing)
    if settings.APP_ENV == "production":
        _validate_production_auth(missing)
        _validate_production_integrations(missing)
        _validate_hardened_profile(missing)
    return missing


def main() -> int:
    """Print validation result and return a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--load-ssm",
        action="store_true",
        help="Load deployed SSM values before validating them.",
    )
    parser.add_argument(
        "--require-production",
        action="store_true",
        help="Require APP_ENV=production for a production restart.",
    )
    args = parser.parse_args()
    if args.load_ssm:
        settings.load_ssm_config()
    missing = validate(require_production=args.require_production)
    if missing:
        print("AskVera configuration is incomplete. Configure these values through the environment or SSM:")
        for name in missing:
            print(f"- {name}")
        return 1
    print("AskVera configuration is complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
