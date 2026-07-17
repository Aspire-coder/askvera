"""FastAPI route definitions for ASK Vera."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.orchestrator import ConsentRequiredError, ai_orchestrator
from app.response import ChatResponse
from app.widget_auth import WidgetInitRequest, WidgetRefreshRequest, widget_auth_service
from app.widget_auth.jwt import WidgetTokenError
from app.widget_auth.service import WidgetAuthError
from config import settings
from services import cache as cache_service
from services.consent_service import record_consent
from services.session_service import close_session
from services.db import get_engine
from services.feedback import enqueue_feedback
from services.analytics import record_chat_interaction, record_feedback_event
from app.operations import pipeline_trace_store
from services.legal_service import get_legal_documents
from services.market_config import get_countries, get_country_codes, get_language_codes_for_country
from utils.exceptions import AskVeraError
from utils.logging import get_logger
from utils.validators import ChatRequest, ConsentRequest, EndSessionRequest, Envelope, FeedbackRequest

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


def _session_matches_widget_token(request: Request, session_id: str) -> bool:
    """Prevent one authenticated widget session from operating on another."""
    claims = getattr(request.state, "widget_auth", {}) or {}
    claimed_session_id = str(claims.get("sessionId") or "")
    return not settings.WIDGET_AUTH_REQUIRED or claimed_session_id == session_id


def _session_mismatch_response(correlation_id: str) -> JSONResponse:
    envelope = Envelope(
        success=False,
        error={"code": "SESSION_MISMATCH", "message": "Please start a new chat."},
        correlationId=correlation_id,
    )
    return JSONResponse(status_code=403, content=envelope.model_dump())


@router.post("/api/widget/init", response_model=None)
def widget_init(body: WidgetInitRequest, request: Request) -> Envelope | JSONResponse:
    """Initialize a short-lived authenticated widget session."""
    correlation_id = _correlation_id(request)
    origin_header = request.headers.get("origin")
    if not origin_header and not body.origin:
        LOGGER.warning("widget_auth_origin_missing", correlation_id=correlation_id, ip_address=request.client.host if request.client else None)
        envelope = Envelope(
            success=False,
            error={"code": "WIDGET_AUTH_FAILED", "message": "Widget origin could not be verified."},
            correlationId=correlation_id,
        )
        return JSONResponse(status_code=403, content=envelope.model_dump())

    if origin_header and body.origin and origin_header.rstrip("/") != body.origin:
        LOGGER.warning(
            "widget_auth_origin_mismatch",
            correlation_id=correlation_id,
            widget_id=body.widgetId,
            origin=origin_header,
            body_origin=body.origin,
            ip_address=request.client.host if request.client else None,
        )
        envelope = Envelope(
            success=False,
            error={"code": "WIDGET_AUTH_FAILED", "message": "Widget origin could not be verified."},
            correlationId=correlation_id,
        )
        return JSONResponse(status_code=403, content=envelope.model_dump())
    try:
        effective_origin = origin_header or body.origin
        result = widget_auth_service.initialize(
            body.model_copy(update={"origin": effective_origin}),
            correlation_id,
            request.client.host if request.client else None,
        )
        return success(result.model_dump(), correlation_id)
    except WidgetAuthError as exc:
        return error_response(exc, correlation_id)


@router.post("/api/widget/refresh", response_model=None)
def widget_refresh(body: WidgetRefreshRequest, request: Request) -> Envelope | JSONResponse:
    """Refresh a short-lived authenticated widget session token."""
    correlation_id = _correlation_id(request)
    try:
        result = widget_auth_service.refresh(body.token, correlation_id, request.headers.get("origin"))
        return success(result.model_dump(), correlation_id)
    except WidgetTokenError as exc:
        return error_response(exc, correlation_id)
    except WidgetAuthError as exc:
        return error_response(exc, correlation_id)


@router.get("/api/widget/config", response_model=None)
def widget_config(request: Request) -> Envelope | JSONResponse:
    """Return backend-owned widget branding, market config, and legal documents."""
    correlation_id = _correlation_id(request)
    claims = getattr(request.state, "widget_auth", {}) or {}
    registration = widget_auth_service.get_registration(str(claims.get("widgetId", "")))
    if registration is None:
        return error_response(WidgetAuthError("Widget is not active."), correlation_id)

    metadata = registration.metadata or {}
    documents = get_legal_documents()
    return success(
        {
            "widgetId": registration.widgetId,
            "companyName": registration.companyName,
            "logo": str(metadata.get("logo") or ""),
            "theme": str(metadata.get("theme") or "light"),
            "primaryColor": str(metadata.get("primaryColor") or "#2D7FF9"),
            "sdkVersion": str(metadata.get("sdkVersion") or "1.0.0"),
            "countries": get_countries(),
            "privacyVersion": documents["version"],
            "legalDocs": documents["documents"],
            "starterTopics": metadata.get("starterTopics"),
            "contextualTopics": metadata.get("contextualTopics"),
        },
        correlation_id,
    )


def _valid_language_codes(country_code: str) -> set[str]:
    return get_language_codes_for_country(country_code)


@router.post("/api/chat", response_model=None)
def chat(body: ChatRequest, request: Request) -> Envelope | JSONResponse:
    """Answer a user message using RAG-only ASK Vera flow."""
    correlation_id = _correlation_id(request)
    if not _session_matches_widget_token(request, body.sessionId):
        return _session_mismatch_response(correlation_id)
    pipeline_trace_store.start(
        correlation_id,
        country=body.country,
        language=body.language,
        role=body.role,
        session_id=body.sessionId,
        question_preview=body.message,
    )
    try:
        result = ai_orchestrator.handle_chat(body, correlation_id)
        if isinstance(result, ChatResponse):
            token_usage = result.metadata.get("token_usage") if isinstance(result.metadata, dict) else {}
            token_usage = token_usage if isinstance(token_usage, dict) else {}
            record_chat_interaction(body, result, correlation_id)
            pipeline_trace_store.finish(
                correlation_id,
                success=True,
                metadata={
                    "confidence": result.confidence or 0.0,
                    "source_count": len(result.citations),
                    "fallback": bool(result.metadata.get("fallback")),
                    "provider": str(result.metadata.get("provider") or ""),
                    "model": str(result.metadata.get("model_name") or ""),
                    "inputTokens": int(token_usage.get("inputTokens", token_usage.get("input_tokens", 0)) or 0),
                    "outputTokens": int(token_usage.get("outputTokens", token_usage.get("output_tokens", 0)) or 0),
                    "cacheHit": str(result.metadata.get("cache") or "").lower() == "hit",
                    "tokensSaved": int(result.metadata.get("cache_token_savings", 0) or 0),
                },
            )
            return success(result.to_api_result(), correlation_id)
        pipeline_trace_store.finish(correlation_id, success=True)
        return success(result, correlation_id)
    except ConsentRequiredError:
        pipeline_trace_store.finish(correlation_id, success=False, metadata={"reason": "consent_required"})
        return consent_required_response(correlation_id)
    except AskVeraError as exc:
        pipeline_trace_store.finish(correlation_id, success=False, metadata={"reason": exc.error_code})
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
    if not _session_matches_widget_token(request, body.sessionId):
        return _session_mismatch_response(correlation_id)
    try:
        record_consent(body, correlation_id)
        return success({"recorded": True, "legalVersion": settings.LEGAL_VERSION}, correlation_id)
    except AskVeraError as exc:
        return error_response(exc, correlation_id)


@router.post("/api/session/end", response_model=None)
def end_session(body: EndSessionRequest, request: Request) -> Envelope | JSONResponse:
    """End a chat while retaining its transcript and consent audit records."""
    correlation_id = _correlation_id(request)
    if not _session_matches_widget_token(request, body.sessionId):
        return _session_mismatch_response(correlation_id)
    try:
        closed = close_session(body.sessionId, body.reason, correlation_id)
        return success({"ended": True, "found": closed, "reason": body.reason}, correlation_id)
    except AskVeraError as exc:
        return error_response(exc, correlation_id)


@router.post("/api/feedback", response_model=None)
def feedback(body: FeedbackRequest, request: Request) -> Envelope | JSONResponse:
    """Send user feedback to SQS."""
    correlation_id = _correlation_id(request)
    if not _session_matches_widget_token(request, body.sessionId):
        return _session_mismatch_response(correlation_id)
    try:
        record_feedback_event(body, correlation_id)
        enqueue_feedback(body, correlation_id)
        return success(
            {
                "queued": True,
                "requestType": body.requestType,
                "ticketId": correlation_id if body.requestType == "support" else None,
            },
            correlation_id,
        )
    except AskVeraError as exc:
        return error_response(exc, correlation_id)


@router.get("/health")
def health() -> JSONResponse:
    """Return fast ALB health status in the same envelope used by the widget."""
    import main

    status = "draining" if main.shutdown_requested else "healthy"
    correlation_id = "health"
    envelope = Envelope(
        success=not main.shutdown_requested,
        data={"status": status, "version": settings.APP_VERSION},
        correlationId=correlation_id,
    )
    return JSONResponse(status_code=503 if main.shutdown_requested else 200, content=envelope.model_dump())


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
