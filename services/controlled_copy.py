"""Safe on-demand localization for reviewed conversational copy."""

from __future__ import annotations

import re
from functools import lru_cache

from botocore.exceptions import BotoCoreError, ClientError

from config import settings
from services.aws_clients import get_aws_clients
from utils.logging import get_logger

LOGGER = get_logger("services.controlled_copy")
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
_LINK_OR_EMAIL_RE = re.compile(r"(?:https?://|www\.|\b[^\s@]+@[^\s@]+\b)", re.IGNORECASE)


@lru_cache(maxsize=256)
def localize_reviewed_copy(source_text: str, language: str, response_key: str = "") -> str | None:
    """Translate reviewed copy without adding facts, promises, or contact details."""
    source = (source_text or "").strip()
    locale = (language or "").split("-", 1)[0].split("_", 1)[0].lower()
    if not source or not locale or locale == "en":
        return source or None

    system_prompt = (
        "Translate reviewed customer-service safety copy into the requested language. "
        "Preserve the exact meaning and the product name AskVera. Do not add facts, "
        "numbers, promises, citations, links, email addresses, phone numbers, or advice. "
        "Return only the translated text, with no label or commentary."
    )
    user_prompt = f"Target language code: {locale}\nText:\n{source}"
    try:
        response = get_aws_clients().bedrock_runtime.converse(
            modelId=settings.BEDROCK_MODEL_ARN,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": user_prompt}]}],
            inferenceConfig={"maxTokens": 256, "temperature": 0},
        )
        candidate = response["output"]["message"]["content"][0].get("text", "").strip()
    except (BotoCoreError, ClientError, KeyError, IndexError, TypeError):
        LOGGER.exception(
            "controlled_copy_localization_failed",
            language=locale,
            response_key=response_key,
        )
        return None

    if not _is_safe_translation(source, candidate):
        LOGGER.warning(
            "controlled_copy_localization_rejected",
            language=locale,
            response_key=response_key,
        )
        return None
    return candidate


def _is_safe_translation(source: str, candidate: str) -> bool:
    if not candidate or len(candidate) > max(800, len(source) * 4):
        return False
    if _NUMBER_RE.findall(candidate) != _NUMBER_RE.findall(source):
        return False
    if not _LINK_OR_EMAIL_RE.search(source) and _LINK_OR_EMAIL_RE.search(candidate):
        return False
    return "```" not in candidate
