"""Claims about the reader that no source and no session could support.

An Algeria answer in the pilot told the reader what their purchase history was.
The pipeline has no purchase history. It has a session with a market, a
language and a declared role, and approved policy documents that describe rules
for categories of people. Nothing anywhere knows what this reader has bought,
what rank they hold, or whether they have already placed a first order.

An invented fact about the reader is worse than an invented fact about policy.
Policy is checkable - the document either says it or it does not. "You have
already placed your first order" is about the reader, they know it is wrong the
moment they read it, and everything else in the answer loses its authority with
it. It also lands people in the wrong branch of a rule: Algeria's first-order
figure is for a Preferred Customer's first order, and an existing FBO told it
is theirs has been given the wrong number.

The distinction drawn here is between a **rule** and a **record**:

    "You must order 2 CC as a first order."     a rule, addressed to the reader
    "You have already ordered 2 CC."            a record we do not have
    "As a Preferred Customer, you order 2 CC."  a rule for a stated category
    "As an existing FBO, you have ordered."     a claim about this reader

Rules use modals - must, can, may, will need to, should. Records use the past
tense, the perfect, or an assertion of current qualification. Only records are
removed.

Deliberately narrow. A claim phrased in a way not listed here survives, which
leaves current behaviour; removing an ordinary sentence would take a real
answer away from a reader who asked for it.

Nothing here is language-aware beyond English. That is a real gap and not a
silent one - `unsupported_personal_claims` is documented as English-only, and
an answer in another language passes through untouched.
"""

from __future__ import annotations

import re

# Sentence splitting that keeps a decimal, an abbreviation and a bullet intact,
# matching how the rest of the codebase bounds a sentence.
_SENTENCE_RE = re.compile(r"[^.!?\n]+(?:[.!?]+|\n|$)")

# The reader having done something, or already being something. Present perfect
# and past tense addressed to "you", and possessives over things only a record
# could know.
_RECORD_CLAIM_RES = (
    # "you have ordered", "you've already purchased", "you have not yet placed"
    re.compile(
        r"\byou(?:'ve|\s+have|\s+had)\s+(?:not\s+|never\s+|already\s+|recently\s+)*"
        r"(?:\w+ed|\w+en|been|placed|made|bought|ordered|purchased|reached|qualified)\b",
        re.IGNORECASE,
    ),
    # "you ordered", "you purchased", "you qualified", "you joined"
    re.compile(
        r"\byou\s+(?:already\s+|recently\s+|previously\s+)?"
        r"(?:ordered|purchased|bought|joined|enrolled|registered|qualified|sponsored|reached)\b",
        re.IGNORECASE,
    ),
    # "since you ordered", "after you placed", "when you purchased"
    re.compile(
        r"\b(?:since|after|when|because)\s+you\s+\w+ed\b",
        re.IGNORECASE,
    ),
    # "your first order was", "your previous orders", "your purchase history"
    re.compile(
        r"\byour\s+(?:previous|last|recent|first|current|existing)\s+"
        r"(?:order|orders|purchase|purchases|rank|level|position|status)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\byour\s+(?:purchase|order|account|transaction)\s+history\b", re.IGNORECASE),
    # "you are currently a Manager", "you are already an FBO"
    re.compile(
        r"\byou\s+are\s+(?:currently|already|now)\b",
        re.IGNORECASE,
    ),
    # "as an existing FBO, you ..." - asserts which category this reader is in
    re.compile(
        r"\bas\s+an?\s+(?:existing|current|active|new|newly\s+sponsored)\s+"
        r"(?:fbo|distributor|member|customer|preferred\s+customer)\b",
        re.IGNORECASE,
    ),
)

# A sentence that only states a rule, even when it uses the past tense
# somewhere, is not a record about the reader. Modals are the marker.
_RULE_RE = re.compile(
    r"\byou\s+(?:must|should|can|may|will|would|need\s+to|have\s+to)\b",
    re.IGNORECASE,
)

# A conditional puts the reader's state in the question, not in the answer:
# "if you have already ordered" claims nothing about whether they have.
_CONDITIONAL_RE = re.compile(r"\b(?:if|unless|whether|once|provided\s+that)\b", re.IGNORECASE)


def _sentences(answer: str) -> list[str]:
    return [match.group(0) for match in _SENTENCE_RE.finditer(answer or "") if match.group(0).strip()]


def _is_record_claim(sentence: str) -> bool:
    if _CONDITIONAL_RE.search(sentence):
        return False
    if not any(pattern.search(sentence) for pattern in _RECORD_CLAIM_RES):
        return False
    # A sentence that also states the rule is answering the question; the
    # modal is what makes it a rule rather than a record.
    return not _RULE_RE.search(sentence)


def unsupported_personal_claims(answer: str) -> list[str]:
    """Sentences asserting something about this reader that nothing can support.

    English only. An answer in another language returns nothing, which leaves
    current behaviour rather than removing text this cannot read.
    """
    return [sentence.strip() for sentence in _sentences(answer) if _is_record_claim(sentence)]


def remove_unsupported_personal_claims(answer: str) -> tuple[str, list[str]]:
    """Drop those sentences, keeping the rest of the answer intact.

    Same shape as numeric repair: remove the sentence, revalidate, and use the
    result only if it stands on its own. An answer that is nothing but such
    claims comes back empty, and an empty answer is not delivered.
    """
    removed: list[str] = []
    kept: list[str] = []
    for sentence in _sentences(answer):
        if _is_record_claim(sentence):
            removed.append(sentence.strip())
        else:
            kept.append(sentence)
    if not removed:
        return answer or "", []
    return re.sub(r"\n{3,}", "\n\n", "".join(kept)).strip(), removed
