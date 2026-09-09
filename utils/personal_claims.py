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

# Claiming to have looked something up. Unsupportable in principle - there is
# nothing to look in - and the one thing the reader's own statement cannot
# rescue. They can tell us they ordered yesterday; we still have not verified
# it, and saying we have is a different and worse claim than repeating them.
_VERIFICATION_CLAIM_RE = re.compile(
    r"\b(?:our|the)\s+(?:records?|system|database)\b"
    r"|\byour\s+account\s+(?:shows?|indicates?|confirms?)\b"
    r"|\bwe\s+(?:can\s+see|have\s+verified|can\s+confirm)\b"
    r"|\baccording\s+to\s+your\s+(?:account|record|records|history|profile)\b"
    r"|\bi\s+can\s+(?:see|confirm|verify)\s+that\s+you\b",
    re.IGNORECASE,
)

# Words too common to make a claim recognisably the reader's own.
_CORROBORATION_STOPWORDS = frozenset(
    {
        "your", "have", "has", "had", "been", "already", "that", "this", "with",
        "from", "will",
        # Connectives that introduce the claim rather than form part of it. A
        # reader saying "I placed my first order" has not said the word "since",
        # and requiring it would refuse every corroboration phrased this way.
        "since", "after", "when", "because", "while", "given", "recently",
        "previously",
    }
)


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


def _stem(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


# Where a claim about the reader ends and the policy answer begins. "You have
# already placed your first order, so the minimum is 7 800DZD" is a claim and a
# consequence, and only the claim is the reader's to corroborate - testing the
# whole sentence asks them to have said the figure too, which they never do.
_CLAIM_CLAUSE_SPLIT_RE = re.compile(
    r"(?<!\d)[,;](?!\d)|\bso\b|\btherefore\b|\bwhich means\b|\bthen\b", re.IGNORECASE
)


def _claim_clauses(sentence: str) -> list[str]:
    return [part.strip() for part in _CLAIM_CLAUSE_SPLIT_RE.split(sentence) if part.strip()]


def _reader_said(sentence: str, user_context: str) -> bool:
    """Whether the reader themselves supplied what this sentence claims.

    A reader who says "I placed my first order yesterday" has told us
    something, and an answer that uses it has invented nothing. Matched on the
    content words of the clause making the claim, so a restatement counts and
    an unrelated claim does not.

    This makes the claim a restatement, never a verification. Nothing here
    checked that the order happened; `_VERIFICATION_CLAIM_RE` is what stops the
    answer implying otherwise.
    """
    if not user_context:
        return False
    said = {
        _stem(word)
        for word in re.findall(r"[^\W_]+", user_context.casefold(), flags=re.UNICODE)
    }
    for clause in _claim_clauses(sentence):
        if not any(pattern.search(clause) for pattern in _RECORD_CLAIM_RES):
            continue
        words = {
            _stem(word)
            for word in re.findall(r"[^\W_]+", clause.casefold(), flags=re.UNICODE)
            if len(word) > 3 and word not in _CORROBORATION_STOPWORDS
        }
        if not words or not words <= said:
            return False
    return True


def _is_unsupported(sentence: str, supported: set[str], user_context: str = "") -> bool:
    # Claiming to have looked something up is unsupportable whatever the reader
    # said. They can tell us they ordered yesterday; we still have not verified
    # it, and saying we have is a different and worse claim than repeating them.
    if _VERIFICATION_CLAIM_RE.search(sentence):
        return True
    if _CONDITIONAL_RE.search(sentence):
        return False
    if any(pattern.search(sentence) for pattern in _RECORD_CLAIM_RES) and not _RULE_RE.search(
        sentence
    ):
        return not _reader_said(sentence, user_context)
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
        if _is_unsupported(sentence, supported, user_context)
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
        if _is_unsupported(sentence, supported, user_context):
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
