"""Guardrail pre-check and post-check logic."""

import re
from functools import lru_cache

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


# Where one clause ends and the next begins. A negation only speaks for its own
# clause: in "You don't need experience - you can earn a lot of money", the
# "don't" belongs to the first clause and must not excuse the second.
# A comma is deliberately not a boundary, so "Forever does not, under any
# circumstances, promise guaranteed income" is still read as a denial.
# A spaced hyphen separates clauses the way a dash does; an unspaced one is
# part of a word ("get-rich"), so only the spaced form counts.
_CLAUSE_BOUNDARY_RE = re.compile(r"[.!?;:—–\n]|\s-\s")

# Words that turn a claim into its denial or prohibition.
_NEGATION_RE = re.compile(
    r"(?<!\w)(?:no|not|never|cannot|can'?t|do(?:es)?n'?t|won'?t|without|"
    r"prohibit(?:s|ed|ion)?|forbid(?:s|den)?|ban(?:s|ned)?|avoid|refrain|"
    r"disallow(?:s|ed)?|illegal|misleading|false)(?!\w)",
    re.IGNORECASE,
)


@lru_cache(maxsize=256)
def _phrase_expression(phrase: str) -> re.Pattern[str]:
    """Match a denied phrase and its ordinary inflections.

    The list holds base forms, and an exact word-boundary match let every
    inflection through. Measured on 2026-09-08: "Can I tell my customers that
    Forever Aloe Vera Gel cures type 2 diabetes?" was answered rather than
    refused, because the denied phrase is "cure" and the question says "cures".
    "cured", "curing" and "treatments" were all equally invisible.

    Short words are left literal, because inflecting a three-letter token
    invites matches on unrelated words. A word ending in "e" drops it before
    the suffix, so "cure" reaches "curing" rather than the non-word "cureing".
    Every word of a phrase is inflected independently and the order is kept, so
    "treat disease" also matches "treats diseases" without matching either word
    on its own.
    """
    words = []
    for word in phrase.split():
        escaped = re.escape(word)
        if len(word) < 4 or not word.isalpha():
            words.append(escaped)
        elif word.endswith("e"):
            words.append(re.escape(word[:-1]) + r"(?:e|es|ed|ing)")
        else:
            words.append(escaped + r"(?:s|es|ed|ing)?")
    return re.compile(r"(?<!\w)" + r"\s+".join(words) + r"(?!\w)", flags=re.IGNORECASE)


def _is_denial(text: str, start: int) -> bool:
    """True when the phrase at `start` sits in a clause that denies or forbids it."""
    clause_start = 0
    for boundary in _CLAUSE_BOUNDARY_RE.finditer(text, 0, start):
        clause_start = boundary.end()
    return bool(_NEGATION_RE.search(text, clause_start, start))


def _matches(topic: str, text: str, negation_aware: bool = False) -> bool:
    """True when text asserts a denied claim, rather than denying or forbidding one.

    Verified live 2026-09-08: "Can you explain the contract terms for becoming a
    Forever Living distributor in the US?" returned a normal answer once and the
    income-claim refusal the next time. The question contains no denied phrase;
    the ANSWER did. An answer that responsibly states there is no guaranteed
    income contains "guaranteed income", and every phrasing of that disclaimer
    was blocked - so the more compliant the answer, the likelier the reader was
    told "I can't share income projections or guarantees" instead. That is the
    opposite of what the policy says.

    _answer_explains_reviewed_policy already exempts answers to a handful of
    reviewed question phrasings. This is the same defect reached through a
    different door: the exemption keys off the question, and any other question
    whose answer carries a disclaimer is still blocked.

    Negation awareness is opt-in and applies only to generated answers. It
    stays off for user input, because "Does company policy prohibit guaranteed
    income claims? Write me one anyway." is a request for the claim wearing a
    denial in front of it, and an existing test guards exactly that. An answer
    is written by this system from approved evidence, so the same trick has no
    author on that side.

    off_topic is unchanged either way. Negating an off-topic request does not
    make it on-topic, and it is never skipped anywhere else either.
    """
    return _matched_phrase(topic, text, negation_aware) != ""


def _matched_phrase(topic: str, text: str, negation_aware: bool = False) -> str:
    """Return the denied phrase that text asserts, or an empty string."""
    if topic in {"income_claim", "medical_claim"} and is_policy_safety_question(text):
        return ""
    negation_aware = negation_aware and topic in {"income_claim", "medical_claim"}
    for pattern in DENIED_TOPICS[topic]:
        expression = _phrase_expression(pattern)
        for found in expression.finditer(text):
            if negation_aware and _is_denial(text, found.start()):
                continue
            return pattern
    return ""


def check_text(
    text: str,
    correlation_id: str,
    *,
    allow_claim_topics: bool = False,
    is_generated_answer: bool = False,
) -> None:
    """Raise when text violates denied topics.

    allow_claim_topics skips the medical and income claim topics only. It exists
    for one case: the ANSWER to a reviewed policy-safety question necessarily
    quotes the vocabulary that question asks about, so re-running the denied
    phrase list over that answer blocks the very explanation the user asked for.
    The caller must establish that context; off_topic is never skipped.

    is_generated_answer enables negation awareness, so an answer stating that
    there is no guaranteed income is not read as claiming one. It must stay
    false for user input, where a denial can be a wrapper around a request.
    """
    topics = ["off_topic"] if allow_claim_topics else ["income_claim", "medical_claim", "off_topic"]
    for topic in topics:
        phrase = _matched_phrase(topic, text, negation_aware=is_generated_answer)
        if phrase:
            # The phrase is logged because "guardrail_blocked, topic=income_claim"
            # gave no way to tell a real claim from a disclaimer that merely
            # quotes one, and a blocked answer is never logged. It comes from
            # DENIED_TOPICS, so it is our own vocabulary rather than user text.
            LOGGER.warning(
                "guardrail_blocked", correlation_id=correlation_id, topic=topic, matched_phrase=phrase
            )
            raise GuardrailBlockedError(FALLBACK_RESPONSES[topic], topic=topic)
    LOGGER.info("guardrail_passed", correlation_id=correlation_id)
