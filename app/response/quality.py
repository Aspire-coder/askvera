"""Deterministic final-response quality and date-scope protections."""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from app.response.outcome import OutcomeKind
from app.response.partial_answer import FieldCoverage
from app.retrieval.models import RetrievedDocument
from app.retrieval.providers import DIRECTORY_POLICY_WORDING_RE
from config.directory_field_vocabulary import normalize_language_code
from utils.directory_fields import _fold_diacritics, _INLINE_FIELD_RE, localized_policy_wording_present
from utils.redaction import drop_emptied_lead_ins
from utils.sentence_spans import iter_sentences
_PLACEHOLDER_RE = re.compile(
    r"\*{4,}|(?:\[|\{|<)(?:ADDRESS|EMAIL|NAME|PHONE|PII|URL|WEBSITE|CONTACT|TBD)(?::[^\]\}>]*)?(?:\]|\}|>)",
    flags=re.IGNORECASE,
)
_PHONE_PLACEHOLDER_RE = re.compile(
    r"\*{4,}|(?:\[|\{|<)(?:PHONE|CONTACT)(?::[^\]\}>]*)?(?:\]|\}|>)",
    re.IGNORECASE,
)
_WEBSITE_PLACEHOLDER_RE = re.compile(
    r"(?:\[|\{|<)(?:URL|WEBSITE)(?::[^\]\}>]*)?(?:\]|\}|>)",
    re.IGNORECASE,
)
_EXPLICIT_YEAR_RE = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
_INCOMPLETE_ENGLISH_END_RE = re.compile(
    r"\b(?:a|an|the|at|include|including|in\s+the)\s*[,:;.!?]?\s*$",
    re.IGNORECASE,
)
_INTERNAL_RETRIEVAL_LANGUAGE_RE = re.compile(
    r"\b(?:retrieved|approved)\s+(?:(?:authori[sz]ed|approved)\s+)?"
    r"(?:chunks?|directory\s+records?|evidence\s+chunks?)\b",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _public_contacts() -> dict[str, Any]:
    default_path = Path(__file__).resolve().parents[2] / "config" / "public_contacts.json"
    path = Path(os.environ.get("PUBLIC_CONTACTS_PATH", str(default_path)))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def contact_for_country(country: str) -> dict[str, str]:
    """Return reviewed public contact values for one market."""
    payload = _public_contacts()
    default = payload.get("default", {})
    countries = payload.get("countries", {})
    market = countries.get((country or "").upper(), {}) if isinstance(countries, dict) else {}
    merged = {
        **(default if isinstance(default, dict) else {}),
        **(market if isinstance(market, dict) else {}),
    }
    return {str(key): str(value).strip() for key, value in merged.items() if str(value).strip()}


def remove_or_replace_contact_placeholders(answer: str, country: str) -> tuple[str, list[str]]:
    """Resolve reviewed contact tokens and remove unresolved contact-bearing lines."""
    if not answer:
        return answer, []
    contacts = contact_for_country(country)
    changes: list[str] = []
    originals = answer.splitlines()
    lines: list[str | None] = []
    for line in originals:
        updated = line
        if _WEBSITE_PLACEHOLDER_RE.search(updated):
            website = contacts.get("website", "")
            if website:
                updated = _WEBSITE_PLACEHOLDER_RE.sub(website, updated)
                changes.append("website_replaced")
            else:
                changes.append("website_line_removed")
                lines.append(None)
                continue
        if _PHONE_PLACEHOLDER_RE.search(updated):
            phone = contacts.get("customerCarePhone", "")
            if phone:
                updated = _PHONE_PLACEHOLDER_RE.sub(phone, updated)
                changes.append("phone_replaced")
            else:
                changes.append("phone_line_removed")
                lines.append(None)
                continue
        if _PLACEHOLDER_RE.search(updated):
            changes.append("unresolved_placeholder_line_removed")
            lines.append(None)
            continue
        lines.append(updated.rstrip() if updated.strip() else None)
    # Tracker row 27: removing every contact line under "You can reach them
    # at:" left the lead-in introducing nothing at the end of the answer.
    without_orphans = drop_emptied_lead_ins(lines, originals)
    if without_orphans != lines:
        changes.append("orphaned_lead_in_removed")
    return "\n".join(line for line in without_orphans if line).strip(), sorted(set(changes))


def contains_unresolved_placeholder(answer: str) -> bool:
    """Return whether a user-visible placeholder remains."""
    return bool(_PLACEHOLDER_RE.search(answer or ""))


def incomplete_ending_reason(answer: str, language: str = "") -> str | None:
    """Name the rule that judged an answer broken, or None if it looks whole.

    The reason exists because this check discards a complete answer and shows
    the reader the insufficient-evidence fallback instead, and the rejected
    text is deliberately never logged. That left "INCOMPLETE_OUTPUT" as the
    entire record of the decision -- true of the Algeria minimum-order case,
    where retrieval scored 9.542 on the right record, evidence was approved,
    grounding repair removed nothing, and the reader still got the fallback
    with no way to tell which of these rules had fired.

    Every reason is drawn from this function's own vocabulary or from counts,
    never from the answer, so naming it adds no answer text to the logs.
    """
    text = (answer or "").strip()
    if not text:
        return "empty"
    # Only an UNCLOSED opener indicates truncation. Surplus closers are how
    # enumerations are written - "a) ... b) ... c) ..." - and policy answers list
    # requirements that way constantly.
    #
    # Measured on the deployed build: "How can i become a recognized manager?"
    # abstained 2 times in 12, every failure on this check, with counts like
    # 0 "(" against 3 ")". The answers were complete, correct and cited, ending
    # in a normal closing question; they were replaced by "the approved policy
    # documents do not contain enough information".
    if text.count("(") > text.count(")"):
        return f"unclosed_paren:{text.count('(')}>{text.count(')')}"
    if text.count("[") > text.count("]"):
        return f"unclosed_bracket:{text.count('[')}>{text.count(']')}"
    locale = (language or "en").split("-", 1)[0].lower()
    if locale != "en":
        return None
    match = _INCOMPLETE_ENGLISH_END_RE.search(text)
    return f"dangling_word:{match.group(0).strip().lower()}" if match else None


def has_incomplete_ending(answer: str, language: str = "") -> bool:
    """Detect high-confidence broken endings without rewriting factual content."""
    return incomplete_ending_reason(answer, language) is not None


def contains_internal_retrieval_language(answer: str) -> bool:
    """Return whether implementation jargon leaked into customer-facing copy."""
    return bool(_INTERNAL_RETRIEVAL_LANGUAGE_RE.search(answer or ""))


def unsupported_requested_years(question: str, documents: Iterable[RetrievedDocument]) -> list[int]:
    """Return explicit requested years that are absent from dated approved evidence."""
    requested = sorted({int(value) for value in _EXPLICIT_YEAR_RE.findall(question or "")})
    if not requested:
        return []

    evidence_years: set[int] = set()
    effective_years: list[int] = []
    for document in documents:
        evidence_years.update(int(value) for value in _EXPLICIT_YEAR_RE.findall(document.content or ""))
        values = [
            document.document_version,
            document.metadata.get("effective_date", ""),
            document.metadata.get("expiry_date", ""),
            document.metadata.get("document_version", ""),
        ]
        for value in values:
            years = [int(item) for item in _EXPLICIT_YEAR_RE.findall(str(value or ""))]
            evidence_years.update(years)
            effective_years.extend(years)

    # Without dated evidence, leave the normal evidence contract in control.
    if not effective_years:
        return []
    minimum, maximum = min(effective_years), max(effective_years)
    return [year for year in requested if year not in evidence_years and not minimum <= year <= maximum]


def format_period_not_covered(template: str, years: list[int]) -> str:
    """Format a reviewed period-unavailable response without model generation."""
    period = ", ".join(str(year) for year in years)
    return template.replace("{period}", period)


# ---------------------------------------------------------------------------
# CX phase 3, Lane 2 (docs/conversation-quality/phase3/CX_DESIGN.md,
# docs/conversation-quality/phase3/CX_LANES.md): final-answer quality checks.
# Pure functions only -- no I/O, no model calls, no answer of the coordinator's
# own decisions. See docs/conversation-quality/phase3/CX_LANE2_PARTIAL_AND_QUALITY.md
# for the recommended hook call sites in app/orchestrator/chat_orchestrator.py.
# ---------------------------------------------------------------------------

# CLOSED, per-language table of pure-pleasantry SENTENCE OPENERS -- the kind
# of sentence that says nothing about the reader's question ("Great
# question!", "Certainly!", "I'd be happy to help.") and exists only to
# precede the real answer. Deliberately small and closed, the same discipline
# every other per-language table in this codebase uses (see e.g.
# config/reference_vocabulary.py's own docstring): every entry below is a
# complete opener phrase, matched only at the very START of the answer's
# first sentence, never a bare word matched anywhere in it -- so an answer
# that happens to mention "of course you can return the item within 30 days"
# is never touched (that phrase does not open the sentence).
#
# Confidence per language (documents which of these are held to the same bar
# as the rest of this codebase's reviewed copy, and which are a best-effort
# structural analogy pending native review -- the same distinction this
# repository's other per-language tables draw, e.g.
# utils/sentence_spans.py's ABBREVIATIONS docstring):
#   en, es, fr, de, it, nl -- high confidence: phrases mirror the reviewed
#       route-copy tone for these languages (config/conversation_routes.json)
#       and have been checked against real generated openers in this
#       codebase's own examples.
#   da, no, sv, fi -- medium confidence: built the same way (literal
#       translation of the en/de set plus each language's own idiomatic
#       "of course"/"certainly"), not yet checked against a corpus of real
#       generated openers in these languages.
#   ru, sr -- lower confidence: no native-speaker review yet; kept narrow
#       (fewer, more literal variants) rather than guessing at additional
#       idiomatic phrasings.
_PREAMBLE_OPENERS: dict[str, tuple[str, ...]] = {
    "en": (
        "great question", "thanks for asking", "thank you for asking",
        "i'd be happy to help", "i would be happy to help", "happy to help",
        "certainly", "of course", "sure thing", "no problem",
    ),
    "es": (
        "buena pregunta", "gracias por preguntar", "con gusto te ayudo",
        "con mucho gusto", "claro que si", "por supuesto",
    ),
    "fr": (
        "bonne question", "merci de poser la question", "avec plaisir",
        "je suis ravi de vous aider", "bien sur", "certainement",
    ),
    "de": (
        "gute frage", "danke fur die frage", "gerne helfe ich",
        "sehr gerne helfe ich", "naturlich", "selbstverstandlich",
    ),
    "it": (
        "ottima domanda", "grazie per la domanda",
        "sono felice di aiutarti", "certamente", "certo", "con piacere",
    ),
    "nl": (
        "goede vraag", "bedankt voor de vraag", "ik help je graag",
        "natuurlijk", "zeker",
    ),
    "da": (
        "godt sporgsmal", "tak for sporgsmalet", "jeg hjaelper gerne",
        "selvfolgelig", "naturligvis",
    ),
    "no": (
        "godt sporsmal", "takk for sporsmalet", "jeg hjelper deg gjerne",
        "selvfolgelig", "naturligvis",
    ),
    "sv": (
        "bra fraga", "tack for fragan", "jag hjalper garna till",
        "sjalvklart", "absolut",
    ),
    "fi": (
        "hyva kysymys", "kiitos kysymyksesta", "autan mielellani",
        "totta kai", "tietenkin",
    ),
    "ru": (
        "хороший вопрос", "спасибо за вопрос", "конечно",
    ),
    "sr": (
        "dobro pitanje", "hvala na pitanju", "naravno", "svakako",
    ),
}

# A sentence opener is matched after folding accents/diacritics away (the
# same NFKD/strip-combining/casefold recipe
# utils.directory_fields._fold_diacritics uses, imported above), so
# "Selbstverständlich," matches the accent-free "selbstverstandlich" table
# entry above without a second, accented spelling being hand-written for
# every language.

# A citation marker in the shape utils/inline_citations.py already produces
# and recognises ("[1]", "[Source 1]"): a sentence carrying one is reporting
# a specific sourced fact, never an empty pleasantry.
_CITATION_MARKER_RE = re.compile(r"\[(?:source\s+)?\d+\]", re.IGNORECASE)
_ANY_DIGIT_RE = re.compile(r"\d")


def _sentence_is_never_preamble(sentence: str, language: str) -> bool:
    """True when ``sentence`` must never be treated as pure preamble.

    Every check here reuses an existing signal rather than inventing a new
    one: a digit, a citation marker in the shape
    ``utils.inline_citations.separate_verified_citations`` already
    recognises, a directory "Label: value" line
    (``utils.directory_fields._INLINE_FIELD_RE`` -- the exact pattern
    ``utils.directory_fields.parse_directory_fields`` uses to find one), or
    policy wording (English: ``app.retrieval.providers.DIRECTORY_POLICY_WORDING_RE``;
    other languages: ``utils.directory_fields.localized_policy_wording_present``,
    itself backed by the reviewed ``config.directory_field_vocabulary.POLICY_WORDING_TERMS``
    table) all mean this sentence is carrying real content, not a pleasantry.
    """
    if _ANY_DIGIT_RE.search(sentence):
        return True
    if _CITATION_MARKER_RE.search(sentence):
        return True
    if _INLINE_FIELD_RE.match(sentence.strip()):
        return True
    if DIRECTORY_POLICY_WORDING_RE.search(sentence):
        return True
    if localized_policy_wording_present(sentence, language=language):
        return True
    return False


def leading_preamble_span(answer: str, language: str) -> tuple[int, int] | None:
    """Return the ``(start, end)`` span of a pure-preamble opening sentence, if any.

    Only ever the answer's FIRST sentence (span-aware, via
    ``utils.sentence_spans.iter_sentences`` -- so a decimal, abbreviation,
    initial, email or URL in that sentence is never mistaken for a sentence
    break). ``None`` when the answer is empty, the first sentence carries
    any of the never-preamble signals in :func:`_sentence_is_never_preamble`,
    or ``language`` has no reviewed opener table (:data:`_PREAMBLE_OPENERS`).
    """
    sentences = iter_sentences(answer or "")
    if not sentences:
        return None
    first = sentences[0]
    text = first.text.strip()
    if not text:
        return None
    if _sentence_is_never_preamble(first.text, language):
        return None
    openers = _PREAMBLE_OPENERS.get(normalize_language_code(language))
    if not openers:
        return None
    folded = _fold_diacritics(text).strip(" \t\"'*.!?,:;-")
    if any(folded == opener or folded.startswith(opener + " ") or folded.startswith(opener + ",")
           for opener in openers):
        return (first.start, first.end)
    return None


def strip_leading_preamble(answer: str, language: str) -> str:
    """Remove a detected leading-preamble sentence so the direct answer comes first.

    Removes only the span :func:`leading_preamble_span` identifies -- every
    other sentence is untouched. Never empties the answer: when nothing but
    the preamble sentence remains (or removing it would leave only
    whitespace), the original ``answer`` is returned unchanged rather than
    handing the reader an empty response.
    """
    span = leading_preamble_span(answer, language)
    if span is None:
        return answer
    start, end = span
    remainder = (answer[:start] + answer[end:]).lstrip()
    if not remainder.strip():
        return answer
    return remainder


# ---------------------------------------------------------------------------
# Overclaim detection: an answer sentence that asserts a specific value for a
# directory field no approved evidence document carries (FieldCoverage.unsupported,
# app/response/partial_answer.py). Report-only -- the numeric and contact
# validators (app/validation/validators/numeric_grounding_validator.py,
# utils/directory_fields.py's restore/repair helpers) already own actually
# editing the answer; this function never touches the text.
#
# Deliberately narrow: only the four directory fields with an unambiguous,
# low-false-positive value SHAPE get a pattern here (a phone number, an
# email address, a website). Address, business hours, payment methods and
# delivery cost/time values are free-form prose with no shape distinct
# enough to flag without a high false-positive rate against ordinary policy
# sentences -- left undetected here rather than guessed at (documented
# limitation, not an oversight).
# ---------------------------------------------------------------------------
_OVERCLAIM_FIELD_PATTERNS: dict[str, re.Pattern[str]] = {
    "phone": re.compile(r"(?:\+\d{1,3}[\s().-]*)?(?:\(?\d{2,4}\)?[\s.-]){2,}\d{2,4}"),
    "order_phone": re.compile(r"(?:\+\d{1,3}[\s().-]*)?(?:\(?\d{2,4}\)?[\s.-]){2,}\d{2,4}"),
    "email": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    "website": re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE),
}


def overclaim_findings(answer: str, coverage: FieldCoverage) -> list[str]:
    """Return the sentences that assert a value for an unsupported field.

    ``coverage`` is the same :class:`app.response.partial_answer.FieldCoverage`
    :func:`app.response.partial_answer.assess_field_coverage` already
    computed for this turn -- this function reads its ``unsupported`` set,
    never recomputes coverage itself. Diagnostic only: returns the offending
    sentence texts (stripped, in answer order, de-duplicated) for logging or
    a downstream repair pass to act on; it never edits ``answer``.
    """
    if not coverage.unsupported:
        return []
    patterns = [
        pattern
        for field, pattern in _OVERCLAIM_FIELD_PATTERNS.items()
        if field in coverage.unsupported
    ]
    if not patterns:
        return []
    findings: list[str] = []
    for sentence in iter_sentences(answer or ""):
        text = sentence.text.strip()
        if not text:
            continue
        if any(pattern.search(text) for pattern in patterns) and text not in findings:
            findings.append(text)
    return findings


def confidence_framing_key(outcome_kind: OutcomeKind, coverage: FieldCoverage) -> str | None:
    """Return the one localized-copy key a partial answer's framing may add, or ``None``.

    No numeric confidence is ever computed or shown -- this returns only the
    existing ``partial_answer_gap`` message key (Lane 4 owns its copy in
    ``config/conversation_routes.json``; see
    ``docs/conversation-quality/phase3/CX_LANES.md``'s message-key table) for
    a partial answer that actually has an unsupported field, and ``None``
    for every other outcome, including a full ``OutcomeKind.ANSWER`` -- a
    complete answer is never given hedging framing it does not need.
    """
    if outcome_kind == OutcomeKind.PARTIAL_ANSWER and coverage.unsupported:
        return "partial_answer_gap"
    return None
