"""The conditions attached to a figure, and whether an answer kept them.

A minimum order is almost never one number. The records say things like:

    0,200CC as a first order for Preferred Customers, 7 800DZD ($60) and the
    equivalent of 5 000 DZD ($43) after the first purchase for all FBOs

    We do not have a minimum order in France, yet a newly sponsored Preferred
    Customer will have to order 150EUR minimum of products within 72 hours in
    order to validate his sponsorship

An answer that keeps the figure and drops "for Preferred Customers" is not
slightly incomplete. It is a different rule, told to the wrong person - and it
reads as authoritative, so nothing about it invites the reader to check. The
France answer delivered in the pilot said there is no minimum order, which is
the first half of a sentence whose second half is a 150EUR condition.

What counts as a qualification here is structural, not a list of known
sentences: a clause introduced by a word that narrows who, when or whether -
"for", "after", "as a", "within", "if", "unless", "provided", "per". That is
general to the corpus's phrasing rather than tied to any one record, which is
the point; a rule written for the France sentence would have to be rewritten
for the next market.

Deliberately conservative in one direction: it reports a qualification only for
phrasing it recognises, so a condition worded unusually is missed and the
answer is judged complete when it is not. Being wrong that way leaves current
behaviour; being wrong the other way would append text no source supports.
"""

from __future__ import annotations

import re

from utils.number_notation import readings_in

# Words that begin a clause narrowing who a figure applies to, when it applies,
# or whether it applies at all. Ordered longest first so "as a" is recognised
# before "as", and "in order to" before "in".
_QUALIFIER_OPENERS = (
    "provided that",
    "in order to",
    "as long as",
    "only for",
    "only if",
    "except",
    "unless",
    "within",
    "before",
    "during",
    "after",
    "as a",
    "an",
    "for",
    "per",
    "if",
    "when",
    "up to",
    "at least",
)

# A clause ends at a comma or semicolon, or at a conjunction starting a new
# statement.
#
# Never inside a figure. "0,200CC as a first order for Preferred Customers"
# split at the decimal comma into "0" and "200CC as a first order...", which
# attached the wrong half of the number to the condition - a figure appeared to
# be governed by a role it was not, and the check that reads this reported
# exactly backwards. A separator with digits on both sides is part of the
# number, not a clause boundary.
_CLAUSE_SPLIT_RE = re.compile(r"(?<!\d)[,;]|[,;](?!\d)|\band\b|\byet\b|\bbut\b", re.IGNORECASE)

_OPENER_RE = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(word) for word in _QUALIFIER_OPENERS) + r")(?!\w)",
    re.IGNORECASE,
)

# A qualification has to say something. "for" on its own, or "per order" where
# "order" is the field's own subject, is not a condition worth restoring.
_MIN_QUALIFIER_WORDS = 2


def qualifying_clauses(value: str) -> list[str]:
    """The clauses in `value` that narrow who, when or whether it applies.

    Returned as written, in the order the source wrote them, so a caller can
    put them back verbatim rather than paraphrasing a policy condition.
    """
    text = " ".join((value or "").split())
    if not text:
        return []

    clauses: list[str] = []
    for segment in _CLAUSE_SPLIT_RE.split(text):
        segment = segment.strip()
        if not segment:
            continue
        opener = _OPENER_RE.search(segment)
        if not opener:
            continue
        clause = segment[opener.start():].strip(" .")
        if len(clause.split()) < _MIN_QUALIFIER_WORDS + 1:
            continue
        if clause not in clauses:
            clauses.append(clause)
    return clauses


def _normalized(value: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", (value or "").casefold(), flags=re.UNICODE))


def _stem(word: str) -> str:
    """Drop a trailing plural so "Customer" and "Customers" are one word.

    A source writing "for Preferred Customers" and an answer writing "As a
    Preferred Customer" state the same condition, and comparing them letter for
    letter reported it missing.
    """
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def missing_qualifications(answer: str, value: str) -> list[str]:
    """Conditions the source attached to a figure that the answer does not carry.

    Matching is on the clause's own words rather than the exact string, because
    an answer may legitimately rephrase around it - "for Preferred Customers"
    and "Preferred Customers must" are the same condition. A clause counts as
    present when every one of its meaningful words appears in the answer.
    """
    normalized_answer = _normalized(answer)
    if not normalized_answer:
        return qualifying_clauses(value)

    answer_words = {_stem(word) for word in normalized_answer.split()}
    missing: list[str] = []
    for clause in qualifying_clauses(value):
        words = [
            _stem(word)
            for word in _normalized(clause).split()
            if word not in _QUALIFIER_OPENERS and len(word) > 2
        ]
        if words and not set(words) <= answer_words:
            missing.append(clause)
    return missing


def answer_keeps_every_condition(answer: str, value: str) -> bool:
    """Whether an answer carries every condition its source attached to a figure."""
    return not missing_qualifications(answer, value)


# The categories a figure can be attached to. Normalised to a token, so "all
# FBOs" and "an FBO" are the same category and "Preferred Customers" is not.
_ROLE_TOKENS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("preferred_customer", re.compile(r"\bpreferred\s+customers?\b", re.IGNORECASE)),
    (
        "distributor",
        re.compile(r"\bfbos?\b|\bdistributors?\b|\bbusiness\s+owners?\b", re.IGNORECASE),
    ),
)


# A sentence boundary ends a clause too. Without this, "As an FBO you order
# 0,200CC. Preferred Customers are covered separately." is one segment naming
# both categories, and a figure attached to the wrong one looks attached to
# both. Guarded against digits so a decimal point is not a boundary.
_SEGMENT_SPLIT_RE = re.compile(
    r"(?<!\d)[.!?](?!\d)|\n|" + _CLAUSE_SPLIT_RE.pattern, re.IGNORECASE
)


# A sentence boundary that a decimal cannot be mistaken for. Shared, because
# `personal_claims` had its own splitter without the digit guard and cut
# "0.200 CC" into "0." and "200 CC" - so a claim was reported as a fragment and
# a repair would have left the stray "200 CC" in the answer. One rule for what
# ends a sentence, used by everything that needs one.
_SENTENCE_END_RE = re.compile(r"(?<!\d)[.!?]+(?!\d)(?=\s|$)|\n+")


def sentences(text: str) -> list[str]:
    """Split into sentences without breaking a decimal figure.

    Boundaries are kept on the sentence they end, so joining the result
    reproduces the original text apart from the whitespace between sentences.
    """
    parts: list[str] = []
    position = 0
    for match in _SENTENCE_END_RE.finditer(text or ""):
        chunk = (text or "")[position:match.end()]
        if chunk.strip():
            parts.append(chunk)
        position = match.end()
    tail = (text or "")[position:]
    if tail.strip():
        parts.append(tail)
    return parts


def _segments(text: str) -> list[str]:
    return [segment.strip() for segment in _SEGMENT_SPLIT_RE.split(text or "") if segment.strip()]


def _roles_in(text: str) -> set[str]:
    return {token for token, pattern in _ROLE_TOKENS if pattern.search(text or "")}


def _figures_by_role(text: str) -> dict[str, set[str]]:
    """Which categories each figure is attached to, clause by clause."""
    attached: dict[str, set[str]] = {}
    for segment in _segments(text):
        roles = _roles_in(segment)
        if not roles:
            continue
        for reading in readings_in(segment, document_text=text):
            digits = re.sub(r"\D", "", reading.text)
            if digits:
                attached.setdefault(digits, set()).update(roles)
    return attached


def misattached_figures(answer: str, value: str) -> list[str]:
    """Figures the answer attaches to a different category than the source does.

    Stating the figure and stating the condition is not enough on its own. An
    answer can mention Preferred Customers somewhere, quote 0,200CC, and attach
    that figure to FBOs - every word present, every word in the wrong place,
    and the reader given a number that is not theirs.

    Only a genuine disagreement is reported: the figure must be attached to a
    category in both texts, and the two sets must not overlap. A figure the
    answer states without naming any category is a separate question, and
    `missing_qualifications` is what asks it.
    """
    source_roles = _figures_by_role(value)
    if not source_roles:
        return []
    answer_roles = _figures_by_role(answer)
    return [
        figure
        for figure, roles in source_roles.items()
        if figure in answer_roles and roles and answer_roles[figure] and not (roles & answer_roles[figure])
    ]


def value_is_conveyed(answer: str, value: str) -> bool:
    """Whether the answer already states the figures this field value states.

    Anchored on the figures, not on a substring and not on word coverage.

    A substring test called "As a first order for Preferred Customers the
    minimum order size is 2 CC" incomplete - it says exactly what the field
    says, in the other order, and shares no long substring with it.

    Word coverage failed the other way. A capture can run into the next field,
    so the "value" for Niger was "EUR81. Payment methods accepted: Bank
    Transfer, Cash", and an answer that happened to list the payment methods
    covered every word in it while never mentioning 81. The figure is the thing
    the field is about, so the figure is what has to be there.

    Separators are ignored in the comparison: a source writing "7 800DZD" and
    an answer writing "7800 DZD" are stating the same figure. Conditions are a
    separate question - see `missing_qualifications`.
    """
    figures = [
        re.sub(r"\D", "", reading.text)
        for reading in readings_in(value, document_text=value)
    ]
    if not figures:
        return _normalized(value) in _normalized(answer)
    answer_digits = re.sub(r"\D", "", answer or "")
    return all(figure and figure in answer_digits for figure in figures)
