# ASK Vera Code Export

Generated: 2026-07-04 01:51:06 -04:00

This export contains the current project code and configuration files, excluding generated folders, caches, dependencies, build output, and previous export documents.

## File Index

- `.codex/hooks.json`
- `.github/workflows/deploy.yml`
- `.pre-commit-config.yaml`
- `api/__init__.py`
- `api/middleware.py`
- `api/routes.py`
- `app/audit/__init__.py`
- `app/audit/dispatcher.py`
- `app/audit/enums.py`
- `app/audit/lifecycle.py`
- `app/audit/models.py`
- `app/audit/publisher.py`
- `app/audit/queue.py`
- `app/audit/service.py`
- `app/audit/sinks/__init__.py`
- `app/audit/sinks/base.py`
- `app/audit/sinks/firehose.py`
- `app/audit/sinks/logger.py`
- `app/audit/sinks/metrics.py`
- `app/audit/worker.py`
- `app/middleware/__init__.py`
- `app/middleware/audit.py`
- `app/middleware/correlation.py`
- `app/utils/__init__.py`
- `app/utils/context.py`
- `app/utils/request_context.py`
- `config/__init__.py`
- `config/guardrail_topics.py`
- `config/markets.json`
- `config/settings.py`
- `config/vera_persona.py`
- `deployment/bootstrap.sh`
- `deployment/deploy.sh`
- `deployment/healthcheck.sh`
- `deployment/nginx/askvera.conf`
- `deployment/production.env.example`
- `deployment/rollback.sh`
- `deployment/ssl/certbot.sh`
- `deployment/systemd/askvera.service`
- `main.py`
- `Makefile`
- `pytest.ini`
- `requirements.txt`
- `scripts/cleanup_expired_sessions.py`
- `scripts/validate_config.py`
- `services/__init__.py`
- `services/audit.py`
- `services/aws_clients.py`
- `services/bedrock.py`
- `services/cache.py`
- `services/consent.py`
- `services/consent_service.py`
- `services/db.py`
- `services/feedback.py`
- `services/guardrails.py`
- `services/legal_service.py`
- `services/market_config.py`
- `services/pii.py`
- `services/session.py`
- `services/session_service.py`
- `tests/integration/test_chat_flow.py`
- `tests/unit/test_bedrock.py`
- `tests/unit/test_cache.py`
- `tests/unit/test_consent_service.py`
- `tests/unit/test_guardrails.py`
- `tests/unit/test_legal_service.py`
- `tests/unit/test_market_config.py`
- `tests/unit/test_pii.py`
- `tests/unit/test_privacy_route.py`
- `tests/unit/test_session_service.py`
- `utils/__init__.py`
- `utils/exceptions.py`
- `utils/logging.py`
- `utils/validators.py`
- `widget-wrapper/demo/src/App.tsx`
- `widget-wrapper/demo/src/main.tsx`
- `widget-wrapper/demo/src/styles.css`
- `widget-wrapper/package.json`
- `widget-wrapper/src/generic-widget/config/defaultTheme.ts`
- `widget-wrapper/src/generic-widget/config/exampleWidgetConfig.ts`
- `widget-wrapper/src/generic-widget/ConsentPanel.tsx`
- `widget-wrapper/src/generic-widget/examples/BackendChatDemo.tsx`
- `widget-wrapper/src/generic-widget/examples/ChatwootWidgetExample.tsx`
- `widget-wrapper/src/generic-widget/examples/foreverDemoConfig.tsx`
- `widget-wrapper/src/generic-widget/examples/LocalChatwootDemo.tsx`
- `widget-wrapper/src/generic-widget/examples/ThirdPartyWidgetExample.tsx`
- `widget-wrapper/src/generic-widget/FloatingLauncher.tsx`
- `widget-wrapper/src/generic-widget/generic-widget.css`
- `widget-wrapper/src/generic-widget/GenericWidgetWrapper.tsx`
- `widget-wrapper/src/generic-widget/Header.tsx`
- `widget-wrapper/src/generic-widget/index.ts`
- `widget-wrapper/src/generic-widget/integrations/ChatwootWidgetAdapter.tsx`
- `widget-wrapper/src/generic-widget/LegalLinks.tsx`
- `widget-wrapper/src/generic-widget/Menu.tsx`
- `widget-wrapper/src/generic-widget/MessageFeed.tsx`
- `widget-wrapper/src/generic-widget/PlainStateGenericWidgetWrapper.tsx`
- `widget-wrapper/src/generic-widget/RegionSelector.tsx`
- `widget-wrapper/src/generic-widget/types.ts`
- `widget-wrapper/src/generic-widget/utils.ts`
- `widget-wrapper/tsconfig.json`
- `widget-wrapper/vite.config.ts`

## Source Files

### `.codex/hooks.json`

````json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "graphify hook-check"
          }
        ]
      }
    ]
  }
}
````

### `.github/workflows/deploy.yml`

````yaml
name: ASK Vera CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v5

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install Python dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install -r requirements.txt

      - name: Compile Python source
        run: python -m compileall api config services utils scripts tests

      - name: Test
        run: python -m pytest tests/unit -q

      - name: Validate config defaults
        env:
          SSM_CONFIG_ENABLED: "false"
        run: python scripts/validate_config.py

      - name: Set up Node
        uses: actions/setup-node@v5
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: widget-wrapper/package-lock.json

      - name: Build widget demo
        working-directory: widget-wrapper
        run: |
          npm ci
          npm run typecheck
          npm run build:demo
````

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

### `api/__init__.py`

````python
"""API package for ASK Vera."""
````

### `api/middleware.py`

````python
"""API request middleware."""

from collections.abc import Awaitable, Callable
from collections import defaultdict, deque
from time import monotonic

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings
from utils.logging import get_logger

LOGGER = get_logger("api.middleware")


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

### `api/routes.py`

````python
"""FastAPI route definitions for ASK Vera."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from config.vera_persona import FALLBACK_RESPONSES
from services import cache as cache_service
from services.audit import write_audit_event
from services.bedrock import retrieve_and_generate
from services.cache import build_cache_key, get_cache_value, set_cache_value
from services.consent_service import has_valid_consent, record_consent
from services.db import get_engine
from services.feedback import enqueue_feedback
from services.guardrails import check_text
from services.legal_service import get_legal_documents
from services.market_config import get_countries, get_country_codes, get_language_codes_for_country
from services.pii import scrub_pii
from services.session import append_session_turn, get_session_history
from services.session_service import validate_and_touch_session
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


def consent_required_response(correlation_id: str) -> JSONResponse:
    """Return a business-rule error when chat is attempted before legal consent."""
    envelope = Envelope(
        success=False,
        error={
            "code": "CONSENT_REQUIRED",
            "message": "You must accept the legal documents before chatting.",
            "legalVersion": settings.LEGAL_VERSION,
        },
        correlationId=correlation_id,
    )
    return JSONResponse(status_code=403, content=envelope.model_dump())


def _valid_language_codes(country_code: str) -> set[str]:
    return get_language_codes_for_country(country_code)


@router.post("/api/chat", response_model=None)
def chat(body: ChatRequest, request: Request) -> Envelope | JSONResponse:
    """Answer a user message using RAG-only ASK Vera flow."""
    correlation_id = _correlation_id(request)
    try:
        validate_and_touch_session(body.sessionId, correlation_id)
        if not has_valid_consent(body.sessionId, correlation_id):
            return consent_required_response(correlation_id)
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
    return success({"countries": get_countries(), "privacyVersion": settings.PRIVACY_VERSION}, correlation_id)


@router.get("/api/privacy", response_model=None)
def privacy(request: Request, country: str | None = None, lang: str | None = None) -> Envelope | JSONResponse:
    """Return legal documents for a country and language."""
    correlation_id = _correlation_id(request)
    normalized_country = country.upper() if country else None
    normalized_lang = lang.lower() if lang else None
    if normalized_country and normalized_country not in get_country_codes():
        envelope = Envelope(success=False, error={"code": "UNSUPPORTED_COUNTRY", "message": "Unsupported country."}, correlationId=correlation_id)
        return JSONResponse(status_code=400, content=envelope.model_dump())
    if normalized_country and normalized_lang and normalized_lang not in _valid_language_codes(normalized_country):
        envelope = Envelope(success=False, error={"code": "UNSUPPORTED_LANGUAGE", "message": "Unsupported language."}, correlationId=correlation_id)
        return JSONResponse(status_code=400, content=envelope.model_dump())
    documents = get_legal_documents()
    LOGGER.info("privacy_returned", correlation_id=correlation_id, country=normalized_country, lang=normalized_lang)
    return success(documents, correlation_id)


@router.post("/api/consent", response_model=None)
def consent(body: ConsentRequest, request: Request) -> Envelope | JSONResponse:
    """Record user privacy consent."""
    correlation_id = _correlation_id(request)
    try:
        record_consent(body, correlation_id)
        return success({"recorded": True, "legalVersion": settings.LEGAL_VERSION}, correlation_id)
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
        "firehose": bool(settings.AUDIT_FIREHOSE_STREAM),
        "sqs": bool(settings.SQS_FEEDBACK_QUEUE_URL),
    }
    checks.update({name: "configured" if value else "missing_config" for name, value in configured.items()})
    return JSONResponse(
        status_code=status_code,
        content={"status": "healthy" if status_code == 200 else "unhealthy", "checks": checks, "timestamp": datetime.now(UTC).isoformat()},
    )
````

### `app/audit/__init__.py`

````python
"""Audit domain public exports."""

from .dispatcher import AuditDispatcher, audit_dispatcher
from .lifecycle import AuditLifecycle
from .publisher import AuditPublisher, audit_publisher
from .service import AuditService

audit_service = AuditService(audit_dispatcher)
audit_lifecycle = AuditLifecycle(audit_dispatcher)

__all__ = [
    "AuditDispatcher",
    "AuditLifecycle",
    "AuditPublisher",
    "AuditService",
    "audit_dispatcher",
    "audit_lifecycle",
    "audit_publisher",
    "audit_service",
]
````

### `app/audit/dispatcher.py`

````python
"""Dispatch audit events to registered sinks."""

from collections.abc import Sequence

from .models import AuditEvent
from .sinks.base import AuditSink
from .sinks.logger import LoggerAuditSink
from utils.logging import get_logger

LOGGER = get_logger("app.audit.dispatcher")


class AuditDispatcher:
    """Fan out audit events to all configured sinks."""

    def __init__(self, sinks: Sequence[AuditSink] | None = None) -> None:
        self._sinks = list(sinks or [LoggerAuditSink()])

    @property
    def sinks(self) -> tuple[AuditSink, ...]:
        """Return registered sinks."""
        return tuple(self._sinks)

    def add_sink(self, sink: AuditSink) -> None:
        """Register or replace a sink by name."""
        sink_name = getattr(sink, "name", sink.__class__.__name__)
        self._sinks = [existing for existing in self._sinks if getattr(existing, "name", existing.__class__.__name__) != sink_name]
        self._sinks.append(sink)

    async def start_sinks(self) -> None:
        """Start sinks that expose an async start hook."""
        for sink in self._sinks:
            start = getattr(sink, "start", None)
            if callable(start):
                await start()

    async def stop_sinks(self) -> None:
        """Stop sinks that expose an async stop hook."""
        for sink in reversed(self._sinks):
            stop = getattr(sink, "stop", None)
            if callable(stop):
                await stop()

    async def dispatch(self, event: AuditEvent) -> None:
        """Write one event to every sink without letting one sink stop others."""
        for sink in self._sinks:
            try:
                await sink.write(event)
            except Exception:
                LOGGER.exception(
                    "audit_sink_write_failed",
                    correlation_id=event.correlation_id,
                    sink=getattr(sink, "name", sink.__class__.__name__),
                    event_type=event.event_type.value,
                )


audit_dispatcher = AuditDispatcher()
````

### `app/audit/enums.py`

````python
"""Audit event type definitions."""

from enum import Enum


class AuditEventType(str, Enum):
    """Supported ASK Vera audit event types."""

    HTTP_REQUEST = "HTTP_REQUEST"

    CHAT_REQUEST = "CHAT_REQUEST"
    CHAT_RESPONSE = "CHAT_RESPONSE"

    CONSENT_ACCEPTED = "CONSENT_ACCEPTED"
    CONSENT_REJECTED = "CONSENT_REJECTED"

    SESSION_CREATED = "SESSION_CREATED"
    SESSION_EXPIRED = "SESSION_EXPIRED"

    CACHE_HIT = "CACHE_HIT"
    CACHE_MISS = "CACHE_MISS"

    ERROR = "ERROR"

    STARTUP = "STARTUP"
````

### `app/audit/lifecycle.py`

````python
"""Audit subsystem lifecycle management."""

import asyncio

from .dispatcher import AuditDispatcher
from .queue import audit_queue, queue_size
from .worker import audit_worker
from utils.logging import get_logger

LOGGER = get_logger("app.audit.lifecycle")


class AuditLifecycle:
    """Start and stop audit background workers."""

    def __init__(self, dispatcher: AuditDispatcher) -> None:
        self._dispatcher = dispatcher
        self._worker_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the audit worker if it is not already running."""
        if self._worker_task and not self._worker_task.done():
            return
        await self._dispatcher.start_sinks()
        self._worker_task = asyncio.create_task(audit_worker(self._dispatcher))
        LOGGER.info("audit_lifecycle_started")

    async def stop(self) -> None:
        """Drain queued events and stop the audit worker."""
        LOGGER.info("audit_lifecycle_draining", queue_size=queue_size())
        await audit_queue.join()
        await self._dispatcher.stop_sinks()
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                LOGGER.info("audit_worker_stopped")
        self._worker_task = None
````

### `app/audit/models.py`

````python
"""Pydantic models for audit events."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from .enums import AuditEventType


class AuditEvent(BaseModel):
    """Structured event payload for future audit publishing."""

    event_id: str
    correlation_id: str

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    event_type: AuditEventType

    session_id: str | None = None
    visitor_id: str | None = None

    country: str | None = None
    language: str | None = None

    ip_address: str | None = None
    user_agent: str | None = None

    status: str

    latency_ms: int | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)
````

### `app/audit/publisher.py`

````python
"""Non-blocking audit event publisher."""

import asyncio

from .models import AuditEvent
from .queue import audit_queue, queue_capacity, queue_size, queue_utilization
from utils.logging import get_logger

LOGGER = get_logger("app.audit.publisher")


class AuditPublisher:
    """Single entry point for putting audit events on the queue."""

    async def publish(self, event: AuditEvent) -> None:
        """Enqueue an audit event without blocking the request path."""
        try:
            audit_queue.put_nowait(event)
        except asyncio.QueueFull:
            LOGGER.warning(
                "audit_queue_full_dropped_event",
                correlation_id=event.correlation_id,
                event_type=event.event_type.value,
                queue_size=queue_size(),
                queue_capacity=queue_capacity(),
                queue_utilization=queue_utilization(),
            )


audit_publisher = AuditPublisher()
````

### `app/audit/queue.py`

````python
"""Bounded in-memory audit event queue."""

import asyncio

from .models import AuditEvent

AUDIT_QUEUE_MAX_SIZE = 10000

audit_queue: asyncio.Queue[AuditEvent] = asyncio.Queue(maxsize=AUDIT_QUEUE_MAX_SIZE)


def queue_size() -> int:
    """Return the current number of queued audit events."""
    return audit_queue.qsize()


def queue_capacity() -> int:
    """Return the configured maximum queue size."""
    return audit_queue.maxsize


def queue_utilization() -> float:
    """Return queue usage as a value between 0 and 1."""
    if audit_queue.maxsize <= 0:
        return 0.0
    return round(audit_queue.qsize() / audit_queue.maxsize, 4)
````

### `app/audit/service.py`

````python
"""Backward-compatible audit service wrapper."""

from .dispatcher import AuditDispatcher
from .models import AuditEvent


class AuditService:
    """Compatibility wrapper around the audit dispatcher."""

    def __init__(self, dispatcher: AuditDispatcher | None = None) -> None:
        self._dispatcher = dispatcher or AuditDispatcher()

    async def publish(self, event: AuditEvent) -> None:
        """Publish one audit event through configured sinks."""
        await self._dispatcher.dispatch(event)
````

### `app/audit/sinks/__init__.py`

````python
"""Audit sink implementations."""

from .base import AuditSink
from .logger import LoggerAuditSink

__all__ = ["AuditSink", "LoggerAuditSink"]
````

### `app/audit/sinks/base.py`

````python
"""Base audit sink interface."""

from typing import Protocol

from app.audit.models import AuditEvent


class AuditSink(Protocol):
    """Destination for audit events."""

    name: str

    async def write(self, event: AuditEvent) -> None:
        """Write one audit event to this sink."""
````

### `app/audit/sinks/firehose.py`

````python
"""Firehose audit sink configuration foundation."""

import asyncio
from time import monotonic
from typing import Any

from app.audit.models import AuditEvent
from config import settings
from utils.logging import get_logger

LOGGER = get_logger("app.audit.sinks.firehose")


class FirehoseAuditSink:
    """Send audit events to Amazon Kinesis Data Firehose when enabled."""

    name = "firehose"
    RETRYABLE_ERROR_CODES = {
        "ThrottlingException",
        "ProvisionedThroughputExceededException",
    }
    RETRYABLE_HTTP_STATUS = {500, 502, 503, 504}

    def __init__(self) -> None:
        self.enabled = bool(settings.AUDIT_FIREHOSE_ENABLED)
        self.stream_name = settings.AUDIT_FIREHOSE_STREAM
        self.client = None
        self._batch: list[dict[str, bytes]] = []
        self._batch_lock = asyncio.Lock()
        self._batch_size = settings.AUDIT_BATCH_SIZE
        self._batch_timeout = settings.AUDIT_BATCH_TIMEOUT_SECONDS
        self._retry_attempts = settings.AUDIT_RETRY_MAX_ATTEMPTS
        self._retry_base_delay = settings.AUDIT_RETRY_BASE_DELAY_SECONDS
        self._retry_max_delay = settings.AUDIT_RETRY_MAX_DELAY_SECONDS
        self._last_flush = monotonic()
        self._flush_task: asyncio.Task[None] | None = None
        self._flush_interval_seconds = 1.0

        if not self.enabled:
            LOGGER.info("firehose_audit_sink_disabled", stream=self.stream_name)
            return

        import boto3

        self.client = boto3.client("firehose", region_name=settings.AWS_REGION)
        LOGGER.info("firehose_audit_sink_initialized", stream=self.stream_name, region=settings.AWS_REGION)

    async def start(self) -> None:
        """Start the periodic partial-batch flush loop."""
        if not self.enabled or self.client is None:
            return
        if self._flush_task and not self._flush_task.done():
            return
        self._flush_task = asyncio.create_task(self._periodic_flush_loop())
        LOGGER.info("firehose_audit_flush_timer_started", stream=self.stream_name, timeout_seconds=self._batch_timeout)

    async def stop(self) -> None:
        """Stop the periodic flush loop and send any remaining records."""
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                LOGGER.info("firehose_audit_flush_timer_stopped", stream=self.stream_name)
        self._flush_task = None
        await self._flush()

    async def write(self, event: AuditEvent) -> None:
        """Buffer one audit event as a Firehose-ready record."""
        if not self.enabled or self.client is None:
            return None

        await self._add_to_batch(event)
        return None

    async def _add_to_batch(self, event: AuditEvent) -> None:
        """Serialize and append one event to the in-memory batch."""
        payload = event.model_dump_json() + "\n"
        record = {"Data": payload.encode("utf-8")}
        needs_flush = False
        async with self._batch_lock:
            self._batch.append(record)
            needs_flush = len(self._batch) >= self._batch_size

        if needs_flush:
            await self._flush()

    async def _periodic_flush_loop(self) -> None:
        """Flush partial batches when the configured timeout elapses."""
        while True:
            await asyncio.sleep(self._flush_interval_seconds)
            try:
                if await self._should_flush_for_timeout():
                    await self._flush()
            except Exception:
                LOGGER.exception("firehose_audit_flush_timer_failed", stream=self.stream_name)

    async def _should_flush_for_timeout(self) -> bool:
        """Return True when a partial batch has exceeded its timeout."""
        async with self._batch_lock:
            if not self._batch:
                return False
            return monotonic() - self._last_flush >= self._batch_timeout

    async def _flush(self) -> None:
        """Flush the current batch with one Firehose PutRecordBatch call."""
        if not self.enabled or self.client is None:
            return None

        async with self._batch_lock:
            if not self._batch:
                return None
            records = self._batch
            self._batch = []
            self._last_flush = monotonic()

        total_count = len(records)
        if await self._put_record_batch_with_retries(records):
            LOGGER.info("firehose_audit_batch_written", stream=self.stream_name, batch_size=total_count, failed_count=0)
        return None

    async def _put_record_batch_with_retries(self, records: list[dict[str, bytes]]) -> bool:
        """Send a batch to Firehose with deterministic exponential backoff."""
        records_to_send = records
        original_batch_size = len(records)
        max_attempts = max(1, self._retry_attempts)
        for attempt in range(max_attempts):
            batch_size = len(records_to_send)
            try:
                response = await self._send_batch(records_to_send)
            except Exception as exc:
                error_code, http_status = self._error_details(exc)
                if not self._should_retry(exc):
                    LOGGER.exception(
                        "firehose_non_retryable_error",
                        stream=self.stream_name,
                        batch_size=batch_size,
                        error_code=error_code,
                        http_status=http_status,
                    )
                    return False

                if attempt == max_attempts - 1:
                    LOGGER.exception(
                        "firehose_batch_failed_after_retries",
                        stream=self.stream_name,
                        batch_size=batch_size,
                        attempt=attempt + 1,
                        max_attempts=max_attempts,
                        error_code=error_code,
                        http_status=http_status,
                    )
                    return False

                delay = self._retry_delay(attempt)
                LOGGER.warning(
                    "firehose_retry_scheduled",
                    stream=self.stream_name,
                    batch_size=batch_size,
                    attempt=attempt + 1,
                    max_attempts=max_attempts,
                    delay_seconds=delay,
                    error_code=error_code,
                    http_status=http_status,
                )
                await asyncio.sleep(delay)
                continue

            failed_records = self._failed_records(records_to_send, response)
            failed_count = len(failed_records)
            if not failed_count:
                return True

            if attempt == max_attempts - 1:
                LOGGER.warning(
                    "firehose_partial_batch_failed",
                    stream=self.stream_name,
                    batch_size=batch_size,
                    original_batch_size=original_batch_size,
                    remaining_failed_records=failed_count,
                    attempt=attempt + 1,
                    max_attempts=max_attempts,
                )
                return False

            delay = self._retry_delay(attempt)
            LOGGER.warning(
                "firehose_partial_batch_retry",
                stream=self.stream_name,
                batch_size=batch_size,
                original_batch_size=original_batch_size,
                failed_count=failed_count,
                retry_batch_size=failed_count,
                attempt=attempt + 1,
                max_attempts=max_attempts,
                delay_seconds=delay,
            )
            records_to_send = failed_records
            await asyncio.sleep(delay)
        return False

    async def _send_batch(self, records: list[dict[str, bytes]]) -> dict[str, Any]:
        """Send one Firehose PutRecordBatch request."""
        return self.client.put_record_batch(
            DeliveryStreamName=self.stream_name,
            Records=records,
        )

    def _failed_records(self, records: list[dict[str, bytes]], response: dict[str, Any]) -> list[dict[str, bytes]]:
        """Return only the records Firehose reported as failed."""
        request_responses = response.get("RequestResponses", [])
        failed_records: list[dict[str, bytes]] = []
        for original_record, result in zip(records, request_responses):
            if isinstance(result, dict) and result.get("ErrorCode"):
                failed_records.append(original_record)
        return failed_records

    def _should_retry(self, exc: Exception) -> bool:
        """Return True when a Firehose failure is likely transient."""
        error_code, http_status = self._error_details(exc)
        if error_code in self.RETRYABLE_ERROR_CODES:
            return True
        if http_status in self.RETRYABLE_HTTP_STATUS:
            return True
        return False

    def _error_details(self, exc: Exception) -> tuple[str | None, int | None]:
        """Extract AWS-style error code and HTTP status from an exception."""
        response = getattr(exc, "response", None)
        if not isinstance(response, dict):
            return None, None

        error = response.get("Error", {})
        metadata = response.get("ResponseMetadata", {})
        error_code = error.get("Code") if isinstance(error, dict) else None
        http_status = metadata.get("HTTPStatusCode") if isinstance(metadata, dict) else None
        return error_code, http_status if isinstance(http_status, int) else None

    def _retry_delay(self, attempt: int) -> float:
        """Return deterministic exponential retry delay for one attempt."""
        delay = self._retry_base_delay * (2**attempt)
        return min(delay, self._retry_max_delay)

    def batch_size(self) -> int:
        """Return the current number of buffered records."""
        return len(self._batch)

    def batch_config(self) -> dict[str, Any]:
        """Return the active batch configuration."""
        return {
            "batch_size": self._batch_size,
            "batch_timeout_seconds": self._batch_timeout,
            "last_flush": self._last_flush,
        }


def initialize_firehose_sink() -> FirehoseAuditSink:
    """Initialise the Firehose sink configuration during startup."""
    return FirehoseAuditSink()
````

### `app/audit/sinks/logger.py`

````python
"""Structured logging audit sink."""

from app.audit.models import AuditEvent
from utils.logging import get_logger

LOGGER = get_logger("app.audit.sinks.logger")


class LoggerAuditSink:
    """Write audit events to structured JSON logs."""

    name = "logger"

    async def write(self, event: AuditEvent) -> None:
        """Publish one audit event to CloudWatch-friendly logs."""
        LOGGER.info(
            "audit_event",
            correlation_id=event.correlation_id,
            audit=event.model_dump(mode="json"),
        )
````

### `app/audit/sinks/metrics.py`

````python
"""In-memory audit metrics sink foundation."""

from collections import Counter

from app.audit.models import AuditEvent


class MetricsAuditSink:
    """Track event counts in memory for future CloudWatch metrics."""

    name = "metrics"

    def __init__(self) -> None:
        self._counts: Counter[str] = Counter()

    async def write(self, event: AuditEvent) -> None:
        """Increment the count for this audit event type."""
        self._counts[event.event_type.value] += 1

    def get_count(self, event_type: str) -> int:
        """Return the in-memory count for one event type."""
        return self._counts[event_type]
````

### `app/audit/worker.py`

````python
"""Background audit queue worker."""

from .dispatcher import AuditDispatcher
from .queue import audit_queue
from utils.logging import get_logger

LOGGER = get_logger("app.audit.worker")


async def audit_worker(dispatcher: AuditDispatcher) -> None:
    """Continuously publish queued audit events."""
    LOGGER.info("audit_worker_started")
    while True:
        event = await audit_queue.get()
        try:
            await dispatcher.dispatch(event)
        except Exception:
            LOGGER.exception(
                "audit_worker_dispatch_failed",
                correlation_id=event.correlation_id,
                event_type=event.event_type.value,
            )
        finally:
            audit_queue.task_done()
````

### `app/middleware/__init__.py`

````python
"""Application middleware package."""
````

### `app/middleware/audit.py`

````python
"""Audit middleware for request-complete events."""

from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.audit.enums import AuditEventType
from app.audit.models import AuditEvent
from app.audit.publisher import AuditPublisher, audit_publisher
from app.utils.request_context import get_correlation_id


class AuditMiddleware(BaseHTTPMiddleware):
    """Create lightweight audit events for completed HTTP requests."""

    def __init__(self, app: object, publisher: AuditPublisher | None = None) -> None:
        super().__init__(app)
        self._publisher = publisher or audit_publisher

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Enqueue a request-complete audit event without waiting for publishing."""
        started = perf_counter()
        response = await call_next(request)
        latency_ms = round((perf_counter() - started) * 1000)
        forwarded_for = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded_for.split(",", 1)[0].strip() if forwarded_for else None
        if not client_ip and request.client:
            client_ip = request.client.host

        event = AuditEvent(
            event_id=str(uuid4()),
            correlation_id=get_correlation_id(request),
            event_type=AuditEventType.HTTP_REQUEST,
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent"),
            status="success" if response.status_code < 400 else "error",
            latency_ms=latency_ms,
            metadata={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
            },
        )
        await self._publisher.publish(event)
        return response
````

### `app/middleware/correlation.py`

````python
"""Correlation ID middleware for request tracing."""

from collections.abc import Awaitable, Callable
from re import fullmatch
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.utils.context import correlation_id_ctx
from utils.logging import get_logger

LOGGER = get_logger("app.middleware.correlation")
CORRELATION_ID_HEADER = "X-Correlation-ID"
MAX_CORRELATION_ID_LENGTH = 128
CORRELATION_ID_PATTERN = r"[A-Za-z0-9._:\-]+"


def _is_valid_correlation_id(value: str | None) -> bool:
    """Return True when an incoming correlation ID is safe to reflect."""
    if not value:
        return False
    if len(value) > MAX_CORRELATION_ID_LENGTH:
        return False
    return fullmatch(CORRELATION_ID_PATTERN, value) is not None


def _resolve_correlation_id(request: Request) -> str:
    """Use a safe client-provided correlation ID or generate a new one."""
    incoming_id = request.headers.get(CORRELATION_ID_HEADER)
    if _is_valid_correlation_id(incoming_id):
        return incoming_id or ""
    return str(uuid4())


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach one correlation ID to every request and response."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Set request context, add response header, and log completion."""
        correlation_id = _resolve_correlation_id(request)
        request.state.correlation_id = correlation_id
        token = correlation_id_ctx.set(correlation_id)
        started = perf_counter()

        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = round((perf_counter() - started) * 1000, 2)
            correlation_id_ctx.reset(token)
            if "response" in locals():
                response.headers[CORRELATION_ID_HEADER] = correlation_id
                LOGGER.info(
                    "request_complete",
                    correlation_id=correlation_id,
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )
````

### `app/utils/__init__.py`

````python
"""Application utility package."""
````

### `app/utils/context.py`

````python
"""Async-safe application context values."""

from contextvars import ContextVar

correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")
````

### `app/utils/request_context.py`

````python
"""Helpers for reading request-scoped context."""

from fastapi import Request

from app.utils.context import correlation_id_ctx


def get_correlation_id(request: Request | None = None) -> str:
    """Return the correlation ID from async context or request state."""
    correlation_id = correlation_id_ctx.get()
    if correlation_id:
        return correlation_id
    if request is None:
        return ""
    return getattr(request.state, "correlation_id", "")
````

### `config/__init__.py`

````python
"""Configuration package for ASK Vera."""

from config.settings import get, load_ssm_config as load_config

__all__ = ["get", "load_config"]
````

### `config/guardrail_topics.py`

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

### `config/markets.json`

````json
{
  "version": 1,
  "lastUpdated": "2026-07-03",
  "defaultFeatures": {
    "feedback": true,
    "sources": true,
    "productCards": false
  },
  "markets": [
    {
      "code": "AR",
      "name": "Argentina",
      "enabled": true,
      "region": "Latin America",
      "displayOrder": 1,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "BO",
      "name": "Bolivia",
      "enabled": true,
      "region": "Latin America",
      "displayOrder": 2,
      "defaultLanguage": "es",
      "languages": [
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "BR",
      "name": "Brazil",
      "enabled": true,
      "region": "Latin America",
      "displayOrder": 3,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "pt",
          "name": "Portuguese",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "CL",
      "name": "Chile",
      "enabled": true,
      "region": "Latin America",
      "displayOrder": 4,
      "defaultLanguage": "es",
      "languages": [
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "CO",
      "name": "Colombia",
      "enabled": true,
      "region": "Latin America",
      "displayOrder": 5,
      "defaultLanguage": "es",
      "languages": [
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "EC",
      "name": "Ecuador",
      "enabled": true,
      "region": "Latin America",
      "displayOrder": 6,
      "defaultLanguage": "es",
      "languages": [
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "SV",
      "name": "El Salvador",
      "enabled": true,
      "region": "Latin America",
      "displayOrder": 7,
      "defaultLanguage": "es",
      "languages": [
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "GF",
      "name": "French Guiana",
      "enabled": true,
      "region": "Latin America",
      "displayOrder": 8,
      "defaultLanguage": "ar",
      "languages": [
        {
          "code": "ar",
          "name": "Arabic",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "GT",
      "name": "Guatemala",
      "enabled": true,
      "region": "Latin America",
      "displayOrder": 9,
      "defaultLanguage": "es",
      "languages": [
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "HN",
      "name": "Honduras",
      "enabled": true,
      "region": "Latin America",
      "displayOrder": 10,
      "defaultLanguage": "es",
      "languages": [
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "MX",
      "name": "Mexico",
      "enabled": true,
      "region": "Latin America",
      "displayOrder": 11,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "PA",
      "name": "Panama",
      "enabled": true,
      "region": "Latin America",
      "displayOrder": 12,
      "defaultLanguage": "es",
      "languages": [
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "PY",
      "name": "Paraguay",
      "enabled": true,
      "region": "Latin America",
      "displayOrder": 13,
      "defaultLanguage": "es",
      "languages": [
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "PE",
      "name": "Peru",
      "enabled": true,
      "region": "Latin America",
      "displayOrder": 14,
      "defaultLanguage": "es",
      "languages": [
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "UY",
      "name": "Uruguay",
      "enabled": true,
      "region": "Latin America",
      "displayOrder": 15,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "AL",
      "name": "Albania",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 101,
      "defaultLanguage": "sq",
      "languages": [
        {
          "code": "sq",
          "name": "Albanian",
          "enabled": true
        },
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "AD",
      "name": "Andorra",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 102,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "AT",
      "name": "Austria",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 103,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "de",
          "name": "German",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "AZ",
      "name": "Azerbaijan",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 104,
      "defaultLanguage": "az",
      "languages": [
        {
          "code": "az",
          "name": "Azerbaijani",
          "enabled": true
        },
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "ru",
          "name": "Russian",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "BALTICS",
      "name": "Baltics",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 105,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "et",
          "name": "Estonian",
          "enabled": true
        },
        {
          "code": "lv",
          "name": "Latvian",
          "enabled": true
        },
        {
          "code": "lt",
          "name": "Lithuanian",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "BE",
      "name": "Belgium",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 106,
      "defaultLanguage": "nl",
      "languages": [
        {
          "code": "nl",
          "name": "Dutch",
          "enabled": true
        },
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "BA",
      "name": "Bosnia and Herzegovina",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 107,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "sr",
          "name": "Serbian",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "BG",
      "name": "Bulgaria",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 108,
      "defaultLanguage": "bg",
      "languages": [
        {
          "code": "bg",
          "name": "Bulgarian",
          "enabled": true
        },
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "HR",
      "name": "Croatia",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 109,
      "defaultLanguage": "hr",
      "languages": [
        {
          "code": "hr",
          "name": "Croatian",
          "enabled": true
        },
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "CY",
      "name": "Cyprus",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 110,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "el",
          "name": "Greek",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "CZ",
      "name": "Czech Republic",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 111,
      "defaultLanguage": "cs",
      "languages": [
        {
          "code": "cs",
          "name": "Czech",
          "enabled": true
        },
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "DK",
      "name": "Denmark",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 112,
      "defaultLanguage": "da",
      "languages": [
        {
          "code": "da",
          "name": "Danish",
          "enabled": true
        },
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "FI",
      "name": "Finland",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 113,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "fi",
          "name": "Finnish",
          "enabled": true
        },
        {
          "code": "sv",
          "name": "Swedish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "FR",
      "name": "France",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 114,
      "defaultLanguage": "ar",
      "languages": [
        {
          "code": "ar",
          "name": "Arabic",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "GE",
      "name": "Georgia",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 115,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "ka",
          "name": "Georgian",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "DE",
      "name": "Germany",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 116,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "de",
          "name": "German",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "GI",
      "name": "Gibraltar",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 117,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "GR",
      "name": "Greece",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 118,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "el",
          "name": "Greek",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "HU",
      "name": "Hungary",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 119,
      "defaultLanguage": "sq",
      "languages": [
        {
          "code": "sq",
          "name": "Albanian",
          "enabled": true
        },
        {
          "code": "bs",
          "name": "Bosnian",
          "enabled": true
        },
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "hu",
          "name": "Hungarian",
          "enabled": true
        },
        {
          "code": "sr-ME",
          "name": "Montenegrin",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "IS",
      "name": "Iceland",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 120,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "IE",
      "name": "Ireland",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 121,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "IT",
      "name": "Italy",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 122,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "it",
          "name": "Italian",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "KZ",
      "name": "Kazakhstan",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 123,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "kk",
          "name": "Kazakh",
          "enabled": true
        },
        {
          "code": "ru",
          "name": "Russian",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "XK",
      "name": "Kosovo",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 124,
      "defaultLanguage": "sq",
      "languages": [
        {
          "code": "sq",
          "name": "Albanian",
          "enabled": true
        },
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "KG",
      "name": "Kyrgyzstan",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 125,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "ky",
          "name": "Kyrgyz",
          "enabled": true
        },
        {
          "code": "ru",
          "name": "Russian",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "LU",
      "name": "Luxembourg",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 126,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "MT",
      "name": "Malta",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 127,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "it",
          "name": "Italian",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "MD",
      "name": "Moldova",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 128,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "ro",
          "name": "Romanian",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "ME",
      "name": "Montenegro",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 129,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "sr",
          "name": "Serbian",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "NL",
      "name": "Netherlands",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 130,
      "defaultLanguage": "nl",
      "languages": [
        {
          "code": "nl",
          "name": "Dutch",
          "enabled": true
        },
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "MK",
      "name": "North Macedonia",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 131,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "mk",
          "name": "Macedonian",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "XI",
      "name": "Northern Ireland",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 132,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "NO",
      "name": "Norway",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 133,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "no",
          "name": "Norwegian",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "PL",
      "name": "Poland",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 134,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "pl",
          "name": "Polish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "PT",
      "name": "Portugal",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 135,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "pt",
          "name": "Portuguese",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "RO",
      "name": "Romania",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 136,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "ro",
          "name": "Romanian",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "RU",
      "name": "Russia",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 137,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "ru",
          "name": "Russian",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "RS",
      "name": "Serbia",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 138,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "sr",
          "name": "Serbian",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "SK",
      "name": "Slovak Republic",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 139,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "sk",
          "name": "Slovak",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "SI",
      "name": "Slovenia",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 140,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "hu",
          "name": "Hungarian",
          "enabled": true
        },
        {
          "code": "sl",
          "name": "Slovenian",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "ES",
      "name": "Spain",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 141,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "SE",
      "name": "Sweden",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 142,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "sv",
          "name": "Swedish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "CH",
      "name": "Switzerland",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 143,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        },
        {
          "code": "de",
          "name": "German",
          "enabled": true
        },
        {
          "code": "it",
          "name": "Italian",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "TR",
      "name": "Turkey",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 144,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "tr",
          "name": "Turkish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "UA",
      "name": "Ukraine",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 145,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "uk",
          "name": "Ukrainian",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "GB",
      "name": "United Kingdom",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 146,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "UZ",
      "name": "Uzbekistan",
      "enabled": true,
      "region": "Europe",
      "displayOrder": 147,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "ru",
          "name": "Russian",
          "enabled": true
        },
        {
          "code": "uz",
          "name": "Uzbek",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "AO",
      "name": "Angola",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 201,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "pt",
          "name": "Portuguese",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "BJ",
      "name": "Benin",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 202,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "BW",
      "name": "Botswana",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 203,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "BF",
      "name": "Burkina Faso",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 204,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "BI",
      "name": "Burundi",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 205,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "CM",
      "name": "Cameroon",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 206,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "CV",
      "name": "Cape Verde",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 207,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "CF",
      "name": "Central African Republic",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 208,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "TD",
      "name": "Chad",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 209,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "CI",
      "name": "Cote d'Ivoire (Ivory Coast)",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 210,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "CD",
      "name": "Democratic Republic of Congo",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 211,
      "defaultLanguage": "fr",
      "languages": [
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "GQ",
      "name": "Equatorial Guinea",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 212,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "ER",
      "name": "Eritrea",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 213,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "GA",
      "name": "Gabon",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 214,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "GM",
      "name": "Gambia",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 215,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "GH",
      "name": "Ghana",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 216,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "GN",
      "name": "Guinea",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 217,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "GW",
      "name": "Guinea-Bissau",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 218,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "KE",
      "name": "Kenya",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 219,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "LS",
      "name": "Lesotho",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 220,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "MG",
      "name": "Madagascar",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 221,
      "defaultLanguage": "fr",
      "languages": [
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "MW",
      "name": "Malawi",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 222,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "ML",
      "name": "Mali",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 223,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "MR",
      "name": "Mauritania",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 224,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "MU",
      "name": "Mauritius",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 225,
      "defaultLanguage": "ar",
      "languages": [
        {
          "code": "ar",
          "name": "Arabic",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "MA",
      "name": "Morocco",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 226,
      "defaultLanguage": "fr",
      "languages": [
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "MZ",
      "name": "Mozambique",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 227,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "NA",
      "name": "Namibia",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 228,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "NE",
      "name": "Niger",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 229,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "NG",
      "name": "Nigeria",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 230,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "CG",
      "name": "Republic of Congo",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 231,
      "defaultLanguage": "fr",
      "languages": [
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "RE",
      "name": "Reunion Islands",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 232,
      "defaultLanguage": "ar",
      "languages": [
        {
          "code": "ar",
          "name": "Arabic",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "RW",
      "name": "Rwanda",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 233,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "SN",
      "name": "Senegal",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 234,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "SL",
      "name": "Sierra Leone",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 235,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "ZA",
      "name": "South Africa",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 236,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "SZ",
      "name": "Swaziland",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 237,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "TZ",
      "name": "Tanzania, United Republic of",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 238,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "TG",
      "name": "Togo",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 239,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "TN",
      "name": "Tunisia",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 240,
      "defaultLanguage": "fr",
      "languages": [
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "UG",
      "name": "Uganda",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 241,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "ZM",
      "name": "Zambia",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 242,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "ZW",
      "name": "Zimbabwe",
      "enabled": true,
      "region": "Africa",
      "displayOrder": 243,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "AI",
      "name": "Anguilla",
      "enabled": true,
      "region": "Caribbean",
      "displayOrder": 301,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "AW",
      "name": "Aruba",
      "enabled": true,
      "region": "Caribbean",
      "displayOrder": 302,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "BQ-BO",
      "name": "BONAIRE",
      "enabled": true,
      "region": "Caribbean",
      "displayOrder": 303,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "BS",
      "name": "Bahamas",
      "enabled": true,
      "region": "Caribbean",
      "displayOrder": 304,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "CW",
      "name": "Curacao",
      "enabled": true,
      "region": "Caribbean",
      "displayOrder": 305,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "DO",
      "name": "Dominican Republic",
      "enabled": true,
      "region": "Caribbean",
      "displayOrder": 306,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "GP",
      "name": "Guadeloupe",
      "enabled": true,
      "region": "Caribbean",
      "displayOrder": 307,
      "defaultLanguage": "ar",
      "languages": [
        {
          "code": "ar",
          "name": "Arabic",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "GY",
      "name": "Guyana",
      "enabled": true,
      "region": "Caribbean",
      "displayOrder": 308,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "MQ",
      "name": "Martinique",
      "enabled": true,
      "region": "Caribbean",
      "displayOrder": 309,
      "defaultLanguage": "ar",
      "languages": [
        {
          "code": "ar",
          "name": "Arabic",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "AN",
      "name": "Netherlands Antilles",
      "enabled": true,
      "region": "Caribbean",
      "displayOrder": 310,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "PR",
      "name": "Puerto Rico",
      "enabled": true,
      "region": "Caribbean",
      "displayOrder": 311,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "BQ-SA",
      "name": "Saba",
      "enabled": true,
      "region": "Caribbean",
      "displayOrder": 312,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "BQ-SE",
      "name": "Saint Eustastius",
      "enabled": true,
      "region": "Caribbean",
      "displayOrder": 313,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "LC",
      "name": "Saint Lucia",
      "enabled": true,
      "region": "Caribbean",
      "displayOrder": 314,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "BL",
      "name": "Saint-BarthÃ©lemy",
      "enabled": true,
      "region": "Caribbean",
      "displayOrder": 315,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "SX",
      "name": "St. Maarten",
      "enabled": true,
      "region": "Caribbean",
      "displayOrder": 316,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "SR",
      "name": "Suriname",
      "enabled": true,
      "region": "Caribbean",
      "displayOrder": 317,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "AS",
      "name": "American Samoa",
      "enabled": true,
      "region": "Oceania",
      "displayOrder": 401,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "AU",
      "name": "Australia",
      "enabled": true,
      "region": "Oceania",
      "displayOrder": 402,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "FM",
      "name": "Federated States of Micronesia",
      "enabled": true,
      "region": "Oceania",
      "displayOrder": 403,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "FJ",
      "name": "Fiji",
      "enabled": true,
      "region": "Oceania",
      "displayOrder": 404,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "GU",
      "name": "Guam",
      "enabled": true,
      "region": "Oceania",
      "displayOrder": 405,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "NC",
      "name": "New Caledonia",
      "enabled": true,
      "region": "Oceania",
      "displayOrder": 406,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "NZ",
      "name": "New Zealand",
      "enabled": true,
      "region": "Oceania",
      "displayOrder": 407,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "PG",
      "name": "Papua New Guinea",
      "enabled": true,
      "region": "Oceania",
      "displayOrder": 408,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "WS",
      "name": "Samoa",
      "enabled": true,
      "region": "Oceania",
      "displayOrder": 409,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "VU",
      "name": "Vanuatu",
      "enabled": true,
      "region": "Oceania",
      "displayOrder": 410,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "CA",
      "name": "Canada",
      "enabled": true,
      "region": "North America",
      "displayOrder": 501,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "fr",
          "name": "French",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "US",
      "name": "United States",
      "enabled": true,
      "region": "North America",
      "displayOrder": 502,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "es",
          "name": "Spanish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "IQ",
      "name": "Iraq",
      "enabled": true,
      "region": "Middle East",
      "displayOrder": 601,
      "defaultLanguage": "ar",
      "languages": [
        {
          "code": "ar",
          "name": "Arabic",
          "enabled": true
        },
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "ku",
          "name": "Kurdish",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "IL",
      "name": "Israel",
      "enabled": true,
      "region": "Middle East",
      "displayOrder": 602,
      "defaultLanguage": "en",
      "languages": [
        {
          "code": "en",
          "name": "English",
          "enabled": true
        },
        {
          "code": "he",
          "name": "Hebrew",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "QA",
      "name": "Qatar",
      "enabled": true,
      "region": "Middle East",
      "displayOrder": 603,
      "defaultLanguage": "ar",
      "languages": [
        {
          "code": "ar",
          "name": "Arabic",
          "enabled": true
        },
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "SA",
      "name": "Saudi Arabia",
      "enabled": true,
      "region": "Middle East",
      "displayOrder": 604,
      "defaultLanguage": "ar",
      "languages": [
        {
          "code": "ar",
          "name": "Arabic",
          "enabled": true
        },
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    },
    {
      "code": "AE",
      "name": "United Arab Emirates",
      "enabled": true,
      "region": "Middle East",
      "displayOrder": 605,
      "defaultLanguage": "ar",
      "languages": [
        {
          "code": "ar",
          "name": "Arabic",
          "enabled": true
        },
        {
          "code": "en",
          "name": "English",
          "enabled": true
        }
      ],
      "privacyVersion": "2026.1"
    }
  ]
}
````

### `config/settings.py`

````python
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
# S3 location for legal HTML documents returned by /api/privacy.
LEGAL_BUCKET = "askverachat-prod-content"
LEGAL_PREFIX = "legal"
LEGAL_VERSION = "2026.1"
# Session TTL in seconds. Used by PostgreSQL chat_sessions.expires_at.
SESSION_TIMEOUT_HOURS = 2
MAX_SESSION_DAYS = 7
SESSION_TTL_SECONDS = SESSION_TIMEOUT_HOURS * 60 * 60
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
````

### `config/vera_persona.py`

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
    "low_confidence": "I could not find sufficient approved information for this question. Please contact your upline or Forever Living support if you require an official interpretation.",
    "income_claim": "I cannot provide income projections or guarantees. Please refer to the official Income Disclosure Statement for approved information.",
    "medical_claim": "I cannot provide medical advice or make medical claims. Please speak with a qualified healthcare professional.",
    "bedrock_error": "I am having a brief technical issue reaching the knowledge base. Please try again in a moment.",
    "off_topic": "I can help with Forever Living products, policies, ordering, business support, and approved company information.",
}


def role_scope_for(role: str) -> str:
    """Return the allowed content scope for a user role."""
    return ROLE_CONTENT_SCOPES.get(role, ROLE_CONTENT_SCOPES["new_prospect"])
````

### `deployment/bootstrap.sh`

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

### `deployment/deploy.sh`

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

### `deployment/healthcheck.sh`

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

### `deployment/nginx/askvera.conf`

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

### `deployment/production.env.example`

````dotenv
APP_ENV=production
SSM_CONFIG_ENABLED=true
SSM_PARAMETER_PATH=/askverachat/prod/
HOST=127.0.0.1
PORT=8000
LOG_LEVEL=INFO
PYTHONUNBUFFERED=1

##########################################
# Audit Firehose
##########################################
AUDIT_FIREHOSE_ENABLED=true
AUDIT_FIREHOSE_STREAM=askvera-audit
AUDIT_BATCH_SIZE=100
AUDIT_BATCH_TIMEOUT_SECONDS=2

##########################################
# Audit Firehose Retry
##########################################
AUDIT_RETRY_MAX_ATTEMPTS=4
AUDIT_RETRY_BASE_DELAY_SECONDS=1
AUDIT_RETRY_MAX_DELAY_SECONDS=8
````

### `deployment/rollback.sh`

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

### `deployment/ssl/certbot.sh`

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

### `deployment/systemd/askvera.service`

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

from api.middleware import RateLimitMiddleware
from api.routes import router
from app.audit import audit_dispatcher, audit_lifecycle
from app.audit.sinks.firehose import initialize_firehose_sink
from app.middleware.audit import AuditMiddleware
from app.middleware.correlation import CorrelationIdMiddleware
from config import settings
from scripts.validate_config import validate
from services.aws_clients import init_aws_clients
from services.cache import close_cache, init_cache
from services.db import close_db, init_db
from services.legal_service import load_legal_documents
from services.market_config import load_market_config
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
    market_config = load_market_config()
    LOGGER.info("market_config_loaded", market_count=len(market_config["markets"]))
    signal.signal(signal.SIGTERM, _handle_sigterm)
    init_aws_clients()
    legal_documents = load_legal_documents()
    LOGGER.info("legal_documents_ready", document_count=len(legal_documents["documents"]))
    init_db()
    _init_optional_cache()
    audit_dispatcher.add_sink(initialize_firehose_sink())
    await audit_lifecycle.start()
    LOGGER.info("startup_complete")
    yield
    await audit_lifecycle.stop()
    close_cache()
    close_db()
    LOGGER.info("shutdown_complete")


app = FastAPI(title="ASK Vera", version=settings.APP_VERSION, lifespan=lifespan)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.add_middleware(AuditMiddleware)
app.add_middleware(CorrelationIdMiddleware)
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

### `pytest.ini`

````ini
[pytest]
testpaths = tests/unit
python_files = test_*.py
addopts = -q
````

### `requirements.txt`

````text
fastapi==0.115.6
uvicorn[standard]==0.34.0
boto3==1.35.90
botocore==1.35.90
redis==5.2.1
psycopg[binary]==3.2.3
sqlalchemy==2.0.36
pydantic==2.10.4
pytest==8.3.4
pytest-cov==6.0.0
moto==5.0.24
black==24.10.0
flake8==7.1.1
detect-secrets==1.5.0
reportlab==4.2.5
pypdf==5.1.0
````

### `scripts/cleanup_expired_sessions.py`

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

### `scripts/validate_config.py`

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

### `services/__init__.py`

````python
"""Service package for AWS integrations."""
````

### `services/audit.py`

````python
"""Compatibility wrapper for publishing business audit events."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.audit.enums import AuditEventType
from app.audit.models import AuditEvent
from app.audit.publisher import audit_publisher
from utils.logging import get_logger

LOGGER = get_logger("services.audit")


def _event_type(raw_type: str | None) -> AuditEventType:
    """Map legacy audit type values to the new audit event enum."""
    if raw_type == "chat":
        return AuditEventType.CHAT_RESPONSE
    return AuditEventType.ERROR


async def publish_audit_event(event: dict[str, Any], correlation_id: str) -> None:
    """Publish one business audit event through the async audit pipeline."""
    audit_event = AuditEvent(
        event_id=str(uuid4()),
        correlation_id=correlation_id,
        timestamp=datetime.now(UTC),
        event_type=_event_type(event.get("type")),
        country=event.get("country"),
        language=event.get("language"),
        status="success",
        metadata={key: value for key, value in event.items() if key not in {"country", "language"}},
    )
    await audit_publisher.publish(audit_event)


def write_audit_event(event: dict[str, Any], correlation_id: str) -> None:
    """Queue one audit event without calling Firehose directly.

    This synchronous wrapper preserves existing route call sites while keeping
    one canonical audit delivery path: publisher -> queue -> worker -> sinks.
    """
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(publish_audit_event(event, correlation_id))
        return

    loop.create_task(publish_audit_event(event, correlation_id))
    LOGGER.info("audit_event_queued", correlation_id=correlation_id, event_type=event.get("type", "unknown"))
````

### `services/aws_clients.py`

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
        self.s3 = boto3.client("s3", region_name=settings.AWS_REGION, config=client_config)
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

### `services/bedrock.py`

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


def _score_summary(sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarise source scores for retrieval quality logging."""
    scores: list[float] = []
    for source in sources:
        if source.get("score") is None:
            continue
        try:
            scores.append(float(source["score"]))
        except (TypeError, ValueError):
            continue
    return {
        "top_score": round(max(scores), 3) if scores else None,
        "average_score": round(sum(scores) / len(scores), 3) if scores else None,
        "source_count": len(sources),
    }


def _source_log_summary(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return compact source details that are useful in production logs."""
    return [
        {
            "title": source.get("title", ""),
            "page": source.get("page", ""),
            "score": source.get("score"),
            "country": source.get("country", ""),
            "language": source.get("language", ""),
        }
        for source in sources[: settings.BEDROCK_RETRIEVAL_RESULT_COUNT]
    ]


def _retrieve_sources(message: str, country: str, language: str, correlation_id: str) -> list[dict[str, Any]]:
    """Call the standalone Retrieve API to get reliable scores/sources.

    retrieve_and_generate's citations field has been observed to return a
    placeholder entry with empty retrievedReferences even when generation
    succeeds with a real, correctly cited answer.
    """
    try:
        response = get_aws_clients().bedrock_agent_runtime.retrieve(
            knowledgeBaseId=settings.BEDROCK_KB_ID,
            retrievalQuery={"text": message},
            retrievalConfiguration={
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
        )
    except (BotoCoreError, ClientError):
        LOGGER.exception("bedrock_retrieve_fallback_failed", correlation_id=correlation_id)
        return []

    sources: list[dict[str, Any]] = []
    for result in response.get("retrievalResults", []):
        location = result.get("location", {})
        uri = location.get("s3Location", {}).get("uri", "")
        metadata = result.get("metadata", {}) or {}
        if uri:
            sources.append(
                {
                    "title": _metadata_value(metadata, "title", "document_title") or uri.rsplit("/", 1)[-1],
                    "uri": uri,
                    "excerpt": result.get("content", {}).get("text", "")[:240],
                    "page": _metadata_value(metadata, "page", "page_number", "x-amz-bedrock-kb-document-page-number"),
                    "documentVersion": _metadata_value(metadata, "document_version", "version", "policy_version"),
                    "country": _metadata_value(metadata, "country_code", "countrycode", "country"),
                    "language": _metadata_value(metadata, "language", "lang"),
                    "score": result.get("score"),
                }
            )
    LOGGER.info(
        "bedrock_retrieve_sources",
        correlation_id=correlation_id,
        country=country,
        language=language,
        **_score_summary(sources),
        sources=_source_log_summary(sources),
    )
    return sources


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
    if not sources:
        LOGGER.warning("bedrock_citations_empty_fallback", correlation_id=correlation_id)
        sources = _retrieve_sources(message, country, language, correlation_id)
    confidence = _confidence_from_sources(sources)
    score_summary = _score_summary(sources)
    if not sources:
        LOGGER.warning(
            "bedrock_no_sources",
            correlation_id=correlation_id,
            country=country,
            language=language,
            confidence=confidence,
        )
        raise LowConfidenceError(FALLBACK_RESPONSES["low_confidence"])
    if confidence < settings.BEDROCK_MIN_CONFIDENCE:
        LOGGER.warning(
            "bedrock_low_confidence_with_sources",
            correlation_id=correlation_id,
            country=country,
            language=language,
            confidence=confidence,
            **score_summary,
            sources=_source_log_summary(sources),
        )
    LOGGER.info(
        "bedrock_success",
        correlation_id=correlation_id,
        country=country,
        language=language,
        confidence=confidence,
        **score_summary,
        sources=_source_log_summary(sources),
    )
    return {"response": answer, "sources": sources, "confidence": confidence}
````

### `services/cache.py`

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

### `services/consent.py`

````python
"""Backward-compatible exports for consent service functions."""

from services.consent_service import has_valid_consent, record_consent

__all__ = ["has_valid_consent", "record_consent"]
````

### `services/consent_service.py`

````python
"""Consent recording and session-level validation."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from services.db import get_engine
from utils.exceptions import AwsServiceError
from utils.logging import get_logger
from utils.validators import ConsentRequest

LOGGER = get_logger("services.consent_service")


def record_consent(consent: ConsentRequest, correlation_id: str) -> None:
    """Write consent metadata and mark the session as consented for the current legal version."""
    accepted_at = consent.timestamp or datetime.now(UTC).isoformat()
    expires_at = datetime.now(UTC) + timedelta(hours=settings.SESSION_TIMEOUT_HOURS)
    try:
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO consent_log (session_id, country, lang, accepted_at, version, accepted, correlation_id)
                    VALUES (:session_id, :country, :lang, :accepted_at, :version, true, :correlation_id)
                    """
                ),
                {
                    "session_id": consent.sessionId,
                    "country": consent.country,
                    "lang": consent.lang,
                    "accepted_at": accepted_at,
                    "version": settings.LEGAL_VERSION,
                    "correlation_id": correlation_id,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO chat_sessions (
                        session_id,
                        messages,
                        created_at,
                        last_activity_at,
                        expires_at,
                        updated_at,
                        consent_accepted,
                        consent_legal_version,
                        consent_accepted_at
                    )
                    VALUES (
                        :session_id,
                        '[]'::jsonb,
                        now(),
                        now(),
                        :expires_at,
                        now(),
                        true,
                        :version,
                        :accepted_at
                    )
                    ON CONFLICT (session_id)
                    DO UPDATE SET
                        consent_accepted = true,
                        consent_legal_version = EXCLUDED.consent_legal_version,
                        consent_accepted_at = EXCLUDED.consent_accepted_at,
                        last_activity_at = now(),
                        expires_at = GREATEST(chat_sessions.expires_at, EXCLUDED.expires_at),
                        updated_at = now()
                    """
                ),
                {
                    "session_id": consent.sessionId,
                    "expires_at": expires_at,
                    "version": settings.LEGAL_VERSION,
                    "accepted_at": accepted_at,
                },
            )
    except SQLAlchemyError as exc:
        LOGGER.exception("consent_write_failed", correlation_id=correlation_id)
        raise AwsServiceError("Consent logging failed.") from exc

    LOGGER.info(
        "consent_accepted",
        correlation_id=correlation_id,
        session_id=consent.sessionId,
        country=consent.country,
        language=consent.lang,
        version=settings.LEGAL_VERSION,
    )


def has_valid_consent(session_id: str, correlation_id: str = "system") -> bool:
    """Return true when the session accepted the current legal version."""
    try:
        with get_engine().begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT consent_accepted, consent_legal_version, expires_at
                    FROM chat_sessions
                    WHERE session_id = :session_id
                      AND expires_at > now()
                    """
                ),
                {"session_id": session_id},
            ).mappings().first()
    except SQLAlchemyError as exc:
        LOGGER.exception("consent_read_failed", correlation_id=correlation_id)
        raise AwsServiceError("Consent validation failed.") from exc

    is_valid = bool(row and row["consent_accepted"] is True and row["consent_legal_version"] == settings.LEGAL_VERSION)
    if not is_valid:
        LOGGER.warning(
            "consent_missing",
            correlation_id=correlation_id,
            session_id=session_id,
            expected_version=settings.LEGAL_VERSION,
        )
    return is_valid
````

### `services/db.py`

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
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        expires_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        consent_accepted BOOLEAN NOT NULL DEFAULT false,
                        consent_legal_version TEXT,
                        consent_accepted_at TIMESTAMPTZ
                    )
                    """
                )
            )
            connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()"))
            connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now()"))
            connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS consent_accepted BOOLEAN NOT NULL DEFAULT false"))
            connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS consent_legal_version TEXT"))
            connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS consent_accepted_at TIMESTAMPTZ"))
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
                        accepted BOOLEAN NOT NULL DEFAULT true,
                        correlation_id TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            connection.execute(text("ALTER TABLE consent_log ADD COLUMN IF NOT EXISTS accepted BOOLEAN NOT NULL DEFAULT true"))
            connection.execute(text("ALTER TABLE consent_log ADD COLUMN IF NOT EXISTS correlation_id TEXT"))
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

### `services/feedback.py`

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

### `services/guardrails.py`

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

### `services/legal_service.py`

````python
"""Legal document loading from S3 with process-level memory caching."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from config import settings
from services.aws_clients import get_aws_clients
from utils.exceptions import ConfigurationError
from utils.logging import get_logger

LOGGER = get_logger("services.legal_service")

LEGAL_DOCUMENTS = [
    {
        "id": "privacy",
        "title": "Privacy Notice",
        "file": "Privacy Notice.html",
        "required": True,
    },
    {
        "id": "privacy-addendum",
        "title": "Privacy Addendum",
        "file": "Privacy-Addendum.html",
        "required": True,
    },
    {
        "id": "arbitration",
        "title": "FLP Individual Arbitration and Class Action Waiver Agreement",
        "file": "FLP Individual Arbitration and Class Action Waiver Agreement.html",
        "required": True,
    },
]


def legal_document_key(filename: str) -> str:
    """Build the S3 object key for a legal HTML document."""
    prefix = settings.LEGAL_PREFIX.strip("/")
    version = settings.LEGAL_VERSION.strip("/")
    return f"{prefix}/{version}/html/{filename}"


def _read_s3_text(bucket: str, key: str, title: str, filename: str) -> str:
    """Read one legal document from S3 as UTF-8 HTML."""
    try:
        response = get_aws_clients().s3.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read()
        html = body.decode("utf-8") if isinstance(body, bytes) else str(body)
    except (BotoCoreError, ClientError, KeyError, UnicodeDecodeError) as exc:
        LOGGER.error("legal_document_missing", document_title=title, filename=filename, bucket=bucket, key=key)
        raise ConfigurationError(f"{key} missing from S3 bucket {bucket}.") from exc

    if not html.strip():
        LOGGER.error("legal_document_empty", document_title=title, filename=filename, bucket=bucket, key=key)
        raise ConfigurationError(f"{key} is empty in S3 bucket {bucket}.")
    return html


@lru_cache(maxsize=1)
def load_legal_documents() -> dict[str, Any]:
    """Load all required legal documents from S3 once per process."""
    LOGGER.info(
        "legal_documents_loading",
        bucket=settings.LEGAL_BUCKET,
        prefix=settings.LEGAL_PREFIX,
        version=settings.LEGAL_VERSION,
    )
    documents: list[dict[str, Any]] = []
    for document in LEGAL_DOCUMENTS:
        key = legal_document_key(document["file"])
        html = _read_s3_text(settings.LEGAL_BUCKET, key, document["title"], document["file"])
        LOGGER.info(
            "legal_document_loaded",
            document_id=document["id"],
            document_title=document["title"],
            filename=document["file"],
            key=key,
        )
        documents.append(
            {
                "id": document["id"],
                "title": document["title"],
                "required": document["required"],
                "html": html,
            }
        )

    LOGGER.info("legal_documents_loaded_successfully", document_count=len(documents), version=settings.LEGAL_VERSION)
    return {"version": settings.LEGAL_VERSION, "documents": documents}


def get_legal_documents() -> dict[str, Any]:
    """Return cached legal documents for API responses."""
    return load_legal_documents()
````

### `services/market_config.py`

````python
"""Market and language configuration loaded from JSON."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_MARKETS_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "markets.json"
REQUIRED_MARKET_FIELDS = {"code", "name", "enabled", "defaultLanguage", "languages", "privacyVersion", "displayOrder"}
REQUIRED_LANGUAGE_FIELDS = {"code", "name", "enabled"}


def _config_path() -> Path:
    try:
        from config import settings

        configured_path = getattr(settings, "MARKETS_CONFIG_PATH", None)
    except ImportError:
        configured_path = None
    return Path(os.environ.get("MARKETS_CONFIG_PATH", configured_path or DEFAULT_MARKETS_CONFIG_PATH))


@lru_cache(maxsize=1)
def load_market_config() -> dict[str, Any]:
    """Load the market configuration file once per process."""
    config_path = _config_path()
    with config_path.open("r", encoding="utf-8") as file:
        config = json.load(file)
    _validate_market_config(config, config_path)
    return config


def _validate_market_config(config: dict[str, Any], config_path: Path) -> None:
    """Fail fast when markets.json is malformed."""
    markets = config.get("markets")
    if not isinstance(markets, list) or not markets:
        raise RuntimeError(f"Invalid market config: {config_path} must contain a non-empty markets list.")

    seen_market_codes: set[str] = set()
    seen_display_orders: set[int] = set()
    for index, market in enumerate(markets):
        if not isinstance(market, dict):
            raise RuntimeError(f"Invalid market config: market #{index + 1} must be an object.")

        missing_market_fields = REQUIRED_MARKET_FIELDS - set(market)
        if missing_market_fields:
            raise RuntimeError(
                f"Invalid market config: market #{index + 1} is missing {', '.join(sorted(missing_market_fields))}."
            )

        code = str(market["code"]).upper()
        if code in seen_market_codes:
            raise RuntimeError(f"Invalid market config: duplicate market code {code}.")
        seen_market_codes.add(code)

        if not isinstance(market["enabled"], bool):
            raise RuntimeError(f"Invalid market config: {code}.enabled must be true or false.")
        if not isinstance(market["displayOrder"], int):
            raise RuntimeError(f"Invalid market config: {code}.displayOrder must be a number.")
        if market["displayOrder"] in seen_display_orders:
            raise RuntimeError(f"Invalid market config: duplicate displayOrder {market['displayOrder']}.")
        seen_display_orders.add(market["displayOrder"])

        languages = market["languages"]
        if not isinstance(languages, list) or not languages:
            raise RuntimeError(f"Invalid market config: {code}.languages must be a non-empty list.")

        default_language = str(market["defaultLanguage"])
        enabled_language_codes: set[str] = set()
        all_language_codes: set[str] = set()
        for language_index, language in enumerate(languages):
            if not isinstance(language, dict):
                raise RuntimeError(f"Invalid market config: {code}.languages[{language_index}] must be an object.")

            missing_language_fields = REQUIRED_LANGUAGE_FIELDS - set(language)
            if missing_language_fields:
                raise RuntimeError(
                    f"Invalid market config: {code}.languages[{language_index}] is missing "
                    f"{', '.join(sorted(missing_language_fields))}."
                )

            language_code = str(language["code"])
            if language_code in all_language_codes:
                raise RuntimeError(f"Invalid market config: duplicate language {language_code} in {code}.")
            all_language_codes.add(language_code)

            if not isinstance(language["enabled"], bool):
                raise RuntimeError(f"Invalid market config: {code}.{language_code}.enabled must be true or false.")
            if language["enabled"]:
                enabled_language_codes.add(language_code)

        if market["enabled"] and default_language not in enabled_language_codes:
            raise RuntimeError(
                f"Invalid market config: {code}.defaultLanguage must match an enabled language for that market."
            )


def get_markets() -> list[dict[str, Any]]:
    """Return enabled market objects in display order."""
    markets = load_market_config()["markets"]
    enabled_markets = [market for market in markets if market.get("enabled", True)]
    return sorted(enabled_markets, key=lambda market: (market.get("displayOrder", 9999), market.get("name", "")))


def get_countries() -> list[dict[str, Any]]:
    """Return the country/language shape expected by the public API."""
    countries: list[dict[str, Any]] = []
    for market in get_markets():
        languages = [
            {"code": language["code"], "name": language["name"]}
            for language in market.get("languages", [])
            if language.get("enabled", True)
        ]
        if languages:
            countries.append(
                {
                    "code": market["code"],
                    "name": market["name"],
                    "defaultLanguage": market["defaultLanguage"],
                    "privacyVersion": market["privacyVersion"],
                    "displayOrder": market["displayOrder"],
                    "languages": languages,
                }
            )
    return countries


def get_country_codes() -> set[str]:
    """Return enabled market codes."""
    return {country["code"] for country in get_countries()}


def get_language_codes_for_country(country_code: str) -> set[str]:
    """Return enabled language codes for a specific market."""
    normalized_code = country_code.upper()
    for country in get_countries():
        if country["code"] == normalized_code:
            return {language["code"] for language in country["languages"]}
    return set()
````

### `services/pii.py`

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

### `services/session.py`

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
                    DO UPDATE SET
                        messages = EXCLUDED.messages,
                        last_activity_at = now(),
                        expires_at = EXCLUDED.expires_at,
                        updated_at = now()
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

### `services/session_service.py`

````python
"""Session lifecycle helpers for persistence and sliding expiration."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from services.db import get_engine
from utils.exceptions import AwsServiceError
from utils.logging import get_logger

LOGGER = get_logger("services.session_service")


def session_timeout_delta() -> timedelta:
    """Return the configured inactivity timeout."""
    return timedelta(hours=settings.SESSION_TIMEOUT_HOURS)


def max_session_lifetime_delta() -> timedelta:
    """Return the configured absolute session lifetime."""
    return timedelta(days=settings.MAX_SESSION_DAYS)


def validate_and_touch_session(session_id: str, correlation_id: str = "system") -> bool:
    """Validate an existing session and extend its inactivity timeout."""
    now = datetime.now(UTC)
    next_expiry = now + session_timeout_delta()
    max_created_at = now - max_session_lifetime_delta()
    try:
        with get_engine().begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT session_id, created_at, expires_at
                    FROM chat_sessions
                    WHERE session_id = :session_id
                    """
                ),
                {"session_id": session_id},
            ).mappings().first()
            if not row:
                LOGGER.info("session_created", correlation_id=correlation_id, session_id=session_id)
                return False
            if row["expires_at"] <= now or row["created_at"] <= max_created_at:
                LOGGER.info("session_expired", correlation_id=correlation_id, session_id=session_id)
                return False
            connection.execute(
                text(
                    """
                    UPDATE chat_sessions
                    SET last_activity_at = now(),
                        expires_at = :expires_at,
                        updated_at = now()
                    WHERE session_id = :session_id
                    """
                ),
                {"session_id": session_id, "expires_at": next_expiry},
            )
    except SQLAlchemyError as exc:
        LOGGER.exception("session_validation_failed", correlation_id=correlation_id)
        raise AwsServiceError("Session validation failed.") from exc
    LOGGER.info("session_reused", correlation_id=correlation_id, session_id=session_id)
    return True
````

### `tests/integration/test_chat_flow.py`

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

### `tests/unit/test_bedrock.py`

````python
"""Unit tests for Bedrock prompt rendering and response parsing."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from services.bedrock import _confidence_from_sources, build_prompt, retrieve_and_generate
from utils.exceptions import LowConfidenceError


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


def test_retrieve_and_generate_returns_low_score_answer_with_sources() -> None:
    """Low retrieval scores should be logged, not rejected, when citations exist."""
    runtime = MagicMock()
    runtime.retrieve_and_generate.return_value = {
        "output": {"text": "Return policy answer"},
        "citations": [
            {
                "retrievedReferences": [
                    {
                        "location": {"s3Location": {"uri": "s3://kb/return-policy.pdf"}},
                        "content": {"text": "Return policy excerpt"},
                        "metadata": {"score": 0.39, "page": 8, "country_code": "CA", "language": "en"},
                    }
                ]
            }
        ],
    }
    clients = SimpleNamespace(bedrock_agent_runtime=runtime)
    with patch("services.bedrock.get_aws_clients", return_value=clients):
        result = retrieve_and_generate("return policy", "CA", "en", "new_prospect", "", "cid")

    assert result["response"] == "Return policy answer"
    assert result["confidence"] < 0.5
    assert result["sources"][0]["uri"] == "s3://kb/return-policy.pdf"


def test_retrieve_and_generate_raises_when_no_sources_after_fallback() -> None:
    """No citations and no retrieve fallback sources should still produce the fallback."""
    runtime = MagicMock()
    runtime.retrieve_and_generate.return_value = {"output": {"text": "Ungrounded answer"}, "citations": []}
    runtime.retrieve.return_value = {"retrievalResults": []}
    clients = SimpleNamespace(bedrock_agent_runtime=runtime)

    with patch("services.bedrock.get_aws_clients", return_value=clients), pytest.raises(LowConfidenceError):
        retrieve_and_generate("unrelated", "CA", "en", "new_prospect", "", "cid")
````

### `tests/unit/test_cache.py`

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

### `tests/unit/test_consent_service.py`

````python
"""Unit tests for session-level consent enforcement."""

from unittest.mock import MagicMock, patch

from fastapi.responses import JSONResponse

from api import routes
from services import consent_service
from utils.validators import ChatRequest, ConsentRequest


def _engine_with_row(row):
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.first.return_value = row
    manager = MagicMock()
    manager.__enter__.return_value = connection
    engine = MagicMock()
    engine.begin.return_value = manager
    return engine, connection


def test_has_valid_consent_returns_true_for_current_version(monkeypatch) -> None:
    """Consent is valid only when the session accepted the current legal version."""
    monkeypatch.setattr(consent_service.settings, "LEGAL_VERSION", "2026.1")
    engine, _connection = _engine_with_row({"consent_accepted": True, "consent_legal_version": "2026.1"})
    monkeypatch.setattr(consent_service, "get_engine", lambda: engine)

    assert consent_service.has_valid_consent("session-1", "cid") is True


def test_has_valid_consent_returns_false_for_missing_session(monkeypatch) -> None:
    """A missing session has no valid consent."""
    engine, _connection = _engine_with_row(None)
    monkeypatch.setattr(consent_service, "get_engine", lambda: engine)

    assert consent_service.has_valid_consent("missing-session", "cid") is False


def test_has_valid_consent_returns_false_for_wrong_version(monkeypatch) -> None:
    """Changing LEGAL_VERSION forces re-consent."""
    monkeypatch.setattr(consent_service.settings, "LEGAL_VERSION", "2026.2")
    engine, _connection = _engine_with_row({"consent_accepted": True, "consent_legal_version": "2026.1"})
    monkeypatch.setattr(consent_service, "get_engine", lambda: engine)

    assert consent_service.has_valid_consent("session-1", "cid") is False


def test_has_valid_consent_query_requires_unexpired_session(monkeypatch) -> None:
    """Expired sessions are not treated as consented sessions."""
    engine, connection = _engine_with_row(None)
    monkeypatch.setattr(consent_service, "get_engine", lambda: engine)

    assert consent_service.has_valid_consent("expired-session", "cid") is False
    query = str(connection.execute.call_args.args[0])
    assert "expires_at > now()" in query


def test_record_consent_writes_audit_and_session_hot_path(monkeypatch) -> None:
    """Consent acceptance writes consent_log and updates chat_sessions."""
    monkeypatch.setattr(consent_service.settings, "LEGAL_VERSION", "2026.1")
    engine, connection = _engine_with_row(None)
    monkeypatch.setattr(consent_service, "get_engine", lambda: engine)
    body = ConsentRequest(sessionId="session-1", country="US", lang="en", timestamp="2026-07-03T12:00:00Z", version="2026.1")

    consent_service.record_consent(body, "cid")

    assert connection.execute.call_count == 2
    consent_log_params = connection.execute.call_args_list[0].args[1]
    session_params = connection.execute.call_args_list[1].args[1]
    assert consent_log_params["session_id"] == "session-1"
    assert consent_log_params["country"] == "US"
    assert consent_log_params["lang"] == "en"
    assert consent_log_params["accepted_at"] == "2026-07-03T12:00:00Z"
    assert consent_log_params["version"] == "2026.1"
    assert consent_log_params["correlation_id"] == "cid"
    assert session_params["session_id"] == "session-1"
    assert session_params["version"] == "2026.1"
    assert session_params["accepted_at"] == "2026-07-03T12:00:00Z"


def test_chat_blocks_when_consent_missing() -> None:
    """The chat route returns 403 before calling expensive services."""
    request = MagicMock()
    request.state.correlation_id = "cid"
    body = ChatRequest(message="hello", sessionId="session-1", country="US", language="en")

    with (
        patch("api.routes.validate_and_touch_session", return_value=False),
        patch("api.routes.has_valid_consent", return_value=False),
        patch("api.routes.check_text") as check_text,
    ):
        response = routes.chat(body, request)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 403
    assert b"CONSENT_REQUIRED" in response.body
    check_text.assert_not_called()


def test_chat_blocks_when_consent_version_is_invalid() -> None:
    """A failed consent validation, including wrong legal version, blocks chat."""
    request = MagicMock()
    request.state.correlation_id = "cid"
    body = ChatRequest(message="hello", sessionId="session-1", country="US", language="en")

    with (
        patch("api.routes.validate_and_touch_session", return_value=True),
        patch("api.routes.has_valid_consent", return_value=False),
        patch("api.routes.retrieve_and_generate") as bedrock,
    ):
        response = routes.chat(body, request)

    assert response.status_code == 403
    assert b"CONSENT_REQUIRED" in response.body
    bedrock.assert_not_called()
````

### `tests/unit/test_guardrails.py`

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

### `tests/unit/test_legal_service.py`

````python
"""Unit tests for legal document loading from S3."""

from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError

from services import legal_service
from utils.exceptions import ConfigurationError


class FakeBody:
    """Small stand-in for the streaming body returned by boto3 S3."""

    def __init__(self, value: str) -> None:
        self.value = value

    def read(self) -> bytes:
        return self.value.encode("utf-8")


class FakeS3:
    """Fake S3 client that records requested keys."""

    def __init__(self, objects: dict[str, str]) -> None:
        self.objects = objects
        self.calls: list[tuple[str, str]] = []

    def get_object(self, Bucket: str, Key: str) -> dict[str, FakeBody]:
        self.calls.append((Bucket, Key))
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")
        return {"Body": FakeBody(self.objects[Key])}


def _legal_objects() -> dict[str, str]:
    return {
        "legal/2026.1/html/Privacy Notice.html": "<h1>Privacy</h1>",
        "legal/2026.1/html/Privacy-Addendum.html": "<h1>Addendum</h1>",
        "legal/2026.1/html/FLP Individual Arbitration and Class Action Waiver Agreement.html": "<h1>Arbitration</h1>",
    }


def test_legal_document_key_uses_configured_s3_path(monkeypatch) -> None:
    """Legal document paths are built from bucket-independent settings."""
    monkeypatch.setattr(legal_service.settings, "LEGAL_PREFIX", "legal")
    monkeypatch.setattr(legal_service.settings, "LEGAL_VERSION", "2026.1")

    assert legal_service.legal_document_key("Privacy Notice.html") == "legal/2026.1/html/Privacy Notice.html"


def test_load_legal_documents_returns_expected_response(monkeypatch) -> None:
    """The legal service returns the API response shape."""
    fake_s3 = FakeS3(_legal_objects())
    monkeypatch.setattr(legal_service.settings, "LEGAL_BUCKET", "askverachat-prod-content")
    monkeypatch.setattr(legal_service.settings, "LEGAL_PREFIX", "legal")
    monkeypatch.setattr(legal_service.settings, "LEGAL_VERSION", "2026.1")
    monkeypatch.setattr(legal_service, "get_aws_clients", lambda: SimpleNamespace(s3=fake_s3))
    legal_service.load_legal_documents.cache_clear()

    result = legal_service.load_legal_documents()

    assert result["version"] == "2026.1"
    assert [document["id"] for document in result["documents"]] == ["privacy", "privacy-addendum", "arbitration"]
    assert all(document["required"] is True for document in result["documents"])
    assert result["documents"][0]["html"] == "<h1>Privacy</h1>"


def test_load_legal_documents_caches_s3_results(monkeypatch) -> None:
    """Legal documents are fetched from S3 once and then served from memory."""
    fake_s3 = FakeS3(_legal_objects())
    monkeypatch.setattr(legal_service.settings, "LEGAL_BUCKET", "askverachat-prod-content")
    monkeypatch.setattr(legal_service.settings, "LEGAL_PREFIX", "legal")
    monkeypatch.setattr(legal_service.settings, "LEGAL_VERSION", "2026.1")
    monkeypatch.setattr(legal_service, "get_aws_clients", lambda: SimpleNamespace(s3=fake_s3))
    legal_service.load_legal_documents.cache_clear()

    first = legal_service.load_legal_documents()
    second = legal_service.load_legal_documents()

    assert first is second
    assert len(fake_s3.calls) == 3


def test_load_legal_documents_fails_when_document_missing(monkeypatch) -> None:
    """Startup validation fails if any required legal document is absent."""
    objects = _legal_objects()
    objects.pop("legal/2026.1/html/Privacy Notice.html")
    fake_s3 = FakeS3(objects)
    monkeypatch.setattr(legal_service.settings, "LEGAL_BUCKET", "askverachat-prod-content")
    monkeypatch.setattr(legal_service.settings, "LEGAL_PREFIX", "legal")
    monkeypatch.setattr(legal_service.settings, "LEGAL_VERSION", "2026.1")
    monkeypatch.setattr(legal_service, "get_aws_clients", lambda: SimpleNamespace(s3=fake_s3))
    legal_service.load_legal_documents.cache_clear()

    with pytest.raises(ConfigurationError, match="Privacy Notice.html"):
        legal_service.load_legal_documents()
````

### `tests/unit/test_market_config.py`

````python
"""Unit tests for market configuration loading and validation."""

import json

import pytest

from services import market_config


def _write_config(tmp_path, markets):
    config_path = tmp_path / "markets.json"
    config_path.write_text(json.dumps({"version": 1, "markets": markets}), encoding="utf-8")
    return config_path


def _market(code="CA", languages=None, default_language="en", enabled=True, display_order=10):
    return {
        "code": code,
        "name": "Canada",
        "enabled": enabled,
        "defaultLanguage": default_language,
        "privacyVersion": "2026.1",
        "displayOrder": display_order,
        "languages": languages
        or [
            {"code": "en", "name": "English", "enabled": True},
            {"code": "fr", "name": "French", "enabled": True},
        ],
    }


def test_load_market_config_hides_disabled_markets_and_languages(tmp_path, monkeypatch) -> None:
    """Only enabled market/language options are exposed to the API."""
    config_path = _write_config(
        tmp_path,
        [
            _market(languages=[{"code": "en", "name": "English", "enabled": True}, {"code": "fr", "name": "French", "enabled": False}]),
            _market(code="US", enabled=False, display_order=20),
        ],
    )
    monkeypatch.setenv("MARKETS_CONFIG_PATH", str(config_path))
    market_config.load_market_config.cache_clear()

    countries = market_config.get_countries()

    assert [country["code"] for country in countries] == ["CA"]
    assert countries[0]["languages"] == [{"code": "en", "name": "English"}]


def test_load_market_config_rejects_duplicate_market_codes(tmp_path, monkeypatch) -> None:
    """Duplicate market codes fail fast at config load time."""
    config_path = _write_config(tmp_path, [_market(), _market()])
    monkeypatch.setenv("MARKETS_CONFIG_PATH", str(config_path))
    market_config.load_market_config.cache_clear()

    with pytest.raises(RuntimeError, match="duplicate market code CA"):
        market_config.load_market_config()


def test_load_market_config_rejects_duplicate_language_codes(tmp_path, monkeypatch) -> None:
    """Duplicate language codes within one market fail fast."""
    config_path = _write_config(
        tmp_path,
        [
            _market(
                languages=[
                    {"code": "en", "name": "English", "enabled": True},
                    {"code": "en", "name": "English duplicate", "enabled": True},
                ]
            )
        ],
    )
    monkeypatch.setenv("MARKETS_CONFIG_PATH", str(config_path))
    market_config.load_market_config.cache_clear()

    with pytest.raises(RuntimeError, match="duplicate language en in CA"):
        market_config.load_market_config()


def test_load_market_config_rejects_default_language_not_enabled(tmp_path, monkeypatch) -> None:
    """A market's default language must be one of its enabled language options."""
    config_path = _write_config(
        tmp_path,
        [_market(languages=[{"code": "en", "name": "English", "enabled": True}], default_language="fr")],
    )
    monkeypatch.setenv("MARKETS_CONFIG_PATH", str(config_path))
    market_config.load_market_config.cache_clear()

    with pytest.raises(RuntimeError, match="CA.defaultLanguage"):
        market_config.load_market_config()
````

### `tests/unit/test_pii.py`

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

### `tests/unit/test_privacy_route.py`

````python
"""Unit tests for privacy/legal document route."""

from unittest.mock import MagicMock, patch

from api import routes


def test_privacy_route_works_without_locale_params() -> None:
    """Legal documents are global and do not require country/lang query parameters."""
    request = MagicMock()
    request.state.correlation_id = "cid"

    with patch("api.routes.get_legal_documents", return_value={"version": "2026.1", "documents": []}):
        response = routes.privacy(request)

    assert response.success is True
    assert response.data == {"version": "2026.1", "documents": []}
````

### `tests/unit/test_session_service.py`

````python
"""Unit tests for session persistence and sliding expiration."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from services import session_service


def _engine_with_row(row):
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.first.return_value = row
    manager = MagicMock()
    manager.__enter__.return_value = connection
    engine = MagicMock()
    engine.begin.return_value = manager
    return engine, connection


def test_validate_and_touch_session_reuses_unexpired_session(monkeypatch) -> None:
    """An unexpired session is reused and receives sliding expiration."""
    now = datetime.now(UTC)
    engine, connection = _engine_with_row(
        {
            "session_id": "session-1",
            "created_at": now - timedelta(minutes=5),
            "expires_at": now + timedelta(minutes=30),
        }
    )
    monkeypatch.setattr(session_service, "get_engine", lambda: engine)

    assert session_service.validate_and_touch_session("session-1", "cid") is True
    assert connection.execute.call_count == 2


def test_validate_and_touch_session_rejects_missing_session(monkeypatch) -> None:
    """A missing session is treated as a new session that still requires consent."""
    engine, connection = _engine_with_row(None)
    monkeypatch.setattr(session_service, "get_engine", lambda: engine)

    assert session_service.validate_and_touch_session("new-session", "cid") is False
    assert connection.execute.call_count == 1


def test_validate_and_touch_session_rejects_expired_session(monkeypatch) -> None:
    """Expired sessions are not reused."""
    now = datetime.now(UTC)
    engine, connection = _engine_with_row(
        {
            "session_id": "session-1",
            "created_at": now - timedelta(minutes=5),
            "expires_at": now - timedelta(minutes=1),
        }
    )
    monkeypatch.setattr(session_service, "get_engine", lambda: engine)

    assert session_service.validate_and_touch_session("session-1", "cid") is False
    assert connection.execute.call_count == 1


def test_validate_and_touch_session_rejects_session_over_max_lifetime(monkeypatch) -> None:
    """Sessions beyond absolute max lifetime are renewed."""
    now = datetime.now(UTC)
    engine, connection = _engine_with_row(
        {
            "session_id": "session-1",
            "created_at": now - timedelta(days=8),
            "expires_at": now + timedelta(minutes=30),
        }
    )
    monkeypatch.setattr(session_service, "get_engine", lambda: engine)

    assert session_service.validate_and_touch_session("session-1", "cid") is False
    assert connection.execute.call_count == 1
````

### `utils/__init__.py`

````python
"""Utility package for ASK Vera."""
````

### `utils/exceptions.py`

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

### `utils/logging.py`

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

### `utils/validators.py`

````python
"""Pydantic models for API request and response validation."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from config.vera_persona import ROLE_CONTENT_SCOPES
from services.market_config import get_country_codes, get_language_codes_for_country


def _country_codes() -> set[str]:
    return get_country_codes()


def _language_codes_for_country(country_code: str) -> set[str]:
    return get_language_codes_for_country(country_code)


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

### `widget-wrapper/demo/src/App.tsx`

````tsx
import { BackendChatDemo } from "../../src/generic-widget/examples/BackendChatDemo";
import { useEffect, useState } from "react";

const apiBaseUrl = new URLSearchParams(window.location.search).get("api") || "https://api.vera-api.xyz";

type ApiEnvelope<T> = {
  success: boolean;
  data?: T;
  error?: { message: string };
};

type LegalDocument = {
  id: string;
  title: string;
  html: string;
};

type PrivacyResponseData = {
  version: string;
  documents: LegalDocument[];
};

const joinUrl = (baseUrl: string, path: string) => `${baseUrl.replace(/\/$/, "")}${path}`;

function LegalDocumentPage() {
  const params = new URLSearchParams(window.location.search);
  const api = params.get("api") || apiBaseUrl;
  const country = params.get("country") || "US";
  const lang = params.get("lang") || "en";
  const documentId = params.get("doc") || "privacy";
  const [state, setState] = useState<{ loading: boolean; error?: string; data?: PrivacyResponseData }>({ loading: true });

  useEffect(() => {
    let active = true;
    const path = `/api/privacy?country=${encodeURIComponent(country)}&lang=${encodeURIComponent(lang)}`;

    fetch(joinUrl(api, path))
      .then(async (response) => {
        const envelope = (await response.json()) as ApiEnvelope<PrivacyResponseData>;
        if (!response.ok || !envelope.success || !envelope.data) {
          throw new Error(envelope.error?.message || `Request failed with status ${response.status}`);
        }
        if (active) setState({ loading: false, data: envelope.data });
      })
      .catch((error) => {
        if (active) {
          setState({ loading: false, error: error instanceof Error ? error.message : "Could not load legal document." });
        }
      });

    return () => {
      active = false;
    };
  }, [api, country, documentId, lang]);

  const selectedDocument = state.data?.documents.find((document) => document.id === documentId) || state.data?.documents[0];

  return (
    <main className="legal-page">
      <a className="legal-back-link" href={`/?api=${encodeURIComponent(api)}`}>Back to widget demo</a>
      {state.loading ? <p className="legal-status">Loading legal document...</p> : null}
      {state.error ? <p className="legal-error">{state.error}</p> : null}
      {selectedDocument ? (
        <article className="legal-document">
          <header>
            <p className="legal-eyebrow">{country} / {lang.toUpperCase()} / Version {state.data?.version}</p>
            <h1>{selectedDocument.title}</h1>
          </header>
          <div className="legal-html" dangerouslySetInnerHTML={{ __html: selectedDocument.html }} />
        </article>
      ) : null}
    </main>
  );
}

export function App() {
  if (window.location.pathname === "/legal") {
    return <LegalDocumentPage />;
  }

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

### `widget-wrapper/demo/src/main.tsx`

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

### `widget-wrapper/demo/src/styles.css`

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

.legal-page {
  position: relative;
  max-width: 980px;
  margin: 0 auto;
  padding: 42px 28px 72px;
}

.legal-back-link {
  display: inline-flex;
  margin-bottom: 22px;
  color: #111111;
  font-size: 14px;
  font-weight: 800;
  text-decoration: underline;
  text-decoration-color: #ffc400;
  text-decoration-thickness: 3px;
  text-underline-offset: 4px;
}

.legal-document {
  overflow: hidden;
  background: #ffffff;
  border: 1px solid rgba(0, 0, 0, 0.14);
  border-radius: 8px;
  box-shadow: 0 22px 60px rgba(23, 32, 51, 0.12);
}

.legal-document header {
  padding: 28px 32px;
  color: #ffffff;
  background: #000000;
}

.legal-eyebrow {
  margin: 0 0 8px;
  color: #ffc400;
  font-size: 12px;
  font-weight: 850;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.legal-document h1 {
  margin: 0;
  font-size: 30px;
  line-height: 1.18;
  letter-spacing: 0;
}

.legal-html {
  padding: 30px 34px 42px;
  color: #1f2933;
  font-size: 15px;
  line-height: 1.65;
}

.legal-html h1,
.legal-html h2,
.legal-html h3,
.legal-html strong {
  color: #111111;
}

.legal-html a {
  color: #111111;
  font-weight: 750;
  text-decoration-color: #ffc400;
  text-decoration-thickness: 2px;
  text-underline-offset: 3px;
}

.legal-html table {
  width: 100%;
  border-collapse: collapse;
}

.legal-html th,
.legal-html td {
  padding: 10px;
  border: 1px solid #d8dee6;
  vertical-align: top;
}

.legal-status,
.legal-error {
  padding: 16px 18px;
  background: #ffffff;
  border: 1px solid rgba(0, 0, 0, 0.14);
  border-radius: 8px;
  font-weight: 750;
}

.legal-error {
  color: #8a1f11;
  border-color: rgba(138, 31, 17, 0.28);
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

### `widget-wrapper/package.json`

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

### `widget-wrapper/src/generic-widget/config/defaultTheme.ts`

````ts
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

### `widget-wrapper/src/generic-widget/config/exampleWidgetConfig.ts`

````ts
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

### `widget-wrapper/src/generic-widget/ConsentPanel.tsx`

````tsx
import { useState } from "react";
import type { GenericWidgetConfig } from "./types";
import { LegalLinks } from "./LegalLinks";

export function ConsentPanel({
  config,
  onAccept,
  onReject,
  accepting = false,
  error
}: {
  config: GenericWidgetConfig;
  onAccept: () => void;
  onReject: () => void;
  accepting?: boolean;
  error?: string | null;
}) {
  const [acknowledged, setAcknowledged] = useState(false);

  return (
    <section className="gw-section gw-consent">
      <h2>{config.consent.title}</h2>
      <div className="gw-consent-body">{config.consent.body}</div>
      <LegalLinks config={config} />
      <label className="gw-consent-ack">
        <input
          type="checkbox"
          checked={acknowledged}
          onChange={(event) => setAcknowledged(event.target.checked)}
        />
        <span>I have read and agree to all of the above documents.</span>
      </label>
      {error ? <p className="gw-consent-error" role="alert">{error}</p> : null}
      <div className="gw-consent-actions">
        <button type="button" className="gw-secondary-button" onClick={onReject} disabled={accepting}>{config.labels.rejectConsentLabel}</button>
        <button type="button" className="gw-primary-button" onClick={onAccept} disabled={!acknowledged || accepting}>
          {accepting ? "Saving..." : config.labels.acceptConsentLabel}
        </button>
      </div>
    </section>
  );
}
````

### `widget-wrapper/src/generic-widget/examples/BackendChatDemo.tsx`

````tsx
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { GenericWidgetWrapper } from "../GenericWidgetWrapper";
import type { ConsentEventPayload, MessageEventPayload, WidgetMessage } from "../types";
import { foreverDemoConfig } from "./foreverDemoConfig";

type ApiEnvelope<T> = {
  success: boolean;
  data?: T;
  error?: { code: string; message: string; legalVersion?: string };
  correlationId: string;
};

class ApiRequestError extends Error {
  code?: string;
  legalVersion?: string;
  status?: number;
  correlationId?: string;

  constructor(message: string, code?: string, legalVersion?: string, status?: number, correlationId?: string) {
    super(message);
    this.name = "ApiRequestError";
    this.code = code;
    this.legalVersion = legalVersion;
    this.status = status;
    this.correlationId = correlationId;
  }
}

class ApiTimeoutError extends Error {
  constructor(message = "The request timed out. Please try again.") {
    super(message);
    this.name = "ApiTimeoutError";
  }
}

class ApiNetworkError extends Error {
  constructor(message = "The API could not be reached. Please check the connection and try again.") {
    super(message);
    this.name = "ApiNetworkError";
  }
}

type ChatResponseData = {
  response: string;
  sources?: Array<{ title: string; uri: string; excerpt?: string }>;
  confidence?: number;
  correlationId?: string;
};

type ApiCountry = {
  code: string;
  name: string;
  languages: Array<{ code: string; name: string }>;
};

type ConfigResponseData = {
  countries: ApiCountry[];
  privacyVersion: string;
};

type LegalDocument = {
  id: string;
  title: string;
  required: boolean;
  html: string;
};

type PrivacyResponseData = {
  version: string;
  documents: LegalDocument[];
};

export type BackendChatDemoProps = {
  apiBaseUrl?: string;
};

const REQUEST_TIMEOUT_MS = 30000;

const buildId = (prefix: string) => {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const joinUrl = (baseUrl: string, path: string) => `${baseUrl.replace(/\/$/, "")}${path}`;

const legalViewerHref = (apiBaseUrl: string, country: string, language: string, documentId: string) => {
  const params = new URLSearchParams({
    api: apiBaseUrl,
    country,
    lang: language,
    doc: documentId
  });
  return `/legal?${params.toString()}`;
};

async function fetchWithTimeout(url: string, init?: RequestInit, timeoutMs = REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiTimeoutError();
    }
    throw new ApiNetworkError(error instanceof Error ? error.message : undefined);
  } finally {
    window.clearTimeout(timeoutId);
  }
}

async function parseEnvelope<T>(response: Response): Promise<ApiEnvelope<T>> {
  try {
    return (await response.json()) as ApiEnvelope<T>;
  } catch {
    return {
      success: false,
      correlationId: response.headers.get("x-correlation-id") || "",
      error: { code: "INVALID_RESPONSE", message: "The API returned an unreadable response." }
    };
  }
}

async function postJson<T>(baseUrl: string, path: string, body: unknown): Promise<ApiEnvelope<T>> {
  const response = await fetchWithTimeout(joinUrl(baseUrl, path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const envelope = await parseEnvelope<T>(response);
  if (!response.ok || !envelope.success) {
    throw new ApiRequestError(
      envelope.error?.message || `Request failed with status ${response.status}`,
      envelope.error?.code,
      envelope.error?.legalVersion,
      response.status,
      envelope.correlationId || response.headers.get("x-correlation-id") || undefined
    );
  }
  return envelope;
}

async function getJson<T>(baseUrl: string, path: string): Promise<ApiEnvelope<T>> {
  const response = await fetchWithTimeout(joinUrl(baseUrl, path));
  const envelope = await parseEnvelope<T>(response);
  if (!response.ok || !envelope.success) {
    throw new ApiRequestError(
      envelope.error?.message || `Request failed with status ${response.status}`,
      envelope.error?.code,
      envelope.error?.legalVersion,
      response.status,
      envelope.correlationId || response.headers.get("x-correlation-id") || undefined
    );
  }
  return envelope;
}

function describeApiError(error: unknown): string {
  if (error instanceof ApiTimeoutError) {
    return "The request timed out. Please try again in a moment.";
  }
  if (error instanceof ApiNetworkError) {
    return `The API could not be reached: ${error.message}`;
  }
  if (error instanceof ApiRequestError) {
    const status = error.status ? `HTTP ${error.status}` : "API error";
    return `${status}: ${error.message}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "An unexpected API error occurred.";
}

function logCorrelationId(label: string, correlationId?: string) {
  if (!correlationId || window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1") return;
  console.info(`[ASK Vera] ${label} correlation ID: ${correlationId}`);
}

function buildLocaleOptions(countries: ApiCountry[]) {
  const languageMap = new Map<string, { label: string; countryCodes: string[] }>();
  const sortedCountries = [...countries].sort((first, second) => first.name.localeCompare(second.name));

  for (const country of sortedCountries) {
    for (const language of country.languages) {
      const current = languageMap.get(language.code) || { label: language.name, countryCodes: [] };
      if (!current.countryCodes.includes(country.code)) {
        current.countryCodes.push(country.code);
      }
      languageMap.set(language.code, current);
    }
  }

  return {
    countries: sortedCountries.map((country) => ({
      code: country.code,
      label: country.name,
      languageCodes: country.languages.map((language) => language.code)
    })),
    languages: Array.from(languageMap.entries()).map(([code, language]) => ({
      code,
      label: language.label,
      countryCodes: language.countryCodes
    }))
  };
}

export function BackendChatDemo({ apiBaseUrl = "https://api.vera-api.xyz" }: BackendChatDemoProps) {
  const [apiConfig, setApiConfig] = useState<ConfigResponseData | null>(null);
  const [selectedLocale, setSelectedLocale] = useState({ country: "US", language: "en" });
  const [legalDocuments, setLegalDocuments] = useState<LegalDocument[]>([]);
  const [legalVersion, setLegalVersion] = useState<string | null>(null);
  const [pendingMessage, setPendingMessage] = useState<MessageEventPayload | null>(null);
  const [consentRequiredSignal, setConsentRequiredSignal] = useState(0);
  const requestInFlightRef = useRef(false);
  const config = useMemo(
    () => {
      const localeOptions = apiConfig ? buildLocaleOptions(apiConfig.countries) : null;
      const policyLinks = legalDocuments.length
        ? legalDocuments.map((document) => ({
            id: document.id,
            label: document.title,
            href: legalViewerHref(apiBaseUrl, selectedLocale.country, selectedLocale.language, document.id),
            target: "_blank" as const
          }))
        : foreverDemoConfig.policyLinks.map((link) => ({
            ...link,
            href: legalViewerHref(apiBaseUrl, selectedLocale.country, selectedLocale.language, link.id === "terms" ? "privacy" : link.id),
            target: "_blank" as const
          }));

      return {
        ...foreverDemoConfig,
        provider: { name: "ASK Vera API", type: "custom-react" as const },
        consent: {
          ...foreverDemoConfig.consent,
          policyVersion: legalVersion || apiConfig?.privacyVersion || foreverDemoConfig.consent.policyVersion
        },
        countries: localeOptions?.countries || foreverDemoConfig.countries,
        languages: localeOptions?.languages || foreverDemoConfig.languages,
        defaultCountryCode: selectedLocale.country,
        defaultLanguageCode: selectedLocale.language,
        policyLinks
      };
    },
    [apiBaseUrl, apiConfig, legalDocuments, legalVersion, selectedLocale.country, selectedLocale.language]
  );
  const [messages, setMessages] = useState<WidgetMessage[]>([
    {
      id: "backend-welcome",
      role: "assistant",
      content: "Accept the privacy terms, then ask a question. This demo sends messages to the Python API."
    }
  ]);
  const [loading, setLoading] = useState(false);

  const appendMessage = useCallback((message: WidgetMessage) => {
    setMessages((current) => [...current, message]);
  }, []);

  const upsertMessage = useCallback((message: WidgetMessage) => {
    setMessages((current) => {
      const existingIndex = current.findIndex((item) => item.id === message.id);
      if (existingIndex === -1) return [...current, message];
      return current.map((item, index) => (index === existingIndex ? message : item));
    });
  }, []);

  useEffect(() => {
    let active = true;

    getJson<ConfigResponseData>(apiBaseUrl, "/api/config")
      .then((envelope) => {
        if (active && envelope.data) {
          logCorrelationId("config", envelope.correlationId);
          setApiConfig(envelope.data);
        }
      })
      .catch((error) => {
        if (active) {
          upsertMessage({
            id: "config-warning",
            role: "system",
            content: `Using demo market list because API config could not load. ${describeApiError(error)}`
          });
        }
      });

    return () => {
      active = false;
    };
  }, [apiBaseUrl, upsertMessage]);

  useEffect(() => {
    let active = true;
    const path = `/api/privacy?country=${encodeURIComponent(selectedLocale.country)}&lang=${encodeURIComponent(selectedLocale.language)}`;

    getJson<PrivacyResponseData>(apiBaseUrl, path)
      .then((envelope) => {
        if (active && envelope.data) {
          logCorrelationId("privacy", envelope.correlationId);
          setLegalDocuments(envelope.data.documents);
          setLegalVersion(envelope.data.version);
        }
      })
      .catch((error) => {
        if (active) {
          setLegalDocuments([]);
          upsertMessage({
            id: "privacy-warning",
            role: "system",
            content: `Legal documents could not load yet. ${describeApiError(error)}`
          });
        }
      });

    return () => {
      active = false;
    };
  }, [apiBaseUrl, selectedLocale.country, selectedLocale.language, upsertMessage]);

  const handleConsent = async (payload: ConsentEventPayload) => {
    const envelope = await postJson(apiBaseUrl, "/api/consent", {
      sessionId: payload.sessionId,
      country: payload.selectedCountry,
      lang: payload.selectedLanguage,
      timestamp: payload.timestamp,
      version: payload.policyVersion
    });
    logCorrelationId("consent", envelope.correlationId);
    if (pendingMessage) {
      const retryPayload = { ...pendingMessage, sessionId: payload.sessionId };
      setPendingMessage(null);
      await sendChat(retryPayload, false);
    }
  };

  const sendChat = async (payload: MessageEventPayload, showUserMessage = true) => {
    if (requestInFlightRef.current) return;
    requestInFlightRef.current = true;
    if (showUserMessage) appendMessage({ id: buildId("user"), role: "user", content: payload.message });
    setLoading(true);
    try {
      const envelope = await postJson<ChatResponseData>(apiBaseUrl, "/api/chat", {
        message: payload.message,
        sessionId: payload.sessionId,
        country: payload.selectedCountry,
        language: payload.selectedLanguage,
        role: "new_prospect"
      });
      const correlationId = envelope.data?.correlationId || envelope.correlationId;
      logCorrelationId("chat", correlationId);
      appendMessage({
        id: buildId("assistant"),
        role: "assistant",
        content: envelope.data?.response || "I could not find a response for that question.",
        metadata: {
          sources: envelope.data?.sources || [],
          confidence: envelope.data?.confidence,
          correlationId
        }
      });
    } catch (error) {
      if (error instanceof ApiRequestError && error.code === "CONSENT_REQUIRED") {
        setPendingMessage(payload);
        setConsentRequiredSignal((value) => value + 1);
        appendMessage({
          id: buildId("consent-required"),
          role: "system",
          content: "Please accept the legal documents before chatting. Your message will be sent after consent is recorded."
        });
        return;
      }
      appendMessage({
        id: buildId("api-error"),
        role: "system",
        content: `The message could not be sent. ${describeApiError(error)}`
      });
    } finally {
      requestInFlightRef.current = false;
      setLoading(false);
    }
  };

  const handleMessage = async (payload: MessageEventPayload) => {
    await sendChat(payload);
  };

  return (
    <GenericWidgetWrapper
      config={config}
      messages={messages}
      loading={loading}
      openByDefault
      consentRequiredSignal={consentRequiredSignal}
      onAcceptConsent={handleConsent}
      onCountryChange={(payload) => setSelectedLocale({ country: payload.selectedCountry, language: payload.selectedLanguage })}
      onLanguageChange={(payload) => setSelectedLocale({ country: payload.selectedCountry, language: payload.selectedLanguage })}
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

### `widget-wrapper/src/generic-widget/examples/ChatwootWidgetExample.tsx`

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

### `widget-wrapper/src/generic-widget/examples/foreverDemoConfig.tsx`

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
    title: "Privacy and Terms",
    body: (
      <>
        <p><strong>To use ASK Vera, you must review and accept the legal documents below.</strong></p>
        <p>Your consent will be recorded for this session before you can start chatting.</p>
        <p>Please review the following legal documents before continuing.</p>
      </>
    ),
    categories: ["chat-processing", "market-language-preferences"],
    storageKey: "forever-style-widget-demo-consent"
  },
  persistConsent: true,
  sessionStorageKey: "askvera_session_id",
  sessionMetadataStorageKey: "askvera_session_metadata",
  visitorStorageKey: "askvera_visitor_id",
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

### `widget-wrapper/src/generic-widget/examples/LocalChatwootDemo.tsx`

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

### `widget-wrapper/src/generic-widget/examples/ThirdPartyWidgetExample.tsx`

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

### `widget-wrapper/src/generic-widget/FloatingLauncher.tsx`

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

### `widget-wrapper/src/generic-widget/generic-widget.css`

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
  padding: 18px;
  background: #ffffff;
  border: 1px solid #e2e2e2;
  border-left: 5px solid var(--gw-accent);
  border-radius: 8px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.07);
}

.gw-consent h2 { margin: 0 0 10px; color: #000000; font-size: 18px; font-weight: 850; }
.gw-consent-body { color: #4a4a4a; font-size: 14px; line-height: 1.55; }
.gw-consent-body p { margin: 0 0 10px; }
.gw-consent-body p:last-child { margin-bottom: 0; }

.gw-legal {
  margin-top: 16px;
  display: grid;
  gap: 11px;
}

.gw-legal-item {
  display: grid;
  grid-template-columns: 12px 1fr;
  gap: 8px;
  align-items: start;
  color: #000000;
  font-size: 13px;
  line-height: 1.35;
}

.gw-legal-item > span {
  color: var(--gw-accent);
  font-weight: 900;
}

.gw-legal-item a {
  color: #000000;
  text-decoration: underline;
  text-decoration-color: var(--gw-accent);
  text-decoration-thickness: 2px;
  text-underline-offset: 4px;
  font-size: 13px;
  font-weight: 800;
}

.gw-legal-item a:hover,
.gw-legal-item a:focus-visible { color: color-mix(in srgb, #000000, var(--gw-accent) 22%); }

.gw-consent-ack {
  display: grid;
  grid-template-columns: 18px 1fr;
  gap: 10px;
  align-items: start;
  margin-top: 18px;
  padding: 12px;
  color: #202020;
  background: color-mix(in srgb, var(--gw-accent), white 90%);
  border: 1px solid color-mix(in srgb, var(--gw-accent), white 62%);
  border-radius: 8px;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.4;
}

.gw-consent-ack input {
  width: 18px;
  height: 18px;
  margin: 1px 0 0;
  accent-color: var(--gw-accent);
}

.gw-consent-error {
  margin: 12px 0 0;
  padding: 10px 12px;
  color: #8a1f11;
  background: #fff4f0;
  border: 1px solid rgba(138, 31, 17, 0.28);
  border-radius: 8px;
  font-size: 13px;
  font-weight: 750;
  line-height: 1.4;
}

.gw-consent-actions {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
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

.gw-consent .gw-secondary-button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
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

.gw-message h3,
.gw-message h4,
.gw-message h5 {
  margin: 0 0 10px;
  color: #1f1f1f;
  font-weight: 800;
  line-height: 1.25;
}

.gw-message h3 {
  font-size: 18px;
}

.gw-message h4,
.gw-message h5 {
  font-size: 16px;
}

.gw-message strong {
  color: #1f1f1f;
  font-weight: 800;
}

.gw-message ul,
.gw-message ol {
  margin: 0 0 16px 20px;
  padding: 0;
}

.gw-message li {
  margin: 0 0 8px;
  padding-left: 2px;
}

.gw-message li:last-child {
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

### `widget-wrapper/src/generic-widget/GenericWidgetWrapper.tsx`

````tsx
import { FormEvent, type CSSProperties, useEffect, useMemo, useState } from "react";
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
  readSessionMetadata,
  readStoredId,
  writeSessionMetadata,
  writeStoredId,
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
  consentRequiredSignal = 0,
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
  const [storedSessionMetadata] = useState(() => readSessionMetadata(config.sessionMetadataStorageKey));
  const [visitorId] = useState(() => providedVisitorId || readStoredId(config.visitorStorageKey) || createVisitorId());
  const [sessionId] = useState(() => providedSessionId || readStoredId(config.sessionStorageKey) || createSessionId());
  const storedLocale = useMemo(() => {
    if (!storedSessionMetadata || storedSessionMetadata.sessionId !== sessionId) return undefined;
    const country = config.countries.find((option) => option.code === storedSessionMetadata.market);
    if (!country) return undefined;
    const languageOptions = filterLanguagesByCountry(config.languages, country.code, config.countries);
    const language = languageOptions.find((option) => option.code === storedSessionMetadata.language);
    return language ? { country, language } : undefined;
  }, [config.countries, config.languages, sessionId, storedSessionMetadata]);
  const [isOpen, setIsOpen] = useState(openByDefault);
  const [menuOpen, setMenuOpen] = useState(false);
  const [selectedCountry, setSelectedCountry] = useState(storedLocale?.country || initialLocale.country);
  const [selectedLanguage, setSelectedLanguage] = useState(storedLocale?.language || initialLocale.language);
  const [message, setMessage] = useState("");
  const [showSuccess, setShowSuccess] = useState(initialShowSuccess);
  const [consentSubmitting, setConsentSubmitting] = useState(false);
  const [consentError, setConsentError] = useState<string | null>(null);
  const [sessionCreatedAt] = useState(
    () => storedSessionMetadata?.createdAt || new Date().toISOString()
  );
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

  useEffect(() => {
    writeStoredId(config.visitorStorageKey, visitorId);
    writeStoredId(config.sessionStorageKey, sessionId);
    const storedSession = readSessionMetadata(config.sessionMetadataStorageKey);
    const legalVersionChanged = Boolean(
      storedSession &&
        storedSession.sessionId === sessionId &&
        storedSession.legalVersion &&
        storedSession.legalVersion !== config.consent.policyVersion
    );
    if (legalVersionChanged) {
      setConsentAccepted(false);
      setShowSuccess(false);
      if (config.persistConsent) writeConsentFlag(config.consent.storageKey, false);
    }
    writeSessionMetadata(config.sessionMetadataStorageKey, {
      sessionId,
      createdAt: storedSession?.sessionId === sessionId ? storedSession.createdAt : sessionCreatedAt,
      legalVersion: config.consent.policyVersion,
      market: selectedCountry?.code,
      language: selectedLanguage?.code
    });
  }, [
    config.consent.policyVersion,
    config.consent.storageKey,
    config.persistConsent,
    config.sessionMetadataStorageKey,
    config.sessionStorageKey,
    config.visitorStorageKey,
    sessionCreatedAt,
    sessionId,
    selectedCountry?.code,
    selectedLanguage?.code,
    visitorId
  ]);

  useEffect(() => {
    if (!consentRequiredSignal) return;
    setConsentAccepted(false);
    setShowSuccess(false);
    setConsentError("Please review and accept the legal documents before chatting.");
    if (config.persistConsent) writeConsentFlag(config.consent.storageKey, false);
  }, [config.consent.storageKey, config.persistConsent, consentRequiredSignal]);

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

  const handleConsent = async (actionType: "accepted" | "rejected") => {
    const payload = createConsentRecord({
      actionType,
      config,
      selectedCountry: selectedCountry?.code || "",
      selectedLanguage: selectedLanguage?.code || "",
      visitorId,
      sessionId
    });
    const accepted = actionType === "accepted";
    setConsentError(null);

    if (!accepted) {
      onRejectConsent?.(payload);
      return;
    }

    try {
      setConsentSubmitting(true);
      await onAcceptConsent?.(payload);
      setConsentAccepted(true);
      setShowSuccess(true);
      if (config.persistConsent) writeConsentFlag(config.consent.storageKey, true);
    } catch {
      setConsentAccepted(false);
      setShowSuccess(false);
      setConsentError("Unable to record your consent. Please try again.");
    } finally {
      setConsentSubmitting(false);
    }
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
              <ConsentPanel
                config={config}
                accepting={consentSubmitting}
                error={consentError}
                onAccept={() => handleConsent("accepted")}
                onReject={() => handleConsent("rejected")}
              />
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

### `widget-wrapper/src/generic-widget/Header.tsx`

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

### `widget-wrapper/src/generic-widget/index.ts`

````ts
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

### `widget-wrapper/src/generic-widget/integrations/ChatwootWidgetAdapter.tsx`

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

### `widget-wrapper/src/generic-widget/LegalLinks.tsx`

````tsx
import type { GenericWidgetConfig } from "./types";

export function LegalLinks({ config }: { config: GenericWidgetConfig }) {
  if (!config.policyLinks.length) return null;

  return (
    <nav className="gw-legal" aria-label={config.labels.legalLinksLabel}>
      {config.policyLinks.map((link) => (
        <div key={link.id} className="gw-legal-item">
          <span aria-hidden="true">{"\u2022"}</span>
          <a href={link.href} target={link.target || "_blank"} rel="noreferrer">
            {link.label}
          </a>
        </div>
      ))}
    </nav>
  );
}
````

### `widget-wrapper/src/generic-widget/Menu.tsx`

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

### `widget-wrapper/src/generic-widget/MessageFeed.tsx`

````tsx
import type { ReactNode } from "react";
import type { GenericWidgetConfig, GenericWidgetRenderState, WidgetMessage } from "./types";

function normalizeMessageContent(content: string): string {
  return content
    .replace(/\r\n/g, "\n")
    .replace(/([^\n])\s+(#{1,3}\s+)/g, "$1\n\n$2")
    .replace(/\s+-\s+(?=(?:\*\*)?[A-Z0-9])/g, "\n- ");
}

function renderInlineMarkdown(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /\*\*(.+?)\*\*/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) nodes.push(text.slice(lastIndex, match.index));
    nodes.push(<strong key={`strong-${match.index}`}>{match[1]}</strong>);
    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));
  return nodes;
}

function renderMessageContent(content: string): ReactNode {
  const lines = normalizeMessageContent(content).split("\n");
  const blocks: ReactNode[] = [];
  let paragraph: string[] = [];
  let listItems: string[] = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const text = paragraph.join(" ").trim();
    if (text) blocks.push(<p key={`p-${blocks.length}`}>{renderInlineMarkdown(text)}</p>);
    paragraph = [];
  };

  const flushList = () => {
    if (!listItems.length) return;
    blocks.push(
      <ul key={`ul-${blocks.length}`}>
        {listItems.map((item, index) => (
          <li key={`${item}-${index}`}>{renderInlineMarkdown(item)}</li>
        ))}
      </ul>
    );
    listItems = [];
  };

  lines.forEach((rawLine) => {
    const line = rawLine.trim();

    if (!line) {
      flushParagraph();
      flushList();
      return;
    }

    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      flushParagraph();
      flushList();
      const level = heading[1].length;
      const Tag = level === 1 ? "h3" : level === 2 ? "h4" : "h5";
      blocks.push(<Tag key={`h-${blocks.length}`}>{renderInlineMarkdown(heading[2])}</Tag>);
      return;
    }

    const bullet = /^[-*]\s+(.+)$/.exec(line);
    if (bullet) {
      flushParagraph();
      listItems.push(bullet[1]);
      return;
    }

    flushList();
    paragraph.push(line);
  });

  flushParagraph();
  flushList();

  return blocks.length ? blocks : <p>{content}</p>;
}

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
          <div>
            {message.role === "assistant" && typeof message.content === "string"
              ? renderMessageContent(message.content)
              : message.content}
          </div>
        </article>
      ))}
    </div>
  );
}
````

### `widget-wrapper/src/generic-widget/PlainStateGenericWidgetWrapper.tsx`

````tsx
import { GenericWidgetWrapper } from "./GenericWidgetWrapper";
import type { GenericWidgetWrapperProps } from "./types";

export function PlainStateGenericWidgetWrapper(props: GenericWidgetWrapperProps) {
  return <GenericWidgetWrapper {...props} />;
}
````

### `widget-wrapper/src/generic-widget/RegionSelector.tsx`

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

### `widget-wrapper/src/generic-widget/types.ts`

````ts
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
  sessionStorageKey?: string;
  sessionMetadataStorageKey?: string;
  visitorStorageKey?: string;
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
  consentRequiredSignal?: number;
  showLocaleSelector?: boolean;
  visitorId?: string;
  sessionId?: string;
  className?: string;
  style?: CSSProperties;
  renderMessages?: (messages: WidgetMessage[], state: GenericWidgetRenderState) => ReactNode;
  onOpen?: () => void;
  onClose?: () => void;
  onAcceptConsent?: (payload: ConsentEventPayload) => void | Promise<void>;
  onRejectConsent?: (payload: ConsentEventPayload) => void;
  onCountryChange?: (payload: LocaleChangePayload) => void;
  onLanguageChange?: (payload: LocaleChangePayload) => void;
  onSendMessage?: (payload: MessageEventPayload) => void;
  onEscalate?: (payload: LocaleChangePayload) => void;
  onNewChat?: (payload: LocaleChangePayload) => void;
};
````

### `widget-wrapper/src/generic-widget/utils.ts`

````ts
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

export const readStoredId = (storageKey?: string) =>
  storageKey && typeof localStorage !== "undefined" ? localStorage.getItem(storageKey) || undefined : undefined;

export const writeStoredId = (storageKey: string | undefined, value: string) => {
  if (!storageKey || typeof localStorage === "undefined") return;
  localStorage.setItem(storageKey, value);
};

export type StoredSessionMetadata = {
  sessionId: string;
  createdAt: string;
  legalVersion: string;
  market?: string;
  language?: string;
};

export const readSessionMetadata = (storageKey?: string): StoredSessionMetadata | undefined => {
  if (!storageKey || typeof localStorage === "undefined") return undefined;
  const raw = localStorage.getItem(storageKey);
  if (!raw) return undefined;
  try {
    const parsed = JSON.parse(raw) as Partial<StoredSessionMetadata>;
    if (!parsed.sessionId || !parsed.createdAt || !parsed.legalVersion) return undefined;
    return {
      sessionId: parsed.sessionId,
      createdAt: parsed.createdAt,
      legalVersion: parsed.legalVersion,
      market: parsed.market,
      language: parsed.language
    };
  } catch {
    return undefined;
  }
};

export const writeSessionMetadata = (storageKey: string | undefined, metadata: StoredSessionMetadata) => {
  if (!storageKey || typeof localStorage === "undefined") return;
  localStorage.setItem(storageKey, JSON.stringify(metadata));
};

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

### `widget-wrapper/tsconfig.json`

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

### `widget-wrapper/vite.config.ts`

````ts
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

