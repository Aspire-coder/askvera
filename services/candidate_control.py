"""Runtime control for the admin-portal "current vs experimental" chat toggle.

Mirrors the retrieval_runtime_control pattern (see
docs/RETRIEVAL_PROFILE_CONTROL.md): the admin portal writes a singleton row,
AIOrchestrator.handle_chat reads it fresh on every request (through a short
in-process cache), and any storage failure or missing row fails open to
today's production behavior - it never blocks or errors a chat request.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from sqlalchemy import text

from config import settings
from services.db import get_engine
from utils.logging import get_logger

LOGGER = get_logger("services.candidate_control")

_CACHE_TTL_SECONDS = 5.0
_cached_flags: "CandidateFlags | None" = None
_cache_expires_at = 0.0


@dataclass(frozen=True)
class CandidateFlags:
    """The three independent experimental chat behaviors."""

    narrowing_fallback: bool = False
    in_voice_guardrail: bool = False
    wider_typo_tolerance: bool = False


_DEFAULT_FLAGS = CandidateFlags()


def get_candidate_flags() -> CandidateFlags:
    """Return the active candidate flags, cached for a few seconds.

    Fails open to all-False (today's production behavior) on any database
    error or missing row - this must never raise into a live chat request.
    Also gated behind the settings.CANDIDATE_MODE_LOOKUP_ENABLED master
    switch (off by default): until an environment explicitly turns this
    feature on, this never touches the database at all, so every existing
    chat-orchestration code path - including unit tests that call
    AIOrchestrator.handle_chat directly with no database available - stays
    exactly as fast and DB-free as before this feature existed.
    """
    if not settings.CANDIDATE_MODE_LOOKUP_ENABLED:
        return _DEFAULT_FLAGS

    global _cached_flags, _cache_expires_at
    now = monotonic()
    if _cached_flags is not None and now < _cache_expires_at:
        return _cached_flags

    flags = _DEFAULT_FLAGS
    try:
        with get_engine().connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT narrowing_fallback_enabled, in_voice_guardrail_enabled,
                           wider_typo_tolerance_enabled
                    FROM chat_candidate_control
                    WHERE control_id = 'primary'
                    """
                )
            ).mappings().first()
        if row is not None:
            flags = CandidateFlags(
                narrowing_fallback=bool(row["narrowing_fallback_enabled"]),
                in_voice_guardrail=bool(row["in_voice_guardrail_enabled"]),
                wider_typo_tolerance=bool(row["wider_typo_tolerance_enabled"]),
            )
    except Exception:  # noqa: BLE001 - must never break a live chat request, see module docstring
        LOGGER.warning("candidate_control_read_failed_fail_open", exc_info=True)
        flags = _DEFAULT_FLAGS

    _cached_flags = flags
    _cache_expires_at = now + _CACHE_TTL_SECONDS
    return flags


def set_candidate_flags(flags: CandidateFlags, updated_by: str, reason: str) -> CandidateFlags:
    """Upsert the singleton control row and invalidate the local cache."""
    global _cached_flags, _cache_expires_at
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO chat_candidate_control (
                    control_id, narrowing_fallback_enabled, in_voice_guardrail_enabled,
                    wider_typo_tolerance_enabled, updated_by, reason, updated_at
                )
                VALUES (
                    'primary', :narrowing_fallback, :in_voice_guardrail,
                    :wider_typo_tolerance, :updated_by, :reason, now()
                )
                ON CONFLICT (control_id) DO UPDATE SET
                    narrowing_fallback_enabled = EXCLUDED.narrowing_fallback_enabled,
                    in_voice_guardrail_enabled = EXCLUDED.in_voice_guardrail_enabled,
                    wider_typo_tolerance_enabled = EXCLUDED.wider_typo_tolerance_enabled,
                    updated_by = EXCLUDED.updated_by,
                    reason = EXCLUDED.reason,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {
                "narrowing_fallback": flags.narrowing_fallback,
                "in_voice_guardrail": flags.in_voice_guardrail,
                "wider_typo_tolerance": flags.wider_typo_tolerance,
                "updated_by": updated_by,
                "reason": reason,
            },
        )
    _cached_flags = flags
    _cache_expires_at = monotonic() + _CACHE_TTL_SECONDS
    return flags
