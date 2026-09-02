"""Amazon Comprehend PII scrubbing for input and output text."""

import re
from collections.abc import Iterable
from threading import Lock
from time import monotonic, perf_counter

from botocore.exceptions import BotoCoreError, ClientError

from config import settings
from services.aws_clients import get_aws_clients
from utils.redaction import (
    EMAIL_RE,
    GOVERNMENT_ID_RE,
    PHONE_RE,
    redact_ibans,
    redact_payment_cards,
)
from utils.exceptions import AwsServiceError
from utils.logging import get_logger

LOGGER = get_logger("services.pii")
COMPREHEND_MAX_TEXT_CHARS = 4500
_PII_CIRCUIT_LOCK = Lock()
_pii_failure_count = 0
_pii_open_until = 0.0
SENSITIVE_PII_PLACEHOLDERS = frozenset(
    {
        "BANK_ACCOUNT",
        "CREDIT_DEBIT_NUMBER",
        "GOVERNMENT_ID",
        "PAYMENT_CARD",
        "SSN",
    }
)
# Every placeholder token that must never survive to a user-visible response
# unresolved. Built from both sets so a new sensitive category can never be
# added to detection (SENSITIVE_PII_PLACEHOLDERS) without also being covered
# by the cleanup pass below - the two silently drifted apart once already.
_UNRESOLVED_PLACEHOLDER_TOKENS = frozenset({"ADDRESS", "EMAIL", "PHONE", "NAME", "PII"}) | SENSITIVE_PII_PLACEHOLDERS
_UNRESOLVED_PLACEHOLDER_PATTERN = "|".join(sorted(_UNRESOLVED_PLACEHOLDER_TOKENS))


def contains_sensitive_pii_placeholder(text: str) -> bool:
    """Return whether scrubbed input contains high-risk personal data."""
    placeholders = {item.upper() for item in re.findall(r"\[([A-Z_]+)\]", text or "", flags=re.IGNORECASE)}
    return bool(placeholders & SENSITIVE_PII_PLACEHOLDERS)


def remove_unresolved_pii_placeholders(text: str) -> str:
    """Remove user-visible redaction markers from a generated response.

    Approved contacts are preserved before this point via ``allowed_texts``. A
    remaining marker therefore represents ungrounded content and should not be
    displayed as a broken support contact.
    """
    if not text or "[" not in text:
        return text
    kept_lines: list[str] = []
    for line in text.splitlines():
        if re.search(rf"\[(?:{_UNRESOLVED_PLACEHOLDER_PATTERN})\]\s*:", line, flags=re.IGNORECASE):
            continue
        cleaned = re.sub(
            rf"\s*\[(?:{_UNRESOLVED_PLACEHOLDER_PATTERN})\]"
            rf"(?:\s*,\s*\[(?:{_UNRESOLVED_PLACEHOLDER_PATTERN})\])*",
            "",
            line,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\(\s*\)", "", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
        if cleaned:
            kept_lines.append(cleaned)
    return "\n".join(kept_lines)


def _pii_language_code(language: str) -> str | None:
    """Return a supported Comprehend PII language code."""
    normalized = (language or settings.COMPREHEND_PII_LANGUAGE_CODE).split("-", 1)[0].lower()
    if normalized in settings.COMPREHEND_PII_LANGUAGE_CODES:
        return normalized
    return None


def _approved_entity(entity_text: str, allowed_texts: Iterable[str]) -> bool:
    """Return whether an entity is grounded verbatim in approved evidence."""
    normalized_entity = entity_text.casefold().strip()
    if not normalized_entity:
        return False
    punctuation_insensitive_entity = re.sub(r"[^\w]+", " ", normalized_entity, flags=re.UNICODE).strip()
    for allowed_text in allowed_texts:
        normalized_allowed = str(allowed_text or "").casefold()
        if normalized_entity in normalized_allowed:
            return True
        # PDF extraction can wrap punctuation-separated public values across
        # lines, for example office 706 -\n709. Treat separators consistently
        # while still requiring the complete entity to occur in approved text.
        punctuation_insensitive_allowed = re.sub(
            r"[^\w]+",
            " ",
            normalized_allowed,
            flags=re.UNICODE,
        ).strip()
        if (
            punctuation_insensitive_entity
            and punctuation_insensitive_entity in punctuation_insensitive_allowed
        ):
            return True
        entity_digits = re.sub(r"\D", "", normalized_entity)
        if len(entity_digits) >= 7 and entity_digits in re.sub(r"\D", "", normalized_allowed):
            return True
        entity_tokens = set(re.findall(r"[^\W_]+", punctuation_insensitive_entity, flags=re.UNICODE))
        allowed_tokens = set(re.findall(r"[^\W_]+", punctuation_insensitive_allowed, flags=re.UNICODE))
        if len(entity_tokens) >= 2:
            overlap = len(entity_tokens & allowed_tokens)
            if overlap >= 2 and overlap / len(entity_tokens) >= 0.8:
                return True
    return False


def _looks_like_location_name(entity_text: str) -> bool:
    """Distinguish a short place name from a private street address."""
    if any(character.isdigit() for character in entity_text):
        return False
    tokens = re.findall(r"[^\W_]+", entity_text, flags=re.UNICODE)
    return 1 <= len(tokens) <= 4


def _scrub_pattern_pii(text: str, allowed_texts: Iterable[str]) -> str:
    """Mask language-neutral email and phone patterns without a remote call."""
    approved = tuple(allowed_texts)

    def replace_email(match: re.Match[str]) -> str:
        return match.group(0) if _approved_entity(match.group(0), approved) else "[EMAIL]"

    def replace_phone(match: re.Match[str]) -> str:
        return match.group(0) if _approved_entity(match.group(0), approved) else "[PHONE]"

    def replace_government_id(match: re.Match[str]) -> str:
        # A 3-2-4 digit grouping is shaped like a US SSN, but the same shape
        # occurs in ordinary international phone/order-line numbers (this
        # pattern is not locale-aware). When the exact digits are already
        # grounded in approved evidence - an office directory record, not
        # user-submitted text - it is a public business contact value, not a
        # private government ID, so it gets the same exemption phone/email
        # numbers already have instead of being masked unconditionally.
        return match.group(0) if _approved_entity(match.group(0), approved) else "[GOVERNMENT_ID]"

    scrubbed = GOVERNMENT_ID_RE.sub(replace_government_id, text)
    scrubbed = redact_payment_cards(scrubbed)
    scrubbed = redact_ibans(scrubbed)
    return PHONE_RE.sub(replace_phone, EMAIL_RE.sub(replace_email, scrubbed))


def scrub_pattern_pii(text: str, *, allowed_texts: Iterable[str] = ()) -> str:
    """Mask common language-neutral PII without making a remote AWS call."""
    return _scrub_pattern_pii(text, allowed_texts)


def _detect_pii_entities(text: str, language_code: str) -> list[dict[str, object]]:
    """Detect PII across the complete message using bounded API requests."""
    if _pii_circuit_is_open():
        raise AwsServiceError("Comprehend PII detection is temporarily unavailable.")
    comprehend = get_aws_clients().comprehend
    entities: list[dict[str, object]] = []
    for start in range(0, len(text), COMPREHEND_MAX_TEXT_CHARS):
        chunk = text[start : start + COMPREHEND_MAX_TEXT_CHARS]
        response = comprehend.detect_pii_entities(Text=chunk, LanguageCode=language_code)
        for raw_entity in response.get("Entities", []):
            entity = dict(raw_entity)
            entity["BeginOffset"] = start + int(raw_entity["BeginOffset"])
            entity["EndOffset"] = start + int(raw_entity["EndOffset"])
            entities.append(entity)
    return entities


def _pii_circuit_is_open() -> bool:
    """Fail closed briefly after repeated Comprehend failures."""
    with _PII_CIRCUIT_LOCK:
        return monotonic() < _pii_open_until


def _record_pii_success() -> None:
    global _pii_failure_count, _pii_open_until
    with _PII_CIRCUIT_LOCK:
        _pii_failure_count = 0
        _pii_open_until = 0.0


def _record_pii_failure() -> None:
    global _pii_failure_count, _pii_open_until
    with _PII_CIRCUIT_LOCK:
        _pii_failure_count += 1
        if _pii_failure_count >= settings.PII_CIRCUIT_BREAKER_FAILURE_THRESHOLD:
            _pii_open_until = monotonic() + settings.PII_CIRCUIT_BREAKER_RESET_SECONDS


def scrub_pii(
    text: str,
    correlation_id: str,
    language: str | None = None,
    *,
    allowed_texts: Iterable[str] = (),
    allowed_name_texts: Iterable[str] = (),
    preserve_location_names: bool = False,
    preserve_person_names: bool = False,
) -> str:
    """Mask PII entities using Amazon Comprehend."""
    if not text:
        return text
    started = perf_counter()
    language_code = _pii_language_code(language or settings.COMPREHEND_PII_LANGUAGE_CODE)
    approved = tuple(allowed_texts)
    approved_names = tuple(allowed_name_texts)
    if language_code is None:
        scrubbed = _scrub_pattern_pii(text, approved)
        LOGGER.info(
            "pii_scrubbed_with_patterns",
            correlation_id=correlation_id,
            language=(language or "").split("-", 1)[0].lower(),
            changed=scrubbed != text,
            latency_ms=round((perf_counter() - started) * 1000, 2),
            remote=False,
        )
        return scrubbed
    try:
        entities = _detect_pii_entities(text, language_code)
    except (BotoCoreError, ClientError) as exc:
        _record_pii_failure()
        LOGGER.exception(
            "pii_scrub_failed",
            correlation_id=correlation_id,
            latency_ms=round((perf_counter() - started) * 1000, 2),
            remote=True,
        )
        raise AwsServiceError("Comprehend PII detection failed.") from exc
    _record_pii_success()
    scrubbed = text
    for entity in sorted(entities, key=lambda item: int(item["BeginOffset"]), reverse=True):
        start = int(entity["BeginOffset"])
        end = int(entity["EndOffset"])
        entity_text = text[start:end]
        entity_type = str(entity.get("Type") or "PII").upper()
        if _approved_entity(entity_text, approved):
            continue
        if entity_type == "NAME" and _approved_entity(entity_text, approved_names):
            continue
        if preserve_location_names and entity_type in {"ADDRESS", "LOCATION"} and _looks_like_location_name(entity_text):
            continue
        if preserve_person_names and entity_type == "NAME":
            continue
        scrubbed = f"{scrubbed[:start]}[{entity_type}]{scrubbed[end:]}"
    scrubbed = _scrub_pattern_pii(scrubbed, approved)
    LOGGER.info(
        "pii_scrubbed",
        correlation_id=correlation_id,
        entity_count=len(entities),
        language=language_code,
        latency_ms=round((perf_counter() - started) * 1000, 2),
        remote=True,
    )
    return scrubbed
