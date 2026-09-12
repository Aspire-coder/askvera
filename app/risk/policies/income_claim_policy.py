"""Income claim risk policy."""

import re

from app.risk.models import PolicyAction, RiskContext, RiskIssue, RiskLevel
from app.risk.rules import RiskPolicyMetadata
from config.guardrail_topics import DENIED_TOPICS
from services.guardrails import is_policy_safety_question


# Recognize status context, but never remove earnings words: doing so can
# hide a later dollar/bonus guarantee in the same message.
EARNED_STATUS_RE = re.compile(
    r"\bearn(?:ed|ing|s)?\s+(?:(?:a|an|the|my|your|their|our|his|her)\s+)?"
    r"(?:sales\s+(?:level|rank)|rank|active\s+status)\b"
    r"|\b(?:sales\s+(?:level|rank)|rank|active\s+status)\s+"
    r"(?:itself\s+)?(?:once|is|was|has\s+been)\s+earned\b",
    re.IGNORECASE,
)
NEGATED_STATUS_GUARANTEE_RE = re.compile(
    r"\b(?:does\s+not|doesn['’]t|do\s+not|don['’]t)\s+guarantee\s+"
    r"(?:active\s+status|the\s+other|retention\s+of\s+another\s+status)\b",
    re.IGNORECASE,
)

# Consumer-protection guarantees promise a refund, a replacement or product
# satisfaction - never an income outcome. Measured on 2026-09-12: "What is the
# return policy?" was answered with the income refusal, because the return
# policy (US/CA/Benelux 21.03, Nordic 21.02, UK 21.3) says customers "are
# guaranteed 100% product satisfaction" and, sentences later, mentions
# refunding "the money" and charging back the "Profit and Bonus". "Is there a
# money-back guarantee?" was refused outright. Only these shapes are
# disregarded; every other "guarantee" still pairs with an earnings word.
_SEPARATOR = r"[\s\-‐-―]"
_GUARANTEE_FORM = r"guarantee[sd]?"
_HUNDRED_PERCENT = r"(?:100\s*(?:%|percent|per\s+cent)\s*)?"
CONSUMER_GUARANTEE_RE = re.compile(
    rf"\bmoney{_SEPARATOR}*back{_SEPARATOR}*{_GUARANTEE_FORM}\b"
    rf"|\b{_GUARANTEE_FORM}\s+(?:a\s+)?{_HUNDRED_PERCENT}(?:(?:customer|product)\s+)?satisfaction"
    rf"(?:\s+{_GUARANTEE_FORM})?\b"
    rf"|\b{_HUNDRED_PERCENT}(?:(?:customer|product)\s+)?satisfaction\s+{_GUARANTEE_FORM}\b"
    rf"|\b(?:refund|replacement){_SEPARATOR}+{_GUARANTEE_FORM}\b"
    rf"|\bwarrant(?:y|ies)\s*(?:and\s*/\s*or|and|or|/)\s*{_GUARANTEE_FORM}\b",
    re.IGNORECASE,
)
# A consumer guarantee is NOT disregarded when an earnings word or a currency
# appears anywhere in the same sentence, or within this many words of it across
# a sentence end: "money-back guarantee of income", "satisfaction guarantee:
# salary", "earn $5,000 a month, all of it backed by our money-back guarantee".
# Only ".", "!" or "?" before whitespace ends a sentence; line breaks, colons
# and semicolons do not. Such text is then judged exactly as before.
CONSUMER_GUARANTEE_WINDOW = 6
_NEARBY_EARNINGS_RE = re.compile(
    r"earn\w*|incomes?|money|profits?|revenues?|salar(?:y|ies)|wages?|commissions?|bonus(?:es)?|payouts?|cash"
    r"|dollars?|euros?|pounds?|kronor|kroner|kr|usd|eur|gbp|sek|dkk|nok|chf|[$€£¥]",
    re.IGNORECASE,
)
# Refund wording describes the guarantee itself, not earnings. It is masked only
# for the nearby-earnings check; the earnings search below still sees "money".
_REFUND_MONEY_RE = re.compile(
    rf"\bmoney{_SEPARATOR}*back\b"
    r"|\brefund(?:s|ed|ing)?\s+(?:of\s+)?(?:(?:the|my|your|their|his|her|our)\s+)?money\b"
    r"|\bmoney\s+(?:(?:is|was|will\s+be)\s+)?(?:refunded|returned)\b",
    re.IGNORECASE,
)
_WINDOW_TOKEN_RE = re.compile(
    r"(?P<end>[.!?]+(?=\s|$))|[$€£¥]|\d+(?:[.,]\d+)*|\w+(?:['’]\w+)*"
)


def _window_tokens(segment: str) -> list[str | None]:
    """Words of a segment, with None marking each sentence end."""
    masked = _REFUND_MONEY_RE.sub(" refund ", segment)
    return [None if token.group("end") else token.group(0) for token in _WINDOW_TOKEN_RE.finditer(masked)]


def _earnings_nearby(tokens: list[str | int | None], at: int, step: int) -> bool:
    """Scan one direction: the whole sentence, then only the window beyond it."""
    words = 0
    crossed_sentence_end = False
    index = at + step
    while 0 <= index < len(tokens):
        token = tokens[index]
        index += step
        if token is None:
            crossed_sentence_end = True
            continue
        if crossed_sentence_end and words >= CONSUMER_GUARANTEE_WINDOW:
            return False
        if isinstance(token, str) and _NEARBY_EARNINGS_RE.fullmatch(token):
            return True
        words += 1
    return False


# Earnings words that disqualify setting any consumer guarantee aside. Profit,
# money, commission and bonus are deliberately absent: return-policy answers use
# them ("refund the money", "Profit and Bonus" charge-backs).
_TEXT_EARNINGS_RE = re.compile(r"\b(?:earn(?:ed|ing|ings|s)?|incomes?|salar(?:y|ies)|wages?)\b", re.IGNORECASE)


def _without_consumer_guarantees(text: str) -> str:
    """Blank out consumer-protection guarantees that stand apart from earnings words."""
    # Fable INT4 review A1: with the sentence window alone, "You'll earn $5,000 a
    # month. That is backed by our money-back guarantee." (and 7 similar texts,
    # earnings more than 6 words away across a sentence end) went from refused
    # to allowed on every income layer. An earnings word anywhere in the text
    # means the consumer guarantee may be lending "guarantee" to an earnings
    # statement, so the text is judged exactly as before.
    if _TEXT_EARNINGS_RE.search(text):
        return text
    matches = list(CONSUMER_GUARANTEE_RE.finditer(text))
    if not matches:
        return text
    # Each consumer guarantee becomes one token (its index), so a neighbouring
    # "money-back guarantee" never counts as an earnings word for another one.
    tokens: list[str | int | None] = []
    position = 0
    for index, match in enumerate(matches):
        tokens.extend(_window_tokens(text[position:match.start()]))
        tokens.append(index)
        position = match.end()
    tokens.extend(_window_tokens(text[position:]))

    kept = {
        token for at, token in enumerate(tokens)
        if isinstance(token, int) and (_earnings_nearby(tokens, at, -1) or _earnings_nearby(tokens, at, 1))
    }

    parts: list[str] = []
    position = 0
    for index, match in enumerate(matches):
        parts.append(text[position:match.start()])
        parts.append(match.group(0) if index in kept else " ")
        position = match.end()
    parts.append(text[position:])
    return "".join(parts)


class IncomeClaimPolicy:
    """Flag income and earnings claim language for governance visibility."""

    metadata = RiskPolicyMetadata(
        name="income_claim",
        version="2026.2",
        description="Detects guaranteed-income or earnings-claim language.",
        enabled=True,
        risk_level=RiskLevel.HIGH,
        action=PolicyAction.REFUSE,
    )
    phrases = tuple(DENIED_TOPICS["income_claim"])

    def evaluate(self, context: RiskContext) -> list[RiskIssue]:
        message = (context.user_message or "").lower()
        if is_policy_safety_question(message):
            return []
        if not self._contains_income_claim(message):
            return []
        return [
            RiskIssue(
                code="INCOME_CLAIM_RISK",
                message="User message contains income or earnings claim language.",
                level=RiskLevel.HIGH,
                action=PolicyAction.REFUSE,
                source="business_policy",
                policy=self.metadata.name,
                policy_version=self.metadata.version,
            )
        ]

    def _contains_income_claim(self, message: str) -> bool:
        """Detect configured phrases and generic guarantee/earnings combinations."""
        if any(phrase in message for phrase in self.phrases):
            return True
        # Only exclude an explicit denial about status when the text actually
        # discusses earning a status. Positive guarantees anywhere still count.
        guarantee_text = (
            NEGATED_STATUS_GUARANTEE_RE.sub(" ", message)
            if EARNED_STATUS_RE.search(message) else message
        )
        # A refund, replacement or satisfaction guarantee is not an income
        # guarantee; any other guarantee in the text is judged as before.
        guarantee_text = _without_consumer_guarantees(guarantee_text)
        guarantee = re.search(r"\bguarantee(?:d|s|ing)?\b", guarantee_text)
        earnings = re.search(
            r"\b(?:earn(?:ed|ing|ings|s)?|income|money|profit|revenue|salary|wage|wages)\b",
            message,
        )
        return bool(guarantee and earnings)
