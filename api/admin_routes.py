"""Authenticated operational APIs for the AskVera admin portal."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tempfile import gettempdir
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile

from app.operations import pipeline_trace_store
from config import settings
from services.admin_auth import require_admin_identity
from services.analytics import analytics_overview, interaction_list
from services.knowledge_ingestion import (
    ACCESS_SCOPES,
    DOCUMENT_TYPES,
    create_ingestion_job,
    list_ingestion_jobs,
    process_ingestion_job,
    safe_filename,
    validate_upload,
)
from services.market_config import get_countries, get_country_codes, get_language_codes_for_country

admin_router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin_identity)])


def _payload(data: Any, request: Request) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "correlationId": str(getattr(request.state, "correlation_id", "admin")),
    }


@admin_router.get("/config")
def admin_config(request: Request) -> dict[str, Any]:
    return _payload(
        {
            "countries": get_countries(),
            "documentTypes": sorted(DOCUMENT_TYPES),
            "accessScopes": sorted(ACCESS_SCOPES),
            "maxUploadBytes": settings.ADMIN_UPLOAD_MAX_BYTES,
        },
        request,
    )


@admin_router.get("/analytics/overview")
def overview(
    request: Request,
    days: int = 30,
    country: str = "",
    language: str = "",
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    try:
        result = analytics_overview(
            days=days,
            country=country,
            language=language,
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
    feedback: str = "all",
    limit: int = 100,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    if feedback not in {"all", "helpful", "not_helpful"}:
        raise HTTPException(status_code=400, detail="Unsupported feedback filter.")
    try:
        result = interaction_list(
            days=days,
            country=country,
            language=language,
            feedback=feedback,
            limit=limit,
            start=start,
            end=end,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _payload(result, request)


@admin_router.get("/traces")
def traces(request: Request, limit: int = 20) -> dict[str, Any]:
    return _payload(pipeline_trace_store.latest(limit), request)


@admin_router.get("/traces/{correlation_id}")
def trace_detail(correlation_id: str, request: Request) -> dict[str, Any]:
    trace = pipeline_trace_store.get(correlation_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found in the recent in-process window.")
    return _payload(trace, request)


@admin_router.get("/ingestions")
def ingestions(request: Request, limit: int = 50) -> dict[str, Any]:
    return _payload(list_ingestion_jobs(limit), request)


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
) -> dict[str, Any]:
    normalized_country = country.upper().strip()
    normalized_language = language.lower().strip()
    if normalized_country not in get_country_codes():
        raise HTTPException(status_code=400, detail="Unsupported country.")
    if normalized_language not in get_language_codes_for_country(normalized_country):
        raise HTTPException(status_code=400, detail="Unsupported language for country.")
    if document_type not in DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported document type.")
    if access_scope not in ACCESS_SCOPES:
        raise HTTPException(status_code=400, detail="Unsupported access scope.")

    filename = safe_filename(file.filename or "document")
    content = await file.read(settings.ADMIN_UPLOAD_MAX_BYTES + 1)
    try:
        validate_upload(filename, len(content))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_id = create_ingestion_job(
        filename=filename,
        country=normalized_country,
        language=normalized_language,
        document_type=document_type,
        access_scope=access_scope,
        version=document_version,
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
    )
    return _payload(
        {
            "jobId": job_id,
            "filename": filename,
            "status": "queued",
            "message": "Document accepted. Extraction and indexing continue in the background.",
        },
        request,
    )
