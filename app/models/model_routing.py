"""Deterministic, language-neutral generation model routing."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from app.prompts import PromptPackage
from app.retrieval import RetrievalResult
from config import settings

ALLOWED_ROUTING_MODES = {"off", "shadow", "live"}
QUESTION_MARKS = {"?", "\u061f", "\uff1f"}
NUMERIC_SYMBOLS = {"%", "\u2030"}


@dataclass(frozen=True)
class ModelRouteDecision:
    """A content-free routing decision suitable for logs and metrics."""

    mode: str
    target: str
    target_model_id: str
    reasons: tuple[str, ...]

    @property
    def live(self) -> bool:
        return self.mode == "live"

    @property
    def would_use_fast_model(self) -> bool:
        return self.target == "fast"

    def to_metadata(self) -> dict[str, object]:
        return {
            "model_route_mode": self.mode,
            "model_route_target": self.target,
            "model_route_target_model": self.target_model_id,
            "model_route_reasons": list(self.reasons),
            "model_route_live": self.live,
            "model_route_would_use_fast": self.would_use_fast_model,
            "model_route_version": settings.MODEL_ROUTING_VERSION,
        }


def decide_model_route(prompt: PromptPackage, retrieval_result: RetrievalResult) -> ModelRouteDecision:
    """Select a fast model only when structural evidence signals are low risk."""
    mode = str(settings.MODEL_ROUTING_MODE or "off").strip().lower()
    if mode not in ALLOWED_ROUTING_MODES:
        mode = "off"

    complex_model = str(settings.BEDROCK_COMPLEX_MODEL_ID or settings.BEDROCK_MODEL_ARN).strip()
    fast_model = str(settings.BEDROCK_FAST_MODEL_ID or "").strip()
    if mode == "off" or not fast_model or not complex_model:
        return ModelRouteDecision(
            mode=mode,
            target="default",
            target_model_id=str(settings.BEDROCK_MODEL_ARN).strip(),
            reasons=("routing_disabled",),
        )

    reasons = _complexity_reasons(prompt, retrieval_result)
    if reasons:
        return ModelRouteDecision(
            mode=mode,
            target="complex",
            target_model_id=complex_model,
            reasons=tuple(reasons),
        )
    return ModelRouteDecision(
        mode=mode,
        target="fast",
        target_model_id=fast_model,
        reasons=("low_risk_evidence",),
    )


def _complexity_reasons(prompt: PromptPackage, retrieval_result: RetrievalResult) -> list[str]:
    reasons: list[str] = []
    question = str(prompt.metadata.get("user_question") or prompt.user_prompt or "").strip()

    if bool(prompt.metadata.get("has_conversation")):
        reasons.append("conversation_context")
    if float(retrieval_result.confidence or 0.0) < float(settings.MODEL_ROUTING_FAST_MIN_CONFIDENCE):
        reasons.append("lower_confidence")
    if len(question) > int(settings.MODEL_ROUTING_FAST_MAX_QUESTION_CHARS):
        reasons.append("long_question")
    if sum(question.count(mark) for mark in QUESTION_MARKS) > 1:
        reasons.append("multi_part_question")
    if _contains_numeric_or_currency_symbol(question):
        reasons.append("explicit_numeric_claim")

    distinct_sources = {
        str(document.source or document.title or document.id).strip()
        for document in retrieval_result.documents
        if str(document.source or document.title or document.id).strip()
    }
    if len(distinct_sources) > int(settings.MODEL_ROUTING_FAST_MAX_DISTINCT_SOURCES):
        reasons.append("multiple_documents")

    distinct_countries = {
        str(document.country or "").strip().upper()
        for document in retrieval_result.documents
        if str(document.country or "").strip()
    }
    if len(distinct_countries) > 1:
        reasons.append("cross_market_evidence")

    if any(_document_has_complex_structure(document.metadata) for document in retrieval_result.documents):
        reasons.append("structured_evidence")

    return reasons


def _contains_numeric_or_currency_symbol(text: str) -> bool:
    for character in text:
        if character.isdigit() or character in NUMERIC_SYMBOLS:
            return True
        if unicodedata.category(character) == "Sc":
            return True
    return False


def _document_has_complex_structure(metadata: dict[str, object]) -> bool:
    return any(
        bool(metadata.get(key))
        for key in (
            "is_table",
            "table_row",
            "requires_calculation",
            "conflicting_version",
        )
    )
