"""Shared scoring utilities for section-based retrieval.

These functions score and rank policy-section candidates by title/content
relevance. They are used by the live OpenSearch retrieval path
(`app/retrieval/opensearch_sections.py`).
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from config import settings
from utils.logging import get_logger

from .models import RetrievedDocument

LOGGER = get_logger("app.retrieval.section_index")

_SCORING_RULES_MAX_TERMS = 32
_SCORING_RULES_MAX_TERM_CHARS = 40
_SCORING_RULES_MAX_PHRASES = 32
_SCORING_RULES_MAX_PHRASE_CHARS = 120


def _bounded_lower_strings(value: Any, *, limit: int, max_chars: int) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    result: list[str] = []
    for item in value[:limit]:
        if not isinstance(item, str):
            continue
        cleaned = " ".join(item.split()).strip().lower()
        if cleaned and len(cleaned) <= max_chars and cleaned not in result:
            result.append(cleaned)
    return tuple(result)


def _valid_evidence_rule(payload: Any) -> dict[str, Any] | None:
    """Validate one {intent terms -> evidence phrases -> score} rule."""
    if not isinstance(payload, dict):
        return None
    evidence = _bounded_lower_strings(
        payload.get("evidence_any_phrases"), limit=_SCORING_RULES_MAX_PHRASES, max_chars=_SCORING_RULES_MAX_PHRASE_CHARS
    )
    score = payload.get("score")
    if not evidence or not isinstance(score, (int, float)) or isinstance(score, bool):
        return None
    return {
        "intent_any": frozenset(
            _bounded_lower_strings(payload.get("intent_any_terms"), limit=_SCORING_RULES_MAX_TERMS, max_chars=_SCORING_RULES_MAX_TERM_CHARS)
        ),
        "intent_all": frozenset(
            _bounded_lower_strings(payload.get("intent_all_terms"), limit=_SCORING_RULES_MAX_TERMS, max_chars=_SCORING_RULES_MAX_TERM_CHARS)
        ),
        "evidence": evidence,
        "score": float(score),
    }


@lru_cache(maxsize=1)
def _load_scoring_rules(path: str) -> dict[str, Any]:
    """Load optional evidence-phrase scoring rules without failing retrieval closed."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        LOGGER.warning("retrieval_scoring_rules_unavailable", path=path, error=str(exc))
        return {}
    if not isinstance(payload, dict):
        return {}

    rules: dict[str, Any] = {}
    purchase_channel = _valid_evidence_rule(payload.get("purchase_channel"))
    if purchase_channel:
        rules["purchase_channel"] = purchase_channel

    return_policy_raw = payload.get("return_policy")
    if isinstance(return_policy_raw, dict):
        intent_any = _bounded_lower_strings(
            return_policy_raw.get("intent_any_terms"), limit=_SCORING_RULES_MAX_TERMS, max_chars=_SCORING_RULES_MAX_TERM_CHARS
        )
        buyback_window = _valid_evidence_rule(return_policy_raw.get("buyback_window"))
        general = _valid_evidence_rule(return_policy_raw.get("general"))
        if intent_any and buyback_window and general:
            rules["return_policy"] = {
                "intent_any": frozenset(intent_any),
                "buyback_window": buyback_window,
                "general": general,
            }
    return rules


def _intent_matches(message_terms: set[str], rule: dict[str, Any]) -> bool:
    """A rule fires when the message contains any listed term, or all terms in the combo."""
    intent_any: frozenset[str] = rule.get("intent_any", frozenset())
    intent_all: frozenset[str] = rule.get("intent_all", frozenset())
    return bool(message_terms & intent_any) or bool(intent_all and intent_all <= message_terms)


def _evidence_score(evidence_text: str, rule: dict[str, Any]) -> float:
    return rule["score"] if any(phrase in evidence_text for phrase in rule["evidence"]) else 0.0


def _tokens(text_value: str) -> list[str]:
    """Return Unicode word tokens in source order without language-specific rules."""
    tokens: list[str] = []
    normalized = unicodedata.normalize("NFKC", text_value or "").casefold()
    for token in re.findall(r"[^\W_]+", normalized, flags=re.UNICODE):
        if len(token) <= 1:
            continue
        if token not in tokens:
            tokens.append(token)
    return tokens


def _ts_query(tokens: list[str]) -> str:
    """Build a safe broad Postgres tsquery from Unicode-normalized tokens."""
    cleaned = [token.replace("'", "") for token in tokens if token and "'" not in token]
    return " | ".join(f"{token}:*" for token in cleaned) or "policy"


def _token_regex(tokens: list[str]) -> str:
    """Build a broad regex fallback for candidate collection."""
    cleaned = [re.escape(token) for token in tokens if token]
    if not cleaned:
        return r"policy"
    return r"\m(?:" + "|".join(cleaned) + r")\M"


def _key_phrases(message: str) -> list[str]:
    """Extract short phrases worth matching exactly."""
    ordered = _tokens(message)
    phrases: list[str] = []
    for size in (4, 3, 2):
        for index in range(0, max(len(ordered) - size + 1, 0)):
            phrase = " ".join(ordered[index : index + size])
            if phrase not in phrases:
                phrases.append(phrase)
    return phrases[:12]


def _normalize_text(value: str) -> str:
    """Normalize whitespace and case while retaining every language's letters."""
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return " ".join(normalized.split())


def _character_ngrams(value: str, size: int = 3) -> set[str]:
    """Provide language-neutral lexical matching when word boundaries vary."""
    compact = "".join(character for character in _normalize_text(value) if character.isalnum())
    if len(compact) < size:
        return {compact} if compact else set()
    return {compact[index : index + size] for index in range(len(compact) - size + 1)}


def _character_overlap(left: str, right: str) -> float:
    """Measure how much of a shorter named phrase appears in the other text."""
    left_ngrams = _character_ngrams(left)
    right_ngrams = _character_ngrams(right)
    if not left_ngrams or not right_ngrams:
        return 0.0
    return len(left_ngrams & right_ngrams) / min(len(left_ngrams), len(right_ngrams))


def _exact_topic_score(message: str, title: str, content: str) -> float:
    """Reward a document's own named topic without policy-specific heuristics."""
    normalized_message = _normalize_text(message)
    normalized_title = _normalize_text(title)
    normalized_content = _normalize_text(content[:1800])
    score = 0.0

    # A section title is content-managed data. If it appears in the question, it is
    # the strongest generic evidence that this section is about the asked topic.
    if normalized_title and len(normalized_title) >= 3 and normalized_title in normalized_message:
        score += 1.6

    for phrase in _key_phrases(message):
        if phrase in normalized_title:
            score = max(score, 1.5)
        elif phrase in normalized_content:
            score = max(score, 0.65)

    for token in _tokens(message):
        if len(token) < 4 or not any(character.isdigit() for character in token):
            continue
        if token in normalized_title:
            score = max(score, 1.8)
        elif token in normalized_content:
            score = max(score, 0.9)

    return score


def _governing_requirement_score(message: str, title: str, content: str) -> float:
    """Prefer a governing qualification clause over nearby rank mentions."""
    if not settings.OPENSEARCH_RETRIEVAL_HARDENING_ENABLED:
        return 0.0
    normalized_message = _normalize_text(message)
    intent_terms = {
        "achieve",
        "achieved",
        "become",
        "condition",
        "conditions",
        "criteria",
        "qualification",
        "qualifications",
        "qualify",
        "requirement",
        "requirements",
    }
    if not (set(_tokens(normalized_message)) & intent_terms):
        return 0.0

    rank_terms = ("manager", "supervisor")
    modifiers = (
        "assistant",
        "inherited",
        "recognized",
        "recognised",
        "sponsored",
        "transferred",
        "unrecognized",
        "unrecognised",
    )
    message_tokens = _tokens(normalized_message)
    anchor = ""
    for index, token in enumerate(message_tokens):
        if token not in rank_terms:
            continue
        anchor = token
        if index > 0 and message_tokens[index - 1] in modifiers:
            anchor = f"{message_tokens[index - 1]} {token}"
        break
    if not anchor:
        return 0.0

    evidence = _normalize_text(f"{title} {content[:1800]}")
    if " " in anchor:
        anchor_pattern = rf"\b{re.escape(anchor)}\b"
    else:
        # A generic Manager question must not treat Assistant Manager or
        # Unrecognized Manager as the governing clause.
        anchor_pattern = rf"(?<![a-z]\s)\b{re.escape(anchor)}\b"
    governing_patterns = (
        rf"{anchor_pattern}\s+is\s+achieved\b",
        rf"{anchor_pattern}\s+requires\b",
        rf"\bqualif(?:y|ies|ied)\s+as\s+{re.escape(anchor)}\b",
        rf"\breaches\s+the\s+level\s+of\s+{re.escape(anchor)}\b",
    )
    return 1.8 if any(re.search(pattern, evidence) for pattern in governing_patterns) else 0.0


def _fragment_quality_score(row: dict[str, Any], message: str) -> float:
    """Reduce detached numeric fragments unless the user asks for a value."""
    if not settings.OPENSEARCH_RETRIEVAL_HARDENING_ENABLED:
        return 0.0
    if str(row.get("chunk_type") or "") != "numeric_fact":
        return 0.0
    normalized_message = _normalize_text(message)
    numeric_intent = bool(re.search(
        r"\b(?:amount|cost|how many|how much|minimum|number|percent|percentage|price|rate|when|year)\b",
        normalized_message,
    )) or bool(re.search(r"\d", normalized_message))
    return 0.1 if numeric_intent else -0.35


def _purchase_channel_score(message: str, title: str, content: str) -> float:
    """Prefer clauses that explicitly identify a permitted sales channel.

    The intent terms, evidence phrases, and score are reviewed data, not
    code - see config/retrieval_scoring_rules.json.
    """
    if not settings.OPENSEARCH_RETRIEVAL_HARDENING_ENABLED:
        return 0.0
    rule = _load_scoring_rules(settings.OPENSEARCH_RETRIEVAL_SCORING_RULES_PATH).get("purchase_channel")
    if not rule:
        return 0.0
    message_terms = set(_tokens(message))
    if not _intent_matches(message_terms, rule):
        return 0.0
    evidence = _normalize_text(f"{title} {content[:1800]}")
    return _evidence_score(evidence, rule)


def _return_policy_score(message: str, title: str, content: str) -> float:
    """Prefer clauses that directly state product-return rights or conditions.

    The intent terms, evidence phrases, and score are reviewed data, not
    code - see config/retrieval_scoring_rules.json. A question about the
    buy-back window for an unopened or unsold product is answered by a more
    specific clause than the general satisfaction-guarantee return right. A
    live-index canary (2026-09-01) found that "100 product satisfaction"
    alone was matching that general clause even for this more specific
    question, outranking the correct buy-back clause. Prefer the specific
    clause here, and do not let the generic phrase compete once the
    question is this specific.
    """
    if not settings.OPENSEARCH_RETRIEVAL_HARDENING_ENABLED:
        return 0.0
    rule = _load_scoring_rules(settings.OPENSEARCH_RETRIEVAL_SCORING_RULES_PATH).get("return_policy")
    if not rule:
        return 0.0
    message_terms = set(_tokens(message))
    if not (message_terms & rule["intent_any"]):
        return 0.0
    evidence = _normalize_text(f"{title} {content[:1800]}")

    if _intent_matches(message_terms, rule["buyback_window"]):
        return _evidence_score(evidence, rule["buyback_window"])

    return _evidence_score(evidence, rule["general"])


def _source_score(row: dict[str, Any], message: str) -> float:
    """Blend search rank with generic, document-derived lexical alignment."""
    base_score = float(row.get("rank") or 0.0)
    section_id = str(row.get("section_id") or "").lower()
    title = str(row.get("section_title") or "").lower()
    content = str(row.get("content") or "").lower()
    search_text = str(row.get("search_text") or "").lower()
    message_lower = _normalize_text(message)
    message_tokens = set(_tokens(message))
    content_tokens = set(_tokens(search_text[:2000]))
    phrases = _key_phrases(message)

    score = base_score
    if section_id and section_id in message_lower:
        score += 0.75
    if title and _normalize_text(title) in message_lower:
        score += 0.8
    title_overlap = _character_overlap(message, title)
    if title_overlap >= 0.68:
        score += title_overlap * 1.1
    if message_tokens:
        score += (len(message_tokens & content_tokens) / len(message_tokens)) * 0.35
    score += _exact_topic_score(message, title, content)
    score += _governing_requirement_score(message, title, content)
    score += _fragment_quality_score(row, message)
    score += _purchase_channel_score(message, title, content)
    score += _return_policy_score(message, title, content)
    for phrase in phrases:
        if phrase in _normalize_text(title):
            score += 0.35
        elif phrase in _normalize_text(content[:800]):
            score += 0.12
    return round(score, 6)


def _confidence_from_documents(documents: list[RetrievedDocument]) -> float:
    """Create conservative confidence from selected and corroborating evidence.

    An evidence selector may place the governing section ahead of a higher raw
    lexical score. Preserve that selected order, but grant a small capped bonus
    when another approved section strongly corroborates the selected result.
    """
    if not documents:
        return 0.0
    scores = [float(document.score or 0.0) for document in documents]
    top_score = scores[0]
    # A row the selector passed over can still outscore the selected result
    # on raw lexical terms and land right behind it in the returned order.
    # That row was rejected as evidence, not a competing runner-up, so using
    # its score here would zero out the margin for a result the selector
    # actively preferred. Compare against the next candidate that the raw
    # score itself doesn't already contradict.
    trailing_contenders = [score for score in scores[1:] if score <= top_score]
    runner_up = trailing_contenders[0] if trailing_contenders else 0.0
    avg_score = sum(scores) / len(scores)
    margin = max(top_score - runner_up, 0.0)
    strongest_score = max(scores)
    corroboration = min(max(strongest_score - top_score, 0.0) / 40.0, 0.1)
    normalized = min(
        (top_score / 10.0) + (margin / 10.0) + (avg_score / 30.0) + corroboration,
        0.95,
    )
    return round(normalized, 3)
