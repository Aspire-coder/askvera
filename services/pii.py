"""Amazon Comprehend PII scrubbing for input and output text."""

import re
from collections.abc import Iterable

from botocore.exceptions import BotoCoreError, ClientError

from config import settings
from services.aws_clients import get_aws_clients
from utils.redaction import EMAIL_RE, GOVERNMENT_ID_RE, PHONE_RE, redact_payment_cards
from utils.exceptions import AwsServiceError
from utils.logging import get_logger

LOGGER = get_logger("services.pii")
SENSITIVE_PII_PLACEHOLDERS = frozenset(
    {
        "AWS_ACCESS_KEY",
        "AWS_SECRET_KEY",
        "BANK_ACCOUNT_NUMBER",
        "BANK_ROUTING",
        "CREDIT_DEBIT_CVV",
        "CREDIT_DEBIT_EXPIRY",
        "CREDIT_DEBIT_NUMBER",
        "DRIVER_ID",
        "GOVERNMENT_ID",
        "PASSPORT_NUMBER",
        "PASSWORD",
        "PAYMENT_CARD",
        "PIN",
        "SSN",
    }
)


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
        if re.search(r"\[(?:ADDRESS|EMAIL|PHONE|NAME|PII)\]\s*:", line, flags=re.IGNORECASE):
            continue
        had_placeholder = bool(
            re.search(r"\[(?:ADDRESS|EMAIL|PHONE|NAME|PII)\]", line, flags=re.IGNORECASE)
        )
        cleaned = re.sub(r"\s*\[(?:ADDRESS|EMAIL|PHONE|NAME|PII)\](?:\s*,\s*\[(?:ADDRESS|EMAIL|PHONE|NAME|PII)\])*", "", line, flags=re.IGNORECASE)
        cleaned = re.sub(r"\(\s*\)", "", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
        label_candidate = re.sub(r"[*_`]", "", cleaned).strip()
        if had_placeholder and re.fullmatch(r"(?:-\s*)?[^:\n]{1,80}:", label_candidate):
            continue
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

    scrubbed = GOVERNMENT_ID_RE.sub("[GOVERNMENT_ID]", text)
    scrubbed = redact_payment_cards(scrubbed)
    return PHONE_RE.sub(replace_phone, EMAIL_RE.sub(replace_email, scrubbed))


def scrub_pattern_pii(text: str, *, allowed_texts: Iterable[str] = ()) -> str:
    """Mask common language-neutral PII without making a remote AWS call."""
    return _scrub_pattern_pii(text, allowed_texts)


def scrub_pii(
    text: str,
    correlation_id: str,
    language: str | None = None,
    *,
    allowed_texts: Iterable[str] = (),
    preserve_location_names: bool = False,
) -> str:
    """Mask PII entities using Amazon Comprehend."""
    if not text:
        return text
    language_code = _pii_language_code(language or settings.COMPREHEND_PII_LANGUAGE_CODE)
    approved = tuple(allowed_texts)
    if language_code is None:
        scrubbed = _scrub_pattern_pii(text, approved)
        LOGGER.info(
            "pii_scrubbed_with_patterns",
            correlation_id=correlation_id,
            language=(language or "").split("-", 1)[0].lower(),
            changed=scrubbed != text,
        )
        return scrubbed
    try:
        response = get_aws_clients().comprehend.detect_pii_entities(
            Text=text[:5000],
            LanguageCode=language_code,
        )
    except (BotoCoreError, ClientError) as exc:
        LOGGER.exception("pii_scrub_failed", correlation_id=correlation_id)
        raise AwsServiceError("Comprehend PII detection failed.") from exc
    scrubbed = text
    for entity in sorted(response.get("Entities", []), key=lambda item: item["BeginOffset"], reverse=True):
        start = int(entity["BeginOffset"])
        end = int(entity["EndOffset"])
        entity_text = text[start:end]
        entity_type = str(entity.get("Type") or "PII").upper()
        if _approved_entity(entity_text, approved):
            continue
        if preserve_location_names and entity_type in {"ADDRESS", "LOCATION"} and _looks_like_location_name(entity_text):
            continue
        scrubbed = f"{scrubbed[:start]}[{entity_type}]{scrubbed[end:]}"
    scrubbed = _scrub_pattern_pii(scrubbed, approved)
    LOGGER.info("pii_scrubbed", correlation_id=correlation_id, entity_count=len(response.get("Entities", [])), language=language_code)
    return scrubbed
