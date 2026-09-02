"""Data-driven classification and localized responses for regulated claims."""

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path


_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "claim_safety.json"


@lru_cache(maxsize=1)
def _config() -> dict:
    return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))


def _locale(language: str) -> str:
    return (language or "en").split("-", 1)[0].strip().lower() or "en"


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold()
    text = "".join(char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip()


def _contains_term(text: str, term: str) -> bool:
    normalized_term = _normalize(term)
    if not normalized_term:
        return False
    if " " in normalized_term:
        return normalized_term in text
    return re.search(rf"(?<!\w){re.escape(normalized_term)}(?!\w)", text, flags=re.UNICODE) is not None


def _terms(group: str, language: str) -> list[str]:
    values = _config().get(group, {})
    return [*values.get("default", []), *values.get(_locale(language), [])]


def classify_claim_scope(message: str, governance_topic: str, language: str = "en") -> str:
    """Return a stable claim subtype without changing knowledge retrieval."""
    topic = (governance_topic or "").strip().lower()
    if topic != "medical_claim":
        return topic
    text = _normalize(message)
    has_product = any(_contains_term(text, term) for term in _terms("product_terms", language))
    has_disease_claim = any(_contains_term(text, term) for term in _terms("disease_claim_terms", language))
    return "product_disease_claim" if has_product and has_disease_claim else "medical_claim"


def localized_claim_response(message: str, governance_topic: str, country: str, language: str) -> tuple[str | None, str]:
    """Return localized reviewed copy and its classification."""
    scope = classify_claim_scope(message, governance_topic, language)
    if scope != "product_disease_claim":
        return None, scope
    responses = _config().get("responses", {})
    locale = _locale(language)
    return responses.get(locale, responses.get("en")), scope
