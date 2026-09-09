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

# A clause ends at the next clause opener, a comma before another opener, a
# conjunction that starts a new statement, or the end of the value.
_CLAUSE_SPLIT_RE = re.compile(r"[,;]|\band\b|\byet\b|\bbut\b", re.IGNORECASE)

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

    answer_words = set(normalized_answer.split())
    missing: list[str] = []
    for clause in qualifying_clauses(value):
        words = [
            word
            for word in _normalized(clause).split()
            if word not in _QUALIFIER_OPENERS and len(word) > 2
        ]
        if words and not set(words) <= answer_words:
            missing.append(clause)
    return missing


def answer_keeps_every_condition(answer: str, value: str) -> bool:
    """Whether an answer carries every condition its source attached to a figure."""
    return not missing_qualifications(answer, value)


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
