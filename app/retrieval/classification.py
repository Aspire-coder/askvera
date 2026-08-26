"""Deterministic retrieval classifications shared by ingestion and ranking.

The classifiers deliberately use reviewed, bounded rules instead of a model call.
They never create evidence or alter locale/access-scope filters. Unknown text is
kept as ``general``/``supporting`` so existing indexed documents remain usable.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable


QUESTION_TYPES = (
    "definition",
    "qualification",
    "timing",
    "eligibility",
    "restriction",
    "process",
    "benefit",
    "pricing",
    "exception",
    "contact",
    "general",
)

SECTION_AUTHORITIES = (
    "governing",
    "supporting",
    "definition",
    "exception",
    "directory",
    "summary",
)


@dataclass(frozen=True)
class QuestionClassification:
    """Stable, content-free intent tags for one question."""

    entities: tuple[str, ...]
    question_type: str


@dataclass(frozen=True)
class SectionClassification:
    """Stable tags attached to one approved source section."""

    entities: tuple[str, ...]
    question_types: tuple[str, ...]
    authority: str


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "").casefold()
    normalized = "".join(character for character in normalized if not unicodedata.combining(character))
    return " ".join(normalized.split())


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(_normalize(phrase))}(?!\w)", text))


# Canonical concepts are intentionally business-level, not country-specific.
# Aliases cover common approved-document languages and familiar abbreviations.
_ENTITY_ALIASES: dict[str, tuple[str, ...]] = {
    "forever_business_owner": (
        "forever business owner", "fbo", "forever business-eigentumer", "forever business owner",
    ),
    "preferred_customer": (
        "preferred customer", "preferred client", "client privilegie", "bevorzugter kunde",
        "cliente preferenziale", "cliente preferente", "voorkeursklant",
    ),
    "assistant_supervisor": ("assistant supervisor", "assistent supervisor"),
    "supervisor": ("supervisor",),
    "assistant_manager": ("assistant manager", "assistent manager"),
    "manager": ("manager",),
    "recognized_manager": ("recognized manager", "recognised manager", "anerkannter manager"),
    "eagle_manager": ("eagle manager",),
    "gem_manager": ("gem manager",),
    "bonus": ("bonus", "bonificacion", "boni", "prime"),
    "leadership_bonus": ("leadership bonus", "bonus de leadership", "fuhrungsbonus"),
    "chairmans_bonus": ("chairman's bonus", "chairmans bonus", "chairman bonus"),
    "orders": ("order", "ordering", "commande", "bestellung", "ordine", "pedido", "bestelling"),
    "returns": ("return", "refund", "retour", "ruckgabe", "rimborso", "devolucion", "restitutie"),
    "international_sponsoring": (
        "international sponsoring", "international sponsor", "sponsoring international",
        "internationales sponsoring", "sponsorizzazione internazionale", "patrocinio internacional",
    ),
    "sponsoring": ("sponsor", "sponsoring", "parrain", "patrocinador"),
    "activity": ("activity", "active", "aktiv", "activite", "attivita", "actividad"),
    "recognition": ("recognition", "reconnaissance", "anerkennung", "riconoscimento", "reconocimiento"),
    "products": ("product", "produit", "produkt", "prodotto", "producto"),
    "joining": ("join", "joining", "enrol", "enroll", "register", "sign up", "inscription", "anmeldung"),
    "fees": ("fee", "cost", "price", "charge", "frais", "gebuhr", "costo", "tarifa"),
    "contact_details": (
        "telephone", "phone", "email", "address", "website", "business hours", "contact",
        "telefon", "adresse", "telefono", "correo", "horario",
    ),
}


_QUESTION_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("contact", ("telephone", "phone", "email", "address", "website", "business hours", "contact", "telefon", "telefono")),
    (
        "pricing",
        (
            "cost", "fee", "price", "pay", "payment", "investment", "minimum order",
            "frais", "gebuhr", "costo", "precio",
        ),
    ),
    ("qualification", ("qualify", "qualification", "requirement", "achieve", "become", "reach", "criteria", "voraussetzung", "requisito")),
    ("eligibility", ("eligible", "eligibility", "who can", "allowed to", "berechtigt", "admissible")),
    ("timing", ("when", "how long", "deadline", "within", "days", "months", "wann", "combien de temps", "quanto tempo")),
    ("restriction", ("cannot", "can't", "must not", "prohibited", "restriction", "not allowed", "verboten", "interdit", "vietato")),
    ("exception", ("exception", "unless", "except", "special case", "ausnahme", "eccezione", "excepcion")),
    ("process", ("how do", "how can", "steps", "process", "procedure", "sign up", "register", "comment", "wie kann")),
    ("benefit", ("benefit", "receive", "earn", "entitled", "advantage", "avantage", "vorteil")),
    ("definition", ("what is", "what does", "define", "meaning", "definition", "qu'est-ce", "was ist", "che cos'e", "que es")),
)


def classify_entities(*values: str) -> tuple[str, ...]:
    """Return canonical entities found in the supplied question or section text."""
    text = _normalize(" ".join(values))
    matches: list[tuple[int, str]] = []
    for entity, aliases in _ENTITY_ALIASES.items():
        best_alias_length = max(
            (len(_normalize(alias)) for alias in aliases if _contains_phrase(text, alias)),
            default=0,
        )
        if best_alias_length:
            matches.append((best_alias_length, entity))

    # Remove broad entities when a more precise descendant was found.
    found = {entity for _length, entity in matches}
    if "recognized_manager" in found or "assistant_manager" in found or "eagle_manager" in found or "gem_manager" in found:
        found.discard("manager")
    if "assistant_supervisor" in found:
        found.discard("supervisor")
    if "leadership_bonus" in found or "chairmans_bonus" in found:
        found.discard("bonus")
    return tuple(sorted(found)) or ("general",)


def classify_question(message: str) -> QuestionClassification:
    """Classify a user question without changing or expanding its meaning."""
    text = _normalize(message)
    question_type = "general"
    for candidate, phrases in _QUESTION_PATTERNS:
        if any(_contains_phrase(text, phrase) for phrase in phrases):
            question_type = candidate
            break
    return QuestionClassification(entities=classify_entities(message), question_type=question_type)


def _section_question_types(text: str, authority: str) -> tuple[str, ...]:
    matches = [
        candidate
        for candidate, phrases in _QUESTION_PATTERNS
        if any(_contains_phrase(text, phrase) for phrase in phrases)
    ]
    if authority == "definition" and "definition" not in matches:
        matches.insert(0, "definition")
    if authority == "directory" and "contact" not in matches:
        matches.insert(0, "contact")
    return tuple(dict.fromkeys(matches)) or ("general",)


def classify_section(
    *,
    title: str,
    content: str,
    chunk_type: str = "section",
    document_type: str = "policy",
    metadata: dict[str, Any] | None = None,
) -> SectionClassification:
    """Classify approved evidence using structure first and wording second."""
    metadata = metadata or {}
    text = _normalize(f"{title} {content[:4000]}")
    normalized_chunk_type = _normalize(chunk_type)
    normalized_document_type = _normalize(document_type)

    if normalized_document_type in {"office_directory", "international_sponsoring_directory"}:
        authority = "directory"
    elif normalized_chunk_type == "definition" or _contains_phrase(text, "definition"):
        authority = "definition"
    elif normalized_chunk_type in {"document_outline", "document_front_matter"}:
        authority = "summary"
    elif any(_contains_phrase(text, phrase) for phrase in ("exception", "unless", "except that", "provided however")):
        authority = "exception"
    elif any(
        _contains_phrase(text, phrase)
        for phrase in (
            "must", "shall", "required", "requirement", "may not", "is prohibited",
            "is achieved", "qualify", "eligible", "no minimum capital investment",
        )
    ):
        authority = "governing"
    else:
        authority = "supporting"

    entities = classify_entities(
        title,
        content,
        str(metadata.get("record_type") or ""),
        str(metadata.get("directory_kind") or ""),
    )
    return SectionClassification(
        entities=entities,
        question_types=_section_question_types(text, authority),
        authority=authority,
    )


def normalized_tags(values: Iterable[str] | str | None, *, fallback: str = "general") -> tuple[str, ...]:
    """Normalize index/JSON tag shapes while remaining backward compatible."""
    if isinstance(values, str):
        values = [values]
    normalized = tuple(dict.fromkeys(_normalize(str(value)).replace(" ", "_") for value in (values or []) if str(value).strip()))
    return normalized or (fallback,)
