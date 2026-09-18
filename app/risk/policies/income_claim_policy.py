"""Income claim risk policy."""

import re

from app.risk.models import PolicyAction, RiskContext, RiskIssue, RiskLevel
from app.risk.policies.income_claim_translations import (
    contains_translated_income_claim,
    contains_translated_income_context,
)
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
# W16b (2026-09-12): also "money is paid back / reimbursed", "repay the money".
_REFUND_MONEY_RE = re.compile(
    rf"\bmoney{_SEPARATOR}*back\b"
    r"|\b(?:refund(?:s|ed|ing)?|repa(?:y|ys|id|ying)|reimburs(?:e|es|ed|ing))\s+(?:of\s+)?"
    r"(?:(?:the|my|your|their|his|her|our|all)\s+)?money\b"
    r"|\bmoney\s+(?:(?:is|are|was|were|will\s+be|would\s+be|gets?|has\s+been|have\s+been|being)\s+)?"
    r"(?:(?:fully|promptly|always|then|also|immediately)\s+)?"
    r"(?:refunded|returned|reimbursed|repaid|paid\s+back|given\s+back)\b",
    re.IGNORECASE,
)
# Refunded money that comes back again and again, multiplied or with interest
# is a return, not a refund: "your money is returned every month", "money back
# twice over". Refund wording with such a word anywhere in its clause (up to
# ".", "!", "?", ";" or ":") is never masked, so "money" still counts next to
# the guarantee.
_RECURRING_GAIN_RE = re.compile(
    r"\b(?:twice|double\w*|tripl\w*|\w+fold|interest|profits?|gains?|dividends?|monthly|weekly|yearly|annually"
    r"|daily|(?:two|three|four|five|ten|many|several|\d+)\s+times|times\s+over"
    r"|(?:every|each|per)\s+(?:single\s+)?(?:day|week|month|year))\b",
    re.IGNORECASE,
)
# Fable W16 review, Fix A (2026-09-12): the recurring words above were a vocabulary list, and refunded money next to
# a prize still counted as a refund ("The guarantee covers defects; your money is returned in full, plus a new car."
# was allowed on every income layer). Beyond those words, a gain, premium, prize or lifestyle word, an addition
# ("plus ..." unless it is shipping, handling or taxes, "extra", "then some", "again and again"), a payout word, or an
# amount of 1,000 or more that is not a duration or percentage keeps the money counting.
_UNITS = r"(?:business|working|calendar|day|week|month|year|hour)s?"
_AMOUNT_GUARD = rf"(?<![\d.,])(?:\d{{1,3}}(?:[.,]\d{{3}})++|\d{{4,}}+)(?![\d.,]*+\s*+(?:{_UNITS}|%|percent)\b)"
_SHIPPING = r"(?:shipping|postage|delivery|handling|taxes|vat|duties|costs?|fees?|charges?)"
_GAIN_OR_PRIZE_RE = re.compile(
    r"(?:" + _RECURRING_GAIN_RE.pattern + r")"
    + r"|\b(?:premiums?|uplift|extra|multipl\w*|x\s*\d+|\d+\s*x|again,?\s+and\s+again|then\s+some|grand|\d+k"
    r"|thousands?|millions?|hundreds?|jackpots?|prizes?|gifts?|rewards?|royalt\w*|residuals?|upside"
    r"|wealth\w*|rich(?:es|er)?|millionaires?|retire\w*|lifestyle|freedom|streams?"
    r"|cars?|holidays?|vacations?|houses?|villas?|cruises?|yachts?|rolex|mercedes|tesla|bmw|bitcoin|crypto\w*"
    r"|pay(?:s|ing)?(?!\s+(?:for|by|to|via|through|with|on|in)\b)|payouts?|paychecks?"
    r"|paid(?!\s+(?:for|by|to|via|through|with|on|in|back)\b)"
    r"|payments?(?!\s+(?:method|card|provider|account|details|option|type|means))"
    rf"|plus(?!\s+(?:\w+\s+){{0,2}}{_SHIPPING}\b))\b"
    rf"|{_AMOUNT_GUARD}",
    re.IGNORECASE,
)
_CLAUSE_END_RE = re.compile(r"[.!?;:]")
_WINDOW_TOKEN_RE = re.compile(
    r"(?P<end>[.!?]+(?=\s|$))|[$€£¥]|\d+(?:[.,]\d+)*|\w+(?:['’]\w+)*"
)


def _mask_refund_money(segment: str, text: str | None = None, offset: int = 0) -> str:
    """Replace refund-money wording with " refund ", unless its clause in the whole text has a gain or prize."""
    if text is None:
        text = segment

    def replace(match: re.Match) -> str:
        # Fable W16 Fix A: only the clause around the refund wording is searched, not the wording itself ("paid
        # back" is refund wording, not pay).
        before = _CLAUSE_END_RE.split(text[:offset + match.start()])[-1]
        after = _CLAUSE_END_RE.split(text[offset + match.end():], maxsplit=1)[0]
        return match.group(0) if _GAIN_OR_PRIZE_RE.search(before) or _GAIN_OR_PRIZE_RE.search(after) else " refund "

    return _REFUND_MONEY_RE.sub(replace, segment)


# W18 (2026-09-12, candidate 0eb5493, diagnostic case 15): the answer to "What is the return policy?" described the FBO
# buyback: "that profit is deducted from your refund", "bonuses ... received by your upline are deducted from them",
# "a refund check equal to your cost of the products, minus bonuses you personally received". A profit, bonus or
# commission that is deducted, charged back or taken back (or that a refund is "minus"/"less") is taken away, not
# promised. It is masked only when judging a copula satisfaction guarantee (below); the earnings search still sees
# "profit". It is never masked when its line clause (up to ".", "!", "?", ";", ":" or a line break) has a negation
# ("no profit is deducted"), a gain or prize word, or another earnings, money or currency word inside the wording.
_DEDUCTION_NOUN = r"(?:profits?|bonus(?:es)?|commissions?)"
_DEDUCTED_ITEMS = rf"{_DEDUCTION_NOUN}(?:\s+(?:and|&)\s+(?:case\s+credits?|{_DEDUCTION_NOUN}))?"
_DEDUCTION_RE = re.compile(
    rf"\b{_DEDUCTED_ITEMS}(?:\s+[^\W\d_]+){{0,4}}?\s+(?:is|are|was|were|will\s+be|gets?)\s+"
    r"(?:deducted|charged\s+back|taken\s+back|subtracted|withheld)\b"
    rf"|\b(?:minus|less)\s+(?:(?:the|any|all|your)\s+)?{_DEDUCTED_ITEMS}\b",
    re.IGNORECASE,
)
_LINE_CLAUSE_END_RE = re.compile(r"[.!?;:\n]")
_NEGATION_RE = re.compile(r"\b(?:no|not|never|none|nothing|without|zero)\b|n['’]t\b", re.IGNORECASE)
_DEDUCTION_WORD_RE = re.compile(rf"{_DEDUCTION_NOUN}|case|credits?|and|minus|less", re.IGNORECASE)


def _mask_deductions(segment: str, text: str, offset: int) -> str:
    """Blank deduction wording (same length, so offsets into text still hold) unless its clause says otherwise."""

    def replace(match: re.Match) -> str:
        before = _LINE_CLAUSE_END_RE.split(text[:offset + match.start()])[-1]
        after = _LINE_CLAUSE_END_RE.split(text[offset + match.end():], maxsplit=1)[0]
        clause = f"{before} {match.group(0)} {after}"
        inner = [word for word in re.findall(r"\w+|[$€£¥]", match.group(0)) if not _DEDUCTION_WORD_RE.fullmatch(word)]
        if (
            _NEGATION_RE.search(clause)
            or _GAIN_OR_PRIZE_RE.search(before) or _GAIN_OR_PRIZE_RE.search(after)
            or any(_NEARBY_EARNINGS_RE.fullmatch(word) or _GAIN_OR_PRIZE_RE.fullmatch(word) for word in inner)
        ):
            return match.group(0)
        return "deducted".ljust(len(match.group(0)))

    return _DEDUCTION_RE.sub(replace, segment)


def _window_tokens(
    segment: str, text: str | None = None, offset: int = 0, percent: bool = False, deductions: bool = False,
) -> list[str | None]:
    """Words of a segment (at offset in text), with None marking each sentence end."""
    if text is None:
        text = segment
    if deductions:
        segment = _mask_deductions(segment, text, offset)
    masked = _mask_refund_money(segment, text, offset)
    if percent:
        masked = _PERCENT_RE.sub(" percent ", masked)
    return [None if token.group("end") else token.group(0) for token in _WINDOW_TOKEN_RE.finditer(masked)]


# W16b (2026-09-12): a product warranty is a consumer guarantee too. "The
# guarantee covers defects; the money is refunded within 30 days." was refused,
# because "guarantee" paired with the refunded "money". A guarantee is set aside
# as a warranty only when it covers, applies to or protects against defects,
# faults or damage (or defective products, or their repair or replacement), or
# products are "guaranteed free from defects", and that warranty object closes
# its clause: a sentence end, ";", or straight into refund wording ("... and the
# money is refunded"). It is then judged like every consumer guarantee above: an
# earnings word anywhere, or a money word (unmasked) nearby, keeps it.
_DEFECT_WORD = r"(?:defects?|faults?|damage|malfunctions?)"
_PRODUCT_WORD = r"(?:products?|items?|goods|merchandise)"
_BROKEN_WORD = r"(?:defective|faulty|damaged|broken)"
_WARRANTY_OBJECT = (
    rf"(?:(?:all|any|the|its|their|such|possible|hidden|material|manufacturing|product|workmanship)\s+){{0,3}}"
    rf"(?:{_DEFECT_WORD}(?:\s+(?:and|or)\s+(?:(?:material|manufacturing)\s+)?{_DEFECT_WORD})?"
    rf"(?:\s+(?:in|of|on)\s+(?:(?:the|any|all|our|its|their|these)\s+)?"
    rf"(?:{_PRODUCT_WORD}|materials?(?:\s+(?:and|or)\s+workmanship)?|workmanship))?"
    rf"|{_BROKEN_WORD}\s+{_PRODUCT_WORD}"
    rf"|(?:(?:the|free)\s+)?(?:repairs?|replacements?)(?:\s*(?:or|and|/)\s*(?:repairs?|replacements?))?\s+of\s+"
    rf"(?:(?:the|a|an|any|all|your|their)\s+)?(?:{_BROKEN_WORD}\s+)?{_PRODUCT_WORD})"
)
_WARRANTY_DURATION = (
    r"(?:\s+(?:for|within|during|up\s+to)\s+(?:(?:a|the|one|two|three|thirty|sixty|ninety)\s+)?(?:\(?\d+\)?\s+)?"
    r"(?:days?|months?|years?)(?:\s+(?:from|after|of)\s+(?:the\s+)?(?:date\s+of\s+)?purchase)?)?"
)
_WARRANTY_END = (
    r"(?=\s*(?:[.!?;](?:\s|$)|$)"
    r"|\s*,?\s+(?:(?:and|so|then)\s+)?(?:(?:the|your|their|any|a|full)\s+)*"
    rf"(?:refunds?\b|refunded\b|{_REFUND_MONEY_RE.pattern}))"
)
_WARRANTY_GUARANTEE = (
    r"\bguarantee[sd]?\s+(?:(?:also|only|fully)\s+)?(?:covers?|covered|covering|includes?|applies\s+to"
    rf"|protects?\s+(?:(?:you|customers|buyers)\s+)?against)\s+{_WARRANTY_OBJECT}{_WARRANTY_DURATION}{_WARRANTY_END}"
    rf"|\bguaranteed\s+(?:to\s+be\s+)?(?:free\s+(?:from|of)|against)\s+{_WARRANTY_OBJECT}{_WARRANTY_DURATION}"
    rf"{_WARRANTY_END}"
)
# W18 (2026-09-12, candidate 0eb5493, diagnostic case 15): "**100% product satisfaction is guaranteed.**" was not a
# consumer guarantee at all, so it paired with the buyback "profit" paragraphs later. A satisfaction guarantee with a
# verb between ("satisfaction is guaranteed", "customer satisfaction will be 100% guaranteed") is set aside under the
# warranty rule below: only when every earnings, money or currency word in the whole text is refund or deduction
# wording. "Satisfaction is guaranteed. ... you will make a lot of money." keeps it.
_COPULA_SATISFACTION_GUARANTEE = (
    rf"\b{_HUNDRED_PERCENT}(?:(?:customer|product)\s+)?satisfaction\s+(?:is|are|will\s+be)\s+"
    rf"(?:(?:always|fully)\s+)?{_HUNDRED_PERCENT}guaranteed\b"
)
_CONSUMER_OR_WARRANTY_RE = re.compile(
    rf"{CONSUMER_GUARANTEE_RE.pattern}|{_WARRANTY_GUARANTEE}|{_COPULA_SATISFACTION_GUARANTEE}", re.IGNORECASE
)
_COPULA_SATISFACTION_RE = re.compile(_COPULA_SATISFACTION_GUARANTEE, re.IGNORECASE)


def _is_warranty(match: re.Match) -> bool:
    """The match came from the warranty or copula-satisfaction shapes, not from CONSUMER_GUARANTEE_RE (tried first)."""
    consumer = CONSUMER_GUARANTEE_RE.match(match.string, match.start())
    return not (consumer and consumer.end() == match.end())


def _earnings_nearby(tokens: list[str | int | tuple[str, int] | None], at: int, step: int, is_evidence=None) -> bool:
    """Scan one direction: the whole sentence, then only the window beyond it."""
    words = 0
    crossed_sentence_end = False
    index = at + step
    while 0 <= index < len(tokens):
        position = index
        token = tokens[position]
        index += step
        if token is None:
            crossed_sentence_end = True
            continue
        if crossed_sentence_end and words >= CONSUMER_GUARANTEE_WINDOW:
            return False
        if is_evidence is not None:
            # The evidence check sees the whole stream, so it can look at the
            # token after this one ("30 days" is a duration, not an amount).
            if is_evidence(tokens, position):
                return True
        elif isinstance(token, str) and _NEARBY_EARNINGS_RE.fullmatch(token):
            return True
        words += 1
    return False


# A guarantee that only refers back to one already named: "Is there a specific
# aspect of the guarantee or return process you'd like to know more about?"
# Measured on 2026-09-12 (ec82147): the answer to "Is there a money-back
# guarantee?" was refused because, once the consumer guarantees were set aside,
# "the guarantee" in the closing question paired with the "money" of
# "money-back". Only a noun after a determiner counts. "this/that guarantee"
# followed by a pronoun, article or outcome is a verb ("Will this guarantee
# success?", "plans that guarantee you ..."), and "this/that guarantees" is
# always a verb, so neither is ever set aside.
_REFERRING_GUARANTEE_RE = re.compile(
    r"\b(?:the|our|your|its|their)\s+guarantees?\b"
    r"|\b(?:this|that)\s+guarantee\b(?!\s+(?:you|your|i|me|my|we|us|our|they|them|their|he|him|his|she|her|it|"
    r"its|a|an|the|that|this|every|each|all|any|some|success|results?)\b)",
    re.IGNORECASE,
)
# Beyond the earnings words and currencies above, a referring guarantee is kept
# when its sentence (or the window beyond it) speaks of pay, wealth or returns,
# or holds an amount: any number except a duration ("30 days", "(30) days",
# "30-day") or a percentage.
_REFERRING_EARNINGS_RE = re.compile(
    r"pay(?:s|ing|ment|ments|check|checks|out|outs)?|paid|rich(?:es)?|wealth\w*|financ\w*|fortunes?|lucrative"
    r"|thousands?|millions?|billions?|monthly|weekly|yearly|annual(?:ly)?|\w+fold|doubl\w*|tripl\w*|multipl\w*"
    r"|invest\w*|roi|francs?|cfa|rand|naira|shillings?|dirhams?|pesos?|rupees?|yen|yuan"
    r"|hundreds?|grand|compensat\w*|dividends?|retire\w*|jobs?|living|stakes?|upside",
    re.IGNORECASE,
)
_DURATION_RE = re.compile(r"(?:day|week|month|year|hour|business|working|calendar)s?", re.IGNORECASE)
_PERCENT_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|percent\b|per\s+cent\b)", re.IGNORECASE)


def _referring_evidence(tokens: list, index: int) -> bool:
    """An earnings, pay or currency word, or an amount that is not a duration."""
    token = tokens[index]
    if not isinstance(token, str):
        return False
    if _NEARBY_EARNINGS_RE.fullmatch(token) or _REFERRING_EARNINGS_RE.fullmatch(token):
        return True
    if token[0].isdigit():
        following = tokens[index + 1] if index + 1 < len(tokens) else None
        return not (isinstance(following, str) and _DURATION_RE.fullmatch(following))
    return False


# Fable W10c review (2026-09-12): the evidence words above are a vocabulary list,
# and 33 of 79 adversarial texts slipped past it on every income layer ("The
# guarantee: 20% return.", "ten grand a month", "quit your job", "retire early").
# A referring guarantee is therefore set aside only when its own sentence also
# shows it is the consumer guarantee: a consumer guarantee, or return, refund or
# product wording ("the guarantee or return process"). Without that positive
# anchor the text is judged exactly as before.
_ANCHOR_RE = re.compile(
    r"refund\w*|returns|returned|returning|replacements?|products?|purchases?|customers?|satisfaction"
    r"|warrant(?:y|ies)|defective|items?",
    re.IGNORECASE,
)
# "return" alone is also an investment return ("a 20% return"), so it anchors
# only before a word that makes it the consumer act ("return process", "return
# the product").
_RETURN_FOLLOWER_RE = re.compile(r"process|policy|period|window|the|it|them|your|my|a|an|any|this|that", re.IGNORECASE)


def _anchored(stream: list[str | tuple[str, int] | None], at: int) -> bool:
    """A consumer guarantee, or return/refund/product wording, in the referring guarantee's own sentence."""
    for step in (-1, 1):
        index = at + step
        while 0 <= index < len(stream):
            token = stream[index]
            if token is None:
                break
            if isinstance(token, tuple) and token[0] == "consumer":
                return True
            if isinstance(token, str):
                if _ANCHOR_RE.fullmatch(token):
                    return True
                if token.lower() == "return":
                    following = stream[index + 1] if index + 1 < len(stream) else None
                    if isinstance(following, str) and _RETURN_FOLLOWER_RE.fullmatch(following):
                        return True
            index += step
    return False


# Fable W10d review (2026-09-12): the anchor proves consumer wording is present,
# not that the guarantee is only about it ("Our guarantee to customers and
# FBOs: enough to live on", "The guarantee on returns: a new car every year").
# A referring guarantee is therefore set aside only when, as well as being
# anchored, its sentence is a question ("Is there a specific aspect of the
# guarantee or return process you'd like to know more about?") or it is
# directly conjoined with return/refund wording ("the guarantee or return
# process", "the guarantee and refund policy", "the guarantee/return policy";
# bare "returns" is not enough: "the guarantee and returns mean you never work
# again"), and no clause follows it in its sentence: no ":" or ";", and no ","
# or dash after it (", or the return process" excepted). Declarative "the/our
# guarantee ..." statements are never set aside.
_SENTENCE_END_RE = re.compile(r"[.!?]+(?=\s|$)")
_RETURN_WORDING = (
    r"(?:returns?|refunds?|replacements?|exchanges?)\s+"
    r"(?:process|policy|policies|period|window|terms|procedures?|rules|options?|conditions|rights)"
)
_CONJOINED_AFTER_RE = re.compile(
    rf"\s*(?:,\s*)?(?:or|and|nor|&|/)\s*(?:(?:the|our|your|its|their|a|an)\s+)?{_RETURN_WORDING}\b",
    re.IGNORECASE,
)
_CONJOINED_BEFORE_RE = re.compile(
    rf"\b{_RETURN_WORDING}\s*(?:,\s*)?(?:or|and|nor|&|/)\s*$",
    re.IGNORECASE,
)
_CLAUSE_BREAK_RE = re.compile(r"[:;—–]|\s-\s|,(?!\s*(?:or|and|nor)\b)", re.IGNORECASE)


def _question_or_conjoined(text: str, match: re.Match) -> bool:
    """The referring guarantee's sentence is a question, or the guarantee is conjoined with return wording."""
    end = _SENTENCE_END_RE.search(text, match.end())
    rest = text[match.end():end.start()] if end else text[match.end():]
    if _CLAUSE_BREAK_RE.search(rest):
        return False
    if end and "?" in end.group(0):
        return True
    return bool(_CONJOINED_AFTER_RE.match(rest)) or bool(_CONJOINED_BEFORE_RE.search(text, 0, match.start()))


# Earnings words that disqualify setting any consumer guarantee aside. Profit,
# money, commission and bonus are deliberately absent: return-policy answers use
# them ("refund the money", "Profit and Bonus" charge-backs).
# Fable W16 review, Fix B (2026-09-12): wealth and lifestyle outcomes are earnings words too, here and in the
# guarantee/earnings pairing ("Guaranteed free from defects, and guaranteed to make you rich." was allowed). Bare
# "rich" ("rich in nutrients") and "a wealth of" are deliberately not listed.
_LIFESTYLE = (
    r"millionaires?|wealthy|wealthier|build(?:ing)?\s+wealth|retire\s+(?:early|young|rich)"
    r"|quit\s+(?:your|my|the|his|her|their)\s+(?:day\s+)?jobs?|never\s+(?:have\s+to\s+|need\s+to\s+)?work\s+again"
    r"|(?:get|got|getting|be|become|becoming|make\s+you|making\s+you|makes\s+you|made\s+you|makes\s+people)\s+rich"
)
_TEXT_EARNINGS_RE = re.compile(
    rf"\b(?:earn(?:ed|ing|ings|s)?|incomes?|salar(?:y|ies)|wages?|{_LIFESTYLE})\b", re.IGNORECASE
)
# The pairing's earnings words; the message is already lower-cased.
_EARNINGS_MAIN_RE = re.compile(
    rf"\b(?:earn(?:ed|ing|ings|s)?|income|money|profit|revenue|salary|wage|wages|{_LIFESTYLE})\b"
)


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
    matches = list(_CONSUMER_OR_WARRANTY_RE.finditer(text))
    if not matches:
        return text
    # Each consumer guarantee becomes one token (its index), so a neighbouring
    # "money-back guarantee" never counts as an earnings word for another one.
    tokens: list[str | int | None] = []
    position = 0
    for index, match in enumerate(matches):
        tokens.extend(_window_tokens(text[position:match.start()], text, position))
        tokens.append(index)
        position = match.end()
    tokens.extend(_window_tokens(text[position:], text, position))

    copula = {index for index, match in enumerate(matches) if _COPULA_SATISFACTION_RE.fullmatch(match.group(0))}
    kept = {
        token for at, token in enumerate(tokens)
        if isinstance(token, int) and token not in copula
        and (_earnings_nearby(tokens, at, -1) or _earnings_nearby(tokens, at, 1))
    }
    # W16b: a warranty is set aside only when every money word in the whole text is refund wording, however far
    # apart: "The guarantee covers defects and the money is refunded. Join the team and after a few months you will
    # make a lot of money." keeps it.
    if any(isinstance(token, str) and _NEARBY_EARNINGS_RE.fullmatch(token) for token in tokens):
        kept.update(index for index, match in enumerate(matches) if _is_warranty(match) and index not in copula)
    # W18: a copula satisfaction guarantee ("satisfaction is guaranteed") follows the same whole-text rule, but here
    # deduction wording ("profit is deducted from your refund") is not a money word either. (A money word nearby is
    # also a money word anywhere, so the nearby check adds nothing for it.) Every other consumer guarantee and warranty
    # is judged exactly as before: masking deductions in their word window would push a later "make money" out of it
    # ("Money-back guarantee. Your profit is deducted from your refund and you will make money.").
    if copula:
        position = 0
        words: list[str | None] = []
        for match in matches:
            words.extend(_window_tokens(text[position:match.start()], text, position, deductions=True))
            position = match.end()
        words.extend(_window_tokens(text[position:], text, position, deductions=True))
        if any(isinstance(word, str) and _NEARBY_EARNINGS_RE.fullmatch(word) for word in words):
            kept.update(copula)

    # A referring guarantee ("the guarantee", "our guarantee") is set aside only
    # when a consumer guarantee was set aside above (so the text has no earnings
    # word) and no earnings, pay, currency word or amount sits in its sentence or
    # the window beyond it. "The guarantee also covers your monthly income", "our
    # guarantee: $5,000" and "the guarantee pays commissions" stay refused. It
    # must also be anchored: a consumer guarantee or return/refund/product
    # wording in its own sentence, and its sentence must be a question or
    # conjoin it with return wording.
    spans = [(match.start(), match.end(), match.group(0) if index in kept else " ")
             for index, match in enumerate(matches)]
    if len(kept) < len(matches):
        referring = [
            match for match in _REFERRING_GUARANTEE_RE.finditer(text)
            if not any(match.start() < end and start < match.end() for start, end, _ in spans)
        ]
        if referring:
            placeholders = sorted(
                [(start, end, ("consumer", index)) for index, (start, end, _) in enumerate(spans)]
                + [(match.start(), match.end(), ("referring", index)) for index, match in enumerate(referring)]
            )
            stream: list = []
            position = 0
            for start, end, placeholder in placeholders:
                stream.extend(_window_tokens(text[position:start], text, position, percent=True))
                stream.append(placeholder)
                position = end
            stream.extend(_window_tokens(text[position:], text, position, percent=True))
            for at, token in enumerate(stream):
                if isinstance(token, tuple) and token[0] == "referring" and not (
                    _earnings_nearby(stream, at, -1, _referring_evidence)
                    or _earnings_nearby(stream, at, 1, _referring_evidence)
                ) and _anchored(stream, at) and _question_or_conjoined(text, referring[token[1]]):
                    match = referring[token[1]]
                    spans.append((match.start(), match.end(), " "))
            spans.sort()

    parts: list[str] = []
    position = 0
    for start, end, replacement in spans:
        parts.append(text[position:start])
        parts.append(replacement)
        position = end
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
        is_claim_topic=True,
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
        if contains_translated_income_claim(message):
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
        earnings = _EARNINGS_MAIN_RE.search(message)
        return bool(guarantee and earnings)

    def has_income_context(self, message: str) -> bool:
        """Return whether a possible income route needs semantic confirmation.

        Context is deliberately broader than a confirmed claim. It preserves
        review for typical, projected, or personalised earnings questions while
        allowing an obviously unrelated planner false positive to reach normal
        knowledge retrieval.
        """
        normalized = (message or "").lower()
        return bool(
            self._contains_income_claim(normalized)
            or _EARNINGS_MAIN_RE.search(normalized)
            or _GAIN_OR_PRIZE_RE.search(normalized)
            or contains_translated_income_context(normalized)
        )
