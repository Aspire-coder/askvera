"""Safe runtime control for current and shadow retrieval profiles."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from typing import Any, Literal

from sqlalchemy import text

from config import settings
from services.db import get_engine
from utils.logging import get_logger

LOGGER = get_logger("services.retrieval_runtime")
CONTROL_ID = "primary"
CONTROL_CACHE_SECONDS = 5.0
CONTROL_LOCK_ID = 8_922_026_073_000_025
RetrievalMode = Literal["current", "shadow"]


@dataclass(frozen=True)
class RetrievalRuntimeControl:
    """The only runtime choices currently allowed by the Operations portal."""

    mode: RetrievalMode
    sample_rate: float
    source: str
    updated_by: str = ""
    reason: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_cached_control: RetrievalRuntimeControl | None = None
_cached_at = 0.0
_cache_lock = Lock()


def _validated_rate(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def _settings_fallback() -> RetrievalRuntimeControl:
    mode: RetrievalMode = "shadow" if settings.RETRIEVAL_SHADOW_ENABLED else "current"
    rate = _validated_rate(settings.RETRIEVAL_SHADOW_SAMPLE_RATE if mode == "shadow" else 0.0)
    return RetrievalRuntimeControl(mode=mode, sample_rate=rate, source="deployment_config")


def _row_to_control(row: Any) -> RetrievalRuntimeControl:
    updated_at = row.get("updated_at")
    if isinstance(updated_at, datetime):
        updated_at = updated_at.astimezone(timezone.utc).isoformat()
    return RetrievalRuntimeControl(
        mode="shadow" if row.get("mode") == "shadow" else "current",
        sample_rate=_validated_rate(row.get("sample_rate") or 0.0),
        source="operations_portal",
        updated_by=str(row.get("updated_by") or ""),
        reason=str(row.get("reason") or ""),
        updated_at=str(updated_at or ""),
    )


def clear_retrieval_runtime_cache() -> None:
    """Clear the short process cache after an administrator update."""
    global _cached_control, _cached_at
    with _cache_lock:
        _cached_control = None
        _cached_at = 0.0


def get_retrieval_runtime_control(*, force: bool = False) -> RetrievalRuntimeControl:
    """Return runtime control, falling back safely if storage is unavailable."""
    global _cached_control, _cached_at
    now = monotonic()
    with _cache_lock:
        if not force and _cached_control and now - _cached_at < CONTROL_CACHE_SECONDS:
            return _cached_control

    try:
        with get_engine().connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT mode, sample_rate, updated_by, reason, updated_at
                    FROM retrieval_runtime_control
                    WHERE control_id = :control_id
                    """
                ),
                {"control_id": CONTROL_ID},
            ).mappings().first()
        control = _row_to_control(row) if row else _settings_fallback()
    except Exception:  # noqa: BLE001 - runtime control must never interrupt retrieval.
        LOGGER.exception("retrieval_runtime_control_read_failed")
        control = _settings_fallback()

    with _cache_lock:
        _cached_control = control
        _cached_at = monotonic()
    return control


def set_retrieval_runtime_control(
    mode: RetrievalMode,
    sample_rate: float,
    *,
    actor: str,
    reason: str,
) -> RetrievalRuntimeControl:
    """Persist a reviewed Current or Shadow selection under a transaction lock."""
    if mode not in {"current", "shadow"}:
        raise ValueError("Unsupported retrieval mode.")
    normalized_rate = _validated_rate(sample_rate if mode == "shadow" else 0.0)
    if mode == "shadow" and normalized_rate <= 0.0:
        raise ValueError("Shadow mode requires a positive sample rate.")
    with get_engine().begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": CONTROL_LOCK_ID})
        connection.execute(
            text(
                """
                INSERT INTO retrieval_runtime_control
                    (control_id, mode, sample_rate, updated_by, reason, updated_at)
                VALUES
                    (:control_id, :mode, :sample_rate, :updated_by, :reason, now())
                ON CONFLICT (control_id) DO UPDATE SET
                    mode = EXCLUDED.mode,
                    sample_rate = EXCLUDED.sample_rate,
                    updated_by = EXCLUDED.updated_by,
                    reason = EXCLUDED.reason,
                    updated_at = now()
                """
            ),
            {
                "control_id": CONTROL_ID,
                "mode": mode,
                "sample_rate": normalized_rate,
                "updated_by": actor[:320],
                "reason": reason[:500],
            },
        )
    clear_retrieval_runtime_cache()
    return get_retrieval_runtime_control(force=True)


def retrieval_profile_status(*, check_index: bool = True) -> dict[str, Any]:
    """Describe serving, shadow and parsing state without exposing credentials."""
    control = get_retrieval_runtime_control()
    primary_index = str(settings.OPENSEARCH_INDEX or "")
    candidate_index = str(settings.OPENSEARCH_VNEXT_INDEX or "")
    configured = settings.RETRIEVAL_VNEXT_PROVIDER == "opensearch_section" and bool(candidate_index)
    isolated = bool(candidate_index) and candidate_index != primary_index
    index_exists: bool | None = None
    readiness_error = ""
    if check_index and configured and isolated:
        try:
            from app.retrieval.opensearch_sections import opensearch_index_exists

            index_exists = opensearch_index_exists(candidate_index)
            if not index_exists:
                readiness_error = "The candidate OpenSearch index does not exist."
        except Exception:  # noqa: BLE001 - status must remain readable during dependency failure.
            LOGGER.exception("retrieval_candidate_readiness_failed")
            readiness_error = "Candidate index readiness could not be verified."
    elif not configured:
        readiness_error = "The candidate provider and index are not configured."
    elif not isolated:
        readiness_error = "The candidate index must be separate from the current index."

    ready = configured and isolated and index_exists is True
    return {
        "control": control.to_dict(),
        "customer_serving_profile": "current",
        "shadow_changes_customer_answers": False,
        "primary": {
            "provider": settings.RETRIEVAL_PROVIDER,
            "index": primary_index,
            "pipeline_version": settings.RETRIEVAL_PIPELINE_VERSION,
            "chunk_profile": settings.ADMIN_INGESTION_CHUNK_PROFILE,
        },
        "candidate": {
            "provider": settings.RETRIEVAL_VNEXT_PROVIDER,
            "index": candidate_index,
            "pipeline_version": settings.RETRIEVAL_VNEXT_PIPELINE_VERSION,
            "chunk_profile": "vnext",
            "configured": configured,
            "isolated": isolated,
            "index_exists": index_exists,
            "ready": ready,
            "readiness_error": readiness_error,
            "reranking_enabled": bool(settings.RETRIEVAL_VNEXT_RERANK_ENABLED),
        },
        "parsing": {
            "runtime_switch_reprocesses_documents": False,
            "current_chunk_profile": settings.ADMIN_INGESTION_CHUNK_PROFILE,
            "candidate_chunk_profile": "vnext",
        },
    }
