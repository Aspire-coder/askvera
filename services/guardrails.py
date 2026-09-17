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


# Wording that carries a negation word without negating anything. "Not only can
# you earn guaranteed income, you can retire early" asserts the claim twice over,
# and "no doubt" and "without question" are intensifiers. Reading any of these as
# a denial would let an affirmative claim through behind a one-word disguise, so
# a negation match is only a real negation when it is not one of these.
_FALSE_NEGATION_RE = re.compile(
    r"(?:not|no)\s+(?:only|just|merely)(?!\w)"
    r"|no\s+doubt(?!\w)"
    r"|without\s+(?:a\s+)?(?:doubt|question)(?!\w)",
    re.IGNORECASE,
)


def _is_denial(text: str, start: int) -> bool:
    """True when the phrase at `start` sits in a clause that denies or forbids it.

    A negation only counts when it actually reverses the clause. Quotation marks
    are deliberately not consulted: quoting a claim is not rejecting it, and
    deciding which side of a quotation the writer stands on is not something a
    regex can establish. An explicit rejection that follows the quote instead of
    preceding it is therefore still read as an assertion and refused, which is
    the strict direction.
    """
    clause_start = 0
    for boundary in _CLAUSE_BOUNDARY_RE.finditer(text, 0, start):
        clause_start = boundary.end()
    for negation in _NEGATION_RE.finditer(text, clause_start, start):
        if _FALSE_NEGATION_RE.match(text, negation.start()):
            continue
        return True
    return False


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


# Generated answers only. A UK retail answer was refused as a medical claim
# because it said products may be sold "within the section of the premises where
# the service is supplied (for example, a treatment room)". "treatment" there
# names a place, not a remedy. The skip is deliberately narrow: only "room(s)" or
# "area(s)" directly after it, and never when the same clause names a condition,
# patient or remedy - "used in cancer treatment areas" and "a treatment room for
# eczema patients" are claims and stay blocked (Fable review). "treat disease"
# and "cure" are separate phrases that still match on their own.
_PREMISES_AFTER_TREATMENT_RE = re.compile(r"\s+(?:rooms?|areas?)(?!\w)", re.IGNORECASE)
_MEDICAL_CONTEXT_RE = re.compile(
    r"(?<!\w)(?:cancer\w*|tumou?r\w*|chemo\w*|arthritis|rheumat\w*|gout|eczema|psoriasis|acne|diabet\w*|"
    r"diseases?|ill|illness(?:es)?|sick\w*|sufferers?|infections?|inflamm\w*|conditions?|patients?|pains?|"
    r"injur(?:y|ies)|wounds?|symptoms?|disorders?|syndromes?|ibs|blood\s+pressure|hypertens\w*|obes\w*|"
    r"cholesterol|asthma|allerg(?:y|ies|ic)|migrain\w*|depression|anxiety|insomnia|therap(?:y|ies)|medical|"
    r"recover\w*|cur(?:e|es|ed|ing)|heal(?:s|ed|ing)?|remed(?:y|ies))(?!\w)",
    re.IGNORECASE,
)
# Sentence scope, not clause scope: a line break or semicolon must not separate
# "treatment rooms" from "for eczema". A "." inside "09.00" is not a boundary.
_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?](?=\s|$)")


def _is_premises_treatment(text: str, start: int, end: int) -> bool:
    """True when "treatment" at [start, end) names a room or area in a sentence with no medical context."""
    if not _PREMISES_AFTER_TREATMENT_RE.match(text, end):
        return False
    sentence_start = 0
    for boundary in _SENTENCE_BOUNDARY_RE.finditer(text, 0, start):
        sentence_start = boundary.end()
    sentence_end_match = _SENTENCE_BOUNDARY_RE.search(text, end)
    sentence_end = sentence_end_match.start() if sentence_end_match else len(text)
    return not _MEDICAL_CONTEXT_RE.search(text, sentence_start, sentence_end)


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
            if (
                negation_aware
                and topic == "medical_claim"
                and pattern == "treatment"
                and _is_premises_treatment(text, found.start(), found.end())
            ):
                continue
            return pattern
    return ""


def asserts_denied_claim(topic: str, text: str) -> bool:
    """True when a generated answer affirmatively asserts a denied claim.

    The clause-level reading of _matched_phrase, exposed for the risk layer so
    that both enforcement points judge an answer by the same rule rather than
    each carrying its own idea of what counts as a claim. Generated answers
    only -- negation awareness is unsafe on user input, where a denial can be
    a wrapper around a request.
    """
    if topic not in {"income_claim", "medical_claim"}:
        return False
    return _matched_phrase(topic, text, negation_aware=True) != ""


def check_text(
    text: str,
    correlation_id: str,
    *,
    allow_claim_topics: bool = False,
    is_generated_answer: bool = False,
) -> None:
    """Raise when text violates denied topics.

    allow_claim_topics no longer skips a topic. It used to drop income_claim and
    medical_claim outright for the ANSWER to a reviewed policy-safety question,
    on the grounds that such an answer necessarily quotes the vocabulary the
    question asks about. That reasoning is sound about the question and says
    nothing about the answer: it trusted an entire generated answer because of
    how the user had phrased their question, so an affirmative income guarantee
    sitting inside that answer had nothing left to catch it.

    Every topic is now always checked. What distinguishes an explanation from an
    assertion is the clause-level negation awareness below, which reads the
    answer's own text: "Forever prohibits promising guaranteed income" denies the
    claim in the clause that contains it and passes, while "you will earn
    guaranteed income" asserts it and is refused, whatever the question was.
    The parameter is retained so that both enforcement layers keep receiving the
    one gated value GovernanceEngine computes (see RiskEngine.evaluate, which
    uses it to reach asserts_denied_claim).

    is_generated_answer enables that negation awareness. It must stay false for
    user input, where a denial can be a wrapper around a request.
    """
    for topic in ("income_claim", "medical_claim", "off_topic"):
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
