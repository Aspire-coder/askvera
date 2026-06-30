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
