"""Amazon Comprehend PII scrubbing for input and output text."""

from botocore.exceptions import BotoCoreError, ClientError

from config import settings
from services.aws_clients import get_aws_clients
from utils.exceptions import AwsServiceError
from utils.logging import get_logger

LOGGER = get_logger("services.pii")


def _pii_language_code(language: str) -> str:
    """Return a Comprehend PII language code, falling back safely."""
    normalized = (language or settings.COMPREHEND_PII_LANGUAGE_CODE).split("-", 1)[0].lower()
    if normalized in settings.COMPREHEND_PII_LANGUAGE_CODES:
        return normalized
    return settings.COMPREHEND_PII_LANGUAGE_CODE


def scrub_pii(text: str, correlation_id: str, language: str | None = None) -> str:
    """Mask PII entities using Amazon Comprehend."""
    if not text:
        return text
    language_code = _pii_language_code(language or settings.COMPREHEND_PII_LANGUAGE_CODE)
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
        scrubbed = f"{scrubbed[:start]}[{entity['Type']}]{scrubbed[end:]}"
    LOGGER.info("pii_scrubbed", correlation_id=correlation_id, entity_count=len(response.get("Entities", [])), language=language_code)
    return scrubbed
