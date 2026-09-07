"""Guardrail pre-check and post-check logic."""

import re

from config.guardrail_topics import DENIED_TOPICS
from config.vera_persona import FALLBACK_RESPONSES
from utils.exceptions import GuardrailBlockedError
from utils.logging import get_logger

LOGGER = get_logger("services.guardrails")


def is_policy_safety_question(text: str) -> bool:
    """Recognize questions about restrictions, not requests to make claims.

    Deliberately excludes compound requests and imperative instructions; those
    need per-intent routing rather than a whole-message safety exemption.
    """
    return bool(re.fullmatch(
        r"\s*(?:does (?:the |company |the company )?policy (?:prohibit|forbid|ban) "
        r"|what (?:does|do) (?:the |company |the company )?(?:policy|policies|rules) say about )"
        r"(?:guaranteed (?:income|earnings)(?: claims)?|medical advice|(?:medical|income|health) claims)\s*\?\s*",
        text, re.IGNORECASE,
    ))


def _matches(topic: str, text: str) -> bool:
    if topic in {"income_claim", "medical_claim"} and is_policy_safety_question(text):
        return False
    return any(re.search(r"(?<!\w)" + re.escape(pattern) + r"(?!\w)", text, flags=re.IGNORECASE)
               for pattern in DENIED_TOPICS[topic])


def check_text(text: str, correlation_id: str) -> None:
    """Raise when text violates denied topics."""
    for topic in ["income_claim", "medical_claim", "off_topic"]:
        if _matches(topic, text):
            LOGGER.warning("guardrail_blocked", correlation_id=correlation_id, topic=topic)
            raise GuardrailBlockedError(FALLBACK_RESPONSES[topic], topic=topic)
    LOGGER.info("guardrail_passed", correlation_id=correlation_id)
