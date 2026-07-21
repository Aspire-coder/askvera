"""Guardrail pre-check and post-check logic."""

import re

from config.guardrail_topics import DENIED_TOPICS
from config.vera_persona import FALLBACK_RESPONSES
from utils.exceptions import GuardrailBlockedError
from utils.logging import get_logger

LOGGER = get_logger("services.guardrails")


def _matches(topic: str, text: str) -> bool:
    return any(re.search(re.escape(pattern), text, flags=re.IGNORECASE) for pattern in DENIED_TOPICS[topic])


def check_text(text: str, correlation_id: str) -> None:
    """Raise when text violates denied topics."""
    for topic in ["income_claim", "medical_claim", "off_topic"]:
        if _matches(topic, text):
            LOGGER.warning("guardrail_blocked", correlation_id=correlation_id, topic=topic)
            raise GuardrailBlockedError(FALLBACK_RESPONSES[topic], topic=topic)
    LOGGER.info("guardrail_passed", correlation_id=correlation_id)
