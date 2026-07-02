"""Deploy-time settings for ASK Vera.

Defaults live here for local/dev safety. Production can override these values
from SSM Parameter Store at startup using the `/askverachat/prod/` path.
"""

import json
import os
from typing import Any

# Required values checked by scripts/validate_config.py before startup accepts traffic.
REQUIRED_VALUES = [
    "AWS_REGION",
    "RDS_SECRET_ARN",
    "REDIS_HOST",
    "REDIS_CACHE_NAME",
    "REDIS_USER",
]

# AWS Region where all runtime resources are deployed. Found in AWS Console top-right region selector.
AWS_REGION = "us-east-1"
AWS_ACCOUNT_ID = "615592621509"
BEDROCK_REGION = AWS_REGION
# Public API version returned by /health. Found in release notes or deployment tag.
APP_VERSION = "1.0.0"
# Prompt/cache version values used to invalidate stale AI responses after content or policy changes.
PROMPT_VERSION = "2026-06-29"
KB_VERSION = "2026-06-29"
# RDS PostgreSQL database identifier. Found in RDS -> Databases -> database-1.
RDS_DB_IDENTIFIER = "database-1"
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
# Bedrock Knowledge Base ID. Found in Bedrock -> Knowledge Bases -> your KB -> Knowledge base ID.
BEDROCK_KB_ID = "P482AUAHKM"
# Bedrock data source ID. Found in Bedrock -> Knowledge Bases -> Data sources.
BEDROCK_DATA_SOURCE_ID = "JSAC3THB67"
# Alias matching the SSM key naming used in the AWS setup notes.
BEDROCK_DATASOURCE_ID = BEDROCK_DATA_SOURCE_ID
# Bedrock model ARN or inference profile ARN. Found in Bedrock -> Model access or Inference profiles.
BEDROCK_MODEL_ARN = "arn:aws:bedrock:us-east-1:615592621509:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0"
# Bedrock Guardrail ID. Found in Bedrock -> Guardrails -> your guardrail -> Guardrail ID.
BEDROCK_GUARDRAIL_ID = "idy33rbs9v1i"
# Bedrock Guardrail version. Found in Bedrock -> Guardrails -> Versions.
BEDROCK_GUARDRAIL_VERSION = "DRAFT"
# Minimum retrieval confidence required before answering. Raw HYBRID scores for relevant matches often land around 0.5-0.7.
BEDROCK_MIN_CONFIDENCE = 0.5
# Retrieval configuration and fallback confidence weighting.
BEDROCK_RETRIEVAL_RESULT_COUNT = 5
BEDROCK_FALLBACK_SOURCE_WEIGHT = 0.12
BEDROCK_FALLBACK_CITATION_WEIGHT = 0.08
# S3 bucket backing the Bedrock Knowledge Base approved documents.
S3_BUCKET = "askverachat-prod-kb"
# Session TTL in seconds. Used by PostgreSQL chat_sessions.expires_at.
SESSION_TTL_SECONDS = 7200
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
# Kinesis Firehose delivery stream for audit logs. Found in Kinesis -> Delivery streams.
FIREHOSE_STREAM_NAME = "vera-audit-stream"
KINESIS_FIREHOSE_STREAM_NAME = FIREHOSE_STREAM_NAME
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
]
API_DOMAIN = "api.vera-api.xyz"
WIDGET_DOMAIN = "chat.vera-api.xyz"
# Country and language list returned to the widget by /api/config.
COUNTRIES = [
    {"code": "US", "name": "United States", "languages": [{"code": "en", "name": "English"}, {"code": "es", "name": "Spanish"}]},
    {"code": "CA", "name": "Canada", "languages": [{"code": "en", "name": "English"}, {"code": "fr", "name": "French"}]},
    {"code": "GB", "name": "United Kingdom", "languages": [{"code": "en", "name": "English"}]},
]

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
