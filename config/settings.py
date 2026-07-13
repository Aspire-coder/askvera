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
    "RDS_SECRET_ARN",
    "REDIS_HOST",
    "REDIS_CACHE_NAME",
    "REDIS_USER",
    "LEGAL_BUCKET",
    "LEGAL_PREFIX",
    "LEGAL_VERSION",
]

# AWS Region where all runtime resources are deployed. Found in AWS Console top-right region selector.
AWS_REGION = "us-east-1"
AWS_ACCOUNT_ID = "615592621509"
BEDROCK_REGION = AWS_REGION
# Bedrock embedding model used for app-owned section semantic retrieval.
BEDROCK_EMBED_MODEL_ID = _env_str("BEDROCK_EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
# Public API version returned by /health. Found in release notes or deployment tag.
APP_VERSION = "1.0.0"
# Runtime environment. Production disables development-only auth conveniences.
APP_ENV = _env_str("APP_ENV", "development").lower()
# Prompt/cache version values used to invalidate stale AI responses after content or policy changes.
PROMPT_VERSION = "2026-07-09"
KB_VERSION = "2026-06-29"
# RDS PostgreSQL database identifier. Found in RDS -> Databases -> database-1.
RDS_DB_IDENTIFIER = "database-1"
# RDS PostgreSQL connection target. RDS-managed Secrets Manager credentials may
# only contain username/password, so keep the endpoint in deploy-time config.
RDS_HOST = _env_str("RDS_HOST", "database-1.cebeiie8qr4i.us-east-1.rds.amazonaws.com")
RDS_PORT = _env_int("RDS_PORT", 5432)
RDS_DB_NAME = _env_str("RDS_DB_NAME", "postgres")
# Secrets Manager ARN for the RDS PostgreSQL master credentials. Found in RDS -> database-1 -> Configuration -> Master credentials ARN.
RDS_SECRET_ARN = "arn:aws:secretsmanager:us-east-1:615592621509:secret:rds!db-617fcf32-1ae3-4f45-b803-4378b966fcf6-0xz7wN"
# PostgreSQL connection pool size for the FastAPI process. Tune in production after load testing.
POSTGRES_POOL_SIZE = 5
# Extra PostgreSQL connections allowed above the base pool. Tune in production after load testing.
POSTGRES_MAX_OVERFLOW = 10
# PostgreSQL connection timeout in seconds.
POSTGRES_CONNECT_TIMEOUT_SECONDS = 5
# Default AWS client timeouts and retry budget.
AWS_CONNECT_TIMEOUT_SECONDS = 3
AWS_READ_TIMEOUT_SECONDS = 12
AWS_MAX_ATTEMPTS = 3
# Basic per-IP in-process request limiting for public widget endpoints.
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 30
RATE_LIMIT_PATHS = ["/api/chat", "/api/consent", "/api/feedback"]
RATE_LIMIT_POLICIES = {
    "/api/chat": _env_int("RATE_LIMIT_CHAT_PER_MINUTE", 30),
    "/api/consent": _env_int("RATE_LIMIT_CONSENT_PER_MINUTE", 20),
    "/api/feedback": _env_int("RATE_LIMIT_FEEDBACK_PER_MINUTE", 15),
    "/api/privacy": _env_int("RATE_LIMIT_PRIVACY_PER_MINUTE", 120),
    "/api/config": _env_int("RATE_LIMIT_CONFIG_PER_MINUTE", 120),
    "/api/widget/init": _env_int("RATE_LIMIT_WIDGET_INIT_PER_MINUTE", 10),
    "/api/widget/refresh": _env_int("RATE_LIMIT_WIDGET_REFRESH_PER_MINUTE", 20),
}
MAX_REQUEST_BODY_BYTES = _env_int("MAX_REQUEST_BODY_BYTES", 32768)
# Widget authentication. Keep disabled by default for local/dev until production
# registry values and JWT secret are configured.
WIDGET_AUTH_REQUIRED = _env_bool("WIDGET_AUTH_REQUIRED", False)
WIDGET_JWT_SECRET = _env_str("WIDGET_JWT_SECRET", "dev-only-change-before-production")
WIDGET_JWT_TTL_SECONDS = _env_int("WIDGET_JWT_TTL_SECONDS", 900)
WIDGET_JWT_ISSUER = _env_str("WIDGET_JWT_ISSUER", "ask-vera")
WIDGET_JWT_AUDIENCE = _env_str("WIDGET_JWT_AUDIENCE", "widget-api")
WIDGET_JWT_CLOCK_SKEW_SECONDS = _env_int("WIDGET_JWT_CLOCK_SKEW_SECONDS", 60)
WIDGET_AUTH_PROTECTED_PATHS = ["/api/chat", "/api/consent", "/api/feedback", "/api/privacy", "/api/config", "/api/widget/config"]
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
                "companyName": "ASK Vera",
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
BEDROCK_KB_ID = _env_str("BEDROCK_KB_ID", "P482AUAHKM")
# Bedrock data source ID. Found in Bedrock -> Knowledge Bases -> Data sources.
BEDROCK_DATA_SOURCE_ID = _env_str("BEDROCK_DATA_SOURCE_ID", "JSAC3THB67")
# Alias matching the SSM key naming used in the AWS setup notes.
BEDROCK_DATASOURCE_ID = BEDROCK_DATA_SOURCE_ID
# Bedrock model ARN or inference profile ARN. Found in Bedrock -> Model access or Inference profiles.
BEDROCK_MODEL_ARN = "arn:aws:bedrock:us-east-1:615592621509:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0"
# Bedrock Guardrail ID. Found in Bedrock -> Guardrails -> your guardrail -> Guardrail ID.
BEDROCK_GUARDRAIL_ID = "idy33rbs9v1i"
# Bedrock Guardrail version. Found in Bedrock -> Guardrails -> Versions.
BEDROCK_GUARDRAIL_VERSION = "DRAFT"
# Default model provider selected by the model router.
DEFAULT_MODEL_PROVIDER = _env_str("DEFAULT_MODEL_PROVIDER", "claude")
# Minimum retrieval confidence required before answering. Raw HYBRID scores for relevant policy matches
# can land just below 0.5, so keep this configurable instead of hardcoding a brittle cutoff.
BEDROCK_MIN_CONFIDENCE = _env_float("BEDROCK_MIN_CONFIDENCE", 0.47)
# Allow model generation when the KB returns enough plausible evidence even if
# the blended confidence is slightly below the minimum.
BEDROCK_CONFIDENCE_EVIDENCE_MIN_SOURCES = _env_int("BEDROCK_CONFIDENCE_EVIDENCE_MIN_SOURCES", 3)
BEDROCK_CONFIDENCE_EVIDENCE_TOP_SCORE = _env_float("BEDROCK_CONFIDENCE_EVIDENCE_TOP_SCORE", 0.45)
# Retrieval configuration and fallback confidence weighting.
BEDROCK_RETRIEVAL_RESULT_COUNT = _env_int("BEDROCK_RETRIEVAL_RESULT_COUNT", 5)
BEDROCK_RETRIEVAL_CANDIDATE_COUNT = _env_int(
    "BEDROCK_RETRIEVAL_CANDIDATE_COUNT",
    max(BEDROCK_RETRIEVAL_RESULT_COUNT, 20),
)
BEDROCK_RETRIEVAL_CONFIGURATION = _env_str("BEDROCK_RETRIEVAL_CONFIGURATION", "vector").lower()
BEDROCK_STRONG_LOCAL_MATCH_THRESHOLD = _env_float("BEDROCK_STRONG_LOCAL_MATCH_THRESHOLD", 0.52)
BEDROCK_QUERY_PLANNER_ENABLED = _env_bool("BEDROCK_QUERY_PLANNER_ENABLED", False)
BEDROCK_QUERY_PLANNER_QUERY_COUNT = _env_int("BEDROCK_QUERY_PLANNER_QUERY_COUNT", 4)
BEDROCK_EVIDENCE_SELECTOR_ENABLED = _env_bool("BEDROCK_EVIDENCE_SELECTOR_ENABLED", False)
BEDROCK_EVIDENCE_SELECTOR_CANDIDATE_COUNT = _env_int("BEDROCK_EVIDENCE_SELECTOR_CANDIDATE_COUNT", 30)
BEDROCK_FALLBACK_SOURCE_WEIGHT = 0.12
BEDROCK_FALLBACK_CITATION_WEIGHT = 0.08
# Retrieval backend. Keep "bedrock" as the default production path. Use
# "section" only after loading reviewed policy sections into PostgreSQL and
# validating retrieval quality with the test harness.
RETRIEVAL_PROVIDER = _env_str("RETRIEVAL_PROVIDER", "bedrock").lower()
SECTION_RETRIEVAL_RESULT_COUNT = _env_int("SECTION_RETRIEVAL_RESULT_COUNT", 5)
SECTION_RETRIEVAL_CANDIDATE_COUNT = _env_int("SECTION_RETRIEVAL_CANDIDATE_COUNT", 30)
SECTION_RETRIEVAL_MIN_SCORE = _env_float("SECTION_RETRIEVAL_MIN_SCORE", 0.05)
SECTION_RETRIEVAL_MODE = _env_str("SECTION_RETRIEVAL_MODE", "keyword").lower()
SECTION_RETRIEVAL_VECTOR_CANDIDATE_COUNT = _env_int("SECTION_RETRIEVAL_VECTOR_CANDIDATE_COUNT", 30)
SECTION_RETRIEVAL_VECTOR_WEIGHT = _env_float("SECTION_RETRIEVAL_VECTOR_WEIGHT", 8.0)
# S3 bucket backing the Bedrock Knowledge Base approved documents.
S3_BUCKET = "askverachat-prod-kb"
# S3 location for legal HTML documents returned by /api/privacy.
LEGAL_BUCKET = "askverachat-prod-content"
LEGAL_PREFIX = "legal"
LEGAL_VERSION = "2026.1"
# Session TTL in seconds. Used by PostgreSQL chat_sessions.expires_at.
SESSION_TIMEOUT_HOURS = 2
MAX_SESSION_DAYS = 7
SESSION_TTL_SECONDS = SESSION_TIMEOUT_HOURS * 60 * 60

# Chat memory storage for conversation history.
# Use "postgres" in production. Use "memory" only for local tests or demos.
CHAT_MEMORY_BACKEND = _env_str("CHAT_MEMORY_BACKEND", "postgres").lower()
CHAT_HISTORY_MAX_MESSAGES = _env_int("CHAT_HISTORY_MAX_MESSAGES", 10)
# ElastiCache Valkey cache name. Found in ElastiCache -> Valkey caches.
REDIS_CACHE_NAME = "askverachat-cache"
# ElastiCache Valkey primary endpoint hostname. Found in ElastiCache -> Valkey cache -> Connectivity.
REDIS_HOST = "master.askverachat-cache.iivrdz.use1.cache.amazonaws.com"
# ElastiCache Valkey TLS port. Found in ElastiCache -> Valkey cache details -> Port.
REDIS_PORT = 6379
# Whether Valkey requires in-transit TLS. Found in ElastiCache -> Valkey cache -> Security.
ELASTICACHE_REDIS_TLS = True
# Valkey user configured for the application. Found in ElastiCache -> User groups.
REDIS_USER = "askverachat-app-user"
# Backward-compatible aliases used by older cache code paths.
ELASTICACHE_REDIS_HOST = REDIS_HOST
ELASTICACHE_REDIS_PORT = REDIS_PORT
# Redis TTL for answer cache in seconds. Found in architecture plan for cache layer.
CACHE_TTL_SECONDS = 7200
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
SQS_FEEDBACK_QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/615592621509/askverachat-feedback"
# AWS Comprehend PII language code for PII detection. Found in Comprehend supported language docs.
COMPREHEND_PII_LANGUAGE_CODE = "en"
# Languages supported for Comprehend PII detection by this app.
COMPREHEND_PII_LANGUAGE_CODES = ["en", "es", "fr"]
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
]
API_DOMAIN = "api.vera-api.xyz"
WIDGET_DOMAIN = "chat.vera-api.xyz"
MARKETS_CONFIG_PATH = os.environ.get("MARKETS_CONFIG_PATH", str(Path(__file__).with_name("markets.json")))

SSM_PARAMETER_PATH = os.environ.get("SSM_PARAMETER_PATH", "/askverachat/prod/")
SSM_CONFIG_ENABLED = os.environ.get("SSM_CONFIG_ENABLED", "true").lower() == "true"
_SSM_CONFIG: dict[str, str] = {}


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

    for key, raw_value in loaded.items():
        if key in globals():
            globals()[key] = _coerce_value(globals()[key], raw_value)
        else:
            globals()[key] = raw_value

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

    _SSM_CONFIG = loaded
    return loaded


def get(key: str) -> Any:
    """Get a setting value and raise clearly if it is missing."""
    value = globals().get(key)
    if value in (None, ""):
        raise RuntimeError(f"Missing config key: {key} - check SSM {SSM_PARAMETER_PATH}")
    return value
