"""Deploy-time settings for ASK Vera.

Defaults live here for local/dev safety. Production can override these values
from SSM Parameter Store at startup using the `/askverachat/prod/` path.
"""

import json
import os
from pathlib import Path
from typing import Any


def _env_bool(name: str, default: bool) -> bool:
    """Read a boolean from the process environment with a safe default."""
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    """Read an integer from the process environment with a safe default."""
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return int(raw_value)


def _env_float(name: str, default: float) -> float:
    """Read a float from the process environment with a safe default."""
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return float(raw_value)


def _env_str(name: str, default: str) -> str:
    """Read a string from the process environment with a safe default."""
    return os.environ.get(name, default)


# Required values checked by scripts/validate_config.py before startup accepts traffic.
REQUIRED_VALUES = [
    "AWS_REGION",
    "RDS_HOST",
    "RDS_SECRET_ARN",
    "REDIS_HOST",
    "REDIS_CACHE_NAME",
    "REDIS_USER",
    "S3_BUCKET",
    "LEGAL_BUCKET",
    "LEGAL_PREFIX",
    "LEGAL_VERSION",
]

# AWS Region where all runtime resources are deployed. Found in AWS Console top-right region selector.
AWS_REGION = _env_str("AWS_REGION", "us-east-1")
AWS_ACCOUNT_ID = _env_str("AWS_ACCOUNT_ID", "")
BEDROCK_REGION = _env_str("BEDROCK_REGION", AWS_REGION)
# Bedrock embedding model used for app-owned section semantic retrieval.
BEDROCK_EMBED_MODEL_ID = _env_str("BEDROCK_EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
# Public API version returned by /health. Found in release notes or deployment tag.
APP_VERSION = "1.0.0"
# Runtime environment. Production disables development-only auth conveniences.
APP_ENV = _env_str("APP_ENV", "development").lower()
# Prompt/cache version values used to invalidate stale AI responses after content or policy changes.
PROMPT_VERSION = _env_str("PROMPT_VERSION", "2026-07-17.1")
# Rotate this value whenever approved indexed content is published. Keeping it
# configurable lets the ingestion workflow invalidate stale answers without a
# code change.
KB_VERSION = _env_str("KB_VERSION", "2026-07-15-global-directory-v2")
# Code-owned retrieval behavior version. Bump when query normalization or
# ranking changes so previously cached failures cannot mask a deployed fix.
RETRIEVAL_PIPELINE_VERSION = "2026-08-23-selector-calibration-v4"
# Code-owned response behavior version. Bump when deterministic response
# post-processing changes so stale rendered answers are not served from cache.
RESPONSE_PIPELINE_VERSION = _env_str("RESPONSE_PIPELINE_VERSION", "2026-08-22-legal-output-integrity-v3")
# Code-owned conversation-routing behavior version. Change this when routing
# semantics change so stale cached answers cannot bypass the new router.
CONVERSATION_ROUTING_VERSION = "2026-08-22-verified-risk-routing-v4"
# Code-owned model-routing behavior version. It participates in cache keys so
# routing changes cannot silently reuse answers produced by an older policy.
MODEL_ROUTING_VERSION = "2026-08-19-risk-router-v1"
# RDS PostgreSQL database identifier. Found in RDS -> Databases.
RDS_DB_IDENTIFIER = _env_str("RDS_DB_IDENTIFIER", "")
# RDS PostgreSQL connection target. RDS-managed Secrets Manager credentials may
# only contain username/password, so keep the endpoint in deploy-time config.
RDS_HOST = _env_str("RDS_HOST", "")
RDS_PORT = _env_int("RDS_PORT", 5432)
RDS_DB_NAME = _env_str("RDS_DB_NAME", "postgres")
# Secrets Manager ARN for the RDS PostgreSQL master credentials. Found in RDS -> database-1 -> Configuration -> Master credentials ARN.
RDS_SECRET_ARN = _env_str("RDS_SECRET_ARN", "")
# PostgreSQL connection pool size for the FastAPI process. Tune in production after load testing.
POSTGRES_POOL_SIZE = 5
# Extra PostgreSQL connections allowed above the base pool. Tune in production after load testing.
POSTGRES_MAX_OVERFLOW = 10
# PostgreSQL connection timeout in seconds.
POSTGRES_CONNECT_TIMEOUT_SECONDS = 5
# Schema changes are applied by scripts/run_db_migrations.py. This compatibility
# switch is only for explicitly bootstrapping a fresh local database.
DB_SCHEMA_BOOTSTRAP_ON_STARTUP = _env_bool("DB_SCHEMA_BOOTSTRAP_ON_STARTUP", False)
# Default AWS client timeouts and retry budget.
AWS_CONNECT_TIMEOUT_SECONDS = 3
AWS_READ_TIMEOUT_SECONDS = 12
AWS_MAX_ATTEMPTS = 3
# Interactive chat calls use a bounded budget so a transient dependency does
# not consume the entire request latency budget.
AWS_INTERACTIVE_READ_TIMEOUT_SECONDS = _env_int("AWS_INTERACTIVE_READ_TIMEOUT_SECONDS", 8)
AWS_INTERACTIVE_MAX_ATTEMPTS = _env_int("AWS_INTERACTIVE_MAX_ATTEMPTS", 1)
AWS_PII_READ_TIMEOUT_SECONDS = _env_int("AWS_PII_READ_TIMEOUT_SECONDS", 5)
AWS_PII_MAX_ATTEMPTS = _env_int("AWS_PII_MAX_ATTEMPTS", 1)
# Per-IP request limiting for public widget endpoints. Production uses Valkey
# so limits and token revocations remain consistent across API processes.
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 30
RATE_LIMIT_PATHS = ["/api/chat", "/api/consent", "/api/feedback", "/api/support", "/api/source-link"]
RATE_LIMIT_POLICIES = {
    "/api/chat": _env_int("RATE_LIMIT_CHAT_PER_MINUTE", 30),
    "/api/consent": _env_int("RATE_LIMIT_CONSENT_PER_MINUTE", 20),
    "/api/feedback": _env_int("RATE_LIMIT_FEEDBACK_PER_MINUTE", 15),
    "/api/support": _env_int("RATE_LIMIT_SUPPORT_PER_MINUTE", 5),
    "/api/source-link": _env_int("RATE_LIMIT_SOURCE_LINK_PER_MINUTE", 30),
    "/api/privacy": _env_int("RATE_LIMIT_PRIVACY_PER_MINUTE", 120),
    "/api/config": _env_int("RATE_LIMIT_CONFIG_PER_MINUTE", 120),
    "/api/widget/init": _env_int("RATE_LIMIT_WIDGET_INIT_PER_MINUTE", 10),
    "/api/widget/refresh": _env_int("RATE_LIMIT_WIDGET_REFRESH_PER_MINUTE", 20),
    "/api/session/end": _env_int("RATE_LIMIT_SESSION_END_PER_MINUTE", 20),
    "/api/admin/documents": _env_int("RATE_LIMIT_ADMIN_UPLOAD_PER_MINUTE", 10),
}
SHARED_SECURITY_STATE_ENABLED = _env_bool("SHARED_SECURITY_STATE_ENABLED", True)
SHARED_SECURITY_STATE_REQUIRED = _env_bool("SHARED_SECURITY_STATE_REQUIRED", APP_ENV == "production")
SHARED_SECURITY_STATE_PREFIX = _env_str("SHARED_SECURITY_STATE_PREFIX", "ask-vera:security")
MAX_REQUEST_BODY_BYTES = _env_int("MAX_REQUEST_BODY_BYTES", 32768)
# Admin portal authentication and general knowledge ingestion.
ADMIN_API_KEY = _env_str("ADMIN_API_KEY", "dev-admin-key" if APP_ENV != "production" else "")
ADMIN_AUTH_MODE = _env_str("ADMIN_AUTH_MODE", "api_key" if APP_ENV != "production" else "cognito").lower()
ADMIN_AUTH_ALLOW_API_KEY = _env_bool("ADMIN_AUTH_ALLOW_API_KEY", APP_ENV != "production")
ADMIN_COGNITO_REGION = _env_str("ADMIN_COGNITO_REGION", AWS_REGION)
ADMIN_COGNITO_USER_POOL_ID = _env_str("ADMIN_COGNITO_USER_POOL_ID", "")
ADMIN_COGNITO_CLIENT_ID = _env_str("ADMIN_COGNITO_CLIENT_ID", "")
ADMIN_COGNITO_REQUIRED_GROUP = _env_str("ADMIN_COGNITO_REQUIRED_GROUP", "AskVeraAdmins")
ADMIN_BOOTSTRAP_SUPER_ADMIN_EMAIL = _env_str("ADMIN_BOOTSTRAP_SUPER_ADMIN_EMAIL", "").lower()
ADMIN_UPLOAD_MAX_BYTES = _env_int("ADMIN_UPLOAD_MAX_BYTES", 25 * 1024 * 1024)
ADMIN_RBAC_ENABLED = _env_bool("ADMIN_RBAC_ENABLED", False)
ADMIN_USER_MANAGEMENT_ENABLED = _env_bool("ADMIN_USER_MANAGEMENT_ENABLED", False)
ADMIN_INVITE_EXPIRY_DAYS = _env_int("ADMIN_INVITE_EXPIRY_DAYS", 7)
ADMIN_ACCESS_REVIEW_DAYS = _env_int("ADMIN_ACCESS_REVIEW_DAYS", 90)
WIDGET_CONFIG_ADMIN_ENABLED = _env_bool("WIDGET_CONFIG_ADMIN_ENABLED", False)
WIDGET_KEY_ROTATION_GRACE_HOURS = _env_int("WIDGET_KEY_ROTATION_GRACE_HOURS", 24)
WIDGET_CONFIG_RUNTIME_ENABLED = _env_bool("WIDGET_CONFIG_RUNTIME_ENABLED", False)
WIDGET_LOADER_URL = _env_str("WIDGET_LOADER_URL", "https://d1wzljalfbhsv7.cloudfront.net/widget/latest/widget.js")
WIDGET_STYLES_URL = _env_str("WIDGET_STYLES_URL", "https://d1wzljalfbhsv7.cloudfront.net/widget/latest/widget.css")
WIDGET_ASSET_BUCKET = _env_str("WIDGET_ASSET_BUCKET", "")
WIDGET_ASSET_PUBLIC_BASE_URL = _env_str("WIDGET_ASSET_PUBLIC_BASE_URL", "")
WIDGET_LOGO_MAX_BYTES = _env_int("WIDGET_LOGO_MAX_BYTES", 1024 * 1024)
KNOWLEDGE_UPLOAD_BUCKET = _env_str("KNOWLEDGE_UPLOAD_BUCKET", "")
KNOWLEDGE_UPLOAD_PREFIX = _env_str("KNOWLEDGE_UPLOAD_PREFIX", "approved-knowledge")
ADMIN_INGESTION_QUEUE_ENABLED = _env_bool("ADMIN_INGESTION_QUEUE_ENABLED", False)
ADMIN_INGESTION_QUEUE_URL = _env_str("ADMIN_INGESTION_QUEUE_URL", "")
ADMIN_INGESTION_DLQ_URL = _env_str("ADMIN_INGESTION_DLQ_URL", "")
ADMIN_INGESTION_QUARANTINE_PREFIX = _env_str(
    "ADMIN_INGESTION_QUARANTINE_PREFIX",
    "quarantine/admin-uploads",
)
ADMIN_INGESTION_STAGED_PUBLISH_ENABLED = _env_bool(
    "ADMIN_INGESTION_STAGED_PUBLISH_ENABLED",
    False,
)
ADMIN_INGESTION_GENERATION_POINTER_ENABLED = _env_bool(
    "ADMIN_INGESTION_GENERATION_POINTER_ENABLED",
    False,
)
ADMIN_INGESTION_APPROVAL_METADATA_REQUIRED = _env_bool(
    "ADMIN_INGESTION_APPROVAL_METADATA_REQUIRED",
    False,
)
ADMIN_INGESTION_MALWARE_SCAN_REQUIRED = _env_bool(
    "ADMIN_INGESTION_MALWARE_SCAN_REQUIRED",
    False,
)
ADMIN_TEXTRACT_OCR_ENABLED = _env_bool("ADMIN_TEXTRACT_OCR_ENABLED", False)
ADMIN_TEXTRACT_OCR_TIMEOUT_SECONDS = _env_int("ADMIN_TEXTRACT_OCR_TIMEOUT_SECONDS", 600)
ADMIN_INGESTION_WORKER_WAIT_SECONDS = _env_int("ADMIN_INGESTION_WORKER_WAIT_SECONDS", 20)
ADMIN_INGESTION_WORKER_VISIBILITY_SECONDS = _env_int(
    "ADMIN_INGESTION_WORKER_VISIBILITY_SECONDS",
    900,
)
ADMIN_INGESTION_MAX_ATTEMPTS = _env_int("ADMIN_INGESTION_MAX_ATTEMPTS", 5)
ADMIN_INGESTION_MAX_ARCHIVE_RATIO = _env_int("ADMIN_INGESTION_MAX_ARCHIVE_RATIO", 100)
ADMIN_INGESTION_QUARANTINE_RETENTION_DAYS = _env_int(
    "ADMIN_INGESTION_QUARANTINE_RETENTION_DAYS",
    14,
)
ADMIN_INGESTION_RETIRED_GENERATION_RETENTION_DAYS = _env_int(
    "ADMIN_INGESTION_RETIRED_GENERATION_RETENTION_DAYS",
    30,
)
SECURITY_PROFILE = _env_str("SECURITY_PROFILE", "standard").lower()
# Widget authentication. Keep disabled by default for local/dev until production
# registry values and JWT secret are configured.
WIDGET_AUTH_REQUIRED = _env_bool("WIDGET_AUTH_REQUIRED", False)
WIDGET_JWT_SECRET = _env_str("WIDGET_JWT_SECRET", "dev-only-change-before-production")
WIDGET_JWT_TTL_SECONDS = _env_int("WIDGET_JWT_TTL_SECONDS", 900)
WIDGET_JWT_ISSUER = _env_str("WIDGET_JWT_ISSUER", "ask-vera")
WIDGET_JWT_AUDIENCE = _env_str("WIDGET_JWT_AUDIENCE", "widget-api")
WIDGET_JWT_CLOCK_SKEW_SECONDS = _env_int("WIDGET_JWT_CLOCK_SKEW_SECONDS", 60)
WIDGET_AUTH_PROTECTED_PATHS = [
    "/api/chat",
    "/api/consent",
    "/api/feedback",
    "/api/support",
    "/api/source-link",
    "/api/session/end",
    "/api/privacy",
    "/api/config",
    "/api/widget/config",
]
WIDGET_ALLOW_LOCALHOST_ORIGINS = _env_bool("WIDGET_ALLOW_LOCALHOST_ORIGINS", APP_ENV != "production")
WIDGET_REGISTRY_PROVIDER = _env_str("WIDGET_REGISTRY_PROVIDER", "json")
WIDGET_REGISTRY_TABLE = _env_str("WIDGET_REGISTRY_TABLE", "AskVeraWidgets")
WIDGET_REGISTRY_CACHE_SECONDS = _env_int("WIDGET_REGISTRY_CACHE_SECONDS", 300)
WIDGET_REGISTRY_JSON = _env_str(
    "WIDGET_REGISTRY_JSON",
    json.dumps(
        [
            {
                "widgetId": "askvera-demo",
                "organizationId": "askvera",
                "companyName": "AskVera",
                "metadata": {
                    "logo": "",
                    "theme": "light",
                    "primaryColor": "#2D7FF9",
                },
                "allowedOrigins": [
                    "http://localhost:5173",
                    "http://127.0.0.1:5173",
                    "http://localhost:4173",
                    "http://127.0.0.1:4173",
                    "http://localhost:5174",
                    "http://127.0.0.1:5174",
                    "http://localhost:5175",
                    "http://127.0.0.1:5175",
                    "http://localhost:9000",
                    "http://127.0.0.1:9000",
                    "https://chat.vera-api.xyz",
                    "https://vera-api.xyz",
                ],
                "status": "active",
            }
        ]
    ),
)
# Bedrock Knowledge Base ID. Found in Bedrock -> Knowledge Bases -> your KB -> Knowledge base ID.
BEDROCK_KB_ID = _env_str("BEDROCK_KB_ID", "")
# Bedrock data source ID. Found in Bedrock -> Knowledge Bases -> Data sources.
BEDROCK_DATA_SOURCE_ID = _env_str("BEDROCK_DATA_SOURCE_ID", "")
# Alias matching the SSM key naming used in the AWS setup notes.
BEDROCK_DATASOURCE_ID = BEDROCK_DATA_SOURCE_ID
# Bedrock model ARN or inference profile ARN. Found in Bedrock -> Model access or Inference profiles.
BEDROCK_MODEL_ARN = _env_str("BEDROCK_MODEL_ARN", "")
# Optional secondary generation model. Keep empty until the fallback model has
# passed the same retrieval and validation evaluation suite as the primary.
BEDROCK_FALLBACK_MODEL_ARN = _env_str("BEDROCK_FALLBACK_MODEL_ARN", "")
# Risk-aware generation routing. Production begins in shadow mode; live mode is
# valid only after the same benchmark and evidence-contract checks pass for the
# fast model. Geographic profiles keep inference within the US geography.
MODEL_ROUTING_MODE = _env_str("MODEL_ROUTING_MODE", "off").lower()
BEDROCK_FAST_MODEL_ID = _env_str(
    "BEDROCK_FAST_MODEL_ID",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
)
BEDROCK_COMPLEX_MODEL_ID = _env_str(
    "BEDROCK_COMPLEX_MODEL_ID",
    "us.anthropic.claude-sonnet-5",
)
MODEL_ROUTING_FAST_MIN_CONFIDENCE = _env_float("MODEL_ROUTING_FAST_MIN_CONFIDENCE", 0.75)
MODEL_ROUTING_FAST_MAX_DISTINCT_SOURCES = _env_int("MODEL_ROUTING_FAST_MAX_DISTINCT_SOURCES", 1)
MODEL_ROUTING_FAST_MAX_QUESTION_CHARS = _env_int("MODEL_ROUTING_FAST_MAX_QUESTION_CHARS", 220)
# Configurable US geographic inference prices used only for projected dashboard
# savings. They never affect routing or billing. Refresh them when AWS pricing
# changes and update the label so administrators can see the estimate's basis.
MODEL_ROUTING_FAST_INPUT_USD_PER_MILLION = _env_float("MODEL_ROUTING_FAST_INPUT_USD_PER_MILLION", 1.10)
MODEL_ROUTING_FAST_OUTPUT_USD_PER_MILLION = _env_float("MODEL_ROUTING_FAST_OUTPUT_USD_PER_MILLION", 5.50)
MODEL_ROUTING_COMPLEX_INPUT_USD_PER_MILLION = _env_float("MODEL_ROUTING_COMPLEX_INPUT_USD_PER_MILLION", 2.20)
MODEL_ROUTING_COMPLEX_OUTPUT_USD_PER_MILLION = _env_float("MODEL_ROUTING_COMPLEX_OUTPUT_USD_PER_MILLION", 11.00)
MODEL_ROUTING_PRICING_LABEL = _env_str(
    "MODEL_ROUTING_PRICING_LABEL",
    "US geographic on-demand rates configured 2026-08-19",
)
BEDROCK_CIRCUIT_BREAKER_FAILURE_THRESHOLD = _env_int("BEDROCK_CIRCUIT_BREAKER_FAILURE_THRESHOLD", 3)
BEDROCK_CIRCUIT_BREAKER_RESET_SECONDS = _env_int("BEDROCK_CIRCUIT_BREAKER_RESET_SECONDS", 60)
BEDROCK_SHARED_CIRCUIT_BREAKER_ENABLED = _env_bool("BEDROCK_SHARED_CIRCUIT_BREAKER_ENABLED", False)
BEDROCK_SHARED_CIRCUIT_BREAKER_PREFIX = _env_str(
    "BEDROCK_SHARED_CIRCUIT_BREAKER_PREFIX",
    "ask-vera:model-circuit",
)
# Generous ceiling that prevents runaway responses without shortening normal
# policy and directory answers.
BEDROCK_MAX_OUTPUT_TOKENS = _env_int("BEDROCK_MAX_OUTPUT_TOKENS", 1024)
# Bedrock Guardrail ID. Found in Bedrock -> Guardrails -> your guardrail -> Guardrail ID.
BEDROCK_GUARDRAIL_ID = _env_str("BEDROCK_GUARDRAIL_ID", "")
# Bedrock Guardrail version. Found in Bedrock -> Guardrails -> Versions.
BEDROCK_GUARDRAIL_VERSION = _env_str("BEDROCK_GUARDRAIL_VERSION", "")
# Default model provider selected by the model router.
DEFAULT_MODEL_PROVIDER = _env_str("DEFAULT_MODEL_PROVIDER", "claude")
# Minimum retrieval confidence required before answering. Raw HYBRID scores for relevant policy matches
# can land just below 0.5, so keep this configurable instead of hardcoding a brittle cutoff.
BEDROCK_MIN_CONFIDENCE = _env_float("BEDROCK_MIN_CONFIDENCE", 0.47)
# Allow model generation when the KB returns enough plausible evidence even if
# the blended confidence is slightly below the minimum.
BEDROCK_CONFIDENCE_EVIDENCE_MIN_SOURCES = _env_int("BEDROCK_CONFIDENCE_EVIDENCE_MIN_SOURCES", 3)
BEDROCK_CONFIDENCE_EVIDENCE_TOP_SCORE = _env_float("BEDROCK_CONFIDENCE_EVIDENCE_TOP_SCORE", 0.45)
# The evidence-count override is only for borderline results. It must never
# turn a very low-confidence retrieval into a generated and cacheable answer.
BEDROCK_CONFIDENCE_EVIDENCE_MIN_CONFIDENCE = _env_float(
    "BEDROCK_CONFIDENCE_EVIDENCE_MIN_CONFIDENCE",
    0.35,
)
# Retrieval configuration and fallback confidence weighting.
BEDROCK_RETRIEVAL_RESULT_COUNT = _env_int("BEDROCK_RETRIEVAL_RESULT_COUNT", 5)
BEDROCK_RETRIEVAL_CANDIDATE_COUNT = _env_int(
    "BEDROCK_RETRIEVAL_CANDIDATE_COUNT",
    max(BEDROCK_RETRIEVAL_RESULT_COUNT, 20),
)
BEDROCK_RETRIEVAL_CONFIGURATION = _env_str("BEDROCK_RETRIEVAL_CONFIGURATION", "vector").lower()
BEDROCK_STRONG_LOCAL_MATCH_THRESHOLD = _env_float("BEDROCK_STRONG_LOCAL_MATCH_THRESHOLD", 0.52)
# Generic multilingual query rewriting is enabled by default. It produces
# search phrases from each question at runtime, so new markets do not require
# country-specific aliases in source code or configuration.
BEDROCK_QUERY_PLANNER_ENABLED = _env_bool("BEDROCK_QUERY_PLANNER_ENABLED", True)
BEDROCK_QUERY_PLANNER_QUERY_COUNT = _env_int("BEDROCK_QUERY_PLANNER_QUERY_COUNT", 4)
BEDROCK_QUERY_PLANNER_MAX_QUERY_CHARS = _env_int("BEDROCK_QUERY_PLANNER_MAX_QUERY_CHARS", 500)
BEDROCK_QUERY_PLANNER_MAX_RESPONSE_CHARS = _env_int("BEDROCK_QUERY_PLANNER_MAX_RESPONSE_CHARS", 12000)
BEDROCK_QUERY_PLANNER_MAX_OUTPUT_TOKENS = _env_int("BEDROCK_QUERY_PLANNER_MAX_OUTPUT_TOKENS", 512)
BEDROCK_CONVERSATION_ROUTE_MIN_CONFIDENCE = _env_float("BEDROCK_CONVERSATION_ROUTE_MIN_CONFIDENCE", 0.85)
BEDROCK_SUPPORT_ROUTE_MIN_CONFIDENCE = _env_float("BEDROCK_SUPPORT_ROUTE_MIN_CONFIDENCE", 0.95)
BEDROCK_SUPPORT_ROUTE_MAX_OUTPUT_TOKENS = _env_int("BEDROCK_SUPPORT_ROUTE_MAX_OUTPUT_TOKENS", 128)
BEDROCK_EVIDENCE_SELECTOR_ENABLED = _env_bool("BEDROCK_EVIDENCE_SELECTOR_ENABLED", False)
BEDROCK_EVIDENCE_SELECTOR_CANDIDATE_COUNT = _env_int("BEDROCK_EVIDENCE_SELECTOR_CANDIDATE_COUNT", 30)
BEDROCK_EVIDENCE_SELECTOR_MAX_OUTPUT_TOKENS = _env_int("BEDROCK_EVIDENCE_SELECTOR_MAX_OUTPUT_TOKENS", 512)
BEDROCK_GLOBAL_TRANSLATION_MAX_OUTPUT_TOKENS = _env_int("BEDROCK_GLOBAL_TRANSLATION_MAX_OUTPUT_TOKENS", 128)
BEDROCK_FALLBACK_SOURCE_WEIGHT = 0.12
BEDROCK_FALLBACK_CITATION_WEIGHT = 0.08
# Retrieval backend. The deployed and evaluated path is OpenSearch section
# retrieval. A missing value must not silently route requests to a retired KB.
RETRIEVAL_PROVIDER = _env_str("RETRIEVAL_PROVIDER", "opensearch_section").lower()
SECTION_RETRIEVAL_RESULT_COUNT = _env_int("SECTION_RETRIEVAL_RESULT_COUNT", 5)
SECTION_RETRIEVAL_CANDIDATE_COUNT = _env_int("SECTION_RETRIEVAL_CANDIDATE_COUNT", 30)
SECTION_RETRIEVAL_MIN_SCORE = _env_float("SECTION_RETRIEVAL_MIN_SCORE", 0.05)
SECTION_RETRIEVAL_MODE = _env_str("SECTION_RETRIEVAL_MODE", "keyword").lower()
SECTION_RETRIEVAL_VECTOR_CANDIDATE_COUNT = _env_int("SECTION_RETRIEVAL_VECTOR_CANDIDATE_COUNT", 30)
SECTION_RETRIEVAL_VECTOR_WEIGHT = _env_float("SECTION_RETRIEVAL_VECTOR_WEIGHT", 8.0)
SECTION_RETRIEVAL_FALLBACK_MIN_SCORE = _env_float("SECTION_RETRIEVAL_FALLBACK_MIN_SCORE", 3.0)
OPENSEARCH_ENDPOINT = _env_str("OPENSEARCH_ENDPOINT", "")
OPENSEARCH_INDEX = _env_str("OPENSEARCH_INDEX", "askvera-policy-sections")
OPENSEARCH_SERVICE = _env_str("OPENSEARCH_SERVICE", "aoss")
OPENSEARCH_RESULT_COUNT = _env_int("OPENSEARCH_RESULT_COUNT", 5)
OPENSEARCH_CANDIDATE_COUNT = _env_int("OPENSEARCH_CANDIDATE_COUNT", 30)
# Raised from 0.25: OpenSearch BM25 text scores (50-80+) were drowning out
# k-NN vector scores (~0-1) even after log-normalization, so paraphrased or
# synonym-only questions rarely out-ranked a weak lexical match. Validate
# against the retrieval canary before promoting further.
OPENSEARCH_VECTOR_WEIGHT = _env_float("OPENSEARCH_VECTOR_WEIGHT", 1.5)
OPENSEARCH_GLOSSARY_ENABLED = _env_bool("OPENSEARCH_GLOSSARY_ENABLED", True)
# Bedrock reranking on the live opensearch_section provider, defaulted OFF: a
# live-index canary run (2026-09-01) showed this environment already had a
# reranker model ARN configured from a prior (now-retired) shadow experiment,
# so enabling this by default silently started reranking real traffic with a
# model that had not been evaluated for that purpose and, in that test,
# picked a worse candidate (Sec 21.03 over the correct 21.05) than no
# reranking at all. Enable only after the model is actually evaluated for the
# live path.
OPENSEARCH_LIVE_RERANK_ENABLED = _env_bool("OPENSEARCH_LIVE_RERANK_ENABLED", False)
OPENSEARCH_RERANK_MODEL_ARN = _env_str("OPENSEARCH_RERANK_MODEL_ARN", "")
OPENSEARCH_GLOSSARY_QUERY_LIMIT = _env_int("OPENSEARCH_GLOSSARY_QUERY_LIMIT", 4)
OPENSEARCH_GLOSSARY_PATH = _env_str("OPENSEARCH_GLOSSARY_PATH", str(Path(__file__).with_name("search_glossary.json")))
OPENSEARCH_EVIDENCE_SELECTOR_ENABLED = _env_bool("OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", False)
OPENSEARCH_EVIDENCE_SELECTOR_CANDIDATE_COUNT = _env_int("OPENSEARCH_EVIDENCE_SELECTOR_CANDIDATE_COUNT", 30)
OPENSEARCH_EVIDENCE_SELECTOR_MAX_OUTPUT_TOKENS = _env_int("OPENSEARCH_EVIDENCE_SELECTOR_MAX_OUTPUT_TOKENS", 512)
OPENSEARCH_SELECTOR_STRONG_MATCH_THRESHOLD = _env_float(
    "OPENSEARCH_SELECTOR_STRONG_MATCH_THRESHOLD",
    0.44,
)
# Ranking and evidence-coverage protections, evaluated as one reversible
# profile (see docs/RETRIEVAL_HARDENING_ROLLOUT.md: 648 unit tests, 7/7 and
# 4/4 legal QA canaries passed locally). Reverted to off after a live-index
# canary run (2026-09-01) showed a real regression: _return_policy_score's
# "100 product satisfaction" phrase match (section_index.py) outranks the
# correct unopened-product buy-back clause (21.05) with the general
# satisfaction-guarantee clause (21.03) that happens to contain that phrase.
# Re-enable only after that heuristic is fixed and re-validated against the
# retrieval_canary.json release-gate fixture on the live index.
OPENSEARCH_RETRIEVAL_HARDENING_ENABLED = _env_bool("OPENSEARCH_RETRIEVAL_HARDENING_ENABLED", False)
RETRIEVAL_RRF_ENABLED = _env_bool("RETRIEVAL_RRF_ENABLED", False)
RETRIEVAL_RRF_K = _env_int("RETRIEVAL_RRF_K", 60)
RETRIEVAL_PARENT_DIVERSITY_ENABLED = _env_bool("RETRIEVAL_PARENT_DIVERSITY_ENABLED", False)
RETRIEVAL_MAX_RESULTS_PER_PARENT = _env_int("RETRIEVAL_MAX_RESULTS_PER_PARENT", 2)
RETRIEVAL_NEIGHBOR_EXPANSION_ENABLED = _env_bool("RETRIEVAL_NEIGHBOR_EXPANSION_ENABLED", False)
RETRIEVAL_NEIGHBOR_LIMIT = _env_int("RETRIEVAL_NEIGHBOR_LIMIT", 2)
RETRIEVAL_PROMOTION_MIN_SAME_SECTION_RATE = _env_float("RETRIEVAL_PROMOTION_MIN_SAME_SECTION_RATE", 0.85)
RETRIEVAL_PROMOTION_MIN_EVIDENCE_OVERLAP = _env_float("RETRIEVAL_PROMOTION_MIN_EVIDENCE_OVERLAP", 0.70)
RETRIEVAL_PROMOTION_MAX_LATENCY_MS = _env_float("RETRIEVAL_PROMOTION_MAX_LATENCY_MS", 1500.0)
# English-language documents for the SAME country become eligible when the
# local-language index has no match; the country filter is untouched, so
# cross-market leakage is not possible. Output language is still enforced by
# app/validation/validators/language_validator.py.
OPENSEARCH_ALLOW_ENGLISH_FALLBACK = _env_bool("OPENSEARCH_ALLOW_ENGLISH_FALLBACK", True)
OPENSEARCH_GLOBAL_DOCUMENT_LANGUAGE = _env_str("OPENSEARCH_GLOBAL_DOCUMENT_LANGUAGE", "en")
# Retained as an explicit runtime flag for startup telemetry and compatibility
# with deployments that expose this setting. Query translation remains governed
# by the existing global-document retrieval path.
OPENSEARCH_GLOBAL_DOCUMENT_TRANSLATION_ENABLED = _env_bool(
    "OPENSEARCH_GLOBAL_DOCUMENT_TRANSLATION_ENABLED",
    False,
)
EMBEDDING_SHARED_CACHE_ENABLED = _env_bool("EMBEDDING_SHARED_CACHE_ENABLED", False)
EMBEDDING_SHARED_CACHE_PREFIX = _env_str("EMBEDDING_SHARED_CACHE_PREFIX", "ask-vera:embedding")
EMBEDDING_SHARED_CACHE_TTL_SECONDS = _env_int("EMBEDDING_SHARED_CACHE_TTL_SECONDS", 604800)
ADMIN_DOCUMENT_PREFLIGHT_ENABLED = _env_bool("ADMIN_DOCUMENT_PREFLIGHT_ENABLED", False)
ADMIN_ANALYTICS_REDACTED_BY_DEFAULT = _env_bool(
    "ADMIN_ANALYTICS_REDACTED_BY_DEFAULT",
    False,
)
ADMIN_ANALYTICS_RAW_TRANSCRIPT_ACCESS_ENABLED = _env_bool(
    "ADMIN_ANALYTICS_RAW_TRANSCRIPT_ACCESS_ENABLED",
    False,
)
ADMIN_INGESTION_MAX_PDF_PAGES = _env_int("ADMIN_INGESTION_MAX_PDF_PAGES", 500)
ADMIN_INGESTION_MAX_EXTRACTED_TEXT_CHARS = _env_int(
    "ADMIN_INGESTION_MAX_EXTRACTED_TEXT_CHARS",
    5_000_000,
)
ADMIN_INGESTION_PARSER_TIMEOUT_SECONDS = _env_int(
    "ADMIN_INGESTION_PARSER_TIMEOUT_SECONDS",
    90,
)
ADMIN_INGESTION_CHUNK_PROFILE = _env_str("ADMIN_INGESTION_CHUNK_PROFILE", "current").lower()
CONVERSATION_ROUTES_PATH = _env_str("CONVERSATION_ROUTES_PATH", str(Path(__file__).with_name("conversation_routes.json")))
# When a country-policy question fails the evidence gate, look up that
# country's contact record in the global sponsoring/office directory and
# offer it instead of a bare "contact support" message. Opt-in: this issues
# one extra retrieval call on the fallback path and has not yet been
# validated against the live index.
FALLBACK_OFFICE_CONTACT_ENABLED = _env_bool("FALLBACK_OFFICE_CONTACT_ENABLED", False)
# Optional staged rollout: require the model to declare the retrieved section IDs
# that support every factual claim before an answer is released.
EVIDENCE_GATED_OUTPUT_ENABLED = _env_bool("EVIDENCE_GATED_OUTPUT_ENABLED", False)
# S3 bucket backing the Bedrock Knowledge Base approved documents.
S3_BUCKET = _env_str("S3_BUCKET", "")
# S3 location for legal HTML documents returned by /api/privacy.
LEGAL_BUCKET = _env_str("LEGAL_BUCKET", "")
LEGAL_PREFIX = _env_str("LEGAL_PREFIX", "legal")
LEGAL_VERSION = _env_str("LEGAL_VERSION", "2026.1")
# Session inactivity timeout. A closed or idle session keeps its transcript for
# retention/audit purposes, but cannot receive additional chat messages.
SESSION_IDLE_TIMEOUT_MINUTES = _env_int("SESSION_IDLE_TIMEOUT_MINUTES", 30)
SESSION_TTL_SECONDS = SESSION_IDLE_TIMEOUT_MINUTES * 60
# Backward-compatible alias for integrations that still read the old setting.
SESSION_TIMEOUT_HOURS = SESSION_TTL_SECONDS / (60 * 60)
MAX_SESSION_DAYS = 7

# Chat memory storage for conversation history.
# Use "postgres" in production. Use "memory" only for local tests or demos.
CHAT_MEMORY_BACKEND = _env_str("CHAT_MEMORY_BACKEND", "postgres").lower()
CHAT_HISTORY_MAX_MESSAGES = _env_int("CHAT_HISTORY_MAX_MESSAGES", 10)
CHAT_TRANSCRIPT_RETENTION_DAYS = _env_int("CHAT_TRANSCRIPT_RETENTION_DAYS", 90)
CHAT_ANALYTICS_RETENTION_DAYS = _env_int("CHAT_ANALYTICS_RETENTION_DAYS", 180)
FEEDBACK_RETENTION_DAYS = _env_int("FEEDBACK_RETENTION_DAYS", 365)
SUPPORT_REQUEST_RETENTION_DAYS = _env_int("SUPPORT_REQUEST_RETENTION_DAYS", 365)
INGESTION_JOB_RETENTION_DAYS = _env_int("INGESTION_JOB_RETENTION_DAYS", 90)
CONSENT_LOG_RETENTION_DAYS = _env_int("CONSENT_LOG_RETENTION_DAYS", 2555)
# ElastiCache Valkey cache name. Found in ElastiCache -> Valkey caches.
REDIS_CACHE_NAME = _env_str("REDIS_CACHE_NAME", "")
# ElastiCache Valkey primary endpoint hostname. Found in ElastiCache -> Valkey cache -> Connectivity.
REDIS_HOST = _env_str("REDIS_HOST", "")
# ElastiCache Valkey TLS port. Found in ElastiCache -> Valkey cache details -> Port.
REDIS_PORT = 6379
# Whether Valkey requires in-transit TLS. Found in ElastiCache -> Valkey cache -> Security.
ELASTICACHE_REDIS_TLS = True
# Valkey user configured for the application. Found in ElastiCache -> User groups.
REDIS_USER = _env_str("REDIS_USER", "")
# Backward-compatible aliases used by older cache code paths.
ELASTICACHE_REDIS_HOST = REDIS_HOST
ELASTICACHE_REDIS_PORT = REDIS_PORT
# Redis TTL for answer cache in seconds. Found in architecture plan for cache layer.
CACHE_TTL_SECONDS = 7200
CACHE_SCHEMA_VERSION = _env_str("CACHE_SCHEMA_VERSION", "4")
# Semantic caching is deliberately opt-in. Exact, versioned caching remains
# the default UAT and production behavior until similarity quality is evaluated.
# Shadow mode is defaulted on so real match/agreement data accumulates for the
# docs/SEMANTIC_CACHE.md rollout gates; it never serves a semantic answer.
SEMANTIC_CACHE_ENABLED = _env_bool("SEMANTIC_CACHE_ENABLED", False)
SEMANTIC_CACHE_SHADOW_ENABLED = _env_bool("SEMANTIC_CACHE_SHADOW_ENABLED", True)
SEMANTIC_CACHE_SCHEMA_VERSION = _env_str("SEMANTIC_CACHE_SCHEMA_VERSION", "1")
SEMANTIC_CACHE_THRESHOLD = _env_float("SEMANTIC_CACHE_THRESHOLD", 0.96)
SEMANTIC_CACHE_MIN_SCORE_MARGIN = _env_float("SEMANTIC_CACHE_MIN_SCORE_MARGIN", 0.02)
SEMANTIC_CACHE_MIN_CONFIDENCE = _env_float("SEMANTIC_CACHE_MIN_CONFIDENCE", 0.75)
SEMANTIC_CACHE_MAX_CANDIDATES = _env_int("SEMANTIC_CACHE_MAX_CANDIDATES", 64)
SEMANTIC_CACHE_MAX_ENTRIES = _env_int("SEMANTIC_CACHE_MAX_ENTRIES", 256)
SEMANTIC_CACHE_TTL_SECONDS = _env_int("SEMANTIC_CACHE_TTL_SECONDS", CACHE_TTL_SECONDS)
SEMANTIC_CACHE_MAX_VECTOR_DIMENSIONS = _env_int("SEMANTIC_CACHE_MAX_VECTOR_DIMENSIONS", 1536)
SEMANTIC_CACHE_EMBED_MODEL_ID = _env_str("SEMANTIC_CACHE_EMBED_MODEL_ID", BEDROCK_EMBED_MODEL_ID)
SEMANTIC_CACHE_SHADOW_MIN_ANSWER_AGREEMENT = _env_float(
    "SEMANTIC_CACHE_SHADOW_MIN_ANSWER_AGREEMENT", 0.70
)
# Audit Firehose sink configuration. Defaults are overridden by production.env, then by SSM.
AUDIT_FIREHOSE_ENABLED = _env_bool("AUDIT_FIREHOSE_ENABLED", False)
AUDIT_FIREHOSE_STREAM = _env_str("AUDIT_FIREHOSE_STREAM", "askvera-audit")
# Maximum number of audit events to send in one future Firehose PutRecordBatch call.
AUDIT_BATCH_SIZE = _env_int("AUDIT_BATCH_SIZE", 100)
# Maximum time in seconds to wait before flushing a future partial audit batch.
AUDIT_BATCH_TIMEOUT_SECONDS = _env_float("AUDIT_BATCH_TIMEOUT_SECONDS", 2.0)
# Maximum number of retry attempts for future transient Firehose failures.
AUDIT_RETRY_MAX_ATTEMPTS = _env_int("AUDIT_RETRY_MAX_ATTEMPTS", 4)
# Initial delay in seconds before the first future Firehose retry.
AUDIT_RETRY_BASE_DELAY_SECONDS = _env_float("AUDIT_RETRY_BASE_DELAY_SECONDS", 1.0)
# Maximum delay in seconds between future Firehose retries.
AUDIT_RETRY_MAX_DELAY_SECONDS = _env_float("AUDIT_RETRY_MAX_DELAY_SECONDS", 8.0)
# Kinesis Firehose delivery stream for audit logs. Found in Kinesis -> Delivery streams.
FIREHOSE_STREAM_NAME = "vera-audit-stream"
KINESIS_FIREHOSE_STREAM_NAME = FIREHOSE_STREAM_NAME
# Metrics provider selection and CloudWatch backend configuration.
ENABLE_METRICS = _env_bool("ENABLE_METRICS", True)
METRICS_PROVIDER = _env_str("METRICS_PROVIDER", "null")
ENABLE_CLOUDWATCH_METRICS = _env_bool("ENABLE_CLOUDWATCH_METRICS", False)
CLOUDWATCH_NAMESPACE = _env_str("CLOUDWATCH_NAMESPACE", "ASKVera")
CLOUDWATCH_BATCH_SIZE = _env_int("CLOUDWATCH_BATCH_SIZE", 20)
CLOUDWATCH_FLUSH_INTERVAL = _env_int("CLOUDWATCH_FLUSH_INTERVAL", 30)
# CloudWatch alarm configuration. Used by monitoring setup scripts, not request handling.
ENABLE_CLOUDWATCH_ALARMS = _env_bool("ENABLE_CLOUDWATCH_ALARMS", False)
CLOUDWATCH_ALARM_PREFIX = _env_str("CLOUDWATCH_ALARM_PREFIX", "AskVera")
CLOUDWATCH_ALARM_HOSTNAME = _env_str("CLOUDWATCH_ALARM_HOSTNAME", "")
EC2_INSTANCE_ID = _env_str("EC2_INSTANCE_ID", "")
REQUEST_LATENCY_THRESHOLD = _env_int("REQUEST_LATENCY_THRESHOLD", 3000)
ERROR_RATE_THRESHOLD = _env_float("ERROR_RATE_THRESHOLD", 5.0)
CACHE_HIT_THRESHOLD = _env_float("CACHE_HIT_THRESHOLD", 60.0)
CPU_THRESHOLD = _env_float("CPU_THRESHOLD", 80.0)
MEMORY_THRESHOLD = _env_float("MEMORY_THRESHOLD", 80.0)
DISK_THRESHOLD = _env_float("DISK_THRESHOLD", 85.0)
MODEL_LATENCY_THRESHOLD = _env_int("MODEL_LATENCY_THRESHOLD", 5000)
PROMPT_BUILD_LATENCY_THRESHOLD = _env_int("PROMPT_BUILD_LATENCY_THRESHOLD", 500)
PIPELINE_HEALTH_THRESHOLD = _env_float("PIPELINE_HEALTH_THRESHOLD", 95.0)
AUDIT_QUEUE_DEPTH_THRESHOLD = _env_int("AUDIT_QUEUE_DEPTH_THRESHOLD", 100)
FIREHOSE_DELIVERY_FAILURE_THRESHOLD = _env_int("FIREHOSE_DELIVERY_FAILURE_THRESHOLD", 0)
# SNS alarm notification configuration. Disabled by default until operators opt in.
ENABLE_ALARM_NOTIFICATIONS = _env_bool("ENABLE_ALARM_NOTIFICATIONS", False)
SNS_TOPIC_NAME = _env_str("SNS_TOPIC_NAME", "askvera-alerts")
SNS_TOPIC_ARN = _env_str("SNS_TOPIC_ARN", "")
SNS_EMAIL_SUBSCRIPTIONS = _env_str("SNS_EMAIL_SUBSCRIPTIONS", "")
CREATE_SNS_TOPIC_IF_MISSING = _env_bool("CREATE_SNS_TOPIC_IF_MISSING", False)
ENABLE_OK_NOTIFICATIONS = _env_bool("ENABLE_OK_NOTIFICATIONS", True)
ENABLE_INSUFFICIENT_DATA_NOTIFICATIONS = _env_bool("ENABLE_INSUFFICIENT_DATA_NOTIFICATIONS", False)
# SQS feedback queue URL. Found in SQS -> Queues -> your feedback queue -> URL.
SQS_FEEDBACK_QUEUE_URL = _env_str("SQS_FEEDBACK_QUEUE_URL", "")
FEEDBACK_EXPECTED_ANSWER_ENABLED = _env_bool("FEEDBACK_EXPECTED_ANSWER_ENABLED", False)
# Support requests are delivered through Amazon SES. Recipient routing remains
# server-side so internal addresses are never exposed in the public widget.
SUPPORT_EMAIL_ENABLED = _env_bool("SUPPORT_EMAIL_ENABLED", False)
SUPPORT_EMAIL_FROM = _env_str("SUPPORT_EMAIL_FROM", "")
SUPPORT_EMAIL_SUBJECT_PREFIX = _env_str("SUPPORT_EMAIL_SUBJECT_PREFIX", "AskVera support request")
ANALYTICS_REPORTS_ENABLED = _env_bool("ANALYTICS_REPORTS_ENABLED", False)
ANALYTICS_REPORT_FROM = _env_str("ANALYTICS_REPORT_FROM", SUPPORT_EMAIL_FROM)
SUPPORT_RECOMMEND_AFTER_FAILURES = _env_int("SUPPORT_RECOMMEND_AFTER_FAILURES", 2)
SUPPORT_ROUTES_JSON: dict[str, dict[str, str]] = json.loads(_env_str("SUPPORT_ROUTES_JSON", "{}"))
SUPPORT_DEFAULT_ROUTE_JSON: dict[str, str] = json.loads(_env_str("SUPPORT_DEFAULT_ROUTE_JSON", "{}"))
# WhatsApp is a disabled integration boundary until Meta credentials,
# verification, and outbound delivery have been provisioned and tested.
WHATSAPP_ENABLED = _env_bool("WHATSAPP_ENABLED", False)
WHATSAPP_VERIFY_TOKEN = _env_str("WHATSAPP_VERIFY_TOKEN", "")
WHATSAPP_APP_SECRET = _env_str("WHATSAPP_APP_SECRET", "")
# AWS Comprehend PII language code for PII detection. Found in Comprehend supported language docs.
COMPREHEND_PII_LANGUAGE_CODE = "en"
# Languages supported by Amazon Comprehend DetectPiiEntities.
COMPREHEND_PII_LANGUAGE_CODES = ["en", "es"]
# Public organization and assistant names that must not be anonymized in approved answers.
PII_APPROVED_PUBLIC_TERMS = ["AskVera", "ASK Vera", "Forever Living"]
# Privacy notice version displayed by /api/config and stored in consent_log.
PRIVACY_VERSION = "2026-05-01"
# Allowed CORS origins for the widget host domains. Found in CloudFront or website deployment settings.
ALLOWED_ORIGINS = [
    "https://chat.vera-api.xyz",
    "https://vera-api.xyz",
    "http://127.0.0.1:5174",
    "http://localhost:5174",
    "http://127.0.0.1:5175",
    "http://localhost:5175",
    "http://127.0.0.1:9000",
    "http://localhost:9000",
    "http://127.0.0.1:5176",
    "http://localhost:5176",
]
API_DOMAIN = "api.vera-api.xyz"
WIDGET_DOMAIN = "chat.vera-api.xyz"
MARKETS_CONFIG_PATH = os.environ.get("MARKETS_CONFIG_PATH", str(Path(__file__).with_name("markets.json")))

SSM_PARAMETER_PATH = os.environ.get("SSM_PARAMETER_PATH", "/askverachat/prod/")
SSM_CONFIG_ENABLED = os.environ.get("SSM_CONFIG_ENABLED", "true").lower() == "true"
_SSM_CONFIG: dict[str, str] = {}
# These values describe deployed source behavior and participate in cache keys.
# Letting an older SSM value override them can make a successful deployment
# continue serving responses created by previous code.
_CODE_OWNED_SETTINGS = {
    "RETRIEVAL_PIPELINE_VERSION",
    "CONVERSATION_ROUTING_VERSION",
    "MODEL_ROUTING_VERSION",
}


def _coerce_value(current_value: Any, raw_value: str) -> Any:
    """Coerce SSM strings to the existing setting type where possible."""
    if isinstance(current_value, bool):
        return raw_value.lower() in {"1", "true", "yes", "on"}
    if isinstance(current_value, int) and not isinstance(current_value, bool):
        return int(raw_value)
    if isinstance(current_value, float):
        return float(raw_value)
    if isinstance(current_value, list):
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
        return [value.strip() for value in raw_value.split(",") if value.strip()]
    if isinstance(current_value, dict):
        return json.loads(raw_value)
    return raw_value


def _apply_ssm_values(loaded: dict[str, str]) -> None:
    """Apply runtime-owned SSM values while preserving code-owned versions."""
    for key, raw_value in loaded.items():
        if key in _CODE_OWNED_SETTINGS:
            continue
        if key in globals():
            globals()[key] = _coerce_value(globals()[key], raw_value)
        else:
            globals()[key] = raw_value


def load_ssm_config(path: str = SSM_PARAMETER_PATH) -> dict[str, str]:
    """Load config overrides from SSM Parameter Store and apply them to this module."""
    global _SSM_CONFIG
    if not SSM_CONFIG_ENABLED:
        return {}

    import boto3

    ssm = boto3.client("ssm", region_name=AWS_REGION)
    paginator = ssm.get_paginator("get_parameters_by_path")
    loaded: dict[str, str] = {}
    for page in paginator.paginate(Path=path, WithDecryption=True, Recursive=False):
        for parameter in page.get("Parameters", []):
            loaded[parameter["Name"].split("/")[-1]] = parameter["Value"]

    _apply_ssm_values(loaded)

    if "REDIS_HOST" in loaded:
        globals()["ELASTICACHE_REDIS_HOST"] = globals()["REDIS_HOST"]
    if "REDIS_PORT" in loaded:
        globals()["ELASTICACHE_REDIS_PORT"] = globals()["REDIS_PORT"]
    if "FIREHOSE_STREAM_NAME" in loaded:
        globals()["KINESIS_FIREHOSE_STREAM_NAME"] = globals()["FIREHOSE_STREAM_NAME"]
    if "BEDROCK_DATA_SOURCE_ID" in loaded:
        globals()["BEDROCK_DATASOURCE_ID"] = globals()["BEDROCK_DATA_SOURCE_ID"]
    if "BEDROCK_DATASOURCE_ID" in loaded:
        globals()["BEDROCK_DATA_SOURCE_ID"] = globals()["BEDROCK_DATASOURCE_ID"]
    if "AWS_REGION" in loaded:
        globals()["BEDROCK_REGION"] = globals()["AWS_REGION"]
    if "BEDROCK_REGION" in loaded and "AWS_REGION" not in loaded:
        globals()["AWS_REGION"] = globals()["BEDROCK_REGION"]
    if "BEDROCK_EMBED_MODEL_ID" in loaded and "SEMANTIC_CACHE_EMBED_MODEL_ID" not in loaded:
        globals()["SEMANTIC_CACHE_EMBED_MODEL_ID"] = globals()["BEDROCK_EMBED_MODEL_ID"]
    if "SESSION_IDLE_TIMEOUT_MINUTES" in loaded:
        globals()["SESSION_TTL_SECONDS"] = int(globals()["SESSION_IDLE_TIMEOUT_MINUTES"]) * 60
        globals()["SESSION_TIMEOUT_HOURS"] = globals()["SESSION_TTL_SECONDS"] / (60 * 60)

    _SSM_CONFIG = loaded
    return loaded


def get(key: str) -> Any:
    """Get a setting value and raise clearly if it is missing."""
    value = globals().get(key)
    if value in (None, ""):
        raise RuntimeError(f"Missing config key: {key} - check SSM {SSM_PARAMETER_PATH}")
    return value
