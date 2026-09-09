"""Claims about the reader that no source and no session could support.

An Algeria answer in the pilot described the reader's purchase history. There
is no purchase history anywhere in this system. What the pipeline does hold is
a session - a market, a language and a declared role - and whatever the reader
has said about themselves in the conversation.

An invented fact about the reader is worse than an invented fact about policy.
Policy is checkable against the document. "You have already placed your first
order" is about the reader, who knows immediately that it is wrong, and
everything else in the answer loses its authority with it. It also puts them in
the wrong branch of a rule: Algeria's 0,200CC is a Preferred Customer's first
order, and an existing FBO told it is theirs has the wrong number.

Two kinds of claim, and only one of them depends on context.

**Records.** Purchases, past actions, ranks reached, qualifications held.
Nothing in this system can supply these, so no context makes them supportable
and they are always removed.

**Categories.** "As an existing FBO, you..." and "As a Preferred Customer,
you..." are the same *kind* of statement, and neither phrase is safe or unsafe
on its own. Which one is an assumption depends on what is known:

    session role active_distributor  "As an existing FBO"      supported
    session role active_distributor  "As a Preferred Customer" an assumption
    reader said "I'm a Preferred Customer"  either             supported

So the check reads the session role and the reader's own words, and asks
whether the category the answer asserts is one of them. An earlier version
decided this from the phrases alone, which got both of these backwards.

Role-specific advice is the useful part of an answer, so removing a sentence
that carries a condition would cost the reader the qualification along with the
assumption. `remove_unsupported_personal_claims` refuses to repair when that
would happen, leaving the answer to be refused rather than quietly stripped.

Nothing here is language-aware beyond English. A non-English answer passes
through untouched, which leaves current behaviour rather than guessing at
another language's grammar.
"""

from __future__ import annotations

import re

from utils.qualifications import qualifying_clauses

# Sentence splitting that keeps a decimal, an abbreviation and a bullet intact.
_SENTENCE_RE = re.compile(r"[^.!?\n]+(?:[.!?]+|\n|$)")

# Claims nothing in this system can support, whatever the session says. A
# session declares what someone is, never what they have done.
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
    re.compile(r"\b(?:since|after|when|because)\s+you\s+\w+ed\b", re.IGNORECASE),
    # "your first order was", "your previous orders", "your purchase history"
    re.compile(
        r"\byour\s+(?:previous|last|recent|first|current|existing)\s+"
        r"(?:order|orders|purchase|purchases|rank|level|position|status)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\byour\s+(?:purchase|order|account|transaction)\s+history\b", re.IGNORECASE),
)

# "You are currently a Manager." A rank is a record, not a category: no session
# declares one and no document says which one this reader holds. Handled apart
# from the patterns above because the same frame introduces a category, which
# context *can* support - so this fires only when no known category is named.
_STANDING_CLAIM_RE = re.compile(
    r"\byou\s+are\s+(?:currently|already|now)\b|\byou\s+(?:have\s+)?(?:hold|holds|reached)\b",
    re.IGNORECASE,
)

# Categories an answer can place the reader in, and the session role that makes
# each one a statement of what is known rather than an assumption. A category
# with no session role - Preferred Customer, since no session declares one -
# can only be supported by the reader saying so.
_CATEGORY_PATTERNS: tuple[tuple[str, re.Pattern[str], frozenset[str]], ...] = (
    (
        "preferred customer",
        re.compile(r"\bpreferred\s+customers?\b", re.IGNORECASE),
        frozenset(),
    ),
    (
        "established distributor",
        re.compile(
            r"\b(?:existing|current|active|established)\s+"
            r"(?:fbo|distributors?|members?|business\s+owners?)\b",
            re.IGNORECASE,
        ),
        frozenset({"active_distributor"}),
    ),
    (
        "new distributor",
        re.compile(
            r"\b(?:new|newly\s+sponsored|prospective)\s+"
            r"(?:fbo|distributors?|members?|business\s+owners?)\b",
            re.IGNORECASE,
        ),
        frozenset({"new_prospect"}),
    ),
)

# A sentence places the reader in a category when it addresses them and names
# one: "As an existing FBO, you...", "You are currently a Preferred Customer".
_ADDRESSES_READER_RE = re.compile(r"\byou(?:'re|'ve|r)?\b", re.IGNORECASE)
_CATEGORY_FRAME_RE = re.compile(
    r"\bas\s+an?\b|\byou\s+are\s+(?:currently|already|now)\b|\byou\s+are\s+an?\b",
    re.IGNORECASE,
)

# A rule, not a record. The modal is what makes it one.
_RULE_RE = re.compile(
    r"\byou\s+(?:must|should|can|may|will|would|need\s+to|have\s+to)\b",
    re.IGNORECASE,
)

# A conditional puts the reader's state in the question, not in the answer:
# "if you have already ordered" claims nothing about whether they have.
_CONDITIONAL_RE = re.compile(r"\b(?:if|unless|whether|once|provided\s+that)\b", re.IGNORECASE)


def supported_categories(role: str = "", user_context: str = "") -> set[str]:
    """Categories the session or the reader's own words place them in.

    The session role is structural evidence. The reader's words are taken only
    when they say it of themselves - "I am a Preferred Customer" - never from a
    category merely mentioned in a question about one.
    """
    supported = {
        name
        for name, _, roles in _CATEGORY_PATTERNS
        if (role or "") in roles
    }
    said = user_context or ""
    for name, pattern, _ in _CATEGORY_PATTERNS:
        for match in pattern.finditer(said):
            before = said[max(0, match.start() - 40):match.start()]
            if re.search(
                r"\bi\s*(?:'m|\s+am)\b[^.?!]*$|\bmy\s+status\b[^.?!]*$|\bas\s+an?\s*$",
                before,
                re.IGNORECASE,
            ):
                supported.add(name)
    return supported


def _sentences(answer: str) -> list[str]:
    return [
        match.group(0)
        for match in _SENTENCE_RE.finditer(answer or "")
        if match.group(0).strip()
    ]


def _asserted_categories(sentence: str) -> set[str]:
    """Categories this sentence places *the reader* in, if any."""
    if not (_ADDRESSES_READER_RE.search(sentence) and _CATEGORY_FRAME_RE.search(sentence)):
        return set()
    return {name for name, pattern, _ in _CATEGORY_PATTERNS if pattern.search(sentence)}


def _is_unsupported(sentence: str, supported: set[str]) -> bool:
    if _CONDITIONAL_RE.search(sentence):
        return False
    if any(pattern.search(sentence) for pattern in _RECORD_CLAIM_RES) and not _RULE_RE.search(
        sentence
    ):
        return True
    asserted = _asserted_categories(sentence)
    if asserted:
        return not (asserted <= supported)
    # A standing claim naming no category we recognise is a rank or a status,
    # which nothing can support.
    return bool(_STANDING_CLAIM_RE.search(sentence)) and not _RULE_RE.search(sentence)


def unsupported_personal_claims(
    answer: str, *, role: str = "", user_context: str = ""
) -> list[str]:
    """Sentences asserting something about this reader that nothing supports.

    `role` is the session's declared role and `user_context` the reader's own
    words. Both widen what counts as supported; neither can make a claim about
    purchases or past actions supportable, because nothing holds those.

    English only. An answer in another language returns nothing, which leaves
    current behaviour rather than removing text this cannot read.
    """
    supported = supported_categories(role, user_context)
    return [
        sentence.strip()
        for sentence in _sentences(answer)
        if _is_unsupported(sentence, supported)
    ]


def remove_unsupported_personal_claims(
    answer: str, *, role: str = "", user_context: str = ""
) -> tuple[str, list[str]]:
    """Drop those sentences, unless dropping them would cost a condition.

    Role-specific advice is the useful part of an answer. A sentence can carry
    both an assumption about the reader and the condition that makes the figure
    beside it correct - "As a Preferred Customer, you order 0,200CC as a first
    order" - and removing it takes the qualification with the assumption,
    leaving a figure with nothing saying who it applies to. That is the defect
    the completeness work exists to prevent, arriving by a different route.

    So a removal that would strip a condition the rest of the answer does not
    carry is refused, and the answer is returned unchanged for the caller to
    refuse outright. An answer that is nothing but such claims comes back
    empty, and an empty answer is not delivered.
    """
    removed: list[str] = []
    kept: list[str] = []
    supported = supported_categories(role, user_context)
    for sentence in _sentences(answer):
        if _is_unsupported(sentence, supported):
            removed.append(sentence.strip())
        else:
            kept.append(sentence)
    if not removed:
        return answer or "", []

    repaired = re.sub(r"\n{3,}", "\n\n", "".join(kept)).strip()
    if _would_lose_a_condition(removed, repaired):
        return answer or "", []
    return repaired, removed


def _would_lose_a_condition(removed: list[str], repaired: str) -> bool:
    """Whether the removed text carried a condition the rest does not."""
    kept_words = set(re.findall(r"[^\W_]+", repaired.casefold(), flags=re.UNICODE))
    for sentence in removed:
        for clause in qualifying_clauses(sentence):
            words = [
                word
                for word in re.findall(r"[^\W_]+", clause.casefold(), flags=re.UNICODE)
                if len(word) > 3
            ]
            if words and not set(words) <= kept_words:
                return True
    return False
