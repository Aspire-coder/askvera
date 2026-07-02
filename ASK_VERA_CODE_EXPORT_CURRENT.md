# ASK Vera Current Code Export

Generated: 2026-07-02 09:03:17 -04:00

This export includes current source, configuration, deployment, tests, and widget files. Generated dependencies, build outputs, caches, and previous code export documents are excluded.

## File List

- `.pre-commit-config.yaml`
- `AGENTS.md`
- `api\__init__.py`
- `api\middleware.py`
- `api\routes.py`
- `config\__init__.py`
- `config\guardrail_topics.py`
- `config\settings.py`
- `config\vera_persona.py`
- `deployment\bootstrap.sh`
- `deployment\CHECKLIST.md`
- `deployment\deploy.sh`
- `deployment\healthcheck.sh`
- `deployment\nginx\askvera.conf`
- `deployment\production.env.example`
- `deployment\README.md`
- `deployment\rollback.sh`
- `deployment\ssl\certbot.sh`
- `deployment\systemd\askvera.service`
- `main.py`
- `Makefile`
- `PENDING_ITEMS.md`
- `pytest.ini`
- `README.md`
- `scripts\cleanup_expired_sessions.py`
- `scripts\validate_config.py`
- `services\__init__.py`
- `services\audit.py`
- `services\aws_clients.py`
- `services\bedrock.py`
- `services\cache.py`
- `services\consent.py`
- `services\db.py`
- `services\feedback.py`
- `services\guardrails.py`
- `services\pii.py`
- `services\session.py`
- `tests\integration\test_chat_flow.py`
- `tests\unit\test_bedrock.py`
- `tests\unit\test_cache.py`
- `tests\unit\test_guardrails.py`
- `tests\unit\test_pii.py`
- `utils\__init__.py`
- `utils\exceptions.py`
- `utils\logging.py`
- `utils\validators.py`
- `widget-wrapper\demo\index.html`
- `widget-wrapper\demo\src\App.tsx`
- `widget-wrapper\demo\src\main.tsx`
- `widget-wrapper\demo\src\styles.css`
- `widget-wrapper\dist-check\generic-widget-wrapper-check.css`
- `widget-wrapper\package.json`
- `widget-wrapper\package-lock.json`
- `widget-wrapper\README.md`
- `widget-wrapper\src\generic-widget\config\defaultTheme.ts`
- `widget-wrapper\src\generic-widget\config\exampleWidgetConfig.ts`
- `widget-wrapper\src\generic-widget\ConsentPanel.tsx`
- `widget-wrapper\src\generic-widget\examples\BackendChatDemo.tsx`
- `widget-wrapper\src\generic-widget\examples\ChatwootWidgetExample.tsx`
- `widget-wrapper\src\generic-widget\examples\foreverDemoConfig.tsx`
- `widget-wrapper\src\generic-widget\examples\LocalChatwootDemo.tsx`
- `widget-wrapper\src\generic-widget\examples\ThirdPartyWidgetExample.tsx`
- `widget-wrapper\src\generic-widget\FloatingLauncher.tsx`
- `widget-wrapper\src\generic-widget\generic-widget.css`
- `widget-wrapper\src\generic-widget\GenericWidgetWrapper.tsx`
- `widget-wrapper\src\generic-widget\Header.tsx`
- `widget-wrapper\src\generic-widget\index.ts`
- `widget-wrapper\src\generic-widget\integrations\ChatwootWidgetAdapter.tsx`
- `widget-wrapper\src\generic-widget\LegalLinks.tsx`
- `widget-wrapper\src\generic-widget\Menu.tsx`
- `widget-wrapper\src\generic-widget\MessageFeed.tsx`
- `widget-wrapper\src\generic-widget\PlainStateGenericWidgetWrapper.tsx`
- `widget-wrapper\src\generic-widget\RegionSelector.tsx`
- `widget-wrapper\src\generic-widget\types.ts`
- `widget-wrapper\src\generic-widget\utils.ts`
- `widget-wrapper\tsconfig.json`
- `widget-wrapper\vite.config.ts`

## Code

### `.pre-commit-config.yaml`

````yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
  - repo: https://github.com/psf/black
    rev: 24.10.0
    hooks:
      - id: black
  - repo: https://github.com/pycqa/flake8
    rev: 7.1.1
    hooks:
      - id: flake8
````

### `AGENTS.md`

````markdown
## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, invoke the `skill` tool with `skill: "graphify"` before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
````

### `api\__init__.py`

````python
"""API package for ASK Vera."""
````

### `api\middleware.py`

````python
"""Request correlation and structured access logging middleware."""

from collections.abc import Awaitable, Callable
from collections import defaultdict, deque
from time import perf_counter
from time import monotonic
from uuid import uuid4

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings
from utils.logging import get_logger

LOGGER = get_logger("api.middleware")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Injects a correlation ID into every request and response."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Add correlation context, log request completion, and preserve traceability."""
        correlation_id = request.headers.get("x-correlation-id") or str(uuid4())
        request.state.correlation_id = correlation_id
        started = perf_counter()
        response = await call_next(request)
        duration_ms = round((perf_counter() - started) * 1000, 2)
        response.headers["x-correlation-id"] = correlation_id
        LOGGER.info(
            "request_complete",
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Small per-process rate limiter for public widget write endpoints."""

    def __init__(self, app: object) -> None:
        super().__init__(app)
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Reject obvious bursts before they reach AWS-backed services."""
        if request.url.path not in settings.RATE_LIMIT_PATHS:
            return await call_next(request)

        forwarded_for = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded_for.split(",", 1)[0].strip() if forwarded_for else ""
        if not client_ip and request.client:
            client_ip = request.client.host
        key = f"{client_ip or 'unknown'}:{request.url.path}"
        now = monotonic()
        window_start = now - settings.RATE_LIMIT_WINDOW_SECONDS
        history = self._requests[key]
        while history and history[0] < window_start:
            history.popleft()
        if len(history) >= settings.RATE_LIMIT_MAX_REQUESTS:
            LOGGER.warning("rate_limit_exceeded", path=request.url.path, client_ip=client_ip or "unknown")
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": {"code": "RATE_LIMITED", "message": "Too many requests. Please try again shortly."},
                    "correlationId": getattr(request.state, "correlation_id", "unknown"),
                },
            )
        history.append(now)
        return await call_next(request)
````

### `api\routes.py`

````python
"""FastAPI route definitions for ASK Vera."""

from datetime import UTC, datetime
from html import escape
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from config.vera_persona import FALLBACK_RESPONSES
from services import cache as cache_service
from services.audit import write_audit_event
from services.bedrock import retrieve_and_generate
from services.cache import build_cache_key, get_cache_value, set_cache_value
from services.consent import record_consent
from services.db import get_engine
from services.feedback import enqueue_feedback
from services.guardrails import check_text
from services.pii import scrub_pii
from services.session import append_session_turn, get_session_history
from utils.exceptions import AskVeraError, LowConfidenceError
from utils.logging import get_logger
from utils.validators import ChatRequest, ConsentRequest, Envelope, FeedbackRequest

router = APIRouter()
LOGGER = get_logger("api.routes")


def _correlation_id(request: Request) -> str:
    return str(getattr(request.state, "correlation_id", "system"))


def success(data: dict[str, Any], correlation_id: str) -> Envelope:
    """Build a successful response envelope."""
    return Envelope(success=True, data=data, correlationId=correlation_id)


def error_response(exc: AskVeraError, correlation_id: str) -> JSONResponse:
    """Build a consistent error envelope."""
    envelope = Envelope(
        success=False,
        error={"code": exc.error_code, "message": exc.message},
        correlationId=correlation_id,
    )
    return JSONResponse(status_code=exc.status_code, content=envelope.model_dump())


def _valid_language_codes(country_code: str) -> set[str]:
    for country in settings.COUNTRIES:
        if country["code"] == country_code:
            return {language["code"] for language in country["languages"]}
    return set()


@router.post("/api/chat", response_model=None)
def chat(body: ChatRequest, request: Request) -> Envelope | JSONResponse:
    """Answer a user message using RAG-only ASK Vera flow."""
    correlation_id = _correlation_id(request)
    try:
        check_text(body.message, correlation_id)
        scrubbed_input = scrub_pii(body.message, correlation_id, body.language)
        cache_key = build_cache_key(scrubbed_input, body.country, body.language, body.role)
        cached = get_cache_value(cache_key, correlation_id)
        if cached:
            return success({**cached, "correlationId": correlation_id}, correlation_id)
        history = get_session_history(body.sessionId, correlation_id)
        result = retrieve_and_generate(scrubbed_input, body.country, body.language, body.role, history, correlation_id)
        result["response"] = scrub_pii(result["response"], correlation_id, body.language)
        check_text(result["response"], correlation_id)
        append_session_turn(body.sessionId, scrubbed_input, result["response"], correlation_id)
        write_audit_event({"type": "chat", "country": body.country, "language": body.language, "confidence": result["confidence"]}, correlation_id)
        set_cache_value(cache_key, result, correlation_id)
        return success({**result, "correlationId": correlation_id}, correlation_id)
    except LowConfidenceError as exc:
        return success({"response": exc.message, "sources": [], "confidence": 0.0, "correlationId": correlation_id}, correlation_id)
    except AskVeraError as exc:
        return error_response(exc, correlation_id)


@router.get("/api/config")
def config(request: Request) -> Envelope:
    """Return country list, supported languages, and privacy version."""
    correlation_id = _correlation_id(request)
    return success({"countries": settings.COUNTRIES, "privacyVersion": settings.PRIVACY_VERSION}, correlation_id)


@router.get("/api/privacy", response_class=HTMLResponse)
def privacy(country: str, lang: str, request: Request) -> HTMLResponse:
    """Return a privacy notice HTML snippet for a country and language."""
    correlation_id = _correlation_id(request)
    normalized_country = country.upper()
    normalized_lang = lang.lower()
    if normalized_country not in {item["code"] for item in settings.COUNTRIES}:
        return HTMLResponse(content="<section><h1>Privacy Notice</h1><p>Unsupported country.</p></section>", status_code=400)
    if normalized_lang not in _valid_language_codes(normalized_country):
        return HTMLResponse(content="<section><h1>Privacy Notice</h1><p>Unsupported language.</p></section>", status_code=400)
    safe_country = escape(normalized_country)
    safe_lang = escape(normalized_lang)
    safe_version = escape(settings.PRIVACY_VERSION)
    html = (
        f"<section><h1>Privacy Notice</h1><p>Version {safe_version}</p>"
        f"<p>This ASK Vera privacy notice applies to {safe_country} in language {safe_lang}.</p>"
        "<p>ASK Vera stores consent, chat session metadata, feedback, and audit records in AWS for support, compliance, and safety.</p>"
        "<p>Do not enter sensitive personal data into chat unless required for support.</p></section>"
    )
    LOGGER.info("privacy_returned", correlation_id=correlation_id, country=normalized_country, lang=normalized_lang)
    return HTMLResponse(content=html)


@router.post("/api/consent", response_model=None)
def consent(body: ConsentRequest, request: Request) -> Envelope | JSONResponse:
    """Record user privacy consent."""
    correlation_id = _correlation_id(request)
    try:
        record_consent(body, correlation_id)
        return success({"recorded": True}, correlation_id)
    except AskVeraError as exc:
        return error_response(exc, correlation_id)


@router.post("/api/feedback", response_model=None)
def feedback(body: FeedbackRequest, request: Request) -> Envelope | JSONResponse:
    """Send user feedback to SQS."""
    correlation_id = _correlation_id(request)
    try:
        enqueue_feedback(body, correlation_id)
        return success({"queued": True}, correlation_id)
    except AskVeraError as exc:
        return error_response(exc, correlation_id)


@router.get("/health")
def health() -> JSONResponse:
    """Return fast ALB health status without AWS calls."""
    import main

    status = "draining" if main.shutdown_requested else "healthy"
    return JSONResponse(
        status_code=503 if main.shutdown_requested else 200,
        content={"status": status, "version": settings.APP_VERSION, "timestamp": datetime.now(UTC).isoformat()},
    )


@router.get("/health/deep")
def deep_health() -> JSONResponse:
    """Return dependency health for debugging and deployment checks."""
    checks: dict[str, str] = {}
    status_code = 200
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["postgres"] = "healthy"
    except SQLAlchemyError:
        LOGGER.exception("deep_health_postgres_failed", correlation_id="health")
        checks["postgres"] = "unhealthy"
        status_code = 503

    try:
        if cache_service._redis_client is None:
            checks["redis"] = "not_configured"
        else:
            cache_service._redis_client.ping()
            checks["redis"] = "healthy"
    except Exception:
        LOGGER.exception("deep_health_redis_failed", correlation_id="health")
        checks["redis"] = "unhealthy"
        status_code = 503

    configured = {
        "bedrock": all(
            getattr(settings, name, "").startswith("REPLACE_WITH") is False
            for name in ["BEDROCK_KB_ID", "BEDROCK_MODEL_ARN", "BEDROCK_GUARDRAIL_ID", "BEDROCK_GUARDRAIL_VERSION"]
        ),
        "comprehend": bool(settings.COMPREHEND_PII_LANGUAGE_CODE),
        "firehose": bool(settings.KINESIS_FIREHOSE_STREAM_NAME),
        "sqs": bool(settings.SQS_FEEDBACK_QUEUE_URL),
    }
    checks.update({name: "configured" if value else "missing_config" for name, value in configured.items()})
    return JSONResponse(
        status_code=status_code,
        content={"status": "healthy" if status_code == 200 else "unhealthy", "checks": checks, "timestamp": datetime.now(UTC).isoformat()},
    )
````

### `config\__init__.py`

````python
"""Configuration package for ASK Vera."""

from config.settings import get, load_ssm_config as load_config

__all__ = ["get", "load_config"]
````

### `config\guardrail_topics.py`

````python
"""Denied topic definitions used before and after generation."""

DENIED_TOPICS = {
    "income_claim": [
        "guaranteed income",
        "earn a lot of money",
        "financial freedom",
        "replace my salary",
        "get rich",
    ],
    "medical_claim": [
        "cure",
        "treat disease",
        "diagnose",
        "fda approved",
        "heal cancer",
    ],
    "off_topic": [
        "politics",
        "gambling",
        "weapons",
    ],
}
````

### `config\settings.py`

````python
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
# Minimum reranker or retrieval confidence required before answering. Business default from architecture docs.
BEDROCK_MIN_CONFIDENCE = 0.65
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
````

### `config\vera_persona.py`

````python
"""Central ASK Vera persona and fallback responses."""

SYSTEM_PROMPT_TEMPLATE = """
You are ASK Vera, the official support assistant for Forever Living users.

Personality:
- Warm, confident, and professional.
- Clear and direct, with no filler.
- Answer the user's actual question first, then cite sources.
- Use only the retrieved authorised context.
- Keep warmth consistent in every language.

User language: {{user_language}}
User country: {{user_country}}
User role: {{user_role}}
Role content scope: {{role_content_scope}}

Session history:
{{session_history}}

Retrieved authorised chunks:
{{retrieved_chunks}}
"""

ROLE_CONTENT_SCOPES = {
    "new_prospect": "Product information and public company information only.",
    "active_distributor": "Product information, training, policy, and distributor support content.",
    "compliance_officer": "Full policy, IDS, audit, and compliance reference content.",
}

FALLBACK_RESPONSES = {
    "low_confidence": "I do not have authorised information on that yet. Please contact Forever Living support for confirmed guidance.",
    "income_claim": "I cannot provide income projections or guarantees. Please refer to the official Income Disclosure Statement for approved information.",
    "medical_claim": "I cannot provide medical advice or make medical claims. Please speak with a qualified healthcare professional.",
    "bedrock_error": "I am having a brief technical issue reaching the knowledge base. Please try again in a moment.",
    "off_topic": "I can help with Forever Living products, policies, ordering, business support, and approved company information.",
}


def role_scope_for(role: str) -> str:
    """Return the allowed content scope for a user role."""
    return ROLE_CONTENT_SCOPES.get(role, ROLE_CONTENT_SCOPES["new_prospect"])
````

### `deployment\bootstrap.sh`

````bash
#!/usr/bin/env bash
set -euo pipefail

APP_USER="${APP_USER:-askvera}"
APP_DIR="${APP_DIR:-/opt/askvera}"
REPO_URL="${REPO_URL:-https://github.com/Aspire-coder/askvera.git}"
ENV_DIR="${ENV_DIR:-/etc/askvera}"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"
BRANCH="${BRANCH:-main}"
PKG_MANAGER=""

log() {
  echo "[bootstrap] $*"
}

detect_package_manager() {
  if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release
    case "${ID:-}" in
      ubuntu|debian)
        PKG_MANAGER="apt"
        return
        ;;
      amzn|amazon)
        PKG_MANAGER="dnf"
        return
        ;;
    esac

    case "${ID_LIKE:-}" in
      *debian*)
        PKG_MANAGER="apt"
        return
        ;;
      *fedora*|*rhel*)
        PKG_MANAGER="dnf"
        return
        ;;
    esac
  fi

  if command -v apt-get >/dev/null 2>&1; then
    PKG_MANAGER="apt"
  elif command -v dnf >/dev/null 2>&1; then
    PKG_MANAGER="dnf"
  else
    echo "Unsupported OS: expected Ubuntu/Debian with apt or Amazon Linux with dnf." >&2
    exit 1
  fi
}

install_system_packages() {
  case "${PKG_MANAGER}" in
    apt)
      export DEBIAN_FRONTEND=noninteractive
      apt-get update
      apt-get install -y \
        ca-certificates \
        software-properties-common \
        build-essential \
        curl \
        git \
        sudo \
        nginx \
        certbot \
        python3-certbot-nginx \
        python3.11 \
        python3.11-dev \
        python3.11-venv \
        python3-pip
      ;;
    dnf)
      dnf_packages=(
        ca-certificates
        gcc
        gcc-c++
        make
        git
        sudo
        nginx
        certbot
        python3-certbot-nginx
        python3.11
        python3.11-devel
        python3.11-pip
      )
      dnf install -y "${dnf_packages[@]}"
      ;;
    *)
      echo "Unsupported package manager: ${PKG_MANAGER}" >&2
      exit 1
      ;;
  esac
}

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run bootstrap.sh as root." >&2
  exit 1
fi

detect_package_manager
log "Installing system packages with ${PKG_MANAGER}."
install_system_packages

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "${PYTHON_BIN} is not available after package installation." >&2
  echo "On older Ubuntu releases, install Python 3.11 or set PYTHON_BIN to the available interpreter." >&2
  exit 1
fi

if ! id "${APP_USER}" >/dev/null 2>&1; then
  NOLOGIN_SHELL="$(command -v nologin || echo /sbin/nologin)"
  log "Creating service user ${APP_USER}."
  useradd --system --create-home --shell "${NOLOGIN_SHELL}" "${APP_USER}"
fi

mkdir -p "${APP_DIR}" "${ENV_DIR}"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

if [[ ! -d "${APP_DIR}/.git" ]]; then
  if [[ -n "$(find "${APP_DIR}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    echo "${APP_DIR} exists and is not empty, but it is not a Git repository." >&2
    exit 1
  fi
  log "Cloning ${REPO_URL} into ${APP_DIR}."
  sudo -u "${APP_USER}" git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
else
  log "Refreshing existing repository."
  sudo -u "${APP_USER}" git -C "${APP_DIR}" fetch origin "${BRANCH}"
fi

if [[ ! -f "${ENV_DIR}/production.env" ]]; then
  log "Creating ${ENV_DIR}/production.env from template."
  cp "${APP_DIR}/deployment/production.env.example" "${ENV_DIR}/production.env"
  chmod 0640 "${ENV_DIR}/production.env"
  chown root:"${APP_USER}" "${ENV_DIR}/production.env"
else
  log "Keeping existing ${ENV_DIR}/production.env."
fi

log "Installing systemd service."
cp "${APP_DIR}/deployment/systemd/askvera.service" /etc/systemd/system/askvera.service

log "Creating/updating Python virtual environment."
sudo -u "${APP_USER}" "${PYTHON_BIN}" -m venv "${APP_DIR}/.venv"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m pip install --upgrade pip
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m pip install -r "${APP_DIR}/requirements.txt"

log "Enabling systemd service."
systemctl daemon-reload
systemctl enable askvera

log "Validating Python package import and application config."
cd "${APP_DIR}"
set -a
source "${ENV_DIR}/production.env"
set +a
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m compileall api config services utils scripts >/dev/null
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" scripts/validate_config.py

echo "Bootstrap complete. Review ${ENV_DIR}/production.env, run deployment/ssl/certbot.sh, then run deployment/deploy.sh."
````

### `deployment\CHECKLIST.md`

````markdown
# Deployment Checklist

Use this checklist before sending production traffic to ASK Vera.

## AWS And Network

- [ ] EC2 instance is running.
- [ ] EC2 IAM role is attached.
- [ ] Security group allows required inbound traffic.
- [ ] Security group allows outbound AWS service access.
- [ ] DNS `api.vera-api.xyz` points to the API entry point.
- [ ] DNS `chat.vera-api.xyz` points to the widget hosting entry point.
- [ ] SSM parameters are created under `/askverachat/prod/`.
- [ ] Secrets Manager RDS secret is available to the EC2 role.
- [ ] Bedrock Knowledge Base is ready.
- [ ] Bedrock guardrail is published to a numbered version before production.

## Server Bootstrap

- [ ] `deployment/bootstrap.sh` completed successfully.
- [ ] `/etc/askvera/production.env` reviewed.
- [ ] `/opt/askvera` exists and is owned by `askvera`.
- [ ] Python virtual environment exists at `/opt/askvera/.venv`.
- [ ] Python dependencies installed successfully.

## Runtime

- [ ] `askvera.service` installed.
- [ ] `askvera.service` enabled.
- [ ] `askvera.service` starts successfully.
- [ ] `journalctl -u askvera` shows no startup errors.
- [ ] `/health` returns healthy.
- [ ] `/health/deep` returns healthy.

## Nginx And SSL

- [ ] Nginx config installed.
- [ ] Nginx config test passes.
- [ ] Certbot certificate installed.
- [ ] HTTPS works for `api.vera-api.xyz`.
- [ ] HTTP redirects to HTTPS.
- [ ] Certbot renewal timer is enabled.

## Widget

- [ ] Widget build passes.
- [ ] Widget deployed to static hosting.
- [ ] Widget domain loads.
- [ ] Widget points to the production API URL.
- [ ] Browser CORS checks pass.

## End-To-End Services

- [ ] Bedrock responds through `/api/chat`.
- [ ] Redis cache connects.
- [ ] PostgreSQL session storage works.
- [ ] Consent is recorded in PostgreSQL.
- [ ] Comprehend PII detection works.
- [ ] Firehose audit logging works.
- [ ] SQS feedback enqueue works.

## Release Safety

- [ ] `deployment/deploy.sh` completed successfully.
- [ ] `deployment/healthcheck.sh` passed.
- [ ] `deployment/rollback.sh` tested in a non-production run.
- [ ] GitHub Actions CI passed.
- [ ] Current deployed commit recorded.
````

### `deployment\deploy.sh`

````bash
#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/askvera}"
APP_USER="${APP_USER:-askvera}"
SERVICE_NAME="${SERVICE_NAME:-askvera}"
HEALTH_BASE_URL="${HEALTH_BASE_URL:-https://api.vera-api.xyz}"
RUN_TESTS="${RUN_TESTS:-true}"
BRANCH="${BRANCH:-main}"

usage() {
  cat <<USAGE
Usage: sudo ./deployment/deploy.sh [--skip-tests]

Environment overrides:
  APP_DIR=/opt/askvera
  APP_USER=askvera
  SERVICE_NAME=askvera
  HEALTH_BASE_URL=https://api.vera-api.xyz
  BRANCH=main
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-tests)
      RUN_TESTS=false
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

log() {
  echo "[deploy] $*"
}

rollback() {
  local previous_rev="$1"
  if [[ -n "${previous_rev}" ]]; then
    echo "Rolling back to ${previous_rev}" >&2
    sudo -u "${APP_USER}" git -C "${APP_DIR}" checkout "${previous_rev}"
    systemctl restart "${SERVICE_NAME}"
    sleep 3
    PUBLIC_URL="${HEALTH_BASE_URL}" "${APP_DIR}/deployment/healthcheck.sh" || true
  fi
}

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run deploy.sh as root." >&2
  exit 1
fi

log "Deploying ASK Vera from ${APP_DIR}"
cd "${APP_DIR}"

if ! sudo -u "${APP_USER}" git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "${APP_DIR} is not a Git repository. Run bootstrap.sh first." >&2
  exit 1
fi

if [[ ! -x ".venv/bin/python" ]]; then
  echo "${APP_DIR}/.venv is missing or incomplete. Run bootstrap.sh first." >&2
  exit 1
fi

PREVIOUS_REV="$(sudo -u "${APP_USER}" git rev-parse HEAD)"

log "Fetching latest ${BRANCH}."
sudo -u "${APP_USER}" git fetch origin "${BRANCH}"
sudo -u "${APP_USER}" git checkout "${BRANCH}"
sudo -u "${APP_USER}" git pull --ff-only origin "${BRANCH}"

log "Installing Python dependencies."
sudo -u "${APP_USER}" .venv/bin/python -m pip install --upgrade pip
sudo -u "${APP_USER}" .venv/bin/python -m pip install -r requirements.txt

log "Compiling Python source."
sudo -u "${APP_USER}" .venv/bin/python -m compileall api config services utils scripts tests >/dev/null

log "Validating configuration."
sudo -u "${APP_USER}" .venv/bin/python scripts/validate_config.py

if [[ "${RUN_TESTS}" == "true" ]]; then
  log "Running tests."
  sudo -u "${APP_USER}" .venv/bin/python -m pytest tests -q
else
  log "Skipping tests by explicit request."
fi

log "Restarting ${SERVICE_NAME}."
systemctl restart "${SERVICE_NAME}"
sleep 3

log "Running health checks."
if ! PUBLIC_URL="${HEALTH_BASE_URL}" "${APP_DIR}/deployment/healthcheck.sh"; then
  echo "Health check failed after deploy." >&2
  rollback "${PREVIOUS_REV}"
  exit 1
fi

DEPLOYED_REV="$(sudo -u "${APP_USER}" git rev-parse --short HEAD)"
echo "Deployment complete. Deployed commit: ${DEPLOYED_REV}"
````

### `deployment\healthcheck.sh`

````bash
#!/usr/bin/env bash
set -Eeuo pipefail

LOCAL_URL="${LOCAL_URL:-http://127.0.0.1:8000}"
PUBLIC_URL="${PUBLIC_URL:-${BASE_URL:-}}"
CURL_TIMEOUT_SECONDS="${CURL_TIMEOUT_SECONDS:-5}"

check_json_endpoint() {
  local label="$1"
  local base_url="$2"
  local path="$3"
  local expected_status="${4:-200}"
  local tmp_file
  local status
  local url="${base_url}${path}"

  tmp_file="$(mktemp)"
  if ! status="$(curl --silent --show-error --max-time "${CURL_TIMEOUT_SECONDS}" --output "${tmp_file}" --write-out "%{http_code}" "${url}")"; then
    echo "[fail] ${label} failed: ${url} did not respond within ${CURL_TIMEOUT_SECONDS}s." >&2
    rm -f "${tmp_file}"
    return 1
  fi

  if [[ "${status}" != "${expected_status}" ]]; then
    echo "[fail] ${label} failed: ${url} returned HTTP ${status}, expected ${expected_status}." >&2
    cat "${tmp_file}" >&2
    rm -f "${tmp_file}"
    return 1
  fi

  if ! python3 -m json.tool "${tmp_file}" >/dev/null; then
    echo "[fail] ${label} failed: ${url} did not return valid JSON." >&2
    cat "${tmp_file}" >&2
    rm -f "${tmp_file}"
    return 1
  fi

  rm -f "${tmp_file}"
  echo "[ok] ${label}"
}

check_json_endpoint "Local Health" "${LOCAL_URL}" "/health" 200
check_json_endpoint "Local Deep Health" "${LOCAL_URL}" "/health/deep" 200

if [[ -n "${PUBLIC_URL}" ]]; then
  check_json_endpoint "HTTPS Health" "${PUBLIC_URL}" "/health" 200
fi

echo "Health checks passed."
````

### `deployment\nginx\askvera.conf`

````nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    "" close;
}

server {
    listen 80;
    listen [::]:80;
    server_name api.vera-api.xyz;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name api.vera-api.xyz;

    ssl_certificate /etc/letsencrypt/live/api.vera-api.xyz/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.vera-api.xyz/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;

    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 5;
    gzip_min_length 1024;
    gzip_types application/json text/plain text/css application/javascript;

    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    client_max_body_size 512k;
    client_body_timeout 15s;
    send_timeout 60s;
    proxy_connect_timeout 10s;
    proxy_send_timeout 60s;
    proxy_read_timeout 90s;

    location = /health {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        access_log off;
    }

    location = /health/deep {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_buffering on;
    }
}
````

### `deployment\production.env.example`

````text
APP_ENV=production
SSM_CONFIG_ENABLED=true
SSM_PARAMETER_PATH=/askverachat/prod/
HOST=127.0.0.1
PORT=8000
LOG_LEVEL=INFO
PYTHONUNBUFFERED=1
````

### `deployment\README.md`

````markdown
# ASK Vera Deployment

This folder contains repeatable deployment assets for the EC2-hosted FastAPI API.

Production runtime configuration should come from IAM, SSM Parameter Store, and Secrets Manager. Do not place AWS access keys, database passwords, private certificates, or Redis passwords in this folder.

## Files

- `bootstrap.sh` - prepares a fresh Ubuntu EC2 instance.
- `deploy.sh` - pulls the latest code, installs dependencies, validates config, restarts the service, and checks health.
- `rollback.sh` - rolls back to a previous Git revision and restarts the service.
- `healthcheck.sh` - checks `/health` and `/health/deep`.
- `production.env.example` - non-secret runtime environment template.
- `nginx/askvera.conf` - production reverse proxy for `api.vera-api.xyz`.
- `systemd/askvera.service` - systemd unit for Uvicorn.
- `ssl/certbot.sh` - Certbot automation for the API domain.

## First-Time EC2 Setup

```bash
chmod +x deployment/*.sh deployment/ssl/*.sh
sudo REPO_URL=https://github.com/Aspire-coder/askvera.git ./deployment/bootstrap.sh
sudo EMAIL=you@example.com ./deployment/ssl/certbot.sh
sudo ./deployment/deploy.sh
```

`bootstrap.sh` does not enable the HTTPS Nginx site because the certificate does not exist yet. `ssl/certbot.sh` installs a temporary HTTP proxy, obtains the certificate, then installs the production HTTPS config.

## Normal Deploy

```bash
sudo ./deployment/deploy.sh
```

## Health Check

```bash
sudo ./deployment/healthcheck.sh
sudo PUBLIC_URL=https://api.vera-api.xyz ./deployment/healthcheck.sh
```

## Service Operations

```bash
sudo systemctl status askvera --no-pager
sudo systemctl restart askvera
sudo journalctl -u askvera -f
```

## Nginx Operations

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo tail -f /var/log/nginx/access.log /var/log/nginx/error.log
```

## Rollback

```bash
sudo ./deployment/rollback.sh HEAD~1
sudo ./deployment/rollback.sh v1.0.0-beta
sudo ./deployment/rollback.sh 4380931
```

## Widget Deployment

The widget should be built and deployed separately to static hosting such as S3 plus CloudFront for `chat.vera-api.xyz`.

```bash
cd widget-wrapper
npm ci
npm run build:demo
```
````

### `deployment\rollback.sh`

````bash
#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/askvera}"
APP_USER="${APP_USER:-askvera}"
SERVICE_NAME="${SERVICE_NAME:-askvera}"
HEALTH_BASE_URL="${HEALTH_BASE_URL:-https://api.vera-api.xyz}"
TARGET_REV="${1:-HEAD~1}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run rollback.sh as root." >&2
  exit 1
fi

cd "${APP_DIR}"
echo "Rolling ASK Vera back to ${TARGET_REV}"

if ! sudo -u "${APP_USER}" git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "${APP_DIR} is not a Git repository." >&2
  exit 1
fi

sudo -u "${APP_USER}" git fetch --all --tags

if ! RESOLVED_REV="$(sudo -u "${APP_USER}" git rev-parse --verify "${TARGET_REV}^{commit}")"; then
  echo "Rollback target does not exist: ${TARGET_REV}" >&2
  exit 1
fi
CURRENT_REV="$(sudo -u "${APP_USER}" git rev-parse HEAD)"

echo "Current commit: ${CURRENT_REV}"
echo "Target commit: ${RESOLVED_REV}"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "${APP_DIR}/.venv is missing or incomplete. Run bootstrap.sh first." >&2
  exit 1
fi

sudo -u "${APP_USER}" git checkout "${RESOLVED_REV}"
sudo -u "${APP_USER}" .venv/bin/python -m pip install -r requirements.txt
systemctl restart "${SERVICE_NAME}"
sleep 3

if ! PUBLIC_URL="${HEALTH_BASE_URL}" "${APP_DIR}/deployment/healthcheck.sh"; then
  echo "Rollback health check failed. Service may be unhealthy at ${RESOLVED_REV}." >&2
  exit 1
fi

systemctl status "${SERVICE_NAME}" --no-pager
echo "Rollback complete: ${RESOLVED_REV}"
````

### `deployment\ssl\certbot.sh`

````bash
#!/usr/bin/env bash
set -Eeuo pipefail

DOMAIN="${DOMAIN:-api.vera-api.xyz}"
EMAIL="${EMAIL:?Set EMAIL before running certbot.sh}"
APP_DIR="${APP_DIR:-/opt/askvera}"
CURL_TIMEOUT_SECONDS="${CURL_TIMEOUT_SECONDS:-5}"

log() {
  echo "[certbot] $*"
}

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run certbot.sh as root." >&2
  exit 1
fi

if ! getent hosts "${DOMAIN}" >/dev/null; then
  echo "${DOMAIN} does not resolve. Fix DNS before requesting a certificate." >&2
  exit 1
fi

log "Installing Certbot packages if needed."
if ! dpkg -s certbot python3-certbot-nginx openssl >/dev/null 2>&1; then
  apt-get update
  apt-get install -y certbot python3-certbot-nginx openssl
fi

cp "${APP_DIR}/deployment/nginx/askvera.conf" /etc/nginx/sites-available/askvera.conf
ln -sfn /etc/nginx/sites-available/askvera.conf /etc/nginx/sites-enabled/askvera.conf
rm -f /etc/nginx/sites-enabled/default

if [[ ! -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
  log "Installing temporary HTTP Nginx config."
  cat >/etc/nginx/sites-available/askvera.conf <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \\$host;
        proxy_set_header X-Real-IP \\$remote_addr;
        proxy_set_header X-Forwarded-For \\$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \\$scheme;
    }
}
NGINX
fi

nginx -t
systemctl reload nginx || systemctl restart nginx

if ! curl --silent --show-error --max-time "${CURL_TIMEOUT_SECONDS}" "http://${DOMAIN}/health" >/dev/null; then
  echo "HTTP health check failed for ${DOMAIN}. Verify port 80 is open and Nginx can reach FastAPI." >&2
  exit 1
fi

log "Requesting certificate for ${DOMAIN}."
certbot --nginx --non-interactive --agree-tos --redirect --email "${EMAIL}" -d "${DOMAIN}"

if [[ ! -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
  echo "Certificate file was not created for ${DOMAIN}." >&2
  exit 1
fi

openssl x509 -in "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" -noout -subject -issuer -dates

log "Installing production HTTPS Nginx config."
cp "${APP_DIR}/deployment/nginx/askvera.conf" /etc/nginx/sites-available/askvera.conf
nginx -t
systemctl enable certbot.timer
systemctl reload nginx

if ! curl --silent --show-error --fail --max-time "${CURL_TIMEOUT_SECONDS}" "https://${DOMAIN}/health" >/dev/null; then
  echo "HTTPS health check failed for ${DOMAIN} after certificate installation." >&2
  exit 1
fi

echo "Certificate installed for ${DOMAIN}."
````

### `deployment\systemd\askvera.service`

````ini
[Unit]
Description=ASK Vera FastAPI service
Documentation=https://github.com/Aspire-coder/askvera
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=askvera
Group=askvera
WorkingDirectory=/opt/askvera
EnvironmentFile=/etc/askvera/production.env
ExecStart=/opt/askvera/.venv/bin/uvicorn main:app --host 127.0.0.1 --port ${PORT} --proxy-headers --forwarded-allow-ips=127.0.0.1
ExecReload=/bin/kill -HUP $MAINPID
KillSignal=SIGTERM
TimeoutStartSec=60
TimeoutStopSec=30
Restart=on-failure
RestartSec=5
RuntimeDirectory=askvera
RuntimeDirectoryMode=0755
LimitNOFILE=65535
OOMPolicy=continue
SyslogIdentifier=askvera
StandardOutput=journal
StandardError=journal
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectHome=true
ProtectSystem=full
RestrictSUIDSGID=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
CapabilityBoundingSet=
ReadWritePaths=/opt/askvera /run/askvera

[Install]
WantedBy=multi-user.target
````

### `main.py`

````python
"""ASK Vera FastAPI application entry point."""

import signal
import time
from collections.abc import Generator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware import CorrelationIdMiddleware, RateLimitMiddleware
from api.routes import router
from config import settings
from scripts.validate_config import validate
from services.aws_clients import init_aws_clients
from services.cache import close_cache, init_cache
from services.db import close_db, init_db
from utils.exceptions import ConfigurationError
from utils.logging import configure_logging, get_logger

configure_logging()
LOGGER = get_logger("main")
shutdown_requested = False


def _init_optional_cache(max_attempts: int = 3) -> None:
    """Initialise Redis if available, but keep the API online without cache."""
    for attempt in range(max_attempts):
        try:
            init_cache()
            return
        except Exception:
            if attempt == max_attempts - 1:
                LOGGER.exception("redis_cache_unavailable_continuing_without_cache")
                return
            delay_seconds = 2**attempt
            LOGGER.warning(
                "redis_cache_init_retry",
                attempt=attempt + 1,
                max_attempts=max_attempts,
                delay_seconds=delay_seconds,
            )
            time.sleep(delay_seconds)


def _handle_sigterm(signum: int, _frame: object) -> None:
    """Record a graceful shutdown request for EC2 Auto Scaling scale-in."""
    global shutdown_requested
    shutdown_requested = True
    LOGGER.info("shutdown_signal_received", signal=signum)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> Generator[None, None, None]:
    """Validate config, initialise clients, and close cleanly on shutdown."""
    loaded_config = settings.load_ssm_config()
    LOGGER.info(
        "ssm_config_loaded",
        parameter_count=len(loaded_config),
        parameter_path=settings.SSM_PARAMETER_PATH,
        rds_secret_arn=settings.RDS_SECRET_ARN,
    )
    missing = validate()
    if missing:
        raise ConfigurationError(f"Missing required config values: {', '.join(missing)}")
    signal.signal(signal.SIGTERM, _handle_sigterm)
    init_aws_clients()
    init_db()
    _init_optional_cache()
    LOGGER.info("startup_complete")
    yield
    close_cache()
    close_db()
    LOGGER.info("shutdown_complete")


app = FastAPI(title="ASK Vera", version=settings.APP_VERSION, lifespan=lifespan)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(router)
````

### `Makefile`

````makefile
run:
	uvicorn main:app --host 0.0.0.0 --port 8080

test:
	pytest tests/unit --cov=services --cov=utils --cov=api.routes --cov-report=term-missing

lint:
	black --check .
	flake8 .

validate-config:
	python scripts/validate_config.py
````

### `PENDING_ITEMS.md`

````markdown
# Pending Items

This file tracks the remaining setup and production-readiness gaps for the ASK Vera chatbot project.

## High Priority

1. Publish the Bedrock guardrail version when ready.
   - Bedrock Knowledge Base ID is configured.
   - Bedrock data source ID is configured.
   - Bedrock model ARN is configured.
   - Bedrock Guardrail ID is configured.
   - Current guardrail version is `DRAFT`.

2. Decide how local startup should work without AWS access.
   - The app currently initializes AWS Secrets Manager and RDS during startup.
   - Local runs require AWS credentials, network access, and permission to read the RDS secret.
   - Consider adding a local/dev fallback or mock mode if local testing is needed without AWS.

3. Move privacy and consent copy out of the route handler.
   - `/api/privacy` currently returns static generic HTML.
   - Privacy, consent, legal links, country-specific text, and language-specific text should come from config or a content source.

4. Confirm AWS Comprehend access for PII detection.
   - Chat requests currently depend on Comprehend PII detection.
   - If Comprehend is unavailable or the IAM role lacks permission, chat can fail before Bedrock is called.

## Application Behavior Items

1. Decide whether blocked or failed chat turns should be stored.
   - Current session history is updated after successful Bedrock responses.
   - Guardrail-blocked or failed turns may not appear in session history.

2. Decide whether database schema creation should remain in startup.
   - Current code creates tables with `CREATE TABLE IF NOT EXISTS`.
   - For production, consider managed migrations such as Alembic.

3. Schedule expired session cleanup.
   - `scripts/cleanup_expired_sessions.py` can delete expired rows.
   - Production still needs a nightly scheduler such as cron, systemd timer, or EventBridge.

4. Add query rewriting and conversation summarization.
   - These are AI quality improvements after the production hardening pass.
   - Query rewriting should remain grounded in user country/language/role.

## Widget Wrapper Items

1. Decide how the generic widget wrapper should be delivered.
   - Current wrapper code lives in `widget-wrapper`.
   - Local demo is wired to the Python API.
   - Production delivery still needs to confirm whether the widget is served from `chat.vera-api.xyz`, FastAPI static hosting, or a separate frontend/CDN deployment.

2. Add the Chatwoot deployment values.
   - Chatwoot base URL.
   - Chatwoot website token.
   - Final decision on hosted Chatwoot versus self-hosted Chatwoot.
   - Final decision on whether to hide Chatwoot's default bubble and use only the generic wrapper launcher.

3. Install wrapper package dependencies before standalone development.
   - The wrapper has its own `package.json`.
   - Run dependency installation in `widget-wrapper` before using its local build scripts.

4. Confirm final wrapper configuration source.
   - Brand text, starter topics, consent copy, legal links, country options, language options, loading text, and success text should come from config.
   - The wrapper implementation should remain generic and reusable.

## Testing And Cleanup

1. Run the full unit test suite after installing project requirements.
   - Python compile checks passed.
   - Config validation passed.
   - Full `pytest` execution still needs to be run in an environment with test dependencies installed.

2. Clean up generated or stale folders before handoff.
   - Review `graphify-out`.
   - Review `tmp`.
   - Review `__pycache__`.
   - Review generated PDF/output folders.

3. Remove leftover generated document artifacts from the outer project area if they are not needed.
   - Some `.docx` files remain under `dist-generic-widget-check/documents`.
   - These were not part of the Python project and should be cleaned up when file permissions allow.

## Completed AWS Values

- AWS account ID is configured as `615592621509`.
- Production CORS origins are configured for `https://chat.vera-api.xyz` and `https://vera-api.xyz`.
- API domain is recorded as `api.vera-api.xyz`.
- Widget domain is recorded as `chat.vera-api.xyz`.

## Completed Hardening Items

- `/api/privacy` now validates country/language values and escapes rendered HTML values.
- `/api/chat` and `/api/consent` now validate supported country/language pairs.
- `/api/chat` now validates the requested role against configured persona roles.
- Comprehend PII scrubbing now uses the request language when supported.
- AWS clients now use explicit timeout and retry configuration.
- PostgreSQL now uses an explicit connection timeout.
- `/health` now reports `draining` after SIGTERM is received.
- `/health/deep` now checks PostgreSQL and Redis and reports AWS dependency configuration.
- Public write endpoints now have a basic in-process rate limiter.
- Bedrock confidence now uses available retrieval/reranker scores and citation quality instead of a binary source check.
- Source citations now include page, document version, country, language, and score when Bedrock metadata provides them.
- Cache keys now include knowledge base, prompt, guardrail, and model versions.
- Expired session cleanup is implemented in `scripts/cleanup_expired_sessions.py`.
````

### `pytest.ini`

````ini
[pytest]
testpaths = tests/unit
python_files = test_*.py
addopts = -q
````

### `README.md`

````markdown
# ASK Vera

ASK Vera is an AWS-native FastAPI chatbot backend for a public website widget. It uses IAM instance-role authentication only, Bedrock Knowledge Bases for RAG-only answers, Comprehend for PII scrubbing, RDS PostgreSQL for sessions and consent, ElastiCache Valkey for response caching, Kinesis Firehose for audit logs, and SQS for feedback.

## Project Structure

- `api/` - FastAPI routes and middleware.
- `services/` - Bedrock, Valkey, PostgreSQL, Comprehend, Firehose, SQS, consent, session, and guardrail logic.
- `config/` - Non-secret settings, persona, and denied topic definitions.
- `utils/` - Structured logging, typed exceptions, and Pydantic models.
- `tests/` - Unit and gated integration tests.
- `scripts/validate_config.py` - Fails fast when required settings are missing.
- `deployment/` - Repeatable EC2, Nginx, systemd, SSL, health check, and rollback assets.
- `main.py` - App entry point for Uvicorn.
- `widget-wrapper/` - Reusable React + TypeScript widget wrapper package for embedding any assistant, iframe, script widget, or message feed.

## Generic Widget Wrapper

The reusable frontend shell lives in `widget-wrapper/` so the full ASK Vera project stays together in this folder. It exports `GenericWidgetWrapper` and `PlainStateGenericWidgetWrapper`, accepts all visible content through config/props, and contains no brand-specific implementation copy. See `widget-wrapper/README.md` for mock chatbot, iframe, and script embed examples.

## IAM Authentication

No AWS credentials are stored on disk. Boto3 clients are created without explicit keys and use the EC2 instance role `ChatbotAppRole`. Do not add `.env`, credential files, access keys, or secret JSON files. Production settings are loaded from SSM Parameter Store under `/askverachat/prod/` at startup, then RDS credentials are fetched from AWS Secrets Manager using the instance role and held in memory. Valkey uses IAM authentication with the configured Redis user.

## SSM Parameters

Production can override `config/settings.py` with SSM parameters under `/askverachat/prod/`. Current expected keys include:

- `AWS_REGION`
- `RDS_SECRET_ARN`
- `REDIS_HOST`
- `REDIS_PORT`
- `REDIS_USER`
- `BEDROCK_KB_ID`
- `BEDROCK_DATA_SOURCE_ID` / `BEDROCK_DATASOURCE_ID`
- `BEDROCK_MODEL_ARN`
- `BEDROCK_GUARDRAIL_ID`
- `BEDROCK_GUARDRAIL_VERSION`
- `FIREHOSE_STREAM_NAME`
- `SQS_FEEDBACK_QUEUE_URL`
- `S3_BUCKET`

## Configure

Current dev/QA values already configured:

- `AWS_REGION = us-east-1`
- `RDS_DB_IDENTIFIER = database-1`
- `RDS_SECRET_ARN = arn:aws:secretsmanager:us-east-1:615592621509:secret:rds!db-617fcf32-1ae3-4f45-b803-4378b966fcf6-0xz7wN`
- Valkey cache name is `askverachat-cache`, endpoint is `master.askverachat-cache.iivrdz.use1.cache.amazonaws.com:6379`, and Redis user is `askverachat-app-user`.

Fill remaining placeholders in `config/settings.py` after AWS setup is complete. Run:

```bash
python scripts/validate_config.py
```

The app refuses to start unless the currently required foundation values are present. Bedrock Knowledge Base/model/guardrail ID and SQS placeholders are allowed during dev/QA until those resources are created.

## Run Locally

For unit tests, AWS calls are mocked. For the app, use a real AWS environment or mocks around `services.aws_clients`.

```bash
python -m pip install -r requirements.txt
make test
make validate-config
make run
```

## Deploy

Deploy behind CloudFront, WAF, ALB, and an Auto Scaling Group on private EC2 instances. Attach `ChatbotAppRole` to the launch template. Health checks must use `GET /health`, which makes no AWS calls.

Repeatable deployment assets live in `deployment/`:

```bash
sudo ./deployment/bootstrap.sh
sudo EMAIL=you@example.com ./deployment/ssl/certbot.sh
sudo ./deployment/deploy.sh
```

See `deployment/README.md` before running these on EC2.

## Tests

`make test` runs unit tests with coverage. Integration tests are skipped unless `INTEGRATION_TEST=true`.
````

### `scripts\cleanup_expired_sessions.py`

````python
"""Delete expired chat sessions.

Run from the project root with:
python scripts/cleanup_expired_sessions.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from scripts.validate_config import validate
from services.aws_clients import init_aws_clients
from services.db import close_db, init_db
from services.session import cleanup_expired_sessions
from utils.exceptions import ConfigurationError
from utils.logging import configure_logging


def main() -> int:
    """Initialise dependencies, delete expired sessions, and print a short result."""
    configure_logging()
    settings.load_ssm_config()
    missing = validate()
    if missing:
        raise ConfigurationError(f"Missing required config values: {', '.join(missing)}")
    init_aws_clients()
    init_db("session-cleanup")
    deleted = cleanup_expired_sessions()
    close_db("session-cleanup")
    print(f"Deleted expired sessions: {deleted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
````

### `scripts\validate_config.py`

````python
"""Fail-fast startup configuration validator."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings

PLACEHOLDER_PREFIX = "REPLACE_WITH"


def validate() -> list[str]:
    """Return missing or placeholder required setting names."""
    missing: list[str] = []
    for name in settings.REQUIRED_VALUES:
        value = getattr(settings, name, "")
        if value in (None, "") or (isinstance(value, str) and value.startswith(PLACEHOLDER_PREFIX)):
            missing.append(name)
    return missing


def main() -> int:
    """Print validation result and return a process exit code."""
    missing = validate()
    if missing:
        print("ASK Vera configuration is incomplete. Fill these values in config/settings.py:")
        for name in missing:
            print(f"- {name}")
        return 1
    print("ASK Vera configuration is complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
````

### `services\__init__.py`

````python
"""Service package for AWS integrations."""
````

### `services\audit.py`

````python
"""Kinesis Firehose audit logging."""

import json
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from config import settings
from services.aws_clients import get_aws_clients
from utils.exceptions import AwsServiceError
from utils.logging import get_logger

LOGGER = get_logger("services.audit")


def write_audit_event(event: dict[str, Any], correlation_id: str) -> None:
    """Send one audit event to Kinesis Firehose."""
    if settings.KINESIS_FIREHOSE_STREAM_NAME.startswith("REPLACE_WITH"):
        LOGGER.warning("audit_not_configured", correlation_id=correlation_id, event_type=event.get("type", "unknown"))
        return
    payload = {"timestamp": datetime.now(UTC).isoformat(), "correlationId": correlation_id, **event}
    try:
        get_aws_clients().firehose.put_record(
            DeliveryStreamName=settings.KINESIS_FIREHOSE_STREAM_NAME,
            Record={"Data": json.dumps(payload, ensure_ascii=True).encode("utf-8") + b"\n"},
        )
    except (BotoCoreError, ClientError) as exc:
        LOGGER.exception("audit_write_failed", correlation_id=correlation_id)
        raise AwsServiceError("Audit logging failed.") from exc
    LOGGER.info("audit_written", correlation_id=correlation_id, event_type=event.get("type", "unknown"))
````

### `services\aws_clients.py`

````python
"""Application-scoped AWS client container."""

import boto3
from botocore.config import Config

from config import settings


class AwsClients:
    """Creates boto3 clients once using the EC2 IAM instance role."""

    def __init__(self) -> None:
        """Initialise reusable clients without explicit credentials."""
        client_config = Config(
            connect_timeout=settings.AWS_CONNECT_TIMEOUT_SECONDS,
            read_timeout=settings.AWS_READ_TIMEOUT_SECONDS,
            retries={"max_attempts": settings.AWS_MAX_ATTEMPTS, "mode": "standard"},
        )
        self.bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=settings.AWS_REGION, config=client_config)
        self.bedrock_runtime = boto3.client("bedrock-runtime", region_name=settings.AWS_REGION, config=client_config)
        self.comprehend = boto3.client("comprehend", region_name=settings.AWS_REGION, config=client_config)
        self.firehose = boto3.client("firehose", region_name=settings.AWS_REGION, config=client_config)
        self.secretsmanager = boto3.client("secretsmanager", region_name=settings.AWS_REGION, config=client_config)
        self.sqs = boto3.client("sqs", region_name=settings.AWS_REGION, config=client_config)


aws_clients: AwsClients | None = None


def init_aws_clients() -> AwsClients:
    """Create and store application-scoped AWS clients."""
    global aws_clients
    aws_clients = AwsClients()
    return aws_clients


def get_aws_clients() -> AwsClients:
    """Return initialized AWS clients."""
    if aws_clients is None:
        return init_aws_clients()
    return aws_clients
````

### `services\bedrock.py`

````python
"""Bedrock Knowledge Base retrieval and generation calls."""

from typing import Any

from botocore.exceptions import BotoCoreError, ClientError, ReadTimeoutError

from config import settings
from config.vera_persona import FALLBACK_RESPONSES, SYSTEM_PROMPT_TEMPLATE, role_scope_for
from services.aws_clients import get_aws_clients
from utils.exceptions import BedrockServiceError, BedrockTimeoutError, ConfigurationError, LowConfidenceError
from utils.logging import get_logger

LOGGER = get_logger("services.bedrock")


def build_prompt(language: str, country: str, role: str, chunks: str, history: str) -> str:
    """Render the ASK Vera system prompt."""
    return (
        SYSTEM_PROMPT_TEMPLATE.replace("{{user_language}}", language)
        .replace("{{user_country}}", country)
        .replace("{{user_role}}", role)
        .replace("{{role_content_scope}}", role_scope_for(role))
        .replace("{{retrieved_chunks}}", chunks)
        .replace("{{session_history}}", history)
    )


def _metadata_value(metadata: dict[str, Any], *keys: str) -> str:
    """Read the first available metadata value as a string."""
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _reference_score(ref: dict[str, Any]) -> float | None:
    """Extract a retrieval/reranker score from known Bedrock response shapes."""
    metadata = ref.get("metadata", {}) or {}
    candidates = [
        ref.get("score"),
        ref.get("retrievalScore"),
        ref.get("rerankerScore"),
        metadata.get("score"),
        metadata.get("retrieval_score"),
        metadata.get("retrievalScore"),
        metadata.get("reranker_score"),
        metadata.get("rerankerScore"),
    ]
    for candidate in candidates:
        try:
            if candidate is None:
                continue
            score = float(candidate)
            if 0 <= score <= 1:
                return score
            if 1 < score <= 100:
                return score / 100
        except (TypeError, ValueError):
            continue
    return None


def _sources_from_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for citation in response.get("citations", []):
        for ref in citation.get("retrievedReferences", []):
            location = ref.get("location", {})
            uri = location.get("s3Location", {}).get("uri") or location.get("webLocation", {}).get("url") or ""
            metadata = ref.get("metadata", {}) or {}
            if uri:
                sources.append(
                    {
                        "title": _metadata_value(metadata, "title", "document_title") or uri.rsplit("/", 1)[-1],
                        "uri": uri,
                        "excerpt": ref.get("content", {}).get("text", "")[:240],
                        "page": _metadata_value(metadata, "page", "page_number", "x-amz-bedrock-kb-document-page-number"),
                        "documentVersion": _metadata_value(metadata, "document_version", "version", "policy_version"),
                        "country": _metadata_value(metadata, "country_code", "countrycode", "country"),
                        "language": _metadata_value(metadata, "language", "lang"),
                        "score": _reference_score(ref),
                    }
                )
    return sources


def _confidence_from_sources(sources: list[dict[str, Any]]) -> float:
    """Compute answer confidence from scores, source count, and citation quality."""
    if not sources:
        return 0.0
    scores = [float(source["score"]) for source in sources if source.get("score") is not None]
    if scores:
        top_score = max(scores)
        average_score = sum(scores) / len(scores)
        score_confidence = (top_score * 0.7) + (average_score * 0.3)
    else:
        source_count_confidence = min(len(sources), settings.BEDROCK_RETRIEVAL_RESULT_COUNT) * settings.BEDROCK_FALLBACK_SOURCE_WEIGHT
        citation_quality_count = sum(1 for source in sources if source.get("uri") and source.get("excerpt"))
        citation_quality = min(citation_quality_count, 3) * settings.BEDROCK_FALLBACK_CITATION_WEIGHT
        score_confidence = 0.45 + source_count_confidence + citation_quality
    return round(min(score_confidence, 0.99), 3)


def retrieve_and_generate(message: str, country: str, language: str, role: str, session_history: str, correlation_id: str) -> dict[str, Any]:
    """Call Bedrock Knowledge Base with country, language, and role scoping."""
    for name in ["BEDROCK_KB_ID", "BEDROCK_MODEL_ARN", "BEDROCK_GUARDRAIL_ID", "BEDROCK_GUARDRAIL_VERSION"]:
        if getattr(settings, name).startswith("REPLACE_WITH"):
            raise ConfigurationError(f"{name} is not configured yet.")
    prompt = build_prompt(language, country, role, "$search_results$", session_history)
    params = {
        "input": {"text": message},
        "retrieveAndGenerateConfiguration": {
            "type": "KNOWLEDGE_BASE",
            "knowledgeBaseConfiguration": {
                "knowledgeBaseId": settings.BEDROCK_KB_ID,
                "modelArn": settings.BEDROCK_MODEL_ARN,
                "generationConfiguration": {
                    "promptTemplate": {"textPromptTemplate": f"{prompt}\n\nUser question: $query$"},
                    "guardrailConfiguration": {
                        "guardrailId": settings.BEDROCK_GUARDRAIL_ID,
                        "guardrailVersion": settings.BEDROCK_GUARDRAIL_VERSION,
                    },
                },
                "retrievalConfiguration": {
                    "vectorSearchConfiguration": {
                        "numberOfResults": settings.BEDROCK_RETRIEVAL_RESULT_COUNT,
                        "overrideSearchType": "HYBRID",
                        "filter": {
                            "andAll": [
                                {"equals": {"key": "country_code", "value": country}},
                                {"equals": {"key": "language", "value": language}},
                                {"equals": {"key": "status", "value": "active"}},
                            ]
                        },
                    }
                },
            },
        },
    }
    try:
        response = get_aws_clients().bedrock_agent_runtime.retrieve_and_generate(**params)
    except ReadTimeoutError as exc:
        LOGGER.exception("bedrock_timeout", correlation_id=correlation_id)
        raise BedrockTimeoutError(FALLBACK_RESPONSES["bedrock_error"]) from exc
    except (BotoCoreError, ClientError) as exc:
        LOGGER.exception("bedrock_failed", correlation_id=correlation_id)
        raise BedrockServiceError(FALLBACK_RESPONSES["bedrock_error"]) from exc

    answer = response.get("output", {}).get("text", "")
    sources = _sources_from_response(response)
    confidence = _confidence_from_sources(sources)
    if confidence < settings.BEDROCK_MIN_CONFIDENCE:
        LOGGER.warning("bedrock_low_confidence", correlation_id=correlation_id, confidence=confidence)
        raise LowConfidenceError(FALLBACK_RESPONSES["low_confidence"])
    LOGGER.info("bedrock_success", correlation_id=correlation_id, source_count=len(sources), confidence=confidence)
    return {"response": answer, "sources": sources, "confidence": confidence}
````

### `services\cache.py`

````python
"""Valkey cache read/write logic with IAM authentication."""

import hashlib
import json
from typing import Any

import boto3
import botocore.auth
import botocore.awsrequest
import redis
from redis.credentials import CredentialProvider

from config import settings
from utils.exceptions import CacheConnectionError
from utils.logging import get_logger

LOGGER = get_logger("services.cache")
_redis_client: redis.Redis | None = None


class RedisIamCredentialProvider(CredentialProvider):
    """Generate Redis IAM credentials for each new connection."""

    def __init__(self, host: str, port: int, cache_name: str, user_id: str, region: str) -> None:
        self.host = host
        self.port = port
        self.cache_name = cache_name
        self.user_id = user_id
        self.region = region

    def get_credentials(self) -> tuple[str, str]:
        """Return username and a fresh short-lived IAM auth token."""
        return (
            self.user_id,
            generate_iam_auth_token(
                self.host,
                self.port,
                self.cache_name,
                self.user_id,
                self.region,
            ),
        )


def generate_iam_auth_token(host: str, port: int, cache_name: str, user_id: str, region: str) -> str:
    """Generate a short-lived IAM token for ElastiCache Valkey."""
    credentials = boto3.Session().get_credentials()
    if credentials is None:
        raise CacheConnectionError("AWS credentials are required for Redis IAM authentication.")
    request = botocore.awsrequest.AWSRequest(
        method="GET",
        url=f"https://{cache_name}/?Action=connect&User={user_id}",
    )
    signer = botocore.auth.SigV4QueryAuth(
        credentials.get_frozen_credentials(),
        "elasticache",
        region,
        expires=900,
    )
    signer.add_auth(request)
    return request.url.replace("https://", "", 1)


def init_cache(correlation_id: str = "startup") -> redis.Redis | None:
    """Initialise Valkey when its endpoint is configured."""
    global _redis_client
    if settings.REDIS_HOST.startswith("REPLACE_WITH"):
        LOGGER.warning("cache_not_configured", correlation_id=correlation_id)
        return None
    credential_provider = RedisIamCredentialProvider(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        cache_name=settings.REDIS_CACHE_NAME,
        user_id=settings.REDIS_USER,
        region=settings.AWS_REGION,
    )
    client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        credential_provider=credential_provider,
        ssl=True,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=2,
        retry_on_timeout=True,
    )
    try:
        client.ping()
    except redis.RedisError:
        client.close()
        raise
    _redis_client = client
    LOGGER.info("cache_initialized", correlation_id=correlation_id, host=settings.REDIS_HOST, user=settings.REDIS_USER)
    return _redis_client


def close_cache(correlation_id: str = "shutdown") -> None:
    """Close Redis connections during graceful shutdown."""
    global _redis_client
    if _redis_client is not None:
        _redis_client.close()
        _redis_client = None
        LOGGER.info("cache_closed", correlation_id=correlation_id)


def build_cache_key(message: str, country: str, language: str, role: str) -> str:
    """Build a versioned locale-aware SHA256 cache key."""
    versions = "|".join(
        [
            settings.KB_VERSION,
            settings.PROMPT_VERSION,
            settings.BEDROCK_GUARDRAIL_VERSION,
            settings.BEDROCK_MODEL_ARN,
        ]
    )
    digest = hashlib.sha256(f"{message}|{country}|{language}|{role}|{versions}".encode("utf-8")).hexdigest()
    return f"ask-vera:{country}:{language}:{role}:{digest}"


def get_cache_value(key: str, correlation_id: str) -> dict[str, Any] | None:
    """Read and decode a cached response."""
    if _redis_client is None:
        return None
    try:
        raw = _redis_client.get(key)
        LOGGER.info("cache_read", correlation_id=correlation_id, hit=bool(raw), key=key)
        return json.loads(raw) if raw else None
    except redis.RedisError as exc:
        LOGGER.exception("cache_read_failed", correlation_id=correlation_id)
        raise CacheConnectionError("Redis cache read failed.") from exc


def set_cache_value(key: str, value: dict[str, Any], correlation_id: str) -> None:
    """Write a response to Redis with the configured TTL."""
    if _redis_client is None:
        return
    try:
        _redis_client.setex(key, settings.CACHE_TTL_SECONDS, json.dumps(value))
        LOGGER.info("cache_write", correlation_id=correlation_id, key=key, ttl=settings.CACHE_TTL_SECONDS)
    except redis.RedisError as exc:
        LOGGER.exception("cache_write_failed", correlation_id=correlation_id)
        raise CacheConnectionError("Redis cache write failed.") from exc
````

### `services\consent.py`

````python
"""PostgreSQL consent_log write logic."""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from services.db import get_engine
from utils.exceptions import AwsServiceError
from utils.logging import get_logger
from utils.validators import ConsentRequest

LOGGER = get_logger("services.consent")


def record_consent(consent: ConsentRequest, correlation_id: str) -> None:
    """Write a privacy consent record to PostgreSQL."""
    try:
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO consent_log (session_id, country, lang, accepted_at, version)
                    VALUES (:session_id, :country, :lang, :accepted_at, :version)
                    """
                ),
                {
                    "session_id": consent.sessionId,
                    "country": consent.country,
                    "lang": consent.lang,
                    "accepted_at": consent.timestamp,
                    "version": consent.version,
                },
            )
    except SQLAlchemyError as exc:
        LOGGER.exception("consent_write_failed", correlation_id=correlation_id)
        raise AwsServiceError("Consent logging failed.") from exc
    LOGGER.info("consent_recorded", correlation_id=correlation_id, session_id=consent.sessionId, version=consent.version)
````

### `services\db.py`

````python
"""PostgreSQL connection and schema setup for ASK Vera."""

import json
from typing import Any
from urllib.parse import quote_plus

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from services.aws_clients import get_aws_clients
from utils.exceptions import AwsServiceError
from utils.logging import get_logger

LOGGER = get_logger("services.db")
_engine: Engine | None = None


def _read_rds_secret(correlation_id: str) -> dict[str, Any]:
    """Fetch RDS credentials from AWS Secrets Manager using the instance role."""
    try:
        response = get_aws_clients().secretsmanager.get_secret_value(SecretId=settings.RDS_SECRET_ARN)
    except (BotoCoreError, ClientError) as exc:
        LOGGER.exception("rds_secret_read_failed", correlation_id=correlation_id)
        raise AwsServiceError("RDS secret could not be read from Secrets Manager.") from exc
    return json.loads(response["SecretString"])


def _build_database_url(secret: dict[str, Any]) -> str:
    """Build a SQLAlchemy PostgreSQL URL from an AWS RDS secret payload."""
    username = quote_plus(str(secret["username"]))
    password = quote_plus(str(secret["password"]))
    host = secret["host"]
    port = secret.get("port", 5432)
    database = secret.get("dbname") or secret.get("database") or "postgres"
    return f"postgresql+psycopg://{username}:{password}@{host}:{port}/{database}"


def init_db(correlation_id: str = "startup") -> Engine:
    """Initialise the PostgreSQL engine and create required tables."""
    global _engine
    secret = _read_rds_secret(correlation_id)
    _engine = create_engine(
        _build_database_url(secret),
        pool_size=settings.POSTGRES_POOL_SIZE,
        max_overflow=settings.POSTGRES_MAX_OVERFLOW,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": settings.POSTGRES_CONNECT_TIMEOUT_SECONDS,
            "sslmode": "require",
        },
    )
    create_schema(correlation_id)
    LOGGER.info("postgres_initialized", correlation_id=correlation_id, db_identifier=settings.RDS_DB_IDENTIFIER)
    return _engine


def get_engine() -> Engine:
    """Return the initialised PostgreSQL engine."""
    if _engine is None:
        return init_db()
    return _engine


def create_schema(correlation_id: str = "startup") -> None:
    """Create session and consent tables if they do not exist."""
    try:
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS chat_sessions (
                        session_id TEXT PRIMARY KEY,
                        messages JSONB NOT NULL DEFAULT '[]'::jsonb,
                        expires_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS consent_log (
                        id BIGSERIAL PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        country TEXT NOT NULL,
                        lang TEXT NOT NULL,
                        accepted_at TIMESTAMPTZ NOT NULL,
                        version TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
    except SQLAlchemyError as exc:
        LOGGER.exception("postgres_schema_failed", correlation_id=correlation_id)
        raise AwsServiceError("PostgreSQL schema setup failed.") from exc


def close_db(correlation_id: str = "shutdown") -> None:
    """Dispose PostgreSQL connections during graceful shutdown."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None
        LOGGER.info("postgres_closed", correlation_id=correlation_id)
````

### `services\feedback.py`

````python
"""SQS feedback queue logic."""

import json

from botocore.exceptions import BotoCoreError, ClientError

from config import settings
from services.aws_clients import get_aws_clients
from utils.exceptions import AwsServiceError
from utils.logging import get_logger
from utils.validators import FeedbackRequest

LOGGER = get_logger("services.feedback")


def enqueue_feedback(feedback: FeedbackRequest, correlation_id: str) -> None:
    """Send user feedback to SQS for KB review workflows."""
    if settings.SQS_FEEDBACK_QUEUE_URL.startswith("REPLACE_WITH"):
        LOGGER.warning("feedback_queue_not_configured", correlation_id=correlation_id, session_id=feedback.sessionId)
        return
    try:
        get_aws_clients().sqs.send_message(
            QueueUrl=settings.SQS_FEEDBACK_QUEUE_URL,
            MessageBody=json.dumps({"correlationId": correlation_id, **feedback.model_dump()}, ensure_ascii=True),
        )
    except (BotoCoreError, ClientError) as exc:
        LOGGER.exception("feedback_enqueue_failed", correlation_id=correlation_id)
        raise AwsServiceError("Feedback queue write failed.") from exc
    LOGGER.info("feedback_enqueued", correlation_id=correlation_id, session_id=feedback.sessionId, rating=feedback.rating)
````

### `services\guardrails.py`

````python
"""Guardrail pre-check and post-check logic."""

import re

from config.guardrail_topics import DENIED_TOPICS
from config.vera_persona import FALLBACK_RESPONSES
from utils.exceptions import GuardrailBlockedError
from utils.logging import get_logger

LOGGER = get_logger("services.guardrails")


def _matches(topic: str, text: str) -> bool:
    return any(re.search(re.escape(pattern), text, flags=re.IGNORECASE) for pattern in DENIED_TOPICS[topic])


def check_text(text: str, correlation_id: str) -> None:
    """Raise when text violates denied topics."""
    for topic in ["income_claim", "medical_claim", "off_topic"]:
        if _matches(topic, text):
            LOGGER.warning("guardrail_blocked", correlation_id=correlation_id, topic=topic)
            raise GuardrailBlockedError(FALLBACK_RESPONSES[topic])
    LOGGER.info("guardrail_passed", correlation_id=correlation_id)
````

### `services\pii.py`

````python
"""Amazon Comprehend PII scrubbing for input and output text."""

from botocore.exceptions import BotoCoreError, ClientError

from config import settings
from services.aws_clients import get_aws_clients
from utils.exceptions import AwsServiceError
from utils.logging import get_logger

LOGGER = get_logger("services.pii")


def _pii_language_code(language: str) -> str:
    """Return a Comprehend PII language code, falling back safely."""
    normalized = (language or settings.COMPREHEND_PII_LANGUAGE_CODE).split("-", 1)[0].lower()
    if normalized in settings.COMPREHEND_PII_LANGUAGE_CODES:
        return normalized
    return settings.COMPREHEND_PII_LANGUAGE_CODE


def scrub_pii(text: str, correlation_id: str, language: str | None = None) -> str:
    """Mask PII entities using Amazon Comprehend."""
    if not text:
        return text
    language_code = _pii_language_code(language or settings.COMPREHEND_PII_LANGUAGE_CODE)
    try:
        response = get_aws_clients().comprehend.detect_pii_entities(
            Text=text[:5000],
            LanguageCode=language_code,
        )
    except (BotoCoreError, ClientError) as exc:
        LOGGER.exception("pii_scrub_failed", correlation_id=correlation_id)
        raise AwsServiceError("Comprehend PII detection failed.") from exc
    scrubbed = text
    for entity in sorted(response.get("Entities", []), key=lambda item: item["BeginOffset"], reverse=True):
        start = int(entity["BeginOffset"])
        end = int(entity["EndOffset"])
        scrubbed = f"{scrubbed[:start]}[{entity['Type']}]{scrubbed[end:]}"
    LOGGER.info("pii_scrubbed", correlation_id=correlation_id, entity_count=len(response.get("Entities", [])), language=language_code)
    return scrubbed
````

### `services\session.py`

````python
"""PostgreSQL chat session management."""

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from services.db import get_engine
from utils.exceptions import AwsServiceError
from utils.logging import get_logger

LOGGER = get_logger("services.session")


def get_session_history(session_id: str, correlation_id: str) -> str:
    """Load compact session history from PostgreSQL."""
    try:
        with get_engine().begin() as connection:
            row = connection.execute(
                text("SELECT messages FROM chat_sessions WHERE session_id = :session_id"),
                {"session_id": session_id},
            ).mappings().first()
    except SQLAlchemyError as exc:
        LOGGER.exception("session_read_failed", correlation_id=correlation_id)
        raise AwsServiceError("Session read failed.") from exc
    messages = list(row["messages"] if row else [])
    LOGGER.info("session_loaded", correlation_id=correlation_id, session_id=session_id, message_count=len(messages))
    return "\n".join(str(item) for item in messages[-10:])


def append_session_turn(session_id: str, user_message: str, vera_response: str, correlation_id: str) -> None:
    """Append the latest turn to PostgreSQL session history."""
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.SESSION_TTL_SECONDS)
    turn = [f"user: {user_message}", f"vera: {vera_response}"]
    try:
        with get_engine().begin() as connection:
            existing = connection.execute(
                text("SELECT messages FROM chat_sessions WHERE session_id = :session_id"),
                {"session_id": session_id},
            ).scalar_one_or_none()
            messages = [*(existing or []), *turn][-10:]
            connection.execute(
                text(
                    """
                    INSERT INTO chat_sessions (session_id, messages, expires_at, updated_at)
                    VALUES (:session_id, CAST(:messages AS jsonb), :expires_at, now())
                    ON CONFLICT (session_id)
                    DO UPDATE SET messages = EXCLUDED.messages, expires_at = EXCLUDED.expires_at, updated_at = now()
                    """
                ),
                {"session_id": session_id, "messages": json.dumps(messages), "expires_at": expires_at},
            )
    except SQLAlchemyError as exc:
        LOGGER.exception("session_write_failed", correlation_id=correlation_id)
        raise AwsServiceError("Session write failed.") from exc
    LOGGER.info("session_updated", correlation_id=correlation_id, session_id=session_id)


def cleanup_expired_sessions(correlation_id: str = "session-cleanup") -> int:
    """Delete expired chat sessions and return the number of removed rows."""
    try:
        with get_engine().begin() as connection:
            result = connection.execute(text("DELETE FROM chat_sessions WHERE expires_at < now()"))
            deleted = int(result.rowcount or 0)
    except SQLAlchemyError as exc:
        LOGGER.exception("session_cleanup_failed", correlation_id=correlation_id)
        raise AwsServiceError("Expired session cleanup failed.") from exc
    LOGGER.info("session_cleanup_complete", correlation_id=correlation_id, deleted=deleted)
    return deleted
````

### `tests\integration\test_chat_flow.py`

````python
"""Integration tests for the real AWS chat flow.

These tests are skipped unless INTEGRATION_TEST=true.
"""

import os

import pytest


@pytest.mark.skipif(os.getenv("INTEGRATION_TEST") != "true", reason="Real AWS integration tests are opt-in.")
def test_real_chat_flow_placeholder() -> None:
    """Placeholder for real AWS chat flow validation after resource IDs are configured."""
    assert os.getenv("INTEGRATION_TEST") == "true"
````

### `tests\unit\test_bedrock.py`

````python
"""Unit tests for Bedrock prompt rendering and response parsing."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.bedrock import _confidence_from_sources, build_prompt, retrieve_and_generate


def test_build_prompt_replaces_all_variables() -> None:
    """The ASK Vera prompt contains concrete user context."""
    prompt = build_prompt("en", "US", "new_prospect", "chunk", "history")
    assert "{{" not in prompt
    assert "US" in prompt
    assert "chunk" in prompt


def test_retrieve_and_generate_returns_sources() -> None:
    """Bedrock response is transformed into API data."""
    runtime = MagicMock()
    runtime.retrieve_and_generate.return_value = {
        "output": {"text": "Answer"},
        "citations": [
            {
                "retrievedReferences": [
                    {
                        "location": {"s3Location": {"uri": "s3://kb/doc.pdf"}},
                        "content": {"text": "excerpt"},
                        "metadata": {"score": 0.91, "page": 4, "document_version": "v2", "country_code": "US", "language": "en"},
                    }
                ]
            }
        ],
    }
    clients = SimpleNamespace(bedrock_agent_runtime=runtime)
    with patch("services.bedrock.get_aws_clients", return_value=clients):
        result = retrieve_and_generate("q", "US", "en", "new_prospect", "", "cid")
    assert result["response"] == "Answer"
    assert result["confidence"] >= 0.65
    assert result["sources"][0]["uri"] == "s3://kb/doc.pdf"
    assert result["sources"][0]["page"] == "4"
    assert result["sources"][0]["documentVersion"] == "v2"


def test_confidence_uses_scores_when_available() -> None:
    """Confidence uses retrieval scores rather than a binary source check."""
    confidence = _confidence_from_sources([{"score": 0.7}, {"score": 0.9}])
    assert confidence == 0.87


def test_confidence_falls_back_to_citation_quality() -> None:
    """Confidence still works when Bedrock omits explicit scores."""
    confidence = _confidence_from_sources(
        [
            {"uri": "s3://kb/one.pdf", "excerpt": "one"},
            {"uri": "s3://kb/two.pdf", "excerpt": "two"},
        ]
    )
    assert confidence > 0.65
````

### `tests\unit\test_cache.py`

````python
"""Unit tests for Redis cache keying and read/write behavior."""

from unittest.mock import MagicMock

from services import cache


def test_build_cache_key_is_role_and_locale_aware() -> None:
    """Cache key changes when role changes."""
    first = cache.build_cache_key("hello", "US", "en", "new_prospect")
    second = cache.build_cache_key("hello", "US", "en", "active_distributor")
    assert first != second
    assert first.startswith("ask-vera:US:en:new_prospect:")


def test_build_cache_key_is_version_aware(monkeypatch) -> None:
    """Cache keys rotate when prompt or knowledge-base versions change."""
    first = cache.build_cache_key("hello", "US", "en", "new_prospect")
    monkeypatch.setattr(cache.settings, "KB_VERSION", "next-version")
    second = cache.build_cache_key("hello", "US", "en", "new_prospect")
    assert first != second


def test_get_and_set_cache_value() -> None:
    """Cache values are JSON encoded and decoded."""
    client = MagicMock()
    client.get.return_value = '{"response": "ok"}'
    cache._redis_client = client
    assert cache.get_cache_value("k", "cid") == {"response": "ok"}
    cache.set_cache_value("k", {"response": "ok"}, "cid")
    client.setex.assert_called_once()
````

### `tests\unit\test_guardrails.py`

````python
"""Unit tests for local guardrail denied-topic checks."""

import pytest

from services.guardrails import check_text
from utils.exceptions import GuardrailBlockedError


def test_income_claim_is_blocked() -> None:
    """Income guarantees are blocked before Bedrock."""
    with pytest.raises(GuardrailBlockedError):
        check_text("Can I get rich with guaranteed income?", "cid")


def test_normal_policy_question_passes() -> None:
    """Allowed questions do not raise."""
    check_text("What is the return policy?", "cid")
````

### `tests\unit\test_pii.py`

````python
"""Unit tests for Comprehend PII scrubbing."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.pii import scrub_pii


def test_scrub_pii_replaces_detected_entities() -> None:
    """Detected PII spans are replaced with entity labels."""
    comprehend = MagicMock()
    comprehend.detect_pii_entities.return_value = {
        "Entities": [{"BeginOffset": 11, "EndOffset": 27, "Type": "EMAIL"}]
    }
    clients = SimpleNamespace(comprehend=comprehend)
    with patch("services.pii.get_aws_clients", return_value=clients):
        assert scrub_pii("Contact me a@example.com", "cid") == "Contact me [EMAIL]"
````

### `utils\__init__.py`

````python
"""Utility package for ASK Vera."""
````

### `utils\exceptions.py`

````python
"""Typed application exceptions and stable error codes."""


class AskVeraError(Exception):
    """Base class for all expected ASK Vera errors."""

    error_code = "ASK_VERA_ERROR"
    status_code = 500

    def __init__(self, message: str) -> None:
        """Create an exception with a human-readable message."""
        super().__init__(message)
        self.message = message


class ConfigurationError(AskVeraError):
    """Raised when required startup configuration is missing."""

    error_code = "CONFIGURATION_ERROR"
    status_code = 500


class BedrockTimeoutError(AskVeraError):
    """Raised when Bedrock times out."""

    error_code = "BEDROCK_TIMEOUT"
    status_code = 504


class BedrockServiceError(AskVeraError):
    """Raised when Bedrock returns an unexpected error."""

    error_code = "BEDROCK_ERROR"
    status_code = 502


class CacheConnectionError(AskVeraError):
    """Raised when Redis cannot be reached."""

    error_code = "CACHE_CONNECTION_ERROR"
    status_code = 503


class GuardrailBlockedError(AskVeraError):
    """Raised when input or output is blocked by guardrails."""

    error_code = "GUARDRAIL_BLOCKED"
    status_code = 400


class LowConfidenceError(AskVeraError):
    """Raised when retrieved knowledge does not meet the confidence threshold."""

    error_code = "LOW_CONFIDENCE"
    status_code = 200


class AwsServiceError(AskVeraError):
    """Raised when an AWS dependency other than Bedrock fails."""

    error_code = "AWS_SERVICE_ERROR"
    status_code = 502
````

### `utils\logging.py`

````python
"""Structured JSON logging for ASK Vera."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

SERVICE_NAME = "ask-vera-api"


class JsonFormatter(logging.Formatter):
    """Formats log records as CloudWatch-friendly JSON."""

    def format(self, record: logging.LogRecord) -> str:
        """Return a JSON string containing standard and contextual log fields."""
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": SERVICE_NAME,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", "system"),
        }
        context = getattr(record, "context", None)
        if isinstance(context, dict):
            payload.update(context)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


class StructuredLogger:
    """Small adapter that keeps correlation IDs consistent."""

    def __init__(self, logger: logging.Logger) -> None:
        """Store the wrapped Python logger."""
        self._logger = logger

    def info(self, message: str, correlation_id: str = "system", **context: Any) -> None:
        """Log an informational event."""
        self._logger.info(message, extra={"correlation_id": correlation_id, "context": context})

    def warning(self, message: str, correlation_id: str = "system", **context: Any) -> None:
        """Log a warning event."""
        self._logger.warning(message, extra={"correlation_id": correlation_id, "context": context})

    def error(self, message: str, correlation_id: str = "system", **context: Any) -> None:
        """Log an error event."""
        self._logger.error(message, extra={"correlation_id": correlation_id, "context": context})

    def exception(self, message: str, correlation_id: str = "system", **context: Any) -> None:
        """Log an exception with stack trace."""
        self._logger.exception(message, extra={"correlation_id": correlation_id, "context": context})


def configure_logging() -> None:
    """Configure root logging once for JSON stdout output."""
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def get_logger(name: str) -> StructuredLogger:
    """Return a structured logger for a module."""
    if not logging.getLogger().handlers:
        configure_logging()
    return StructuredLogger(logging.getLogger(name))
````

### `utils\validators.py`

````python
"""Pydantic models for API request and response validation."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from config import settings
from config.vera_persona import ROLE_CONTENT_SCOPES


def _country_codes() -> set[str]:
    return {country["code"] for country in settings.COUNTRIES}


def _language_codes_for_country(country_code: str) -> set[str]:
    for country in settings.COUNTRIES:
        if country["code"] == country_code:
            return {language["code"] for language in country["languages"]}
    return set()


class Envelope(BaseModel):
    """Standard success or error response envelope."""

    success: bool
    data: dict[str, Any] | None = None
    error: dict[str, str] | None = None
    correlationId: str
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ChatRequest(BaseModel):
    """Validated /api/chat request body."""

    message: str = Field(min_length=1, max_length=4000)
    sessionId: str = Field(min_length=1, max_length=128)
    country: str = Field(min_length=2, max_length=64)
    language: str = Field(min_length=2, max_length=16)
    role: str = Field(default="new_prospect", max_length=64)

    @field_validator("country")
    @classmethod
    def validate_country(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in _country_codes():
            raise ValueError("Unsupported country.")
        return normalized

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        return value.lower()

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in ROLE_CONTENT_SCOPES:
            raise ValueError("Unsupported role.")
        return value

    @model_validator(mode="after")
    def validate_locale_pair(self) -> "ChatRequest":
        if self.language not in _language_codes_for_country(self.country):
            raise ValueError("Unsupported language for country.")
        return self


class Source(BaseModel):
    """Source citation returned to the widget."""

    title: str
    uri: str
    excerpt: str = ""


class ChatData(BaseModel):
    """Successful chat response data."""

    response: str
    sources: list[Source]
    confidence: float
    correlationId: str


class ConsentRequest(BaseModel):
    """Validated consent logging body."""

    sessionId: str
    country: str
    lang: str
    timestamp: str
    version: str

    @field_validator("country")
    @classmethod
    def validate_country(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in _country_codes():
            raise ValueError("Unsupported country.")
        return normalized

    @field_validator("lang")
    @classmethod
    def validate_language(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def validate_locale_pair(self) -> "ConsentRequest":
        if self.lang not in _language_codes_for_country(self.country):
            raise ValueError("Unsupported language for country.")
        return self


class FeedbackRequest(BaseModel):
    """Validated feedback queue body."""

    sessionId: str
    messageId: str
    rating: int = Field(ge=-1, le=1)
    comment: str = Field(default="", max_length=2000)
````

### `widget-wrapper\demo\index.html`

````html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Generic Widget Wrapper Demo</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
````

### `widget-wrapper\demo\src\App.tsx`

````tsx
import { BackendChatDemo } from "../../src/generic-widget/examples/BackendChatDemo";

const apiBaseUrl = new URLSearchParams(window.location.search).get("api") || "http://127.0.0.1:8000";

export function App() {
  return (
    <main className="demo-page">
      <section className="demo-layout">
        <div className="demo-copy">
          <p className="demo-eyebrow">AWS-connected demo</p>
          <h1>ASK Vera widget connected to the Python API</h1>
          <p>
            Review the market selector, privacy acceptance, and chat flow locally while messages are sent to the
            AWS-backed FastAPI service.
          </p>
          <div className="demo-actions" aria-label="Demo status">
            <span>Local widget</span>
            <span>AWS backend</span>
            <span>Consent-first</span>
          </div>
        </div>

        <aside className="demo-preview" aria-label="Integration preview">
          <div className="demo-preview-header">
            <span className="demo-status-dot" />
            <span>Widget shell preview</span>
          </div>
          <div className="demo-preview-body">
            <div>
              <span className="demo-metric-label">Provider</span>
              <strong>ASK Vera API</strong>
            </div>
            <div>
              <span className="demo-metric-label">Mode</span>
              <strong>Consent-first</strong>
            </div>
            <div>
              <span className="demo-metric-label">API</span>
              <strong>{apiBaseUrl}</strong>
            </div>
          </div>
        </aside>
      </section>
      <BackendChatDemo apiBaseUrl={apiBaseUrl} />
    </main>
  );
}
````

### `widget-wrapper\demo\src\main.tsx`

````tsx
import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";

createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
````

### `widget-wrapper\demo\src\styles.css`

````css
@import "../../src/generic-widget/generic-widget.css";

:root {
  color: #111111;
  background: #ffffff;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

body {
  margin: 0;
  min-height: 100vh;
}

body::before {
  position: fixed;
  inset: 0;
  pointer-events: none;
  content: "";
  background:
    linear-gradient(to bottom, transparent 0 58%, #ffc400 58% 100%),
    linear-gradient(rgba(0, 0, 0, 0.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 0, 0, 0.045) 1px, transparent 1px);
  background-size: auto, 56px 56px, 56px 56px;
}

.demo-page {
  position: relative;
  min-height: 100vh;
  padding: 56px;
}

.demo-layout {
  display: grid;
  grid-template-columns: minmax(360px, 620px) minmax(280px, 380px);
  gap: 40px;
  align-items: start;
  max-width: 1120px;
}

.demo-copy {
  padding-top: 18px;
}

.demo-eyebrow {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  margin: 0 0 18px;
  padding: 0 11px;
  color: #000000;
  background: rgba(255, 255, 255, 0.74);
  border: 1px solid rgba(0, 0, 0, 0.16);
  border-radius: 999px;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.demo-copy h1 {
  max-width: 620px;
  margin: 0;
  color: #000000;
  font-size: 50px;
  line-height: 1.02;
  letter-spacing: 0;
}

.demo-copy p {
  max-width: 600px;
  margin: 20px 0 0;
  color: #516071;
  font-size: 18px;
  line-height: 1.65;
}

.demo-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 28px;
}

.demo-actions span {
  padding: 9px 12px;
  color: #203044;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(0, 0, 0, 0.18);
  border-radius: 8px;
  font-size: 13px;
  font-weight: 750;
  box-shadow: 0 10px 28px rgba(23, 32, 51, 0.08);
}

.demo-preview {
  margin-top: 28px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(0, 0, 0, 0.18);
  border-radius: 8px;
  box-shadow: 0 22px 60px rgba(23, 32, 51, 0.13);
  backdrop-filter: blur(14px);
}

.demo-preview-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  color: #203044;
  background: #ffffff;
  border-bottom: 1px solid rgba(143, 160, 179, 0.28);
  font-size: 13px;
  font-weight: 800;
}

.demo-status-dot {
  width: 9px;
  height: 9px;
  background: #ffc400;
  border-radius: 999px;
  box-shadow: 0 0 0 4px rgba(255, 196, 0, 0.24);
}

.demo-preview-body {
  display: grid;
  gap: 1px;
  background: rgba(143, 160, 179, 0.22);
}

.demo-preview-body > div {
  display: grid;
  gap: 4px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.76);
}

.demo-metric-label {
  color: #66768a;
  font-size: 12px;
  font-weight: 750;
  text-transform: uppercase;
}

.demo-preview strong {
  color: #142235;
  font-size: 16px;
}

.local-provider-status {
  display: grid;
  gap: 10px;
}

.local-provider-status > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.local-provider-status strong {
  color: #172033;
  font-size: 14px;
}

.local-provider-status span {
  padding: 5px 8px;
  color: #0f5f71;
  background: rgba(15, 95, 113, 0.09);
  border-radius: 999px;
  font-size: 12px;
  font-weight: 800;
}

.local-provider-status small {
  overflow: hidden;
  color: #66768a;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 980px) {
  .demo-page {
    padding: 36px 22px 680px;
  }

  .demo-layout {
    grid-template-columns: 1fr;
    gap: 22px;
  }

  .demo-copy h1 {
    font-size: 38px;
  }
}

@media (max-width: 560px) {
  .demo-page {
    padding: 28px 16px 680px;
  }

  .demo-copy h1 {
    font-size: 32px;
  }

  .demo-copy p {
    font-size: 16px;
  }
}
````

### `widget-wrapper\dist-check\generic-widget-wrapper-check.css`

````css
.gw-root{--gw-panel-width:min(420px, calc(100vw - 24px));font-family:var(--gw-font);color:var(--gw-text);z-index:var(--gw-z);position:fixed;bottom:20px;right:20px}.gw-root *{box-sizing:border-box}.gw-launcher{background:var(--gw-launcher);width:62px;height:62px;color:var(--gw-launcher-text);box-shadow:var(--gw-shadow);cursor:pointer;border:0;border-radius:999px;place-items:center;transition:transform .18s;display:grid}.gw-launcher:hover,.gw-launcher:focus-visible{transform:translateY(-2px)}.gw-launcher-mark{border:1px solid #ffffff7a;border-radius:999px;place-items:center;width:34px;height:34px;font-weight:700;display:grid}.gw-panel{width:var(--gw-panel-width);background:var(--gw-surface);border:1px solid var(--gw-border);border-radius:var(--gw-radius);min-height:560px;max-height:min(760px,100vh - 32px);box-shadow:var(--gw-shadow);flex-direction:column;animation:.18s gw-panel-in;display:flex;overflow:hidden}@keyframes gw-panel-in{0%{opacity:0;transform:translateY(10px)scale(.98)}to{opacity:1;transform:translateY(0)scale(1)}}.gw-header{background:var(--gw-panel);border-bottom:1px solid var(--gw-border);justify-content:space-between;align-items:center;gap:12px;min-height:74px;padding:16px;display:flex}.gw-title{font-size:18px;font-weight:750;line-height:1.2}.gw-subtitle{color:var(--gw-muted);margin-top:3px;font-size:13px}.gw-header-actions{gap:8px;display:flex}.gw-icon-button,.gw-success-banner button{color:var(--gw-muted);cursor:pointer;background:0 0;border:1px solid #0000;border-radius:10px;min-width:36px;min-height:36px}.gw-icon-button:hover,.gw-icon-button:focus-visible,.gw-success-banner button:hover,.gw-success-banner button:focus-visible{color:var(--gw-text);background:color-mix(in srgb, var(--gw-border), transparent 45%)}.gw-menu{background:var(--gw-panel);border:1px solid var(--gw-border);border-radius:14px;width:190px;padding:6px;position:absolute;top:66px;right:16px;box-shadow:0 18px 50px #0f172a2e}.gw-menu-item{width:100%;color:var(--gw-text);text-align:left;cursor:pointer;background:0 0;border:0;border-radius:10px;padding:10px 11px}.gw-menu-item:hover,.gw-menu-item:focus-visible{background:var(--gw-surface)}.gw-success-banner{border:1px solid color-mix(in srgb, var(--gw-success), white 65%);background:color-mix(in srgb, var(--gw-success), white 88%);color:var(--gw-text);border-radius:14px;justify-content:space-between;align-items:center;gap:10px;margin:12px 12px 0;padding:11px 12px;font-size:14px;display:flex}.gw-content{flex-direction:column;flex:1;gap:12px;min-height:0;padding:14px;display:flex;overflow-y:auto}.gw-section,.gw-message-feed,.gw-child-slot{background:var(--gw-panel);border:1px solid var(--gw-border);border-radius:14px;padding:14px}.gw-region-selector{grid-template-columns:1fr 1fr;gap:10px;display:grid}.gw-field{color:var(--gw-muted);gap:6px;font-size:12px;font-weight:650;display:grid}.gw-field select,.gw-composer input{border:1px solid var(--gw-border);width:100%;color:var(--gw-text);background:#fff;border-radius:10px;outline:none;min-height:40px;padding:0 11px}.gw-field select:focus,.gw-composer input:focus,.gw-primary-button:focus-visible,.gw-secondary-button:focus-visible,.gw-topic:focus-visible{outline:3px solid color-mix(in srgb, var(--gw-accent), transparent 78%);outline-offset:2px;border-color:var(--gw-accent)}.gw-consent h2{margin:0 0 8px;font-size:16px}.gw-consent-body{color:var(--gw-muted);font-size:14px;line-height:1.55}.gw-legal{flex-wrap:wrap;gap:8px;margin-top:12px;display:flex}.gw-legal a{color:var(--gw-accent);font-size:13px;font-weight:650;text-decoration:none}.gw-legal a:hover,.gw-legal a:focus-visible{text-decoration:underline}.gw-consent-actions{gap:10px;margin-top:14px;display:flex}.gw-primary-button,.gw-secondary-button,.gw-topic{cursor:pointer;border-radius:11px;min-height:40px;padding:0 13px;font-weight:700}.gw-primary-button{border:1px solid var(--gw-accent);background:var(--gw-accent);color:var(--gw-accent-text)}.gw-primary-button:disabled{opacity:.48;cursor:not-allowed}.gw-secondary-button,.gw-topic{border:1px solid var(--gw-border);background:var(--gw-panel);color:var(--gw-text)}.gw-section-title{color:var(--gw-muted);margin-bottom:10px;font-size:12px;font-weight:750}.gw-topic-list{flex-wrap:wrap;gap:8px;display:flex}.gw-message-feed{align-content:start;gap:10px;display:grid}.gw-message{border-radius:14px;max-width:88%;padding:11px 12px;font-size:14px;line-height:1.5}.gw-message-system,.gw-message-assistant{background:var(--gw-surface);border:1px solid var(--gw-border);justify-self:start}.gw-message-user{background:var(--gw-accent);color:var(--gw-accent-text);justify-self:end}.gw-loading{color:var(--gw-muted);align-items:center;gap:10px;padding:8px 4px;font-size:14px;display:flex}.gw-spinner{border:2px solid var(--gw-border);border-top-color:var(--gw-accent);border-radius:999px;width:16px;height:16px;animation:.9s linear infinite gw-spin}@keyframes gw-spin{to{transform:rotate(360deg)}}.gw-composer{background:var(--gw-panel);border-top:1px solid var(--gw-border);grid-template-columns:1fr auto;gap:10px;padding:12px;display:grid}.gw-sr-only{clip:rect(0, 0, 0, 0);white-space:nowrap;border:0;width:1px;height:1px;margin:-1px;padding:0;position:absolute;overflow:hidden}@media (width<=520px){.gw-root{bottom:12px;right:12px}.gw-panel{width:calc(100vw - 24px);min-height:min(620px,100vh - 24px)}.gw-region-selector{grid-template-columns:1fr}}
/*$vite$:1*/
````

### `widget-wrapper\package.json`

````json
{
  "name": "generic-widget-wrapper",
  "version": "1.0.0",
  "type": "module",
  "private": true,
  "scripts": {
    "dev": "vite demo --host 127.0.0.1 --port 5174",
    "demo": "vite demo --host 127.0.0.1 --port 5174",
    "build": "vite build",
    "build:demo": "vite build demo",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@vitejs/plugin-react": "6.0.1",
    "react": "19.2.6",
    "react-dom": "19.2.6",
    "typescript": "5.9.3",
    "vite": "8.0.12"
  },
  "devDependencies": {
    "@types/react": "^19.2.17",
    "@types/react-dom": "^19.2.3"
  }
}
````

### `widget-wrapper\package-lock.json`

````json
{
  "name": "generic-widget-wrapper",
  "version": "1.0.0",
  "lockfileVersion": 3,
  "requires": true,
  "packages": {
    "": {
      "name": "generic-widget-wrapper",
      "version": "1.0.0",
      "dependencies": {
        "@vitejs/plugin-react": "6.0.1",
        "react": "19.2.6",
        "react-dom": "19.2.6",
        "typescript": "5.9.3",
        "vite": "8.0.12"
      },
      "devDependencies": {
        "@types/react": "^19.2.17",
        "@types/react-dom": "^19.2.3"
      }
    },
    "node_modules/@emnapi/core": {
      "version": "1.10.0",
      "resolved": "https://registry.npmjs.org/@emnapi/core/-/core-1.10.0.tgz",
      "integrity": "sha512-yq6OkJ4p82CAfPl0u9mQebQHKPJkY7WrIuk205cTYnYe+k2Z8YBh11FrbRG/H6ihirqcacOgl2BIO8oyMQLeXw==",
      "license": "MIT",
      "optional": true,
      "dependencies": {
        "@emnapi/wasi-threads": "1.2.1",
        "tslib": "^2.4.0"
      }
    },
    "node_modules/@emnapi/runtime": {
      "version": "1.10.0",
      "resolved": "https://registry.npmjs.org/@emnapi/runtime/-/runtime-1.10.0.tgz",
      "integrity": "sha512-ewvYlk86xUoGI0zQRNq/mC+16R1QeDlKQy21Ki3oSYXNgLb45GV1P6A0M+/s6nyCuNDqe5VpaY84BzXGwVbwFA==",
      "license": "MIT",
      "optional": true,
      "dependencies": {
        "tslib": "^2.4.0"
      }
    },
    "node_modules/@emnapi/wasi-threads": {
      "version": "1.2.1",
      "resolved": "https://registry.npmjs.org/@emnapi/wasi-threads/-/wasi-threads-1.2.1.tgz",
      "integrity": "sha512-uTII7OYF+/Mes/MrcIOYp5yOtSMLBWSIoLPpcgwipoiKbli6k322tcoFsxoIIxPDqW01SQGAgko4EzZi2BNv2w==",
      "license": "MIT",
      "optional": true,
      "dependencies": {
        "tslib": "^2.4.0"
      }
    },
    "node_modules/@napi-rs/wasm-runtime": {
      "version": "1.1.6",
      "resolved": "https://registry.npmjs.org/@napi-rs/wasm-runtime/-/wasm-runtime-1.1.6.tgz",
      "integrity": "sha512-ZLv/JdUfkvOy9eCnnBaGfiO+XimbjebAeO+MRQqD/B+FR1tnRN0tpKSJHRbE8sFfS6aqsXZ67TQjfwfsxULVbg==",
      "license": "MIT",
      "optional": true,
      "dependencies": {
        "@tybys/wasm-util": "^0.10.3"
      },
      "funding": {
        "type": "github",
        "url": "https://github.com/sponsors/Brooooooklyn"
      },
      "peerDependencies": {
        "@emnapi/core": "^1.7.1",
        "@emnapi/runtime": "^1.7.1"
      }
    },
    "node_modules/@oxc-project/types": {
      "version": "0.129.0",
      "resolved": "https://registry.npmjs.org/@oxc-project/types/-/types-0.129.0.tgz",
      "integrity": "sha512-3oz8m3FGdr2nDXVqmFUw7jolKliC4MoyXYIG2c7gpjBnzUWQpUGIYcXYKxTdTi+N2jusvt610ckTMkxdwHkYEg==",
      "license": "MIT",
      "funding": {
        "url": "https://github.com/sponsors/Boshen"
      }
    },
    "node_modules/@rolldown/binding-android-arm64": {
      "version": "1.0.0",
      "resolved": "https://registry.npmjs.org/@rolldown/binding-android-arm64/-/binding-android-arm64-1.0.0.tgz",
      "integrity": "sha512-TWMZnRLMe63C2Lhyicviu7ZHaU4kxa6PS3rofvc9GmcvptzNN11BcfQ4Sl7MwTOsisQoa2keB/EBdNCAnUo8vA==",
      "cpu": [
        "arm64"
      ],
      "license": "MIT",
      "optional": true,
      "os": [
        "android"
      ],
      "engines": {
        "node": "^20.19.0 || >=22.12.0"
      }
    },
    "node_modules/@rolldown/binding-darwin-arm64": {
      "version": "1.0.0",
      "resolved": "https://registry.npmjs.org/@rolldown/binding-darwin-arm64/-/binding-darwin-arm64-1.0.0.tgz",
      "integrity": "sha512-6XcD+8k0gPVItNagEw78/qqcBDwKcwDYS8V2hRmVsfUSIrd8cWe/CBvRDI5toqFyPfj+FJr6t8U6Xj2P2prEew==",
      "cpu": [
        "arm64"
      ],
      "license": "MIT",
      "optional": true,
      "os": [
        "darwin"
      ],
      "engines": {
        "node": "^20.19.0 || >=22.12.0"
      }
    },
    "node_modules/@rolldown/binding-darwin-x64": {
      "version": "1.0.0",
      "resolved": "https://registry.npmjs.org/@rolldown/binding-darwin-x64/-/binding-darwin-x64-1.0.0.tgz",
      "integrity": "sha512-iN/tWVXRQDWvmZlKdceP1Dwug9GDpEymhb9p4xnEe6zvCg5lFmzVljl+1qR1NVx3yfGpr2Na+CuLmv5IU8uzfQ==",
      "cpu": [
        "x64"
      ],
      "license": "MIT",
      "optional": true,
      "os": [
        "darwin"
      ],
      "engines": {
        "node": "^20.19.0 || >=22.12.0"
      }
    },
    "node_modules/@rolldown/binding-freebsd-x64": {
      "version": "1.0.0",
      "resolved": "https://registry.npmjs.org/@rolldown/binding-freebsd-x64/-/binding-freebsd-x64-1.0.0.tgz",
      "integrity": "sha512-jjQMDvvwSOuhOwMszD/klSOjyWMM3zI64hWTj9KT5x4MxRbZAf+7vLQ6qouRhtsLVFHr3f0ILaJAfgENPiQdAQ==",
      "cpu": [
        "x64"
      ],
      "license": "MIT",
      "optional": true,
      "os": [
        "freebsd"
      ],
      "engines": {
        "node": "^20.19.0 || >=22.12.0"
      }
    },
    "node_modules/@rolldown/binding-linux-arm-gnueabihf": {
      "version": "1.0.0",
      "resolved": "https://registry.npmjs.org/@rolldown/binding-linux-arm-gnueabihf/-/binding-linux-arm-gnueabihf-1.0.0.tgz",
      "integrity": "sha512-d//Dtg2x6/m3mbV64yUGNnDGNZaDGRpDLLNGerHQUVObuNaIQaaDp25yUiqGXtHEXX+NP2d0wAlmKgpYgIAJ2A==",
      "cpu": [
        "arm"
      ],
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": "^20.19.0 || >=22.12.0"
      }
    },
    "node_modules/@rolldown/binding-linux-arm64-gnu": {
      "version": "1.0.0",
      "resolved": "https://registry.npmjs.org/@rolldown/binding-linux-arm64-gnu/-/binding-linux-arm64-gnu-1.0.0.tgz",
      "integrity": "sha512-n7Ofp0mx+aB2cC+Sdy5YtMnXtY9lchnHbY+3Yt0uq9JsWQExf4f5Whu0tK0R8Jdc9S6RchTHjIFY7uc92puOVQ==",
      "cpu": [
        "arm64"
      ],
      "libc": [
        "glibc"
      ],
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": "^20.19.0 || >=22.12.0"
      }
    },
    "node_modules/@rolldown/binding-linux-arm64-musl": {
      "version": "1.0.0",
      "resolved": "https://registry.npmjs.org/@rolldown/binding-linux-arm64-musl/-/binding-linux-arm64-musl-1.0.0.tgz",
      "integrity": "sha512-EIVjy2cgd7uuMMo94FVkBp7F6DhcZAUwNURkSG3RwUmvAXR6s0ISxM81U+IydcZByPG0pZIHsf1b6kTxoFDgJA==",
      "cpu": [
        "arm64"
      ],
      "libc": [
        "musl"
      ],
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": "^20.19.0 || >=22.12.0"
      }
    },
    "node_modules/@rolldown/binding-linux-ppc64-gnu": {
      "version": "1.0.0",
      "resolved": "https://registry.npmjs.org/@rolldown/binding-linux-ppc64-gnu/-/binding-linux-ppc64-gnu-1.0.0.tgz",
      "integrity": "sha512-JEwwOPcwTLAcpDQlqSmjEmfs63xJnSiUNIGvLcDLUHCWK4XowpS/7c7tUsUH6uT/ct6bMUTdXKfI8967FYj6mg==",
      "cpu": [
        "ppc64"
      ],
      "libc": [
        "glibc"
      ],
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": "^20.19.0 || >=22.12.0"
      }
    },
    "node_modules/@rolldown/binding-linux-s390x-gnu": {
      "version": "1.0.0",
      "resolved": "https://registry.npmjs.org/@rolldown/binding-linux-s390x-gnu/-/binding-linux-s390x-gnu-1.0.0.tgz",
      "integrity": "sha512-0wjCFhLrihtAubnT9iA0N++0pSV0z5Hg7tNGdNJ4RFaINceHadoF+kiFGyY1qSSNVIAZtLotG8Ju1bgDPkjnFA==",
      "cpu": [
        "s390x"
      ],
      "libc": [
        "glibc"
      ],
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": "^20.19.0 || >=22.12.0"
      }
    },
    "node_modules/@rolldown/binding-linux-x64-gnu": {
      "version": "1.0.0",
      "resolved": "https://registry.npmjs.org/@rolldown/binding-linux-x64-gnu/-/binding-linux-x64-gnu-1.0.0.tgz",
      "integrity": "sha512-Dfn7iak9BcMMePxcoJfpSbWqnEyrp/dRF63/8qW/eHBdOZov6x5aShLLEYGYdIeSJ6vMLK/XCVB+lGIxm41bQA==",
      "cpu": [
        "x64"
      ],
      "libc": [
        "glibc"
      ],
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": "^20.19.0 || >=22.12.0"
      }
    },
    "node_modules/@rolldown/binding-linux-x64-musl": {
      "version": "1.0.0",
      "resolved": "https://registry.npmjs.org/@rolldown/binding-linux-x64-musl/-/binding-linux-x64-musl-1.0.0.tgz",
      "integrity": "sha512-5/utzzDmD/pD/bmuaUcbTf/sZYy0aztwIVlfpoW1fTjCZ0BaPOMVWGZL1zvgxyi7ZIVYWlxKONHmSbHuiOh8Jw==",
      "cpu": [
        "x64"
      ],
      "libc": [
        "musl"
      ],
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": "^20.19.0 || >=22.12.0"
      }
    },
    "node_modules/@rolldown/binding-openharmony-arm64": {
      "version": "1.0.0",
      "resolved": "https://registry.npmjs.org/@rolldown/binding-openharmony-arm64/-/binding-openharmony-arm64-1.0.0.tgz",
      "integrity": "sha512-ouJs8VcUomfLfpbUECqFMRqdV4x6aeAK3MA4m6vTrJJjKyWTV5KnxZx7Jd9G+GlDaQQxubcba00x16OyJ1meig==",
      "cpu": [
        "arm64"
      ],
      "license": "MIT",
      "optional": true,
      "os": [
        "openharmony"
      ],
      "engines": {
        "node": "^20.19.0 || >=22.12.0"
      }
    },
    "node_modules/@rolldown/binding-wasm32-wasi": {
      "version": "1.0.0",
      "resolved": "https://registry.npmjs.org/@rolldown/binding-wasm32-wasi/-/binding-wasm32-wasi-1.0.0.tgz",
      "integrity": "sha512-E+oHKGiDA+lsKMmFtffDDw91EryDT7uJocrIuCHqhm6bCTM6xFK+3gaCkYOHfPwQr0cCNarSM2xaELoQDz9jJg==",
      "cpu": [
        "wasm32"
      ],
      "license": "MIT",
      "optional": true,
      "dependencies": {
        "@emnapi/core": "1.10.0",
        "@emnapi/runtime": "1.10.0",
        "@napi-rs/wasm-runtime": "^1.1.4"
      },
      "engines": {
        "node": "^20.19.0 || >=22.12.0"
      }
    },
    "node_modules/@rolldown/binding-win32-arm64-msvc": {
      "version": "1.0.0",
      "resolved": "https://registry.npmjs.org/@rolldown/binding-win32-arm64-msvc/-/binding-win32-arm64-msvc-1.0.0.tgz",
      "integrity": "sha512-yYK02n8Rngo+gbm1y6G0+7jk1sJ/2Wt7K0me0Y7k/ErBpyf+LJ2gFpqWVTcRV1rUepBlQRmpgWkTQCiiwrK0Ow==",
      "cpu": [
        "arm64"
      ],
      "license": "MIT",
      "optional": true,
      "os": [
        "win32"
      ],
      "engines": {
        "node": "^20.19.0 || >=22.12.0"
      }
    },
    "node_modules/@rolldown/binding-win32-x64-msvc": {
      "version": "1.0.0",
      "resolved": "https://registry.npmjs.org/@rolldown/binding-win32-x64-msvc/-/binding-win32-x64-msvc-1.0.0.tgz",
      "integrity": "sha512-14bpChMahXRRXiTwahSl+zzHPW6qQTXtkMuJBFlbo+pqSAews2d4BdCSHfrJ/MBsCZtpmTafsY+1QhBzitcmdg==",
      "cpu": [
        "x64"
      ],
      "license": "MIT",
      "optional": true,
      "os": [
        "win32"
      ],
      "engines": {
        "node": "^20.19.0 || >=22.12.0"
      }
    },
    "node_modules/@rolldown/pluginutils": {
      "version": "1.0.0-rc.7",
      "resolved": "https://registry.npmjs.org/@rolldown/pluginutils/-/pluginutils-1.0.0-rc.7.tgz",
      "integrity": "sha512-qujRfC8sFVInYSPPMLQByRh7zhwkGFS4+tyMQ83srV1qrxL4g8E2tyxVVyxd0+8QeBM1mIk9KbWxkegRr76XzA==",
      "license": "MIT"
    },
    "node_modules/@tybys/wasm-util": {
      "version": "0.10.3",
      "resolved": "https://registry.npmjs.org/@tybys/wasm-util/-/wasm-util-0.10.3.tgz",
      "integrity": "sha512-F3fo1MYrRJYL3zER0OUOmkutjr1Vp23m7OsSgp7nq4SP6OqX6C/56XFIPAl5bt3zaBRjmW7SGz3u/6LwFpYcOg==",
      "license": "MIT",
      "optional": true,
      "dependencies": {
        "tslib": "^2.4.0"
      }
    },
    "node_modules/@types/react": {
      "version": "19.2.17",
      "resolved": "https://registry.npmjs.org/@types/react/-/react-19.2.17.tgz",
      "integrity": "sha512-MXfmqaVPEVgkBT/aY0aGCkRWWtByiYQXo3xdQ8r5RzuFrPiRn8Gar2tQdXSUQ2GKV3bkXckek89V8wQBY2Q/Aw==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "csstype": "^3.2.2"
      }
    },
    "node_modules/@types/react-dom": {
      "version": "19.2.3",
      "resolved": "https://registry.npmjs.org/@types/react-dom/-/react-dom-19.2.3.tgz",
      "integrity": "sha512-jp2L/eY6fn+KgVVQAOqYItbF0VY/YApe5Mz2F0aykSO8gx31bYCZyvSeYxCHKvzHG5eZjc+zyaS5BrBWya2+kQ==",
      "dev": true,
      "license": "MIT",
      "peerDependencies": {
        "@types/react": "^19.2.0"
      }
    },
    "node_modules/@vitejs/plugin-react": {
      "version": "6.0.1",
      "resolved": "https://registry.npmjs.org/@vitejs/plugin-react/-/plugin-react-6.0.1.tgz",
      "integrity": "sha512-l9X/E3cDb+xY3SWzlG1MOGt2usfEHGMNIaegaUGFsLkb3RCn/k8/TOXBcab+OndDI4TBtktT8/9BwwW8Vi9KUQ==",
      "license": "MIT",
      "dependencies": {
        "@rolldown/pluginutils": "1.0.0-rc.7"
      },
      "engines": {
        "node": "^20.19.0 || >=22.12.0"
      },
      "peerDependencies": {
        "@rolldown/plugin-babel": "^0.1.7 || ^0.2.0",
        "babel-plugin-react-compiler": "^1.0.0",
        "vite": "^8.0.0"
      },
      "peerDependenciesMeta": {
        "@rolldown/plugin-babel": {
          "optional": true
        },
        "babel-plugin-react-compiler": {
          "optional": true
        }
      }
    },
    "node_modules/csstype": {
      "version": "3.2.3",
      "resolved": "https://registry.npmjs.org/csstype/-/csstype-3.2.3.tgz",
      "integrity": "sha512-z1HGKcYy2xA8AGQfwrn0PAy+PB7X/GSj3UVJW9qKyn43xWa+gl5nXmU4qqLMRzWVLFC8KusUX8T/0kCiOYpAIQ==",
      "dev": true,
      "license": "MIT"
    },
    "node_modules/detect-libc": {
      "version": "2.1.2",
      "resolved": "https://registry.npmjs.org/detect-libc/-/detect-libc-2.1.2.tgz",
      "integrity": "sha512-Btj2BOOO83o3WyH59e8MgXsxEQVcarkUOpEYrubB0urwnN10yQ364rsiByU11nZlqWYZm05i/of7io4mzihBtQ==",
      "license": "Apache-2.0",
      "engines": {
        "node": ">=8"
      }
    },
    "node_modules/fdir": {
      "version": "6.5.0",
      "resolved": "https://registry.npmjs.org/fdir/-/fdir-6.5.0.tgz",
      "integrity": "sha512-tIbYtZbucOs0BRGqPJkshJUYdL+SDH7dVM8gjy+ERp3WAUjLEFJE+02kanyHtwjWOnwrKYBiwAmM0p4kLJAnXg==",
      "license": "MIT",
      "engines": {
        "node": ">=12.0.0"
      },
      "peerDependencies": {
        "picomatch": "^3 || ^4"
      },
      "peerDependenciesMeta": {
        "picomatch": {
          "optional": true
        }
      }
    },
    "node_modules/fsevents": {
      "version": "2.3.3",
      "resolved": "https://registry.npmjs.org/fsevents/-/fsevents-2.3.3.tgz",
      "integrity": "sha512-5xoDfX+fL7faATnagmWPpbFtwh/R77WmMMqqHGS65C3vvB0YHrgF+B1YmZ3441tMj5n63k0212XNoJwzlhffQw==",
      "hasInstallScript": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "darwin"
      ],
      "engines": {
        "node": "^8.16.0 || ^10.6.0 || >=11.0.0"
      }
    },
    "node_modules/lightningcss": {
      "version": "1.32.0",
      "resolved": "https://registry.npmjs.org/lightningcss/-/lightningcss-1.32.0.tgz",
      "integrity": "sha512-NXYBzinNrblfraPGyrbPoD19C1h9lfI/1mzgWYvXUTe414Gz/X1FD2XBZSZM7rRTrMA8JL3OtAaGifrIKhQ5yQ==",
      "license": "MPL-2.0",
      "dependencies": {
        "detect-libc": "^2.0.3"
      },
      "engines": {
        "node": ">= 12.0.0"
      },
      "funding": {
        "type": "opencollective",
        "url": "https://opencollective.com/parcel"
      },
      "optionalDependencies": {
        "lightningcss-android-arm64": "1.32.0",
        "lightningcss-darwin-arm64": "1.32.0",
        "lightningcss-darwin-x64": "1.32.0",
        "lightningcss-freebsd-x64": "1.32.0",
        "lightningcss-linux-arm-gnueabihf": "1.32.0",
        "lightningcss-linux-arm64-gnu": "1.32.0",
        "lightningcss-linux-arm64-musl": "1.32.0",
        "lightningcss-linux-x64-gnu": "1.32.0",
        "lightningcss-linux-x64-musl": "1.32.0",
        "lightningcss-win32-arm64-msvc": "1.32.0",
        "lightningcss-win32-x64-msvc": "1.32.0"
      }
    },
    "node_modules/lightningcss-android-arm64": {
      "version": "1.32.0",
      "resolved": "https://registry.npmjs.org/lightningcss-android-arm64/-/lightningcss-android-arm64-1.32.0.tgz",
      "integrity": "sha512-YK7/ClTt4kAK0vo6w3X+Pnm0D2cf2vPHbhOXdoNti1Ga0al1P4TBZhwjATvjNwLEBCnKvjJc2jQgHXH0NEwlAg==",
      "cpu": [
        "arm64"
      ],
      "license": "MPL-2.0",
      "optional": true,
      "os": [
        "android"
      ],
      "engines": {
        "node": ">= 12.0.0"
      },
      "funding": {
        "type": "opencollective",
        "url": "https://opencollective.com/parcel"
      }
    },
    "node_modules/lightningcss-darwin-arm64": {
      "version": "1.32.0",
      "resolved": "https://registry.npmjs.org/lightningcss-darwin-arm64/-/lightningcss-darwin-arm64-1.32.0.tgz",
      "integrity": "sha512-RzeG9Ju5bag2Bv1/lwlVJvBE3q6TtXskdZLLCyfg5pt+HLz9BqlICO7LZM7VHNTTn/5PRhHFBSjk5lc4cmscPQ==",
      "cpu": [
        "arm64"
      ],
      "license": "MPL-2.0",
      "optional": true,
      "os": [
        "darwin"
      ],
      "engines": {
        "node": ">= 12.0.0"
      },
      "funding": {
        "type": "opencollective",
        "url": "https://opencollective.com/parcel"
      }
    },
    "node_modules/lightningcss-darwin-x64": {
      "version": "1.32.0",
      "resolved": "https://registry.npmjs.org/lightningcss-darwin-x64/-/lightningcss-darwin-x64-1.32.0.tgz",
      "integrity": "sha512-U+QsBp2m/s2wqpUYT/6wnlagdZbtZdndSmut/NJqlCcMLTWp5muCrID+K5UJ6jqD2BFshejCYXniPDbNh73V8w==",
      "cpu": [
        "x64"
      ],
      "license": "MPL-2.0",
      "optional": true,
      "os": [
        "darwin"
      ],
      "engines": {
        "node": ">= 12.0.0"
      },
      "funding": {
        "type": "opencollective",
        "url": "https://opencollective.com/parcel"
      }
    },
    "node_modules/lightningcss-freebsd-x64": {
      "version": "1.32.0",
      "resolved": "https://registry.npmjs.org/lightningcss-freebsd-x64/-/lightningcss-freebsd-x64-1.32.0.tgz",
      "integrity": "sha512-JCTigedEksZk3tHTTthnMdVfGf61Fky8Ji2E4YjUTEQX14xiy/lTzXnu1vwiZe3bYe0q+SpsSH/CTeDXK6WHig==",
      "cpu": [
        "x64"
      ],
      "license": "MPL-2.0",
      "optional": true,
      "os": [
        "freebsd"
      ],
      "engines": {
        "node": ">= 12.0.0"
      },
      "funding": {
        "type": "opencollective",
        "url": "https://opencollective.com/parcel"
      }
    },
    "node_modules/lightningcss-linux-arm-gnueabihf": {
      "version": "1.32.0",
      "resolved": "https://registry.npmjs.org/lightningcss-linux-arm-gnueabihf/-/lightningcss-linux-arm-gnueabihf-1.32.0.tgz",
      "integrity": "sha512-x6rnnpRa2GL0zQOkt6rts3YDPzduLpWvwAF6EMhXFVZXD4tPrBkEFqzGowzCsIWsPjqSK+tyNEODUBXeeVHSkw==",
      "cpu": [
        "arm"
      ],
      "license": "MPL-2.0",
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">= 12.0.0"
      },
      "funding": {
        "type": "opencollective",
        "url": "https://opencollective.com/parcel"
      }
    },
    "node_modules/lightningcss-linux-arm64-gnu": {
      "version": "1.32.0",
      "resolved": "https://registry.npmjs.org/lightningcss-linux-arm64-gnu/-/lightningcss-linux-arm64-gnu-1.32.0.tgz",
      "integrity": "sha512-0nnMyoyOLRJXfbMOilaSRcLH3Jw5z9HDNGfT/gwCPgaDjnx0i8w7vBzFLFR1f6CMLKF8gVbebmkUN3fa/kQJpQ==",
      "cpu": [
        "arm64"
      ],
      "libc": [
        "glibc"
      ],
      "license": "MPL-2.0",
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">= 12.0.0"
      },
      "funding": {
        "type": "opencollective",
        "url": "https://opencollective.com/parcel"
      }
    },
    "node_modules/lightningcss-linux-arm64-musl": {
      "version": "1.32.0",
      "resolved": "https://registry.npmjs.org/lightningcss-linux-arm64-musl/-/lightningcss-linux-arm64-musl-1.32.0.tgz",
      "integrity": "sha512-UpQkoenr4UJEzgVIYpI80lDFvRmPVg6oqboNHfoH4CQIfNA+HOrZ7Mo7KZP02dC6LjghPQJeBsvXhJod/wnIBg==",
      "cpu": [
        "arm64"
      ],
      "libc": [
        "musl"
      ],
      "license": "MPL-2.0",
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">= 12.0.0"
      },
      "funding": {
        "type": "opencollective",
        "url": "https://opencollective.com/parcel"
      }
    },
    "node_modules/lightningcss-linux-x64-gnu": {
      "version": "1.32.0",
      "resolved": "https://registry.npmjs.org/lightningcss-linux-x64-gnu/-/lightningcss-linux-x64-gnu-1.32.0.tgz",
      "integrity": "sha512-V7Qr52IhZmdKPVr+Vtw8o+WLsQJYCTd8loIfpDaMRWGUZfBOYEJeyJIkqGIDMZPwPx24pUMfwSxxI8phr/MbOA==",
      "cpu": [
        "x64"
      ],
      "libc": [
        "glibc"
      ],
      "license": "MPL-2.0",
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">= 12.0.0"
      },
      "funding": {
        "type": "opencollective",
        "url": "https://opencollective.com/parcel"
      }
    },
    "node_modules/lightningcss-linux-x64-musl": {
      "version": "1.32.0",
      "resolved": "https://registry.npmjs.org/lightningcss-linux-x64-musl/-/lightningcss-linux-x64-musl-1.32.0.tgz",
      "integrity": "sha512-bYcLp+Vb0awsiXg/80uCRezCYHNg1/l3mt0gzHnWV9XP1W5sKa5/TCdGWaR/zBM2PeF/HbsQv/j2URNOiVuxWg==",
      "cpu": [
        "x64"
      ],
      "libc": [
        "musl"
      ],
      "license": "MPL-2.0",
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">= 12.0.0"
      },
      "funding": {
        "type": "opencollective",
        "url": "https://opencollective.com/parcel"
      }
    },
    "node_modules/lightningcss-win32-arm64-msvc": {
      "version": "1.32.0",
      "resolved": "https://registry.npmjs.org/lightningcss-win32-arm64-msvc/-/lightningcss-win32-arm64-msvc-1.32.0.tgz",
      "integrity": "sha512-8SbC8BR40pS6baCM8sbtYDSwEVQd4JlFTOlaD3gWGHfThTcABnNDBda6eTZeqbofalIJhFx0qKzgHJmcPTnGdw==",
      "cpu": [
        "arm64"
      ],
      "license": "MPL-2.0",
      "optional": true,
      "os": [
        "win32"
      ],
      "engines": {
        "node": ">= 12.0.0"
      },
      "funding": {
        "type": "opencollective",
        "url": "https://opencollective.com/parcel"
      }
    },
    "node_modules/lightningcss-win32-x64-msvc": {
      "version": "1.32.0",
      "resolved": "https://registry.npmjs.org/lightningcss-win32-x64-msvc/-/lightningcss-win32-x64-msvc-1.32.0.tgz",
      "integrity": "sha512-Amq9B/SoZYdDi1kFrojnoqPLxYhQ4Wo5XiL8EVJrVsB8ARoC1PWW6VGtT0WKCemjy8aC+louJnjS7U18x3b06Q==",
      "cpu": [
        "x64"
      ],
      "license": "MPL-2.0",
      "optional": true,
      "os": [
        "win32"
      ],
      "engines": {
        "node": ">= 12.0.0"
      },
      "funding": {
        "type": "opencollective",
        "url": "https://opencollective.com/parcel"
      }
    },
    "node_modules/nanoid": {
      "version": "3.3.15",
      "resolved": "https://registry.npmjs.org/nanoid/-/nanoid-3.3.15.tgz",
      "integrity": "sha512-y7Wygv/7mEOvxTuEQDB8StXdMRBWf1kR/tlhAzBRUFkB2jfcLOAxO/SHmOO2zgz1pVgK29/kyupn059/bCHdjA==",
      "funding": [
        {
          "type": "github",
          "url": "https://github.com/sponsors/ai"
        }
      ],
      "license": "MIT",
      "bin": {
        "nanoid": "bin/nanoid.cjs"
      },
      "engines": {
        "node": "^10 || ^12 || ^13.7 || ^14 || >=15.0.1"
      }
    },
    "node_modules/picocolors": {
      "version": "1.1.1",
      "resolved": "https://registry.npmjs.org/picocolors/-/picocolors-1.1.1.tgz",
      "integrity": "sha512-xceH2snhtb5M9liqDsmEw56le376mTZkEX/jEb/RxNFyegNul7eNslCXP9FDj/Lcu0X8KEyMceP2ntpaHrDEVA==",
      "license": "ISC"
    },
    "node_modules/picomatch": {
      "version": "4.0.4",
      "resolved": "https://registry.npmjs.org/picomatch/-/picomatch-4.0.4.tgz",
      "integrity": "sha512-QP88BAKvMam/3NxH6vj2o21R6MjxZUAd6nlwAS/pnGvN9IVLocLHxGYIzFhg6fUQ+5th6P4dv4eW9jX3DSIj7A==",
      "license": "MIT",
      "engines": {
        "node": ">=12"
      },
      "funding": {
        "url": "https://github.com/sponsors/jonschlinkert"
      }
    },
    "node_modules/postcss": {
      "version": "8.5.15",
      "resolved": "https://registry.npmjs.org/postcss/-/postcss-8.5.15.tgz",
      "integrity": "sha512-FfR8sjd4em2T6fb3I2MwAJU7HWVMr9zba+enmQeeWFfCbm+UOC/0X4DS8XtpUTMwWMGbjKYP7xjfNekzyGmB3A==",
      "funding": [
        {
          "type": "opencollective",
          "url": "https://opencollective.com/postcss/"
        },
        {
          "type": "tidelift",
          "url": "https://tidelift.com/funding/github/npm/postcss"
        },
        {
          "type": "github",
          "url": "https://github.com/sponsors/ai"
        }
      ],
      "license": "MIT",
      "dependencies": {
        "nanoid": "^3.3.12",
        "picocolors": "^1.1.1",
        "source-map-js": "^1.2.1"
      },
      "engines": {
        "node": "^10 || ^12 || >=14"
      }
    },
    "node_modules/react": {
      "version": "19.2.6",
      "resolved": "https://registry.npmjs.org/react/-/react-19.2.6.tgz",
      "integrity": "sha512-sfWGGfavi0xr8Pg0sVsyHMAOziVYKgPLNrS7ig+ivMNb3wbCBw3KxtflsGBAwD3gYQlE/AEZsTLgToRrSCjb0Q==",
      "license": "MIT",
      "engines": {
        "node": ">=0.10.0"
      }
    },
    "node_modules/react-dom": {
      "version": "19.2.6",
      "resolved": "https://registry.npmjs.org/react-dom/-/react-dom-19.2.6.tgz",
      "integrity": "sha512-0prMI+hvBbPjsWnxDLxlCGyM8PN6UuWjEUCYmZhO67xIV9Xasa/r/vDnq+Xyq4Lo27g8QSbO5YzARu0D1Sps3g==",
      "license": "MIT",
      "dependencies": {
        "scheduler": "^0.27.0"
      },
      "peerDependencies": {
        "react": "^19.2.6"
      }
    },
    "node_modules/rolldown": {
      "version": "1.0.0",
      "resolved": "https://registry.npmjs.org/rolldown/-/rolldown-1.0.0.tgz",
      "integrity": "sha512-yD986aXDESFGS95spT1LAv0jssywP4npMEjmMHyN2/5+eE8qQJUype2AaKkRiLgBgyD0LFlubwAht7VmY8rGoA==",
      "license": "MIT",
      "dependencies": {
        "@oxc-project/types": "=0.129.0",
        "@rolldown/pluginutils": "1.0.0"
      },
      "bin": {
        "rolldown": "bin/cli.mjs"
      },
      "engines": {
        "node": "^20.19.0 || >=22.12.0"
      },
      "optionalDependencies": {
        "@rolldown/binding-android-arm64": "1.0.0",
        "@rolldown/binding-darwin-arm64": "1.0.0",
        "@rolldown/binding-darwin-x64": "1.0.0",
        "@rolldown/binding-freebsd-x64": "1.0.0",
        "@rolldown/binding-linux-arm-gnueabihf": "1.0.0",
        "@rolldown/binding-linux-arm64-gnu": "1.0.0",
        "@rolldown/binding-linux-arm64-musl": "1.0.0",
        "@rolldown/binding-linux-ppc64-gnu": "1.0.0",
        "@rolldown/binding-linux-s390x-gnu": "1.0.0",
        "@rolldown/binding-linux-x64-gnu": "1.0.0",
        "@rolldown/binding-linux-x64-musl": "1.0.0",
        "@rolldown/binding-openharmony-arm64": "1.0.0",
        "@rolldown/binding-wasm32-wasi": "1.0.0",
        "@rolldown/binding-win32-arm64-msvc": "1.0.0",
        "@rolldown/binding-win32-x64-msvc": "1.0.0"
      }
    },
    "node_modules/rolldown/node_modules/@rolldown/pluginutils": {
      "version": "1.0.0",
      "resolved": "https://registry.npmjs.org/@rolldown/pluginutils/-/pluginutils-1.0.0.tgz",
      "integrity": "sha512-aKs/3GSWyV0mrhNmt/96/Z3yczC3yvrzYATCiCXQebBsGyYzjNdUphRVLeJQ67ySKVXRfMxt2lm12pmXvbPFQQ==",
      "license": "MIT"
    },
    "node_modules/scheduler": {
      "version": "0.27.0",
      "resolved": "https://registry.npmjs.org/scheduler/-/scheduler-0.27.0.tgz",
      "integrity": "sha512-eNv+WrVbKu1f3vbYJT/xtiF5syA5HPIMtf9IgY/nKg0sWqzAUEvqY/xm7OcZc/qafLx/iO9FgOmeSAp4v5ti/Q==",
      "license": "MIT"
    },
    "node_modules/source-map-js": {
      "version": "1.2.1",
      "resolved": "https://registry.npmjs.org/source-map-js/-/source-map-js-1.2.1.tgz",
      "integrity": "sha512-UXWMKhLOwVKb728IUtQPXxfYU+usdybtUrK/8uGE8CQMvrhOpwvzDBwj0QhSL7MQc7vIsISBG8VQ8+IDQxpfQA==",
      "license": "BSD-3-Clause",
      "engines": {
        "node": ">=0.10.0"
      }
    },
    "node_modules/tinyglobby": {
      "version": "0.2.17",
      "resolved": "https://registry.npmjs.org/tinyglobby/-/tinyglobby-0.2.17.tgz",
      "integrity": "sha512-wXR/dYpcqKmfWpEdZjiKJOwCNFndD0DMnrW/cYjVGttEkBfVgcLFHoNrlj47mjOVic9yyNu65alsgF4NQyTa2g==",
      "license": "MIT",
      "dependencies": {
        "fdir": "^6.5.0",
        "picomatch": "^4.0.4"
      },
      "engines": {
        "node": ">=12.0.0"
      },
      "funding": {
        "url": "https://github.com/sponsors/SuperchupuDev"
      }
    },
    "node_modules/tslib": {
      "version": "2.8.1",
      "resolved": "https://registry.npmjs.org/tslib/-/tslib-2.8.1.tgz",
      "integrity": "sha512-oJFu94HQb+KVduSUQL7wnpmqnfmLsOA/nAh6b6EH0wCEoK0/mPeXU6c3wKDV83MkOuHPRHtSXKKU99IBazS/2w==",
      "license": "0BSD",
      "optional": true
    },
    "node_modules/typescript": {
      "version": "5.9.3",
      "resolved": "https://registry.npmjs.org/typescript/-/typescript-5.9.3.tgz",
      "integrity": "sha512-jl1vZzPDinLr9eUt3J/t7V6FgNEw9QjvBPdysz9KfQDD41fQrC2Y4vKQdiaUpFT4bXlb1RHhLpp8wtm6M5TgSw==",
      "license": "Apache-2.0",
      "bin": {
        "tsc": "bin/tsc",
        "tsserver": "bin/tsserver"
      },
      "engines": {
        "node": ">=14.17"
      }
    },
    "node_modules/vite": {
      "version": "8.0.12",
      "resolved": "https://registry.npmjs.org/vite/-/vite-8.0.12.tgz",
      "integrity": "sha512-w2dDofOWv2QB09ZITZBsvKTVAlYvPR4IAmrY/v0ir9KvLs0xybR7i48wxhM1/oyBWO34wPns+bPGw5ZrZqDpZg==",
      "license": "MIT",
      "dependencies": {
        "lightningcss": "^1.32.0",
        "picomatch": "^4.0.4",
        "postcss": "^8.5.14",
        "rolldown": "1.0.0",
        "tinyglobby": "^0.2.16"
      },
      "bin": {
        "vite": "bin/vite.js"
      },
      "engines": {
        "node": "^20.19.0 || >=22.12.0"
      },
      "funding": {
        "url": "https://github.com/vitejs/vite?sponsor=1"
      },
      "optionalDependencies": {
        "fsevents": "~2.3.3"
      },
      "peerDependencies": {
        "@types/node": "^20.19.0 || >=22.12.0",
        "@vitejs/devtools": "^0.1.18",
        "esbuild": "^0.27.0 || ^0.28.0",
        "jiti": ">=1.21.0",
        "less": "^4.0.0",
        "sass": "^1.70.0",
        "sass-embedded": "^1.70.0",
        "stylus": ">=0.54.8",
        "sugarss": "^5.0.0",
        "terser": "^5.16.0",
        "tsx": "^4.8.1",
        "yaml": "^2.4.2"
      },
      "peerDependenciesMeta": {
        "@types/node": {
          "optional": true
        },
        "@vitejs/devtools": {
          "optional": true
        },
        "esbuild": {
          "optional": true
        },
        "jiti": {
          "optional": true
        },
        "less": {
          "optional": true
        },
        "sass": {
          "optional": true
        },
        "sass-embedded": {
          "optional": true
        },
        "stylus": {
          "optional": true
        },
        "sugarss": {
          "optional": true
        },
        "terser": {
          "optional": true
        },
        "tsx": {
          "optional": true
        },
        "yaml": {
          "optional": true
        }
      }
    }
  }
}
````

### `widget-wrapper\README.md`

````markdown
# Generic Widget Wrapper

Reusable React + TypeScript widget shell for wrapping any assistant, iframe, third-party script, or custom message feed.

The implementation is generic. No brand-specific text, country list, language list, consent copy, response text, product copy, or starter content is hardcoded in the components. Visible content comes from `config` or caller-provided children/render functions.

## AWS-Connected Local Demo

The default demo runs the widget locally and sends consent/chat events to the Python API at `http://127.0.0.1:8000`.

Start the API from the `chatbot python` folder:

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

Then start the widget demo:

```bash
cd "chatbot python/widget-wrapper"
npm install
npm run demo
```

Open `http://127.0.0.1:5174`.

To point the demo at a different API host, add the `api` query string:

```text
http://127.0.0.1:5174/?api=https://your-api.example.com
```

The API needs AWS access for RDS, Valkey, Bedrock, Firehose, SQS, and Comprehend before real answers will return. If you are running locally with the defaults in `config/settings.py`, use `SSM_CONFIG_ENABLED=false` only when you do not want startup to read SSM Parameter Store.

## Offline Simulator

`LocalChatwootDemo` is still available when you want to review the visual flow without an API connection. It uses a simulated Chatwoot-style provider so the wrapper can be reviewed before the real Chatwoot inbox is ready.

## Files

- `src/generic-widget/GenericWidgetWrapper.tsx`
- `src/generic-widget/PlainStateGenericWidgetWrapper.tsx`
- `src/generic-widget/Header.tsx`
- `src/generic-widget/RegionSelector.tsx`
- `src/generic-widget/ConsentPanel.tsx`
- `src/generic-widget/LegalLinks.tsx`
- `src/generic-widget/MessageFeed.tsx`
- `src/generic-widget/Menu.tsx`
- `src/generic-widget/FloatingLauncher.tsx`
- `src/generic-widget/types.ts`
- `src/generic-widget/config/defaultTheme.ts`
- `src/generic-widget/config/exampleWidgetConfig.ts`
- `src/generic-widget/examples/ThirdPartyWidgetExample.tsx`
- `src/generic-widget/examples/ChatwootWidgetExample.tsx`
- `src/generic-widget/examples/BackendChatDemo.tsx`
- `src/generic-widget/examples/LocalChatwootDemo.tsx`
- `src/generic-widget/examples/foreverDemoConfig.tsx`
- `src/generic-widget/integrations/ChatwootWidgetAdapter.tsx`
- `demo/`

## Mock Chatbot

```tsx
import { useState } from "react";
import { GenericWidgetWrapper, exampleWidgetConfig, type WidgetMessage } from "./src/generic-widget";

export function DemoChat() {
  const [messages, setMessages] = useState<WidgetMessage[]>([]);

  return (
    <GenericWidgetWrapper
      config={exampleWidgetConfig}
      messages={messages}
      onSendMessage={(payload) => {
        setMessages((current) => [
          ...current,
          { id: crypto.randomUUID(), role: "user", content: payload.message }
        ]);
      }}
    />
  );
}
```

## Iframe

```tsx
import { GenericWidgetWrapper, exampleWidgetConfig } from "./src/generic-widget";

export function IframeWrapper() {
  return (
    <GenericWidgetWrapper config={{ ...exampleWidgetConfig, provider: { name: "Iframe provider", type: "iframe" } }}>
      <iframe title="Embedded assistant" src="https://example.com/embed" />
    </GenericWidgetWrapper>
  );
}
```

## Third-Party Script

```tsx
import { useEffect, useRef } from "react";
import { PlainStateGenericWidgetWrapper, exampleWidgetConfig } from "./src/generic-widget";

function ScriptMount({ src }: { src: string }) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    ref.current.appendChild(script);
    return () => script.remove();
  }, [src]);

  return <div ref={ref} />;
}

export function ScriptWrapper() {
  return (
    <PlainStateGenericWidgetWrapper config={{ ...exampleWidgetConfig, provider: { name: "Script provider", type: "script" } }}>
      <ScriptMount src="https://example.com/widget.js" />
    </PlainStateGenericWidgetWrapper>
  );
}
```

## Chatwoot

Use `ChatwootWidgetAdapter` when Chatwoot is the chat engine behind the generic wrapper. The wrapper still owns the launcher, header, region/language selector, consent step, legal links, and callbacks. Chatwoot is loaded as an injected third-party script and receives wrapper context through custom attributes.

```tsx
import { GenericWidgetWrapper, ChatwootWidgetAdapter, exampleWidgetConfig } from "./src/generic-widget";

export function ChatwootWrapper() {
  return (
    <GenericWidgetWrapper
      config={{
        ...exampleWidgetConfig,
        provider: { name: "Chatwoot", type: "script" }
      }}
    >
      {(state) => (
        <ChatwootWidgetAdapter
          baseUrl="https://app.chatwoot.com"
          websiteToken="replace-with-chatwoot-website-token"
          state={state}
          settings={{
            position: "right",
            type: "standard",
            launcherTitle: exampleWidgetConfig.labels.launcherAriaLabel
          }}
          customAttributes={{
            source: "generic-widget-wrapper"
          }}
        />
      )}
    </GenericWidgetWrapper>
  );
}
```

For self-hosted Chatwoot, pass the self-hosted app URL as `baseUrl`. Keep the website token outside this package and inject it from the consuming app's environment/config.

For a real local Chatwoot instance, run Chatwoot locally and pass its app URL, usually `http://localhost:3000`, plus the website token from the Chatwoot website inbox.
````

### `widget-wrapper\src\generic-widget\config\defaultTheme.ts`

````typescript
import type { WidgetTheme } from "../types";

export const defaultTheme: Required<WidgetTheme> = {
  accentColor: "#155e75",
  accentTextColor: "#ffffff",
  surfaceColor: "#f8fafc",
  panelColor: "#ffffff",
  textColor: "#111827",
  mutedTextColor: "#64748b",
  borderColor: "#dbe3ea",
  launcherColor: "#155e75",
  launcherTextColor: "#ffffff",
  successColor: "#047857",
  dangerColor: "#b42318",
  shadow: "0 24px 70px rgba(15, 23, 42, 0.2)",
  radius: "8px",
  fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
  zIndex: 2147483000
};
````

### `widget-wrapper\src\generic-widget\config\exampleWidgetConfig.ts`

````typescript
import type { GenericWidgetConfig } from "../types";

export const exampleWidgetConfig: GenericWidgetConfig = {
  brandName: "Demo Assistant",
  welcomeText: "Choose your region and review the consent notice to begin.",
  loadingText: "Loading response...",
  successText: "Consent saved. You can now continue.",
  provider: { name: "Demo provider", type: "custom-react" },
  labels: {
    launcherAriaLabel: "Open assistant",
    closeAriaLabel: "Close assistant",
    menuAriaLabel: "Open assistant menu",
    countryLabel: "Region",
    languageLabel: "Language",
    countryPlaceholder: "Select a region",
    languagePlaceholder: "Select a language",
    continueLabel: "Continue",
    acceptConsentLabel: "Accept",
    rejectConsentLabel: "Decline",
    messageInputLabel: "Message",
    messageInputPlaceholder: "Type a message",
    sendMessageLabel: "Send message",
    suggestedTopicsLabel: "Suggested topics",
    legalLinksLabel: "Legal links",
    childrenRegionLabel: "Embedded assistant",
    successDismissLabel: "Dismiss confirmation"
  },
  menu: {
    settings: "Settings",
    history: "History",
    newChat: "New chat",
    escalate: "Contact support"
  },
  consent: {
    title: "Consent",
    body: "This assistant may process your messages according to the linked policies. Accept to continue.",
    policyVersion: "2026-01",
    categories: ["chat-processing", "support"],
    storageKey: "generic-widget-consent-demo",
    requireConsentBeforeMessaging: true
  },
  policyLinks: [
    { id: "privacy", label: "Privacy policy", href: "/privacy" },
    { id: "terms", label: "Terms of use", href: "/terms" }
  ],
  countries: [
    { code: "US", label: "United States", languageCodes: ["en", "es"] },
    { code: "CA", label: "Canada", languageCodes: ["en", "fr"] },
    { code: "GB", label: "United Kingdom", languageCodes: ["en"] }
  ],
  languages: [
    { code: "en", label: "English", countryCodes: ["US", "CA", "GB"] },
    { code: "es", label: "Spanish", countryCodes: ["US"] },
    { code: "fr", label: "French", countryCodes: ["CA"] }
  ],
  starterTopics: [
    { id: "orders", label: "Orders", prompt: "I need help with an order." },
    { id: "account", label: "Account", prompt: "I need help with my account." }
  ],
  contextualTopics: [{ id: "support", label: "Support", prompt: "Connect me with support." }]
};
````

### `widget-wrapper\src\generic-widget\ConsentPanel.tsx`

````tsx
import type { GenericWidgetConfig } from "./types";
import { LegalLinks } from "./LegalLinks";

export function ConsentPanel({
  config,
  onAccept,
  onReject
}: {
  config: GenericWidgetConfig;
  onAccept: () => void;
  onReject: () => void;
}) {
  return (
    <section className="gw-section gw-consent">
      <h2>{config.consent.title}</h2>
      <div className="gw-consent-body">{config.consent.body}</div>
      <LegalLinks config={config} />
      <div className="gw-consent-actions">
        <button type="button" className="gw-secondary-button" onClick={onReject}>{config.labels.rejectConsentLabel}</button>
        <button type="button" className="gw-primary-button" onClick={onAccept}>{config.labels.acceptConsentLabel}</button>
      </div>
    </section>
  );
}
````

### `widget-wrapper\src\generic-widget\examples\BackendChatDemo.tsx`

````tsx
import { useMemo, useState } from "react";
import { GenericWidgetWrapper } from "../GenericWidgetWrapper";
import type { ConsentEventPayload, MessageEventPayload, WidgetMessage } from "../types";
import { foreverDemoConfig } from "./foreverDemoConfig";

type ApiEnvelope<T> = {
  success: boolean;
  data?: T;
  error?: { code: string; message: string };
  correlationId: string;
};

type ChatResponseData = {
  response: string;
  sources?: Array<{ title: string; uri: string; excerpt?: string }>;
  confidence?: number;
  correlationId?: string;
};

export type BackendChatDemoProps = {
  apiBaseUrl?: string;
};

const buildId = (prefix: string) => {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const joinUrl = (baseUrl: string, path: string) => `${baseUrl.replace(/\/$/, "")}${path}`;

async function postJson<T>(baseUrl: string, path: string, body: unknown): Promise<ApiEnvelope<T>> {
  const response = await fetch(joinUrl(baseUrl, path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const envelope = (await response.json()) as ApiEnvelope<T>;
  if (!response.ok || !envelope.success) {
    throw new Error(envelope.error?.message || `Request failed with status ${response.status}`);
  }
  return envelope;
}

export function BackendChatDemo({ apiBaseUrl = "http://127.0.0.1:8000" }: BackendChatDemoProps) {
  const config = useMemo(
    () => ({
      ...foreverDemoConfig,
      provider: { name: "ASK Vera API", type: "custom-react" },
      policyLinks: foreverDemoConfig.policyLinks.map((link) => ({
        ...link,
        href: link.href.startsWith("/api/") ? joinUrl(apiBaseUrl, link.href) : link.href
      }))
    }),
    [apiBaseUrl]
  );
  const [messages, setMessages] = useState<WidgetMessage[]>([
    {
      id: "backend-welcome",
      role: "assistant",
      content: "Accept the privacy terms, then ask a question. This demo sends messages to the Python API."
    }
  ]);
  const [loading, setLoading] = useState(false);

  const appendMessage = (message: WidgetMessage) => {
    setMessages((current) => [...current, message]);
  };

  const handleConsent = async (payload: ConsentEventPayload) => {
    try {
      await postJson(apiBaseUrl, "/api/consent", {
        sessionId: payload.sessionId,
        country: payload.selectedCountry,
        lang: payload.selectedLanguage,
        timestamp: payload.timestamp,
        version: payload.policyVersion
      });
    } catch (error) {
      appendMessage({
        id: buildId("consent-warning"),
        role: "system",
        content: error instanceof Error ? `Consent accepted locally, but the API could not record it: ${error.message}` : "Consent accepted locally, but the API could not record it."
      });
    }
  };

  const handleMessage = async (payload: MessageEventPayload) => {
    appendMessage({ id: buildId("user"), role: "user", content: payload.message });
    setLoading(true);
    try {
      const envelope = await postJson<ChatResponseData>(apiBaseUrl, "/api/chat", {
        message: payload.message,
        sessionId: payload.sessionId,
        country: payload.selectedCountry,
        language: payload.selectedLanguage,
        role: "new_prospect"
      });
      appendMessage({
        id: buildId("assistant"),
        role: "assistant",
        content: envelope.data?.response || "I could not find a response for that question.",
        metadata: {
          sources: envelope.data?.sources || [],
          confidence: envelope.data?.confidence,
          correlationId: envelope.data?.correlationId || envelope.correlationId
        }
      });
    } catch (error) {
      appendMessage({
        id: buildId("api-error"),
        role: "system",
        content: error instanceof Error ? `The API is not ready yet: ${error.message}` : "The API is not ready yet."
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <GenericWidgetWrapper
      config={config}
      messages={messages}
      loading={loading}
      openByDefault
      onAcceptConsent={handleConsent}
      onSendMessage={handleMessage}
      onNewChat={() =>
        setMessages([
          {
            id: buildId("new-chat"),
            role: "assistant",
            content: "New chat started. Your selected market and language will stay active."
          }
        ])
      }
    />
  );
}
````

### `widget-wrapper\src\generic-widget\examples\ChatwootWidgetExample.tsx`

````tsx
import { GenericWidgetWrapper } from "../GenericWidgetWrapper";
import { exampleWidgetConfig } from "../config/exampleWidgetConfig";
import { ChatwootWidgetAdapter } from "../integrations/ChatwootWidgetAdapter";
import type { GenericWidgetConfig } from "../types";

const chatwootConfig: GenericWidgetConfig = {
  ...exampleWidgetConfig,
  provider: { name: "Chatwoot", type: "script" }
};

export function ChatwootWidgetExample({ baseUrl, websiteToken }: { baseUrl: string; websiteToken: string }) {
  return (
    <GenericWidgetWrapper config={chatwootConfig}>
      {(state) => (
        <ChatwootWidgetAdapter
          baseUrl={baseUrl}
          websiteToken={websiteToken}
          state={state}
          settings={{
            position: "right",
            type: "standard",
            launcherTitle: chatwootConfig.labels.launcherAriaLabel
          }}
          customAttributes={{
            provider: chatwootConfig.provider.name,
            providerType: chatwootConfig.provider.type
          }}
        />
      )}
    </GenericWidgetWrapper>
  );
}
````

### `widget-wrapper\src\generic-widget\examples\foreverDemoConfig.tsx`

````tsx
import type { GenericWidgetConfig } from "../types";
import { exampleWidgetConfig } from "../config/exampleWidgetConfig";

export const foreverDemoConfig: GenericWidgetConfig = {
  ...exampleWidgetConfig,
  brandName: "FOREVER",
  welcomeText: (
    <>
      <p>I'm here to help you find clear, useful support for your selected market and language.</p>
      <p>Choose a topic below or ask a question to start a conversation.</p>
    </>
  ),
  successText: "Thank you. Your privacy choices have been saved and chat is ready.",
  labels: {
    ...exampleWidgetConfig.labels,
    countryLabel: "Market",
    languageLabel: "Language",
    acceptConsentLabel: "Accept and continue",
    rejectConsentLabel: "Not now",
    messageInputPlaceholder: "Ask a question"
  },
  consent: {
    ...exampleWidgetConfig.consent,
    title: "Privacy and terms",
    body: "To personalize this chat for your selected market and language, this assistant may process your message and basic session details according to the linked policies.",
    categories: ["chat-processing", "market-language-preferences"],
    storageKey: "forever-style-widget-demo-consent"
  },
  policyLinks: [
    { id: "privacy", label: "Privacy Notice", href: "/api/privacy?country=US&lang=en" },
    { id: "terms", label: "Terms of Use", href: "/terms" }
  ],
  theme: {
    accentColor: "#ffc400",
    accentTextColor: "#000000",
    launcherColor: "#000000",
    launcherTextColor: "#ffc400",
    successColor: "#2f6f4e",
    textColor: "#111111",
    mutedTextColor: "#5f5f5f",
    borderColor: "#dedede",
    surfaceColor: "#ffffff",
    panelColor: "#ffffff",
    shadow: "0 22px 60px rgba(0, 0, 0, 0.18)",
    radius: "8px"
  },
  provider: { name: "ASK Vera API", type: "custom-react" },
  starterTopics: [
    { id: "products", label: "What products are right for me?", prompt: "What products are right for me?" },
    { id: "orders", label: "I need help with an order", prompt: "I need help with an order." },
    { id: "account", label: "Help me with my account", prompt: "Help me with my account." },
    { id: "policies", label: "Where can I find policy information?", prompt: "Where can I find policy information?" }
  ],
  contextualTopics: []
};
````

### `widget-wrapper\src\generic-widget\examples\LocalChatwootDemo.tsx`

````tsx
import { useState } from "react";
import { GenericWidgetWrapper } from "../GenericWidgetWrapper";
import type { MessageEventPayload, WidgetMessage } from "../types";
import { foreverDemoConfig } from "./foreverDemoConfig";

const localChatwootConfig = {
  ...foreverDemoConfig,
  provider: { name: "Local Chatwoot simulator", type: "script" }
};

export function LocalChatwootDemo() {
  const [messages, setMessages] = useState<WidgetMessage[]>([
    {
      id: "local-chatwoot-welcome",
      role: "assistant",
      content: "After privacy acceptance, this local provider simulates the connected widget response."
    }
  ]);

  const handleMessage = (payload: MessageEventPayload) => {
    setMessages((current) => [
      ...current,
      { id: `user-${Date.now()}`, role: "user", content: payload.message },
      {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: `Demo reply from ${localChatwootConfig.provider.name}. Country: ${payload.selectedCountry || "none"}, language: ${payload.selectedLanguage || "none"}.`
      }
    ]);
  };

  return (
    <GenericWidgetWrapper
      config={localChatwootConfig}
      messages={messages}
      openByDefault
      onSendMessage={handleMessage}
    />
  );
}
````

### `widget-wrapper\src\generic-widget\examples\ThirdPartyWidgetExample.tsx`

````tsx
import { useEffect, useRef, useState } from "react";
import { GenericWidgetWrapper } from "../GenericWidgetWrapper";
import { PlainStateGenericWidgetWrapper } from "../PlainStateGenericWidgetWrapper";
import { exampleWidgetConfig } from "../config/exampleWidgetConfig";
import type { MessageEventPayload, WidgetMessage } from "../types";

export function MockChatbotExample() {
  const [messages, setMessages] = useState<WidgetMessage[]>([]);

  const handleMessage = (payload: MessageEventPayload) => {
    setMessages((current) => [
      ...current,
      { id: `user-${Date.now()}`, role: "user", content: payload.message },
      { id: `assistant-${Date.now()}`, role: "assistant", content: "This is a mock response supplied by the demo chat engine." }
    ]);
  };

  return <GenericWidgetWrapper config={exampleWidgetConfig} messages={messages} onSendMessage={handleMessage} />;
}

export function IframeWidgetExample() {
  return (
    <GenericWidgetWrapper config={{ ...exampleWidgetConfig, provider: { name: "Iframe provider", type: "iframe" } }}>
      <iframe title="Embedded assistant" src="https://example.com/embed" style={{ width: "100%", height: 360, border: 0, borderRadius: 12 }} />
    </GenericWidgetWrapper>
  );
}

function ScriptMount({ src }: { src: string }) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    ref.current.appendChild(script);

    return () => script.remove();
  }, [src]);

  return <div ref={ref} />;
}

export function ScriptWidgetExample() {
  return (
    <PlainStateGenericWidgetWrapper config={{ ...exampleWidgetConfig, provider: { name: "Script provider", type: "script" } }}>
      <ScriptMount src="https://example.com/widget.js" />
    </PlainStateGenericWidgetWrapper>
  );
}
````

### `widget-wrapper\src\generic-widget\FloatingLauncher.tsx`

````tsx
import type { GenericWidgetConfig } from "./types";

export function FloatingLauncher({ config, onClick }: { config: GenericWidgetConfig; onClick: () => void }) {
  return (
    <button type="button" className="gw-launcher" onClick={onClick} aria-label={config.labels.launcherAriaLabel}>
      <span aria-hidden="true" className="gw-launcher-mark">
        {config.brandName.slice(0, 1)}
      </span>
    </button>
  );
}
````

### `widget-wrapper\src\generic-widget\generic-widget.css`

````css
.gw-root {
  --gw-panel-width: min(470px, calc(100vw - 24px));
  font-family: var(--gw-font);
  color: var(--gw-text);
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: var(--gw-z);
}

.gw-root * {
  box-sizing: border-box;
}

.gw-launcher {
  width: 58px;
  height: 58px;
  border: 0;
  border-radius: 999px;
  background: var(--gw-launcher);
  color: var(--gw-launcher-text);
  box-shadow: 0 18px 42px rgba(15, 23, 42, 0.22);
  cursor: pointer;
  display: grid;
  place-items: center;
  transition: transform 180ms ease;
}

.gw-launcher:hover,
.gw-launcher:focus-visible {
  transform: translateY(-2px);
}

.gw-launcher-mark {
  width: 32px;
  height: 32px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  border: 1px solid rgba(255, 255, 255, 0.48);
  font-weight: 700;
}

.gw-panel {
  width: var(--gw-panel-width);
  max-height: min(768px, calc(100vh - 28px));
  min-height: min(768px, calc(100vh - 28px));
  background: #ffffff;
  border: 0;
  border-radius: var(--gw-radius);
  box-shadow: var(--gw-shadow);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  animation: gw-panel-in 180ms ease;
}

@keyframes gw-panel-in {
  from { opacity: 0; transform: translateY(10px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.gw-header {
  position: relative;
  min-height: 70px;
  padding: 16px 64px;
  background: #000000;
  border-bottom: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.gw-title {
  color: #ffffff;
  font-family: Georgia, "Times New Roman", serif;
  font-size: 23px;
  font-weight: 500;
  letter-spacing: 0.2em;
  line-height: 1.2;
  text-align: center;
}
.gw-subtitle { display: none; }
.gw-header-actions {
  position: absolute;
  right: 18px;
  top: 50%;
  display: flex;
  gap: 12px;
  transform: translateY(-50%);
}

.gw-icon-button,
.gw-success-banner button {
  border: 1px solid transparent;
  background: transparent;
  border-radius: 8px;
  min-width: 32px;
  min-height: 32px;
  cursor: pointer;
}

.gw-icon-button {
  color: rgba(255, 255, 255, 0.78);
}

.gw-success-banner button {
  color: var(--gw-muted);
}

.gw-icon-button:hover,
.gw-icon-button:focus-visible {
  color: #ffffff;
  background: rgba(255, 255, 255, 0.14);
}

.gw-success-banner button:hover,
.gw-success-banner button:focus-visible {
  color: var(--gw-text);
  background: color-mix(in srgb, var(--gw-success), white 84%);
}

.gw-menu {
  position: absolute;
  right: 16px;
  top: 66px;
  width: 190px;
  background: var(--gw-panel);
  border: 1px solid var(--gw-border);
  border-radius: 8px;
  box-shadow: 0 18px 50px rgba(15, 23, 42, 0.18);
  padding: 6px;
}

.gw-menu-item {
  width: 100%;
  border: 0;
  background: transparent;
  color: var(--gw-text);
  border-radius: 7px;
  padding: 10px 11px;
  text-align: left;
  cursor: pointer;
}

.gw-menu-item:hover,
.gw-menu-item:focus-visible { background: var(--gw-surface); }

.gw-success-banner {
  position: absolute;
  left: 20px;
  right: 20px;
  top: 90px;
  z-index: 3;
  margin: 0;
  border: 1px solid rgba(50, 96, 77, 0.42);
  background: #f1fff7;
  color: #202020;
  border-radius: 4px;
  padding: 12px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  box-shadow: 0 3px 8px rgba(15, 23, 42, 0.16);
  font-size: 16px;
  line-height: 1.45;
}

.gw-success-banner::before {
  content: "\2713";
  flex: 0 0 auto;
  width: 23px;
  height: 23px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: #45795f;
  color: #ffffff;
  font-size: 15px;
  font-weight: 850;
}

.gw-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 26px 38px 24px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.gw-panel-has-success .gw-content {
  padding-top: 112px;
}

.gw-section,
.gw-message-feed,
.gw-child-slot {
  background: transparent;
  border: 0;
  border-radius: 0;
  padding: 0;
}

.gw-region-selector {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 2px;
  padding: 14px;
  background: #fafafa;
  border: 1px solid #e7e7e7;
  border-radius: 8px;
}

.gw-field {
  display: grid;
  gap: 6px;
  color: #666666;
  font-size: 11px;
  font-weight: 850;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.gw-field select,
.gw-composer input {
  width: 100%;
  border: 1px solid #dfdfdf;
  background: #fff;
  color: #272727;
  border-radius: 6px;
  min-height: 42px;
  padding: 0 12px;
  outline: none;
}

.gw-field select {
  appearance: none;
  background:
    linear-gradient(45deg, transparent 50%, #666 50%),
    linear-gradient(135deg, #666 50%, transparent 50%),
    #ffffff;
  background-position:
    calc(100% - 17px) 18px,
    calc(100% - 12px) 18px,
    0 0;
  background-size: 5px 5px, 5px 5px, 100% 100%;
  background-repeat: no-repeat;
  font-size: 14px;
  font-weight: 700;
}

.gw-field select:focus,
.gw-composer input:focus,
.gw-primary-button:focus-visible,
.gw-secondary-button:focus-visible,
.gw-topic:focus-visible {
  outline: 3px solid color-mix(in srgb, var(--gw-accent), transparent 68%);
  outline-offset: 2px;
  border-color: var(--gw-accent);
}

.gw-consent {
  padding: 16px;
  background: #ffffff;
  border: 1px solid #e2e2e2;
  border-left: 5px solid var(--gw-accent);
  border-radius: 8px;
  box-shadow: 0 10px 26px rgba(0, 0, 0, 0.06);
}

.gw-consent h2 { margin: 0 0 8px; color: #000000; font-size: 17px; font-weight: 850; }
.gw-consent-body { color: #4a4a4a; font-size: 14px; line-height: 1.55; }

.gw-legal {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.gw-legal a {
  color: #000000;
  text-decoration: none;
  font-size: 13px;
  font-weight: 800;
  border-bottom: 2px solid var(--gw-accent);
}

.gw-legal a:hover,
.gw-legal a:focus-visible { text-decoration: underline; }

.gw-consent-actions {
  margin-top: 16px;
  display: flex;
  gap: 10px;
}

.gw-primary-button,
.gw-secondary-button,
.gw-topic {
  border-radius: 8px;
  min-height: 40px;
  padding: 0 13px;
  font-weight: 700;
  cursor: pointer;
}

.gw-primary-button {
  border: 1px solid var(--gw-accent);
  background: var(--gw-accent);
  color: var(--gw-accent-text);
}

.gw-primary-button:disabled { opacity: 0.48; cursor: not-allowed; }

.gw-secondary-button,
.gw-topic {
  border: 1px solid var(--gw-border);
  background: #ffffff;
  color: var(--gw-text);
}

.gw-consent .gw-primary-button,
.gw-consent .gw-secondary-button {
  min-height: 42px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-size: 12px;
}

.gw-consent .gw-secondary-button {
  border-color: #cccccc;
}

.gw-secondary-button:hover,
.gw-topic:hover {
  border-color: color-mix(in srgb, var(--gw-accent), var(--gw-border) 58%);
  background: color-mix(in srgb, var(--gw-accent), white 94%);
}

.gw-topic {
  min-height: 40px;
  padding: 0 20px;
  border: 1px solid #000000;
  border-radius: 999px;
  background: #000000;
  color: #ffffff;
  font-size: 14px;
  font-weight: 800;
  box-shadow: none;
}

.gw-topic:hover,
.gw-topic:focus-visible {
  border-color: var(--gw-accent);
  background: var(--gw-accent);
  color: #000000;
}

.gw-section-title {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
  color: var(--gw-muted);
  font-size: 12px;
  font-weight: 750;
  margin-bottom: 10px;
}

.gw-topic-list { display: flex; flex-wrap: wrap; gap: 11px 8px; }

.gw-message-feed {
  display: grid;
  gap: 14px;
  align-content: start;
  color: #555;
  font-size: 17px;
  line-height: 1.48;
}

.gw-message {
  max-width: 100%;
  border-radius: 0;
  padding: 0;
  font-size: inherit;
  line-height: inherit;
}

.gw-message-system,
.gw-message-assistant {
  justify-self: start;
  background: transparent;
  border: 0;
}

.gw-message-user {
  justify-self: end;
  max-width: 86%;
  border-radius: 18px;
  padding: 10px 14px;
  background: #000000;
  color: #ffffff;
}

.gw-message p {
  margin: 0 0 16px;
}

.gw-message p:last-child {
  margin-bottom: 0;
}

.gw-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--gw-muted);
  font-size: 14px;
  padding: 8px 4px;
}

.gw-spinner {
  width: 16px;
  height: 16px;
  border-radius: 999px;
  border: 2px solid var(--gw-border);
  border-top-color: var(--gw-accent);
  animation: gw-spin 900ms linear infinite;
}

@keyframes gw-spin { to { transform: rotate(360deg); } }

.gw-composer {
  padding: 14px 10px 10px;
  margin: 0 0 0;
  background: #ffffff;
  border-top: 0;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
}

.gw-composer input {
  min-height: 56px;
  border-radius: 18px;
  padding: 0 24px;
  color: #262626;
  border-color: #dedede;
  font-size: 18px;
}

.gw-composer input::placeholder {
  color: #a7a7a7;
}

.gw-composer .gw-primary-button {
  width: 54px;
  min-width: 54px;
  min-height: 56px;
  padding: 0;
  border-radius: 18px;
  background: #ffffff;
  border-color: #dedede;
  color: #222222;
  font-size: 0;
}

.gw-composer .gw-primary-button::before {
  content: "\2191";
  font-size: 24px;
  line-height: 1;
}

.gw-sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

@media (max-width: 520px) {
  .gw-root { right: 12px; bottom: 12px; }
  .gw-panel { width: calc(100vw - 24px); min-height: min(620px, calc(100vh - 24px)); }
  .gw-region-selector { grid-template-columns: 1fr; }
}
````

### `widget-wrapper\src\generic-widget\GenericWidgetWrapper.tsx`

````tsx
import { FormEvent, type CSSProperties, useMemo, useState } from "react";
import { ConsentPanel } from "./ConsentPanel";
import { FloatingLauncher } from "./FloatingLauncher";
import { Header } from "./Header";
import { Menu } from "./Menu";
import { MessageFeed } from "./MessageFeed";
import { RegionSelector } from "./RegionSelector";
import { defaultTheme } from "./config/defaultTheme";
import type { GenericWidgetRenderState, GenericWidgetWrapperProps, MessageEventPayload, WidgetTheme } from "./types";
import {
  createConsentRecord,
  createLocalePayload,
  createSessionId,
  createVisitorId,
  detectInitialLocale,
  ensureLanguageForCountry,
  filterLanguagesByCountry,
  readConsentFlag,
  writeConsentFlag
} from "./utils";
import "./generic-widget.css";

const buildThemeVars = (theme?: WidgetTheme) => {
  const merged = { ...defaultTheme, ...theme };
  return {
    "--gw-accent": merged.accentColor,
    "--gw-accent-text": merged.accentTextColor,
    "--gw-surface": merged.surfaceColor,
    "--gw-panel": merged.panelColor,
    "--gw-text": merged.textColor,
    "--gw-muted": merged.mutedTextColor,
    "--gw-border": merged.borderColor,
    "--gw-launcher": merged.launcherColor,
    "--gw-launcher-text": merged.launcherTextColor,
    "--gw-success": merged.successColor,
    "--gw-shadow": merged.shadow,
    "--gw-radius": merged.radius,
    "--gw-font": merged.fontFamily,
    "--gw-z": String(merged.zIndex)
  } as CSSProperties;
};

export function GenericWidgetWrapper({
  config,
  children,
  messages = [],
  loading = false,
  openByDefault = false,
  initialConsentAccepted = false,
  initialShowSuccess = false,
  showLocaleSelector = true,
  visitorId: providedVisitorId,
  sessionId: providedSessionId,
  className = "",
  style,
  renderMessages,
  onOpen,
  onClose,
  onAcceptConsent,
  onRejectConsent,
  onCountryChange,
  onLanguageChange,
  onSendMessage,
  onEscalate,
  onNewChat
}: GenericWidgetWrapperProps) {
  const initialLocale = useMemo(
    () => detectInitialLocale(config.countries, config.languages, config.defaultCountryCode, config.defaultLanguageCode),
    [config.countries, config.defaultCountryCode, config.defaultLanguageCode, config.languages]
  );
  const [isOpen, setIsOpen] = useState(openByDefault);
  const [menuOpen, setMenuOpen] = useState(false);
  const [selectedCountry, setSelectedCountry] = useState(initialLocale.country);
  const [selectedLanguage, setSelectedLanguage] = useState(initialLocale.language);
  const [message, setMessage] = useState("");
  const [showSuccess, setShowSuccess] = useState(initialShowSuccess);
  const [visitorId] = useState(providedVisitorId || createVisitorId());
  const [sessionId] = useState(providedSessionId || createSessionId());
  const [consentAccepted, setConsentAccepted] = useState(
    Boolean(initialConsentAccepted || (config.persistConsent && readConsentFlag(config.consent.storageKey)))
  );
  const availableLanguages = useMemo(
    () => filterLanguagesByCountry(config.languages, selectedCountry?.code, config.countries),
    [config.countries, config.languages, selectedCountry?.code]
  );
  const suggestedTopics = useMemo(
    () => [...(config.starterTopics || []), ...(config.contextualTopics || [])],
    [config.contextualTopics, config.starterTopics]
  );
  const state: GenericWidgetRenderState = { isOpen, selectedCountry, selectedLanguage, consentAccepted, visitorId, sessionId };
  const localePayload = createLocalePayload({
    visitorId,
    sessionId,
    selectedCountry: selectedCountry?.code || "",
    selectedLanguage: selectedLanguage?.code || ""
  });

  const closeWidget = () => {
    setIsOpen(false);
    setMenuOpen(false);
    onClose?.();
  };

  const handleCountryChange = (countryCode: string) => {
    const nextCountry = config.countries.find((country) => country.code === countryCode);
    if (!nextCountry) return;
    const nextLanguage = ensureLanguageForCountry(config.languages, nextCountry.code, selectedLanguage?.code, config.countries);
    setSelectedCountry(nextCountry);
    setSelectedLanguage(nextLanguage);
    onCountryChange?.(
      createLocalePayload({ visitorId, sessionId, selectedCountry: nextCountry.code, selectedLanguage: nextLanguage?.code || "" })
    );
  };

  const handleLanguageChange = (languageCode: string) => {
    const nextLanguage = availableLanguages.find((language) => language.code === languageCode);
    if (!nextLanguage) return;
    setSelectedLanguage(nextLanguage);
    onLanguageChange?.(
      createLocalePayload({ visitorId, sessionId, selectedCountry: selectedCountry?.code || "", selectedLanguage: nextLanguage.code })
    );
  };

  const handleConsent = (actionType: "accepted" | "rejected") => {
    const payload = createConsentRecord({
      actionType,
      config,
      selectedCountry: selectedCountry?.code || "",
      selectedLanguage: selectedLanguage?.code || "",
      visitorId,
      sessionId
    });
    const accepted = actionType === "accepted";
    setConsentAccepted(accepted);
    setShowSuccess(accepted);
    if (config.persistConsent) writeConsentFlag(config.consent.storageKey, accepted);
    accepted ? onAcceptConsent?.(payload) : onRejectConsent?.(payload);
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = message.trim();
    if (!trimmed || (config.consent.requireConsentBeforeMessaging !== false && !consentAccepted)) return;
    const payload: MessageEventPayload = {
      visitorId,
      sessionId,
      message: trimmed,
      selectedCountry: selectedCountry?.code || "",
      selectedLanguage: selectedLanguage?.code || "",
      widgetProviderName: config.provider.name,
      widgetProviderType: config.provider.type
    };
    setMessage("");
    onSendMessage?.(payload);
  };

  return (
    <div className={`gw-root ${className}`} style={{ ...buildThemeVars(config.theme), ...style }}>
      {!isOpen ? (
        <FloatingLauncher
          config={config}
          onClick={() => {
            setIsOpen(true);
            onOpen?.();
          }}
        />
      ) : null}

      {isOpen ? (
        <section className={`gw-panel ${showSuccess ? "gw-panel-has-success" : ""} ${consentAccepted ? "gw-panel-consented" : "gw-panel-needs-consent"}`} aria-label={config.brandName}>
          <Header config={config} selectedCountry={selectedCountry} menuOpen={menuOpen} onToggleMenu={() => setMenuOpen((value) => !value)} onClose={closeWidget} />
          {menuOpen ? <Menu config={config} payload={localePayload} onEscalate={onEscalate} onNewChat={onNewChat} /> : null}
          {showSuccess ? (
            <div className="gw-success-banner" role="status">
              <span>{config.successText}</span>
              <button type="button" onClick={() => setShowSuccess(false)} aria-label={config.labels.successDismissLabel}>{"\u00d7"}</button>
            </div>
          ) : null}
          <div className="gw-content">
            {showLocaleSelector ? (
              <RegionSelector
                config={config}
                countries={config.countries}
                languages={availableLanguages}
                selectedCountryCode={selectedCountry?.code}
                selectedLanguageCode={selectedLanguage?.code}
                onCountryChange={handleCountryChange}
                onLanguageChange={handleLanguageChange}
              />
            ) : null}
            {config.consent.requireConsentBeforeMessaging !== false && !consentAccepted ? (
              <ConsentPanel config={config} onAccept={() => handleConsent("accepted")} onReject={() => handleConsent("rejected")} />
            ) : null}
            <MessageFeed config={config} messages={messages} state={state} renderMessages={renderMessages} />
            {suggestedTopics.length ? (
              <section className="gw-section">
                <div className="gw-section-title">{config.labels.suggestedTopicsLabel}</div>
                <div className="gw-topic-list">
                  {suggestedTopics.map((topic) => (
                    <button key={topic.id} type="button" className="gw-topic" onClick={() => setMessage(topic.prompt || topic.label)}>
                      {topic.label}
                    </button>
                  ))}
                </div>
              </section>
            ) : null}
            {loading ? <div className="gw-loading" role="status"><span className="gw-spinner" aria-hidden="true" /><span>{config.loadingText}</span></div> : null}
            {children ? <section className="gw-child-slot" aria-label={config.labels.childrenRegionLabel}>{typeof children === "function" ? children(state) : children}</section> : null}
          </div>
          <form className="gw-composer" onSubmit={handleSubmit}>
            <label className="gw-sr-only" htmlFor="gw-message-input">{config.labels.messageInputLabel}</label>
            <input
              id="gw-message-input"
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder={config.labels.messageInputPlaceholder}
              disabled={loading || (config.consent.requireConsentBeforeMessaging !== false && !consentAccepted)}
            />
            <button type="submit" className="gw-primary-button" disabled={!message.trim() || loading}>{config.labels.sendMessageLabel}</button>
          </form>
        </section>
      ) : null}
    </div>
  );
}
````

### `widget-wrapper\src\generic-widget\Header.tsx`

````tsx
import type { GenericWidgetConfig, WidgetCountryOption } from "./types";

export function Header({
  config,
  selectedCountry,
  menuOpen,
  onToggleMenu,
  onClose
}: {
  config: GenericWidgetConfig;
  selectedCountry?: WidgetCountryOption;
  menuOpen: boolean;
  onToggleMenu: () => void;
  onClose: () => void;
}) {
  return (
    <header className="gw-header">
      <div>
        <div className="gw-title">{config.brandName}</div>
        {selectedCountry ? <div className="gw-subtitle">{selectedCountry.label}</div> : null}
      </div>
      <div className="gw-header-actions">
        <button type="button" className="gw-icon-button" onClick={onToggleMenu} aria-label={config.labels.menuAriaLabel} aria-expanded={menuOpen}>
          <span aria-hidden="true">â‹®</span>
        </button>
        <button type="button" className="gw-icon-button" onClick={onClose} aria-label={config.labels.closeAriaLabel}>
          <span aria-hidden="true">Ã—</span>
        </button>
      </div>
    </header>
  );
}
````

### `widget-wrapper\src\generic-widget\index.ts`

````typescript
export { GenericWidgetWrapper } from "./GenericWidgetWrapper";
export { PlainStateGenericWidgetWrapper } from "./PlainStateGenericWidgetWrapper";
export { ChatwootWidgetAdapter } from "./integrations/ChatwootWidgetAdapter";
export { BackendChatDemo } from "./examples/BackendChatDemo";
export { LocalChatwootDemo } from "./examples/LocalChatwootDemo";
export { foreverDemoConfig } from "./examples/foreverDemoConfig";
export { exampleWidgetConfig } from "./config/exampleWidgetConfig";
export { defaultTheme } from "./config/defaultTheme";
export type { ChatwootWidgetAdapterProps } from "./integrations/ChatwootWidgetAdapter";
export type {
  ConsentEventPayload,
  GenericWidgetConfig,
  GenericWidgetRenderState,
  GenericWidgetWrapperProps,
  LocaleChangePayload,
  MessageEventPayload,
  WidgetCountryOption,
  WidgetLanguageOption,
  WidgetMessage,
  WidgetPolicyLink,
  WidgetProviderType,
  WidgetTheme,
  WidgetTopic
} from "./types";
````

### `widget-wrapper\src\generic-widget\integrations\ChatwootWidgetAdapter.tsx`

````tsx
import { useEffect, useMemo, useRef, useState } from "react";
import type { GenericWidgetRenderState } from "../types";

type ChatwootUser = {
  identifier: string;
  name?: string;
  email?: string;
  avatarUrl?: string;
  identifierHash?: string;
};

type ChatwootSettings = {
  position?: "left" | "right";
  type?: "standard" | "expanded_bubble";
  launcherTitle?: string;
  locale?: string;
  hideMessageBubble?: boolean;
  showPopoutButton?: boolean;
  [key: string]: unknown;
};

export type ChatwootWidgetAdapterProps = {
  baseUrl: string;
  websiteToken: string;
  state: GenericWidgetRenderState;
  settings?: ChatwootSettings;
  user?: ChatwootUser;
  customAttributes?: Record<string, unknown>;
  hideDefaultBubble?: boolean;
  openWhenWrapperOpens?: boolean;
  resetOnNewSession?: boolean;
  onReady?: () => void;
  onError?: (error: Error) => void;
};

type ChatwootSdk = {
  run: (options: { websiteToken: string; baseUrl: string }) => void;
};

type ChatwootApi = {
  toggle?: (state?: "open" | "close") => void;
  toggleBubbleVisibility?: (visibility: "show" | "hide") => void;
  setLocale?: (locale: string) => void;
  setUser?: (identifier: string, user: Record<string, unknown>) => void;
  setCustomAttributes?: (attributes: Record<string, unknown>) => void;
  reset?: () => void;
};

declare global {
  interface Window {
    chatwootSDK?: ChatwootSdk;
    chatwootSettings?: ChatwootSettings;
    $chatwoot?: ChatwootApi;
  }
}

const scriptId = "generic-widget-chatwoot-sdk";

const normalizeBaseUrl = (baseUrl: string) => baseUrl.replace(/\/$/, "");

const loadChatwootSdk = (baseUrl: string) =>
  new Promise<void>((resolve, reject) => {
    const normalizedBaseUrl = normalizeBaseUrl(baseUrl);
    const existingScript = document.getElementById(scriptId) as HTMLScriptElement | null;

    if (window.chatwootSDK) {
      resolve();
      return;
    }

    if (existingScript) {
      existingScript.addEventListener("load", () => resolve(), { once: true });
      existingScript.addEventListener("error", () => reject(new Error("Unable to load Chatwoot SDK.")), { once: true });
      return;
    }

    const script = document.createElement("script");
    script.id = scriptId;
    script.src = `${normalizedBaseUrl}/packs/js/sdk.js`;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Unable to load Chatwoot SDK."));
    document.head.appendChild(script);
  });

export function ChatwootWidgetAdapter({
  baseUrl,
  websiteToken,
  state,
  settings,
  user,
  customAttributes,
  hideDefaultBubble = true,
  openWhenWrapperOpens = true,
  resetOnNewSession = false,
  onReady,
  onError
}: ChatwootWidgetAdapterProps) {
  const [ready, setReady] = useState(false);
  const initializedRef = useRef(false);
  const normalizedBaseUrl = useMemo(() => normalizeBaseUrl(baseUrl), [baseUrl]);
  const locale = state.selectedLanguage?.code || settings?.locale;

  useEffect(() => {
    window.chatwootSettings = {
      ...(settings || {}),
      locale,
      hideMessageBubble: hideDefaultBubble
    };

    loadChatwootSdk(normalizedBaseUrl)
      .then(() => {
        if (!initializedRef.current) {
          window.chatwootSDK?.run({ websiteToken, baseUrl: normalizedBaseUrl });
          initializedRef.current = true;
        }
      })
      .catch((error: Error) => onError?.(error));
  }, [hideDefaultBubble, locale, normalizedBaseUrl, onError, settings, websiteToken]);

  useEffect(() => {
    const handleReady = () => {
      setReady(true);
      if (hideDefaultBubble) window.$chatwoot?.toggleBubbleVisibility?.("hide");
      onReady?.();
    };

    if (window.$chatwoot) handleReady();
    window.addEventListener("chatwoot:ready", handleReady);
    return () => window.removeEventListener("chatwoot:ready", handleReady);
  }, [hideDefaultBubble, onReady]);

  useEffect(() => {
    if (!ready || !locale) return;
    window.$chatwoot?.setLocale?.(locale);
  }, [locale, ready]);

  useEffect(() => {
    if (!ready || !user?.identifier) return;
    const { identifier, ...profile } = user;
    window.$chatwoot?.setUser?.(identifier, profile);
  }, [ready, user]);

  useEffect(() => {
    if (!ready) return;
    window.$chatwoot?.setCustomAttributes?.({
      ...(customAttributes || {}),
      wrapperVisitorId: state.visitorId,
      wrapperSessionId: state.sessionId,
      selectedCountry: state.selectedCountry?.code || "",
      selectedLanguage: state.selectedLanguage?.code || "",
      wrapperConsentAccepted: state.consentAccepted
    });
  }, [customAttributes, ready, state.consentAccepted, state.selectedCountry?.code, state.selectedLanguage?.code, state.sessionId, state.visitorId]);

  useEffect(() => {
    if (!ready || !openWhenWrapperOpens) return;
    window.$chatwoot?.toggle?.(state.isOpen ? "open" : "close");
  }, [openWhenWrapperOpens, ready, state.isOpen]);

  useEffect(() => {
    if (!ready || !resetOnNewSession) return;
    window.$chatwoot?.reset?.();
  }, [ready, resetOnNewSession, state.sessionId]);

  return null;
}
````

### `widget-wrapper\src\generic-widget\LegalLinks.tsx`

````tsx
import type { GenericWidgetConfig } from "./types";

export function LegalLinks({ config }: { config: GenericWidgetConfig }) {
  if (!config.policyLinks.length) return null;

  return (
    <nav className="gw-legal" aria-label={config.labels.legalLinksLabel}>
      {config.policyLinks.map((link) => (
        <a key={link.id} href={link.href} target={link.target || "_blank"} rel="noreferrer">
          {link.label}
        </a>
      ))}
    </nav>
  );
}
````

### `widget-wrapper\src\generic-widget\Menu.tsx`

````tsx
import type { GenericWidgetConfig, LocaleChangePayload } from "./types";

export function Menu({
  config,
  payload,
  onNewChat,
  onEscalate
}: {
  config: GenericWidgetConfig;
  payload: LocaleChangePayload;
  onNewChat?: (payload: LocaleChangePayload) => void;
  onEscalate?: (payload: LocaleChangePayload) => void;
}) {
  return (
    <div className="gw-menu" role="menu">
      <button type="button" className="gw-menu-item" role="menuitem">{config.menu.settings}</button>
      <button type="button" className="gw-menu-item" role="menuitem">{config.menu.history}</button>
      <button type="button" className="gw-menu-item" role="menuitem" onClick={() => onNewChat?.(payload)}>{config.menu.newChat}</button>
      <button type="button" className="gw-menu-item" role="menuitem" onClick={() => onEscalate?.(payload)}>{config.menu.escalate}</button>
    </div>
  );
}
````

### `widget-wrapper\src\generic-widget\MessageFeed.tsx`

````tsx
import type { ReactNode } from "react";
import type { GenericWidgetConfig, GenericWidgetRenderState, WidgetMessage } from "./types";

export function MessageFeed({
  config,
  messages,
  state,
  renderMessages
}: {
  config: GenericWidgetConfig;
  messages: WidgetMessage[];
  state: GenericWidgetRenderState;
  renderMessages?: (messages: WidgetMessage[], state: GenericWidgetRenderState) => ReactNode;
}) {
  if (renderMessages) return <div className="gw-message-feed">{renderMessages(messages, state)}</div>;

  return (
    <div className="gw-message-feed" role="log" aria-live="polite">
      {config.welcomeText ? <article className="gw-message gw-message-system"><div>{config.welcomeText}</div></article> : null}
      {messages.map((message) => (
        <article key={message.id} className={`gw-message gw-message-${message.role}`}>
          <div>{message.content}</div>
        </article>
      ))}
    </div>
  );
}
````

### `widget-wrapper\src\generic-widget\PlainStateGenericWidgetWrapper.tsx`

````tsx
import { GenericWidgetWrapper } from "./GenericWidgetWrapper";
import type { GenericWidgetWrapperProps } from "./types";

export function PlainStateGenericWidgetWrapper(props: GenericWidgetWrapperProps) {
  return <GenericWidgetWrapper {...props} />;
}
````

### `widget-wrapper\src\generic-widget\RegionSelector.tsx`

````tsx
import type { GenericWidgetConfig, WidgetCountryOption, WidgetLanguageOption } from "./types";

export function RegionSelector({
  config,
  countries,
  languages,
  selectedCountryCode,
  selectedLanguageCode,
  onCountryChange,
  onLanguageChange
}: {
  config: GenericWidgetConfig;
  countries: WidgetCountryOption[];
  languages: WidgetLanguageOption[];
  selectedCountryCode?: string;
  selectedLanguageCode?: string;
  onCountryChange: (countryCode: string) => void;
  onLanguageChange: (languageCode: string) => void;
}) {
  return (
    <section className="gw-section gw-region-selector">
      <label className="gw-field">
        <span>{config.labels.countryLabel}</span>
        <select value={selectedCountryCode || ""} onChange={(event) => onCountryChange(event.target.value)}>
          {config.labels.countryPlaceholder ? <option value="">{config.labels.countryPlaceholder}</option> : null}
          {countries.map((country) => <option key={country.code} value={country.code}>{country.label}</option>)}
        </select>
      </label>
      <label className="gw-field">
        <span>{config.labels.languageLabel}</span>
        <select value={selectedLanguageCode || ""} onChange={(event) => onLanguageChange(event.target.value)}>
          {config.labels.languagePlaceholder ? <option value="">{config.labels.languagePlaceholder}</option> : null}
          {languages.map((language) => <option key={language.code} value={language.code}>{language.label}</option>)}
        </select>
      </label>
    </section>
  );
}
````

### `widget-wrapper\src\generic-widget\types.ts`

````typescript
import type { CSSProperties, ReactNode } from "react";

export type WidgetProviderType = "custom-react" | "script" | "iframe" | "message-feed" | string;

export type WidgetCountryOption = {
  code: string;
  label: string;
  languageCodes?: string[];
  metadata?: Record<string, unknown>;
};

export type WidgetLanguageOption = {
  code: string;
  label: string;
  countryCodes?: string[];
  metadata?: Record<string, unknown>;
};

export type WidgetPolicyLink = {
  id: string;
  label: string;
  href: string;
  target?: "_blank" | "_self" | "_parent" | "_top";
};

export type WidgetTopic = {
  id: string;
  label: string;
  prompt?: string;
  metadata?: Record<string, unknown>;
};

export type WidgetMessage = {
  id: string;
  role: "assistant" | "user" | "system";
  content: ReactNode;
  timestamp?: string;
  metadata?: Record<string, unknown>;
};

export type WidgetTheme = {
  accentColor?: string;
  accentTextColor?: string;
  surfaceColor?: string;
  panelColor?: string;
  textColor?: string;
  mutedTextColor?: string;
  borderColor?: string;
  launcherColor?: string;
  launcherTextColor?: string;
  successColor?: string;
  dangerColor?: string;
  shadow?: string;
  radius?: string;
  fontFamily?: string;
  zIndex?: number;
};

export type WidgetLabels = {
  launcherAriaLabel: string;
  closeAriaLabel: string;
  menuAriaLabel: string;
  countryLabel: string;
  languageLabel: string;
  countryPlaceholder?: string;
  languagePlaceholder?: string;
  continueLabel: string;
  acceptConsentLabel: string;
  rejectConsentLabel: string;
  messageInputLabel: string;
  messageInputPlaceholder: string;
  sendMessageLabel: string;
  suggestedTopicsLabel: string;
  legalLinksLabel: string;
  childrenRegionLabel: string;
  successDismissLabel: string;
};

export type WidgetMenuLabels = {
  settings: string;
  history: string;
  newChat: string;
  escalate: string;
};

export type WidgetConsentConfig = {
  title: string;
  body: ReactNode;
  policyVersion: string;
  categories: string[];
  storageKey?: string;
  requireConsentBeforeMessaging?: boolean;
};

export type GenericWidgetConfig = {
  brandName: string;
  welcomeText?: ReactNode;
  loadingText: ReactNode;
  successText: ReactNode;
  labels: WidgetLabels;
  menu: WidgetMenuLabels;
  provider: { name: string; type: WidgetProviderType };
  consent: WidgetConsentConfig;
  policyLinks: WidgetPolicyLink[];
  countries: WidgetCountryOption[];
  languages: WidgetLanguageOption[];
  starterTopics?: WidgetTopic[];
  contextualTopics?: WidgetTopic[];
  theme?: WidgetTheme;
  defaultCountryCode?: string;
  defaultLanguageCode?: string;
  persistConsent?: boolean;
};

export type ConsentActionType = "accepted" | "rejected";

export type ConsentEventPayload = {
  visitorId: string;
  sessionId: string;
  timestamp: string;
  selectedCountry: string;
  selectedLanguage: string;
  policyVersion: string;
  acceptedCategories: string[];
  widgetProviderName: string;
  widgetProviderType: WidgetProviderType;
  actionType: ConsentActionType;
  metadata?: Record<string, unknown>;
};

export type MessageEventPayload = {
  visitorId: string;
  sessionId: string;
  message: string;
  selectedCountry: string;
  selectedLanguage: string;
  widgetProviderName: string;
  widgetProviderType: WidgetProviderType;
  metadata?: Record<string, unknown>;
};

export type LocaleChangePayload = {
  visitorId: string;
  sessionId: string;
  selectedCountry: string;
  selectedLanguage: string;
  metadata?: Record<string, unknown>;
};

export type GenericWidgetRenderState = {
  isOpen: boolean;
  selectedCountry: WidgetCountryOption | undefined;
  selectedLanguage: WidgetLanguageOption | undefined;
  consentAccepted: boolean;
  visitorId: string;
  sessionId: string;
};

export type GenericWidgetWrapperProps = {
  config: GenericWidgetConfig;
  children?: ReactNode | ((state: GenericWidgetRenderState) => ReactNode);
  messages?: WidgetMessage[];
  loading?: boolean;
  openByDefault?: boolean;
  initialConsentAccepted?: boolean;
  initialShowSuccess?: boolean;
  showLocaleSelector?: boolean;
  visitorId?: string;
  sessionId?: string;
  className?: string;
  style?: CSSProperties;
  renderMessages?: (messages: WidgetMessage[], state: GenericWidgetRenderState) => ReactNode;
  onOpen?: () => void;
  onClose?: () => void;
  onAcceptConsent?: (payload: ConsentEventPayload) => void;
  onRejectConsent?: (payload: ConsentEventPayload) => void;
  onCountryChange?: (payload: LocaleChangePayload) => void;
  onLanguageChange?: (payload: LocaleChangePayload) => void;
  onSendMessage?: (payload: MessageEventPayload) => void;
  onEscalate?: (payload: LocaleChangePayload) => void;
  onNewChat?: (payload: LocaleChangePayload) => void;
};
````

### `widget-wrapper\src\generic-widget\utils.ts`

````typescript
import type {
  ConsentActionType,
  GenericWidgetConfig,
  WidgetCountryOption,
  WidgetLanguageOption
} from "./types";

const createId = (prefix: string) =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? `${prefix}_${crypto.randomUUID()}`
    : `${prefix}_${Math.random().toString(36).slice(2)}_${Date.now().toString(36)}`;

export const createVisitorId = () => createId("visitor");

export const createSessionId = () => createId("session");

export const filterLanguagesByCountry = (
  languages: WidgetLanguageOption[],
  countryCode?: string,
  countries: WidgetCountryOption[] = []
) => {
  if (!countryCode) return languages;
  const country = countries.find((option) => option.code === countryCode);
  if (country?.languageCodes?.length) {
    return languages.filter((language) => country.languageCodes?.includes(language.code));
  }

  return languages.filter((language) => !language.countryCodes?.length || language.countryCodes.includes(countryCode));
};

export const ensureLanguageForCountry = (
  languages: WidgetLanguageOption[],
  countryCode: string,
  currentLanguageCode?: string,
  countries: WidgetCountryOption[] = []
) => {
  const available = filterLanguagesByCountry(languages, countryCode, countries);
  return available.find((language) => language.code === currentLanguageCode) || available[0] || languages[0];
};

export const detectInitialLocale = (
  countries: WidgetCountryOption[],
  languages: WidgetLanguageOption[],
  defaultCountryCode?: string,
  defaultLanguageCode?: string
) => {
  const browserLanguage = typeof navigator !== "undefined" ? navigator.language : "";
  const [browserLanguageCode, browserCountryCode] = browserLanguage.split("-");
  const countryCode = defaultCountryCode || browserCountryCode?.toUpperCase() || countries[0]?.code || "";
  const country = countries.find((option) => option.code === countryCode) || countries[0];
  const languageOptions = filterLanguagesByCountry(languages, country?.code, countries);
  const languageCode = defaultLanguageCode || browserLanguageCode || languageOptions[0]?.code || "";
  const language = languageOptions.find((option) => option.code === languageCode) || languageOptions[0] || languages[0];

  return { country, language };
};

export const readConsentFlag = (storageKey?: string) =>
  Boolean(storageKey && typeof localStorage !== "undefined" && localStorage.getItem(storageKey) === "true");

export const writeConsentFlag = (storageKey: string | undefined, accepted: boolean) => {
  if (!storageKey || typeof localStorage === "undefined") return;
  localStorage.setItem(storageKey, accepted ? "true" : "false");
};

export const createConsentRecord = ({
  actionType,
  config,
  selectedCountry,
  selectedLanguage,
  visitorId,
  sessionId,
  metadata
}: {
  actionType: ConsentActionType;
  config: GenericWidgetConfig;
  selectedCountry: string;
  selectedLanguage: string;
  visitorId: string;
  sessionId: string;
  metadata?: Record<string, unknown>;
}) => ({
  visitorId,
  sessionId,
  timestamp: new Date().toISOString(),
  selectedCountry,
  selectedLanguage,
  policyVersion: config.consent.policyVersion,
  acceptedCategories: actionType === "accepted" ? config.consent.categories : [],
  widgetProviderName: config.provider.name,
  widgetProviderType: config.provider.type,
  actionType,
  metadata
});

export const createLocalePayload = ({
  visitorId,
  sessionId,
  selectedCountry,
  selectedLanguage,
  metadata
}: {
  visitorId: string;
  sessionId: string;
  selectedCountry: string;
  selectedLanguage: string;
  metadata?: Record<string, unknown>;
}) => ({ visitorId, sessionId, selectedCountry, selectedLanguage, metadata });
````

### `widget-wrapper\tsconfig.json`

````json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["DOM", "DOM.Iterable", "ES2020"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx"
  },
  "include": ["src"]
}
````

### `widget-wrapper\vite.config.ts`

````typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    lib: {
      entry: "src/generic-widget/index.ts",
      formats: ["es"],
      fileName: "generic-widget-wrapper"
    },
    rollupOptions: {
      external: ["react", "react-dom", "react/jsx-runtime"]
    }
  }
});
````

