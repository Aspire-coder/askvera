"""Amazon Comprehend PII scrubbing for input and output text."""

import re
from collections.abc import Iterable

from botocore.exceptions import BotoCoreError, ClientError

from config import settings
from services.aws_clients import get_aws_clients
from utils.exceptions import AwsServiceError
from utils.logging import get_logger

LOGGER = get_logger("services.pii")

EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])", re.UNICODE)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{5,}\d)(?!\w)", re.UNICODE)


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
    return False


def _scrub_pattern_pii(text: str, allowed_texts: Iterable[str]) -> str:
    """Mask language-neutral email and phone patterns without a remote call."""
    approved = tuple(allowed_texts)

    def replace_email(match: re.Match[str]) -> str:
        return match.group(0) if _approved_entity(match.group(0), approved) else "[EMAIL]"

    def replace_phone(match: re.Match[str]) -> str:
        return match.group(0) if _approved_entity(match.group(0), approved) else "[PHONE]"

    return PHONE_RE.sub(replace_phone, EMAIL_RE.sub(replace_email, text))


def scrub_pii(
    text: str,
    correlation_id: str,
    language: str | None = None,
    *,
    allowed_texts: Iterable[str] = (),
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
        if _approved_entity(text[start:end], approved):
            continue
        scrubbed = f"{scrubbed[:start]}[{entity['Type']}]{scrubbed[end:]}"
    LOGGER.info("pii_scrubbed", correlation_id=correlation_id, entity_count=len(response.get("Entities", [])), language=language_code)
    return scrubbed
