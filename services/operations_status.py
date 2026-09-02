"""Read-only operational status used by the administrator command center."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import text

from app.metrics.collector import metrics_collector
from config import settings
from services import cache as cache_service
from services.db import get_engine
from services.knowledge_ingestion import list_ingestion_jobs


def _check_database() -> dict[str, str]:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "healthy", "detail": "PostgreSQL accepted a health query."}
    except Exception:
        return {"status": "unhealthy", "detail": "PostgreSQL did not answer the health query."}


def _check_cache() -> dict[str, str]:
    try:
        status = cache_service.cache_health()
        return {"status": "healthy" if status == "healthy" else status, "detail": "Shared response cache is reachable."}
    except Exception:
        return {"status": "unhealthy", "detail": "Shared response cache is not reachable."}


def _low_coverage_documents(limit: int = 50) -> list[dict[str, Any]]:
    """Return active documents whose indexed chunk count looks suspiciously
    low - a fleet-wide safety net that no ingestion coverage check
    previously existed for. This does not replace validating a specific
    document at upload time; it only flags what's already recorded in
    knowledge_documents.section_count for admin follow-up.
    """
    try:
        with get_engine().connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT filename, country, document_type, section_count, logical_document_id
                    FROM knowledge_documents
                    WHERE status = 'active' AND section_count < :threshold
                    ORDER BY section_count ASC, filename ASC
                    LIMIT :limit
                    """
                ),
                {"threshold": settings.ADMIN_INGESTION_LOW_COVERAGE_THRESHOLD, "limit": limit},
            ).mappings()
            return [dict(row) for row in rows]
    except Exception:
        return []


def operations_status() -> dict[str, Any]:
    """Return safe health, version and knowledge synchronization signals."""
    jobs = list_ingestion_jobs(200)
    active_statuses = {"queued", "processing", "extracting", "indexing", "retryable", "staging", "ready_for_review"}
    failed_statuses = {"failed", "error", "deletion_failed"}
    active = [job for job in jobs if str(job.get("status") or "") in active_statuses]
    failed = [job for job in jobs if str(job.get("status") or "") in failed_statuses]
    latest = max((str(job.get("updated_at") or "") for job in jobs), default="")
    expiry_cutoff = date.today() + timedelta(days=30)
    expiring = []
    for job in jobs:
        raw_expiry = str(job.get("expiry_date") or "")
        try:
            expiry = date.fromisoformat(raw_expiry) if raw_expiry else None
        except ValueError:
            expiry = None
        if expiry and expiry <= expiry_cutoff and str(job.get("status") or "") not in {"deleted", "superseded"}:
            expiring.append(job)
    low_coverage = _low_coverage_documents()
    health = metrics_collector.health_summary()
    services = {
        "api": {"status": health.status, "detail": "Request pipeline and validators are reporting."},
        "database": _check_database(),
        "cache": _check_cache(),
        "retrieval": {
            "status": "configured" if settings.OPENSEARCH_INDEX else "missing_config",
            "detail": "OpenSearch retrieval index is configured." if settings.OPENSEARCH_INDEX else "OpenSearch retrieval index is not configured.",
        },
        "ingestion": {
            "status": "degraded" if failed else "healthy",
            "detail": f"{len(failed)} failed and {len(active)} active document jobs.",
        },
    }
    return {
        "status": "degraded" if any(item["status"] in {"unhealthy", "degraded", "missing_config"} for item in services.values()) else "healthy",
        "checked_at": datetime.now(UTC).isoformat(),
        "services": services,
        "knowledge_sync": {
            "status": "attention" if failed else "syncing" if active else "current",
            "active_jobs": len(active),
            "failed_jobs": len(failed),
            "last_change_at": latest,
            "expiring_documents": len(expiring),
            "low_coverage_documents": len(low_coverage),
        },
        "assigned_actions": [
            {
                "label": str(job.get("filename") or "Document job"),
                "owner": str(job.get("document_owner") or "Unassigned"),
                "reason": str(job.get("error_message") or "Processing failed"),
            }
            for job in failed[:5]
        ] + [
            {
                "label": str(job.get("filename") or "Document"),
                "owner": str(job.get("document_owner") or "Unassigned"),
                "reason": f"Expires {job.get('expiry_date')}",
            }
            for job in expiring[:5]
        ] + [
            {
                "label": str(doc.get("filename") or "Document"),
                "owner": "Unassigned",
                "reason": f"Only {doc.get('section_count')} chunk(s) indexed - check extraction coverage",
            }
            for doc in low_coverage[:5]
        ],
        "versions": {
            "application": settings.APP_VERSION,
            "knowledge": settings.KB_VERSION,
            "retrieval_pipeline": settings.RETRIEVAL_PIPELINE_VERSION,
            "response_pipeline": settings.RESPONSE_PIPELINE_VERSION,
            "prompt": settings.PROMPT_VERSION,
        },
        "metrics": {
            "cache_hit_ratio": health.cache_hit_ratio,
            "retrieval_failure_rate": health.retrieval_failure_rate,
            "validation_failures": health.validation_failures,
            "audit_queue_depth": health.audit_queue_depth,
        },
    }
