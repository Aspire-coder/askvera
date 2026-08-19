"""Authenticated operational APIs for the AskVera admin portal."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from tempfile import gettempdir
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError

from app.operations import pipeline_trace_store
from config import settings
from services.admin_auth import require_admin_identity
from services.answer_cache_admin import AnswerCacheUnavailable, reset_answer_cache
from services.admin_users import (
    ADMIN_ROLES,
    ADMIN_SECTIONS,
    accessible_markets,
    certify_admin_access,
    create_admin_user,
    list_admin_audit_events,
    list_admin_users,
    record_admin_audit_event,
    require_admin_access,
    resend_admin_invite,
    set_admin_user_enabled,
    update_admin_user,
)
from services.analytics import (
    analytics_overview,
    interaction_export_csv,
    interaction_export_xlsx,
    interaction_page,
    model_routing_report,
    retrieval_shadow_report,
)
from services.analytics_governance import (
    delete_saved_view,
    list_saved_views,
    review_case_market,
    save_view,
    update_review_case,
)
from services.knowledge_ingestion import (
    ACCESS_SCOPES,
    DOCUMENT_TYPES,
    create_ingestion_job,
    delete_ingestion_job,
    enqueue_ingestion_job,
    fail_ingestion_job,
    list_ingestion_jobs,
    list_document_generations,
    process_ingestion_job,
    preview_ingestion_job,
    publish_ingestion_job,
    rollback_document_generation,
    stage_ingestion_upload,
    test_ingestion_job,
    cleanup_staged_ingestion_upload,
    detect_upload_format,
    safe_filename,
    validate_document_content,
    validate_upload,
)
from services.document_preflight import analyze_pdf_with_timeout
from services.market_config import (
    get_countries,
    get_country_codes,
    get_language_codes_for_country,
    get_widget_countries,
    get_widget_country_codes,
)
from services.market_readiness import build_market_readiness, upsert_market_governance
from services.operations_status import operations_status
from services.support_routes import list_support_routes, send_support_route_test, support_route_history, upsert_support_route
from services.aws_clients import get_aws_clients
from services.widget_configs import (
    create_widget_config,
    disable_widget_config,
    get_widget_config,
    list_widget_configs,
    rotate_widget_key,
    stage_widget_config,
    publish_widget_config,
    update_widget_config,
)
from app.widget_registry.service import widget_registry_service

admin_router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin_identity)])


def _preflight_uploaded_document(filename: str, content: bytes) -> None:
    """Reject suspicious uploads before durable storage when hardened preflight is enabled."""
    if not settings.ADMIN_DOCUMENT_PREFLIGHT_ENABLED:
        return
    directory = Path(gettempdir()) / "askvera-upload-preflight" / str(uuid4())
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    try:
        path.write_bytes(content)
        validate_document_content(path)
        if path.suffix.lower() == ".pdf":
            analyze_pdf_with_timeout(
                path,
                timeout_seconds=settings.ADMIN_INGESTION_PARSER_TIMEOUT_SECONDS,
                max_pages=settings.ADMIN_INGESTION_MAX_PDF_PAGES,
                max_extracted_characters=settings.ADMIN_INGESTION_MAX_EXTRACTED_TEXT_CHARS,
            )
    finally:
        shutil.rmtree(directory, ignore_errors=True)


class AdminScopeInput(BaseModel):
    market: str = Field(min_length=1, max_length=8)
    section: str = Field(min_length=1, max_length=32)
    permission: str = Field(min_length=1, max_length=32)


class AdminUserCreateInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    role: str
    scopes: list[AdminScopeInput] = Field(default_factory=list)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in ADMIN_ROLES:
            raise ValueError("Unsupported administrator role.")
        return value


class AdminUserUpdateInput(BaseModel):
    role: str
    scopes: list[AdminScopeInput] = Field(default_factory=list)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in ADMIN_ROLES:
            raise ValueError("Unsupported administrator role.")
        return value


class WidgetConfigInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    customer: str = Field(default="", max_length=160)
    allowed_origins: list[str] = Field(min_length=1, max_length=100)
    markets: list[str] = Field(min_length=1)
    languages: list[str] = Field(min_length=1)
    default_market: str
    default_language: str
    display_name: str = Field(default="AskVera", min_length=1, max_length=80)
    greeting: str = Field(default="", max_length=500)
    logo_url: str = Field(default="", max_length=2048)
    accent_color: str = Field(default="#2F7D4E", max_length=7)
    position: str = Field(default="bottom-right")
    legal_version: str = Field(default="", max_length=64)
    rate_limit_tier: str = Field(default="standard", max_length=32)
    usage_cap: int | None = Field(default=None, ge=1)


class SupportRouteInput(BaseModel):
    department: str = Field(min_length=1, max_length=160)
    email: str = Field(min_length=3, max_length=254)
    enabled: bool = True
    fallback_department: str = Field(default="", max_length=160)
    fallback_email: str = Field(default="", max_length=254)


class SupportRouteBulkInput(BaseModel):
    countries: list[str] = Field(min_length=1, max_length=200)
    route: SupportRouteInput


class MarketGovernanceInput(BaseModel):
    owner_email: str = Field(default="", max_length=254)
    deadline: str = Field(default="", max_length=10)


class ReviewCaseInput(BaseModel):
    status: str
    assignee_email: str = Field(default="", max_length=254)
    resolution_notes: str = Field(default="", max_length=4000)


class AnalyticsSavedViewInput(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=100)
    filters: dict[str, str] = Field(default_factory=dict)
    schedule: str = "none"
    report_email: str = Field(default="", max_length=254)
    alert_not_helpful_threshold: float | None = Field(default=None, ge=0, le=1)


class CacheResetInput(BaseModel):
    country: str = Field(min_length=2, max_length=12)
    mode: Literal["exact", "exact_and_semantic"] = "exact_and_semantic"
    reason: str = Field(min_length=8, max_length=500)
    confirmation: str = Field(min_length=5, max_length=32)


def _payload(data: Any, request: Request) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "correlationId": str(getattr(request.state, "correlation_id", "admin")),
    }


@admin_router.get("/config")
def admin_config(request: Request) -> dict[str, Any]:
    principal = getattr(request.state, "admin_identity", {}) or {}
    scopes = principal.get("scopes") or []
    allowed_markets = {
        scope["market"]
        for scope in scopes
        if scope.get("market") and scope.get("market") != "*"
    }
    countries = get_countries()
    widget_countries = get_widget_countries()
    if settings.ADMIN_RBAC_ENABLED and principal.get("role") != "super_admin":
        countries = [country for country in countries if country["code"] in allowed_markets]
        widget_countries = [
            country for country in widget_countries if country["code"] in allowed_markets
        ]
    return _payload(
        {
            "countries": countries,
            "widgetCountries": widget_countries,
            "documentTypes": sorted(DOCUMENT_TYPES),
            "accessScopes": sorted(ACCESS_SCOPES),
            "maxUploadBytes": settings.ADMIN_UPLOAD_MAX_BYTES,
            "rbacEnabled": settings.ADMIN_RBAC_ENABLED,
            "userManagementEnabled": settings.ADMIN_USER_MANAGEMENT_ENABLED,
            "widgetConfigEnabled": settings.WIDGET_CONFIG_ADMIN_ENABLED,
            "principal": {
                "role": principal.get("role", "super_admin"),
                "status": principal.get("status", "active"),
                "scopes": scopes,
                "sections": sorted(ADMIN_SECTIONS),
            },
        },
        request,
    )


@admin_router.get("/market-readiness")
def market_readiness(request: Request) -> dict[str, Any]:
    """Return market onboarding checks for the Operations portal."""
    require_admin_access(request, "knowledge", "view")
    return _payload(build_market_readiness(), request)


@admin_router.put("/market-readiness/{country}/governance")
def market_readiness_governance(country: str, body: MarketGovernanceInput, request: Request) -> dict[str, Any]:
    normalized = country.upper().strip()
    require_admin_access(request, "knowledge", "manage", normalized)
    if normalized not in get_country_codes():
        raise HTTPException(status_code=400, detail="Unsupported country.")
    principal = getattr(request.state, "admin_identity", {}) or {}
    actor = str(principal.get("email") or principal.get("sub") or "admin")[:320]
    try:
        result = upsert_market_governance(normalized, body.owner_email, body.deadline, actor)
    except (ValueError, SQLAlchemyError) as exc:
        raise HTTPException(status_code=400, detail="Owner or deadline is invalid.") from exc
    record_admin_audit_event(actor, "market_readiness.governance_updated", normalized)
    return _payload(result, request)


@admin_router.get("/operations/status")
def operational_status(request: Request) -> dict[str, Any]:
    """Return safe dependency, synchronization and deployed-version signals."""
    require_admin_access(request, "flow", "view")
    return _payload(operations_status(), request)


@admin_router.post("/operations/cache/reset")
def operational_cache_reset(body: CacheResetInput, request: Request) -> dict[str, Any]:
    """Reset only cached answers after explicit Super Admin confirmation."""
    principal = getattr(request.state, "admin_identity", {}) or {}
    if principal.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only a Super Admin can reset answer caches.")

    country = body.country.strip().upper()
    supported = get_country_codes() | get_widget_country_codes()
    if country != "ALL" and country not in supported:
        raise HTTPException(status_code=400, detail="Unsupported country.")
    if body.confirmation.strip().upper() != f"RESET {country}":
        raise HTTPException(status_code=400, detail=f'Type "RESET {country}" to confirm.')

    correlation_id = str(getattr(request.state, "correlation_id", "admin"))
    try:
        result = reset_answer_cache(
            country,
            include_semantic=body.mode == "exact_and_semantic",
            correlation_id=correlation_id,
        )
    except AnswerCacheUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    record_admin_audit_event(
        _actor(request),
        "operations.answer_cache_reset",
        country,
        metadata={
            "reason": body.reason.strip(),
            "mode": body.mode,
            "exact_deleted": result["exact_deleted"],
            "semantic_deleted": result["semantic_deleted"],
            "total_deleted": result["total_deleted"],
            "correlation_id": correlation_id,
        },
    )
    return _payload(result, request)


@admin_router.get("/analytics/overview")
def overview(
    request: Request,
    days: int = 30,
    country: str = "",
    language: str = "",
    traffic_source: str = "",
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    principal = getattr(request.state, "admin_identity", None) or {}
    markets = accessible_markets(principal, "insights", "view")
    if country:
        require_admin_access(request, "insights", "view", country)
    elif not markets:
        raise HTTPException(status_code=403, detail="You do not have access to Insights.")
    try:
        result = analytics_overview(
            days=days,
            country=country,
            language=language,
            traffic_source=traffic_source,
            allowed_countries=None if principal.get("role") == "super_admin" else markets,
            start=start,
            end=end,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _payload(result, request)


@admin_router.get("/analytics/model-routing")
def model_routing_analytics(
    request: Request,
    days: int = 7,
    country: str = "",
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    principal = getattr(request.state, "admin_identity", None) or {}
    markets = accessible_markets(principal, "insights", "view")
    if country:
        require_admin_access(request, "insights", "view", country)
    elif not markets:
        raise HTTPException(status_code=403, detail="You do not have access to Insights.")
    try:
        result = model_routing_report(
            days=days,
            country=country,
            allowed_countries=None if principal.get("role") == "super_admin" else markets,
            start=start,
            end=end,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _payload(result, request)


@admin_router.get("/analytics/interactions")
def interactions(
    request: Request,
    days: int = 30,
    country: str = "",
    language: str = "",
    traffic_source: str = "",
    feedback: str = "all",
    search: str = "",
    sort: str = "newest",
    page: int = 1,
    page_size: int = 50,
    start: datetime | None = None,
    end: datetime | None = None,
    include_raw: bool = False,
) -> dict[str, Any]:
    principal = getattr(request.state, "admin_identity", None) or {}
    markets = accessible_markets(principal, "insights", "view")
    if country:
        require_admin_access(request, "insights", "view", country)
    elif not markets:
        raise HTTPException(status_code=403, detail="You do not have access to Insights.")
    if feedback not in {"all", "helpful", "not_helpful", "unrated"}:
        raise HTTPException(status_code=400, detail="Unsupported feedback filter.")
    if include_raw:
        if not settings.ADMIN_ANALYTICS_RAW_TRANSCRIPT_ACCESS_ENABLED:
            raise HTTPException(status_code=403, detail="Raw interaction access is disabled.")
        require_admin_access(request, "audit", "view")
        record_admin_audit_event(
            str(principal.get("sub") or principal.get("email") or "unknown"),
            "analytics.raw_interactions_viewed",
            country.upper() or "all_markets",
        )
    try:
        result = interaction_page(
            days=days,
            country=country,
            language=language,
            traffic_source=traffic_source,
            allowed_countries=None if principal.get("role") == "super_admin" else markets,
            feedback=feedback,
            search=search,
            sort=sort,
            page=page,
            page_size=page_size,
            start=start,
            end=end,
            redact_content=settings.ADMIN_ANALYTICS_REDACTED_BY_DEFAULT and not include_raw,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _payload(result, request)


@admin_router.get("/analytics/interactions.csv")
def interactions_export(
    request: Request,
    days: int = 30,
    country: str = "",
    language: str = "",
    traffic_source: str = "",
    feedback: str = "all",
    search: str = "",
    sort: str = "newest",
    limit: int = 5000,
    start: datetime | None = None,
    end: datetime | None = None,
    include_raw: bool = False,
) -> StreamingResponse:
    """Download filtered feedback/interactions with redaction as the default."""
    principal = getattr(request.state, "admin_identity", None) or {}
    markets = accessible_markets(principal, "insights", "view")
    if country:
        require_admin_access(request, "insights", "view", country)
    elif not markets:
        raise HTTPException(status_code=403, detail="You do not have access to Insights.")
    if feedback not in {"all", "helpful", "not_helpful", "unrated"}:
        raise HTTPException(status_code=400, detail="Unsupported feedback filter.")
    if include_raw:
        if not settings.ADMIN_ANALYTICS_RAW_TRANSCRIPT_ACCESS_ENABLED:
            raise HTTPException(status_code=403, detail="Raw interaction access is disabled.")
        require_admin_access(request, "audit", "view")
        record_admin_audit_event(
            str(principal.get("sub") or principal.get("email") or "unknown"),
            "analytics.raw_interactions_exported",
            country.upper() or "all_markets",
        )
    try:
        csv_text = interaction_export_csv(
            days=days,
            country=country,
            language=language,
            traffic_source=traffic_source,
            allowed_countries=None if principal.get("role") == "super_admin" else markets,
            feedback=feedback,
            search=search,
            sort=sort,
            limit=limit,
            start=start,
            end=end,
            redact_content=settings.ADMIN_ANALYTICS_REDACTED_BY_DEFAULT and not include_raw,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="askvera-interactions.csv"'},
    )


@admin_router.put("/analytics/interactions/{correlation_id}/review")
def interaction_review_update(
    correlation_id: str,
    body: ReviewCaseInput,
    request: Request,
) -> dict[str, Any]:
    """Assign, investigate or resolve one answer-quality case."""
    try:
        country = review_case_market(correlation_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    require_admin_access(request, "insights", "manage", country)
    actor = _actor(request)
    try:
        result = update_review_case(
            correlation_id,
            status=body.status,
            assignee_email=body.assignee_email,
            resolution_notes=body.resolution_notes,
            actor=actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    record_admin_audit_event(actor, "analytics.review_updated", correlation_id)
    return _payload(result, request)


@admin_router.get("/analytics/saved-views")
def analytics_saved_views_list(request: Request) -> dict[str, Any]:
    require_admin_access(request, "insights", "view")
    principal = getattr(request.state, "admin_identity", {}) or {}
    actor = str(principal.get("sub") or principal.get("email") or "unknown")
    return _payload(list_saved_views(actor), request)


@admin_router.put("/analytics/saved-views")
def analytics_saved_view_save(
    body: AnalyticsSavedViewInput,
    request: Request,
) -> dict[str, Any]:
    require_admin_access(request, "insights", "manage")
    actor = _actor(request)
    try:
        result = save_view(
            view_id=body.id,
            name=body.name,
            owner_sub=actor,
            filters={
                **body.filters,
                "_allowed_countries": ",".join(sorted(accessible_markets(
                    getattr(request.state, "admin_identity", {}) or {},
                    "insights",
                    "view",
                ))),
            },
            schedule=body.schedule,
            report_email=body.report_email,
            alert_not_helpful_threshold=body.alert_not_helpful_threshold,
        )
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_admin_audit_event(actor, "analytics.saved_view_updated", result["id"])
    return _payload(result, request)


@admin_router.delete("/analytics/saved-views/{view_id}")
def analytics_saved_view_delete(view_id: str, request: Request) -> dict[str, Any]:
    require_admin_access(request, "insights", "manage")
    actor = _actor(request)
    if not delete_saved_view(view_id, actor):
        raise HTTPException(status_code=404, detail="Saved view not found.")
    record_admin_audit_event(actor, "analytics.saved_view_deleted", view_id)
    return _payload({"deleted": True}, request)


@admin_router.get("/analytics/interactions.xlsx")
def interactions_export_xlsx(
    request: Request,
    days: int = 30,
    country: str = "",
    language: str = "",
    traffic_source: str = "",
    feedback: str = "all",
    search: str = "",
    sort: str = "newest",
    limit: int = 5000,
    start: datetime | None = None,
    end: datetime | None = None,
    include_raw: bool = False,
) -> StreamingResponse:
    """Download filtered feedback as an Excel workbook with the same controls as CSV."""
    principal = getattr(request.state, "admin_identity", None) or {}
    markets = accessible_markets(principal, "insights", "view")
    if country:
        require_admin_access(request, "insights", "view", country)
    elif not markets:
        raise HTTPException(status_code=403, detail="You do not have access to Insights.")
    if feedback not in {"all", "helpful", "not_helpful", "unrated"}:
        raise HTTPException(status_code=400, detail="Unsupported feedback filter.")
    if include_raw:
        if not settings.ADMIN_ANALYTICS_RAW_TRANSCRIPT_ACCESS_ENABLED:
            raise HTTPException(status_code=403, detail="Raw interaction access is disabled.")
        require_admin_access(request, "audit", "view")
        record_admin_audit_event(
            str(principal.get("sub") or principal.get("email") or "unknown"),
            "analytics.raw_interactions_exported",
            country.upper() or "all_markets",
        )
    try:
        workbook = interaction_export_xlsx(
            days=days,
            country=country,
            language=language,
            traffic_source=traffic_source,
            allowed_countries=None if principal.get("role") == "super_admin" else markets,
            feedback=feedback,
            search=search,
            sort=sort,
            limit=limit,
            start=start,
            end=end,
            redact_content=settings.ADMIN_ANALYTICS_REDACTED_BY_DEFAULT and not include_raw,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return StreamingResponse(
        iter([workbook]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="askvera-feedback.xlsx"'},
    )


@admin_router.get("/analytics/retrieval-shadow")
def retrieval_shadow(
    request: Request,
    days: int = 30,
    country: str = "",
    language: str = "",
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    principal = getattr(request.state, "admin_identity", None) or {}
    markets = accessible_markets(principal, "insights", "view")
    if country:
        require_admin_access(request, "insights", "view", country)
    elif not markets:
        raise HTTPException(status_code=403, detail="You do not have access to Insights.")
    try:
        result = retrieval_shadow_report(
            days=days,
            country=country,
            language=language,
            allowed_countries=None if principal.get("role") == "super_admin" else markets,
            start=start,
            end=end,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _payload(result, request)


@admin_router.get("/traces")
def traces(request: Request, limit: int = 20) -> dict[str, Any]:
    principal = require_admin_access(request, "flow", "view")
    markets = accessible_markets(principal, "flow", "view")
    recent = pipeline_trace_store.latest(pipeline_trace_store.capacity)
    visible = [trace for trace in recent if str(trace.get("country") or "").upper() in markets]
    return _payload(visible[: max(1, min(limit, pipeline_trace_store.capacity))], request)


@admin_router.get("/traces/stream")
async def trace_stream(request: Request) -> StreamingResponse:
    """Stream privacy-safe traces to authorized administrators as they change."""
    principal = require_admin_access(request, "flow", "view")
    markets = accessible_markets(principal, "flow", "view")

    async def events():
        previous = ""
        while not await request.is_disconnected():
            recent = pipeline_trace_store.latest(20)
            visible = [trace for trace in recent if str(trace.get("country") or "").upper() in markets]
            payload = json.dumps(visible, separators=(",", ":"), default=str)
            if payload != previous:
                yield f"event: traces\ndata: {payload}\n\n"
                previous = payload
            else:
                yield ": keep-alive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@admin_router.get("/traces/{correlation_id}")
def trace_detail(correlation_id: str, request: Request) -> dict[str, Any]:
    trace = pipeline_trace_store.get(correlation_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found in the recent in-process window.")
    require_admin_access(request, "flow", "view", str(trace.get("country") or ""))
    return _payload(trace, request)


@admin_router.get("/ingestions")
def ingestions(request: Request, limit: int = 50) -> dict[str, Any]:
    principal = require_admin_access(request, "knowledge", "view")
    markets = accessible_markets(principal, "knowledge", "view")
    jobs = list_ingestion_jobs(200)
    visible = [
        job
        for job in jobs
        if job.get("access_scope") == "global" or str(job.get("country") or "").upper() in markets
    ]
    return _payload(visible[: max(1, min(limit, 200))], request)


@admin_router.delete("/ingestions/{job_id}")
def delete_ingestion(job_id: str, request: Request) -> dict[str, Any]:
    """Delete a document and remove it from the live retrieval index."""
    principal = getattr(request.state, "admin_identity", {}) or {}
    if principal.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only a Super Admin can delete documents.")
    require_admin_access(request, "knowledge", "manage")
    deleted_by = str(principal.get("email") or principal.get("sub") or "admin")[:320]
    try:
        job = delete_ingestion_job(job_id, deleted_by=deleted_by)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Ingestion job not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    record_admin_audit_event(deleted_by, "knowledge.document_deleted", job_id)
    return _payload({"job": job, "message": "Document deleted from live retrieval and source storage."}, request)


class IngestionPreviewTestRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=10)


@admin_router.get("/ingestions/{job_id}/preview")
def ingestion_preview(job_id: str, request: Request, limit: int = 20) -> dict[str, Any]:
    require_admin_access(request, "knowledge", "view")
    try:
        preview = preview_ingestion_job(job_id, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Ingestion job not found.") from exc
    require_admin_access(request, "knowledge", "view", str(preview["job"].get("country") or ""))
    return _payload(preview, request)


@admin_router.post("/ingestions/{job_id}/preview-test")
def ingestion_preview_test(
    job_id: str,
    body: IngestionPreviewTestRequest,
    request: Request,
) -> dict[str, Any]:
    require_admin_access(request, "knowledge", "view")
    try:
        preview = preview_ingestion_job(job_id, limit=1)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Ingestion job not found.") from exc
    require_admin_access(request, "knowledge", "view", str(preview["job"].get("country") or ""))
    try:
        result = test_ingestion_job(job_id, body.message, limit=body.limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _payload(result, request)


@admin_router.post("/ingestions/{job_id}/publish")
def publish_ingestion(job_id: str, request: Request) -> dict[str, Any]:
    principal = require_admin_access(request, "knowledge", "stage")
    try:
        preview = preview_ingestion_job(job_id, limit=1)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Ingestion job not found.") from exc
    require_admin_access(request, "knowledge", "stage", str(preview["job"].get("country") or ""))
    accepted_by = str(principal.get("email") or principal.get("sub") or "admin")[:320]
    try:
        result = publish_ingestion_job(job_id, accepted_by=accepted_by)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _payload(result, request)


@admin_router.get("/ingestions/{job_id}/generations")
def ingestion_generations(job_id: str, request: Request) -> dict[str, Any]:
    require_admin_access(request, "knowledge", "view")
    try:
        preview = preview_ingestion_job(job_id, limit=1)
        if str(preview["job"].get("access_scope") or "") != "global":
            require_admin_access(request, "knowledge", "view", str(preview["job"].get("country") or ""))
        result = list_document_generations(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Ingestion job not found.") from exc
    return _payload(result, request)


@admin_router.post("/ingestions/{job_id}/rollback/{target_ingestion_id}")
def ingestion_rollback(job_id: str, target_ingestion_id: str, request: Request) -> dict[str, Any]:
    principal = getattr(request.state, "admin_identity", {}) or {}
    if principal.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only a Super Admin can roll back knowledge.")
    require_admin_access(request, "knowledge", "manage")
    actor = str(principal.get("email") or principal.get("sub") or "admin")[:320]
    try:
        result = rollback_document_generation(job_id, target_ingestion_id, activated_by=actor)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_admin_audit_event(actor, "knowledge.generation_rolled_back", target_ingestion_id)
    return _payload(result, request)


@admin_router.post("/documents")
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    country: Annotated[str, Form()],
    language: Annotated[str, Form()],
    document_type: Annotated[str, Form()] = "other",
    access_scope: Annotated[str, Form()] = "country",
    document_version: Annotated[str, Form()] = "",
    effective_date: Annotated[str, Form()] = "",
    expiry_date: Annotated[str, Form()] = "",
    logical_document_id: Annotated[str, Form()] = "",
    document_owner: Annotated[str, Form()] = "",
    approval_reference: Annotated[str, Form()] = "",
    review_before_publish: Annotated[bool, Form()] = False,
) -> dict[str, Any]:
    normalized_country = country.upper().strip()
    normalized_language = language.lower().strip()
    require_admin_access(request, "knowledge", "stage", normalized_country)
    if normalized_country not in get_country_codes():
        raise HTTPException(status_code=400, detail="Unsupported country.")
    if normalized_language not in get_language_codes_for_country(normalized_country):
        raise HTTPException(status_code=400, detail="Unsupported language for country.")
    if document_type not in DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported document type.")
    if access_scope not in ACCESS_SCOPES:
        raise HTTPException(status_code=400, detail="Unsupported access scope.")
    principal = getattr(request.state, "admin_identity", {}) or {}
    if access_scope == "global" and principal.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only a Super Admin can upload global content.")
    if document_type == "policy" and access_scope != "country":
        raise HTTPException(
            status_code=400,
            detail="Company policies must be restricted to their selected market.",
        )
    if document_type == "office_directory" and access_scope != "global":
        raise HTTPException(
            status_code=400,
            detail="The approved office directory must use global availability.",
        )
    if settings.ADMIN_INGESTION_APPROVAL_METADATA_REQUIRED and (
        not document_owner.strip() or not approval_reference.strip()
    ):
        raise HTTPException(
            status_code=400,
            detail="Document owner and approval reference are required for controlled publication.",
        )

    filename = safe_filename(file.filename or "document")
    content = await file.read(settings.ADMIN_UPLOAD_MAX_BYTES + 1)
    try:
        validate_upload(filename, len(content))
        detected_format = detect_upload_format(filename, content)
        _preflight_uploaded_document(filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    content_hash = hashlib.sha256(content).hexdigest()
    accepted_by = str(principal.get("email") or principal.get("sub") or "admin")[:320]
    job_id = create_ingestion_job(
        filename=filename,
        country=normalized_country,
        language=normalized_language,
        document_type=document_type,
        access_scope=access_scope,
        version=document_version,
        effective_date=effective_date,
        expiry_date=expiry_date,
        content_hash=content_hash,
        accepted_by=accepted_by,
        logical_document_id=logical_document_id.strip(),
        document_owner=document_owner.strip(),
        approval_reference=approval_reference.strip(),
        review_before_publish=review_before_publish,
    )
    if settings.ADMIN_INGESTION_QUEUE_ENABLED:
        try:
            upload_uri = stage_ingestion_upload(
                job_id,
                filename,
                content,
                country=normalized_country,
                access_scope=access_scope,
            )
            enqueue_ingestion_job(
                job_id=job_id,
                upload_uri=upload_uri,
                filename=filename,
                country=normalized_country,
                language=normalized_language,
                document_type=document_type,
                access_scope=access_scope,
                version=document_version,
                effective_date=effective_date,
                expiry_date=expiry_date,
                content_hash=content_hash,
                accepted_by=accepted_by,
                logical_document_id=logical_document_id.strip(),
                document_owner=document_owner.strip(),
                approval_reference=approval_reference.strip(),
                review_before_publish=review_before_publish,
            )
        except (ValueError, BotoCoreError, ClientError) as exc:
            if "upload_uri" in locals():
                cleanup_staged_ingestion_upload(upload_uri)
            fail_ingestion_job(job_id, "Durable ingestion queueing failed.")
            raise HTTPException(status_code=503, detail="The document could not be queued safely.") from exc
        return _payload(
            {
                "jobId": job_id,
                "filename": filename,
                "detectedFormat": detected_format,
                "status": "queued",
                "message": "Document accepted and queued for durable processing.",
            },
            request,
        )
    upload_directory = Path(gettempdir()) / "askvera-ingestion" / job_id
    upload_directory.mkdir(parents=True, exist_ok=True)
    local_path = upload_directory / filename
    local_path.write_bytes(content)
    background_tasks.add_task(
        process_ingestion_job,
        job_id,
        str(local_path),
        filename=filename,
        country=normalized_country,
        language=normalized_language,
        document_type=document_type,
        access_scope=access_scope,
        version=document_version,
        effective_date=effective_date,
        expiry_date=expiry_date,
        accepted_by=accepted_by,
        logical_document_id=logical_document_id.strip(),
        document_owner=document_owner.strip(),
        approval_reference=approval_reference.strip(),
        review_before_publish=review_before_publish,
    )
    return _payload(
        {
            "jobId": job_id,
            "filename": filename,
            "detectedFormat": detected_format,
            "status": "queued",
            "message": "Document accepted. Extraction and indexing continue in the background.",
        },
        request,
    )


def _user_management_enabled() -> None:
    if not settings.ADMIN_USER_MANAGEMENT_ENABLED:
        raise HTTPException(status_code=404, detail="User management is not enabled.")


def _actor(request: Request) -> str:
    return str((getattr(request.state, "admin_identity", {}) or {}).get("sub") or "admin")


@admin_router.get("/users")
def admin_users_list(request: Request) -> dict[str, Any]:
    _user_management_enabled()
    require_admin_access(request, "users", "view")
    return _payload(list_admin_users(), request)


@admin_router.get("/audit-events")
def admin_audit_events(request: Request, limit: int = 100) -> dict[str, Any]:
    _user_management_enabled()
    require_admin_access(request, "audit", "view")
    return _payload(list_admin_audit_events(limit), request)


@admin_router.post("/users")
def admin_user_create(body: AdminUserCreateInput, request: Request) -> dict[str, Any]:
    _user_management_enabled()
    require_admin_access(request, "users", "manage")
    try:
        user = create_admin_user(
            email=body.email,
            role=body.role,
            scopes=[scope.model_dump() for scope in body.scopes],
            actor_sub=_actor(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(status_code=502, detail="Cognito could not create the administrator.") from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="The administrator profile could not be saved.") from exc
    return _payload(user, request)


@admin_router.patch("/users/{user_id}")
def admin_user_update(user_id: str, body: AdminUserUpdateInput, request: Request) -> dict[str, Any]:
    _user_management_enabled()
    require_admin_access(request, "users", "manage")
    try:
        user = update_admin_user(
            user_id,
            role=body.role,
            scopes=[scope.model_dump() for scope in body.scopes],
            actor_sub=_actor(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Administrator not found.") from exc
    return _payload(user, request)


def _set_user_enabled(user_id: str, request: Request, enabled: bool) -> dict[str, Any]:
    _user_management_enabled()
    require_admin_access(request, "users", "manage")
    try:
        return _payload(set_admin_user_enabled(user_id, enabled, _actor(request)), request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Administrator not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(status_code=502, detail="Cognito could not update access.") from exc


@admin_router.post("/users/{user_id}/disable")
def admin_user_disable(user_id: str, request: Request) -> dict[str, Any]:
    return _set_user_enabled(user_id, request, False)


@admin_router.post("/users/{user_id}/enable")
def admin_user_enable(user_id: str, request: Request) -> dict[str, Any]:
    return _set_user_enabled(user_id, request, True)


@admin_router.post("/users/{user_id}/resend-invite")
def admin_user_resend_invite(user_id: str, request: Request) -> dict[str, Any]:
    _user_management_enabled()
    require_admin_access(request, "users", "manage")
    try:
        return _payload(resend_admin_invite(user_id, _actor(request)), request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Administrator not found.") from exc
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(status_code=502, detail="Cognito could not resend the invitation.") from exc


@admin_router.post("/users/{user_id}/certify")
def admin_user_certify(user_id: str, request: Request) -> dict[str, Any]:
    _user_management_enabled()
    require_admin_access(request, "users", "manage")
    try:
        return _payload(certify_admin_access(user_id, _actor(request)), request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Administrator not found.") from exc


@admin_router.get("/support-routes")
def support_routes_list(request: Request) -> dict[str, Any]:
    principal = require_admin_access(request, "support", "view")
    markets = accessible_markets(principal, "support", "view")
    return _payload([route for route in list_support_routes() if route.get("country") in markets], request)


@admin_router.put("/support-routes/bulk")
def support_routes_bulk(body: SupportRouteBulkInput, request: Request) -> dict[str, Any]:
    actor = _actor(request)
    updated = []
    for country in sorted({value.upper().strip() for value in body.countries}):
        require_admin_access(request, "support", "manage", country)
        updated.append(upsert_support_route(country, department=body.route.department, email=body.route.email, fallback_department=body.route.fallback_department, fallback_email=body.route.fallback_email, enabled=body.route.enabled, actor_sub=actor))
    return _payload(updated, request)


@admin_router.put("/support-routes/{country}")
def support_route_update(country: str, body: SupportRouteInput, request: Request) -> dict[str, Any]:
    require_admin_access(request, "support", "manage", country)
    try:
        return _payload(
            upsert_support_route(
                country,
                department=body.department,
                email=body.email,
                fallback_department=body.fallback_department,
                fallback_email=body.fallback_email,
                enabled=body.enabled,
                actor_sub=_actor(request),
            ),
            request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@admin_router.post("/support-routes/{country}/test")
def support_route_test(country: str, request: Request) -> dict[str, Any]:
    require_admin_access(request, "support", "manage", country)
    try:
        result = send_support_route_test(country)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    record_admin_audit_event(_actor(request), "support_route.test_submitted", country.upper())
    return _payload(result, request)


@admin_router.get("/support-routes/{country}/history")
def support_route_history_view(country: str, request: Request) -> dict[str, Any]:
    require_admin_access(request, "support", "view", country)
    return _payload(support_route_history(country), request)


def _widget_management_enabled() -> None:
    if not settings.WIDGET_CONFIG_ADMIN_ENABLED:
        raise HTTPException(status_code=404, detail="Widget configuration is not enabled.")


def _require_widget_markets(request: Request, permission: str, markets: list[str]) -> None:
    if not markets:
        raise HTTPException(status_code=400, detail="A widget instance must have at least one market.")
    for market in markets:
        require_admin_access(request, "widget", permission, market)


def _widget_accessible_markets(principal: dict[str, Any], permission: str) -> set[str]:
    if principal.get("role") == "super_admin":
        return get_widget_country_codes()
    return accessible_markets(principal, "widget", permission)


@admin_router.post("/widget-assets")
async def widget_asset_upload(
    request: Request,
    file: Annotated[UploadFile, File(...)],
) -> dict[str, Any]:
    """Store a validated public widget logo without proxying arbitrary files."""
    _widget_management_enabled()
    principal = getattr(request.state, "admin_identity", {}) or {}
    if not accessible_markets(principal, "widget", "manage"):
        raise HTTPException(status_code=403, detail="You do not have permission to manage widget assets.")
    if not settings.WIDGET_ASSET_BUCKET or not settings.WIDGET_ASSET_PUBLIC_BASE_URL:
        raise HTTPException(status_code=503, detail="Widget asset storage is not configured.")

    content = await file.read(settings.WIDGET_LOGO_MAX_BYTES + 1)
    await file.close()
    if len(content) > settings.WIDGET_LOGO_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Logo must be 1 MB or smaller.")
    signatures = {
        b"\x89PNG\r\n\x1a\n": ("png", "image/png"),
        b"\xff\xd8\xff": ("jpg", "image/jpeg"),
        b"RIFF": ("webp", "image/webp"),
    }
    detected = next((value for signature, value in signatures.items() if content.startswith(signature)), None)
    if detected and detected[0] == "webp" and content[8:12] != b"WEBP":
        detected = None
    if not detected:
        raise HTTPException(status_code=400, detail="Upload a PNG, JPEG or WebP image.")

    extension, content_type = detected
    key = f"widget/assets/logos/{uuid4().hex}.{extension}"
    try:
        get_aws_clients().s3.put_object(
            Bucket=settings.WIDGET_ASSET_BUCKET,
            Key=key,
            Body=content,
            ContentType=content_type,
            CacheControl="public,max-age=31536000,immutable",
        )
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(status_code=502, detail="The logo could not be stored.") from exc
    return _payload(
        {"url": f"{settings.WIDGET_ASSET_PUBLIC_BASE_URL.rstrip('/')}/{key}"},
        request,
    )


@admin_router.get("/widget-configs")
def widget_configs_list(request: Request) -> dict[str, Any]:
    _widget_management_enabled()
    principal = getattr(request.state, "admin_identity", {}) or {}
    markets = _widget_accessible_markets(principal, "view")
    if not markets:
        raise HTTPException(status_code=403, detail="You do not have access to widget configuration.")
    configs = [
        config
        for config in list_widget_configs()
        if set(config.get("markets") or []).issubset(markets)
    ]
    return _payload(configs, request)


@admin_router.post("/widget-configs")
def widget_config_create(body: WidgetConfigInput, request: Request) -> dict[str, Any]:
    _widget_management_enabled()
    _require_widget_markets(request, "manage", body.markets)
    try:
        result = create_widget_config(body.model_dump(), _actor(request))
        widget_registry_service.invalidate()
        return _payload(result, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@admin_router.patch("/widget-configs/{widget_id}")
def widget_config_update(widget_id: str, body: WidgetConfigInput, request: Request) -> dict[str, Any]:
    _widget_management_enabled()
    try:
        current = get_widget_config(widget_id)
        if not current:
            raise KeyError(widget_id)
        _require_widget_markets(request, "manage", current.get("markets") or [])
        _require_widget_markets(request, "manage", body.markets)
        result = update_widget_config(widget_id, body.model_dump(), _actor(request))
        widget_registry_service.invalidate()
        return _payload(result, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Widget instance not found.") from exc


@admin_router.put("/widget-configs/{widget_id}/draft")
def widget_config_draft(widget_id: str, body: WidgetConfigInput, request: Request) -> dict[str, Any]:
    _widget_management_enabled()
    try:
        current = get_widget_config(widget_id)
        if not current:
            raise KeyError(widget_id)
        _require_widget_markets(request, "manage", current.get("markets") or [])
        _require_widget_markets(request, "manage", body.markets)
        return _payload(stage_widget_config(widget_id, body.model_dump(), _actor(request)), request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Widget instance not found.") from exc


@admin_router.post("/widget-configs/{widget_id}/publish")
def widget_config_publish(widget_id: str, request: Request) -> dict[str, Any]:
    _widget_management_enabled()
    try:
        current = get_widget_config(widget_id)
        if not current:
            raise KeyError(widget_id)
        _require_widget_markets(request, "manage", current.get("markets") or [])
        result = publish_widget_config(widget_id, _actor(request))
        widget_registry_service.invalidate()
        return _payload(result, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Widget instance not found.") from exc


@admin_router.post("/widget-configs/{widget_id}/rotate-key")
def widget_config_rotate(widget_id: str, request: Request) -> dict[str, Any]:
    _widget_management_enabled()
    try:
        current = get_widget_config(widget_id)
        if not current:
            raise KeyError(widget_id)
        _require_widget_markets(request, "manage", current.get("markets") or [])
        result = rotate_widget_key(widget_id, _actor(request))
        widget_registry_service.invalidate()
        return _payload(result, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Widget instance not found.") from exc


@admin_router.post("/widget-configs/{widget_id}/disable")
def widget_config_disable(widget_id: str, request: Request) -> dict[str, Any]:
    _widget_management_enabled()
    try:
        current = get_widget_config(widget_id)
        if not current:
            raise KeyError(widget_id)
        _require_widget_markets(request, "manage", current.get("markets") or [])
        result = disable_widget_config(widget_id, _actor(request))
        widget_registry_service.invalidate()
        return _payload(result, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Widget instance not found.") from exc
