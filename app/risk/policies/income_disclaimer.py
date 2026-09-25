"""Exact-match mask for the company's own mandatory income disclaimer.

IncomeClaimPolicy._contains_income_claim refuses any generated answer that
contains a "guarantee" word anywhere alongside an earnings word (income,
money, ...) anywhere else in the same text (app/risk/policies/income_claim_
policy.py, _contains_income_claim). That pairing is not sentence-scoped, so
it also fires on the company's OWN legally mandated disclaimer sentence,
because the sentence itself says "guarantees" next to "income": Company
Policy 1.01(d), "Forever makes no guarantees regarding income or success."
Three real generated answers (R10E r10-05, r10-06, r10-07) were wrongly
refused for exactly this reason (2026-09-25).

This module recognises ONLY a small, explicitly approved list of disclaimer
sentence variants -- never anything else -- and blanks out just the
"guarantee" word(s) inside a matched sentence, leaving every other character
(including the sentence's own "income" word) untouched. The disclaimer's
"income" word therefore still counts as an earnings-word trigger for any
OTHER, unrelated guarantee claim elsewhere in the same answer: this mask
narrows one specific false positive, it does not create a blind spot for
real guarantee/earnings pairings.

Approval: each variant below requires owner + compliance sign-off before it
is added to ACTIVE_VARIANTS. Approved 2026-09-25 (owner, in writing):
EN-1 and EN-2 only. ES-1 (the equivalent US-ES 1.01(d) sentence) and every
other route-copy translation are DELIBERATELY NOT enabled -- see
DISABLED_VARIANTS below, kept only as documentation. Enabling any of those
needs its own owner + compliance sign-off; do not add them here without it.

Residual, owner-accepted risk (2026-09-25, re-measured after all three
2026-09-25 review rounds). Exactly three shapes are NOT caught by the
adjacency guard below, and none is a defect to fix here:
  1. Money-free rebuttals or dismissals ("my upline says otherwise",
     "nobody on my team has ever struggled"). No money is named, so no
     income detector catches them, and the same statements are already
     allowed today in any answer without the disclaimer.
  2. A money-naming statement more than two word-bearing sentences away
     from the disclaimer in either direction (headings, short filler
     sentences like "Really.", and blank lines all count toward that
     distance once they contain a word; genuinely empty/punctuation-only
     fragments do not -- see _prev_neighbours/_next_neighbours). The guard
     only inspects the two nearest word-bearing neighbouring sentences on
     each side.
  3. An amount with no currency sign, word, or code MONEY_RE recognises
     ("5,000 a month", "a 30% return every month", "five grand a month").
     MONEY_RE is deliberately currency-anchored (never bare digits), so an
     unanchored figure does not withhold the exemption via the
     _money_elsewhere check either.
These are DELIBERATELY not extended further: widening the earnings-word
check to match ANY earnings word anywhere in the answer (not just within
the two-neighbour window) would re-refuse legitimate answers like r10-06,
which legitimately says "FBOs ... can earn money by selling them" several
sentences away from its own disclaimer. Do not try to close this gap by
widening the vocabulary or the window further without re-measuring r10-06.

Review round 2 (2026-09-25) closed the previously-flagged gap where a cue or
a money-bearing statement placed one short filler sentence, heading, or
paragraph away from the disclaimer ("... success. Really. But everyone makes
money.") slipped past the guard: the guard inspects the SECOND neighbouring
sentence on each side (see guarded_spans below; round 3 tightened this to
the two nearest WORD-BEARING sentences), and separately withholds the
exemption whenever a currency-anchored amount (MONEY_RE) appears anywhere
else in the answer, however far away.

Review round 3 (2026-09-25) fixed two blocking issues found in round 2's
implementation: (N1) an uncapped neighbour scan combined with F4's
abbreviation-safe sentence boundary made a text with no upper-case-following
period anywhere (e.g. an all-lower-case repeat of the disclaimer) scan to
the edge of the whole text for every span, 85-104 s on a 200 KB shape --
fixed by capping each neighbour scan at _NEIGHBOUR_CAP characters and
failing closed (withholding the exemption) when no boundary is found within
the cap. (N2) "\n\n" before or after the disclaimer produced an empty
"sentence" that trivially passed every guard check, silently disabling the
guard on that side -- fixed by skipping empty/punctuation-only fragments and
using the two nearest sentences that actually contain a word character.
Round 3 also tightened the F3 line-break boundaries themselves (a previous
line must genuinely end its own sentence; a no-period right boundary now
requires a blank line or end of text, not merely a line that looks
structural).
"""

from __future__ import annotations

import re

from app.risk.policies.income_claim_translations import GUARANTEE_RE, fold
from app.risk.policies.income_projection import MONEY_RE as _AMOUNT_RE

# ---------------------------------------------------------------------------
# Approved variant table
# ---------------------------------------------------------------------------
# Each entry: variant_id -> (language, source_note, exact sentence text).
# ENABLED variants only. Adding an entry here requires owner + compliance
# sign-off (see module docstring); do not add or edit without it.
ACTIVE_VARIANTS: dict[str, tuple[str, str, str]] = {
    "EN-1": (
        "en",
        "US-EN Company Policy 1.01(d)",
        "Forever makes no guarantees regarding income or success.",
    ),
    "EN-2": (
        "en",
        "US-EN Company Policy 1.01(d), 'Individual results may vary.' + "
        "'Forever makes no guarantees regarding income or success.' joined by ', and' "
        "(seen live in R10E r10-06)",
        "Individual results may vary, and Forever makes no guarantees regarding income or success.",
    ),
}

# NOT enabled. Kept only for documentation of what was considered and
# explicitly declined on 2026-09-25; do not move any of these into
# ACTIVE_VARIANTS without a fresh owner + compliance sign-off.
DISABLED_VARIANTS: dict[str, tuple[str, str, str]] = {
    "ES-1": (
        "es",
        "US-ES Company Policy 1.01(d) -- deliberately not enabled",
        "Forever no ofrece garantía de ingresos o éxito.",
    ),
}

# ---------------------------------------------------------------------------
# Sentence matching (ported from the measured prototype: scratchpad/income_step2/proto_mask.py)
# ---------------------------------------------------------------------------
# Allowed normalisation only:
#   - whitespace runs (including line breaks) collapsed
#   - letter case folded
#   - straight vs curly quotes treated as equivalent
#   - markdown emphasis markers (*, _, **, ...) and list/blockquote markers
#     (-, *, >, digit+".") stripped at the sentence's edges
#   - an optional final period
# No word may be added, removed, changed or reordered, and no other
# punctuation is allowed inside the sentence. A sentence that continues past
# the variant text must NOT match.
# Whitespace runs at the sentence edges are capped at _EDGE_SPACE characters. Uncapped, adjacent runs backtrack
# against each other and against the right-boundary lookahead, which is quadratic on a long run of spaces. A capped
# run can only fail to match (the answer is then judged exactly as today), never match something new.
#
# The repeated groups below use possessive quantifiers (`{0,40}+`, `{1,3}+`, `{0,4}+`, ...). Without them, two
# adjacent capped-but-still-bounded groups (e.g. an edge-space run followed by an edge-marker run, both of which can
# match the empty string or many overlapping widths) can backtrack against each other and against the right-boundary
# lookahead: still linear in theory but with a large constant, and quadratic-shaped on some 200 KB inputs (measured:
# 28.5 s). A possessive quantifier commits to its first (longest) match and never backtracks into it, so each
# character is visited O(1) times. This can only make a match FAIL where it previously succeeded through
# backtracking into one of these groups (the answer is then judged exactly as today, i.e. refused); it can never
# turn a non-match into a match, because possessive quantifiers only forbid backtracking paths the greedy version
# also tried first. Differential-tested against the greedy version over 80,000 random boundary shapes: 0 diffs
# (scratchpad/income_step2/fable_review/possessive2.py).
_EDGE_SPACE = 40
_EDGE_OPEN_QUOTES = "\"“”„«'‘’"
_EDGE_CLOSE_QUOTES = "\"“”»'‘’"
_EDGE_OPEN = (
    rf"(?:[ \t]{{0,{_EDGE_SPACE}}}+(?:[-*•+]|\d{{1,2}}[.)]|>)[ \t]{{1,{_EDGE_SPACE}}}+)?[ \t]{{0,{_EDGE_SPACE}}}+"
    rf"(?:[*_]{{1,3}}+|[{_EDGE_OPEN_QUOTES}]){{0,4}}+[ \t]{{0,{_EDGE_SPACE}}}+"
)
# _EDGE_CLOSE is deliberately left NON-possessive (unlike _EDGE_OPEN above). The 28.5 s blowup measured before this
# fix came entirely from the OPEN side: several adjacent, independently-bounded groups before "core" that all have
# to be retried in combination once "core" or the right boundary fails further along, which is what makes it
# quadratic-shaped. The CLOSE side has no such adjacent group to interact with, and re-timing every measured
# worst-case shape (scratchpad/income_step2/fable_review/perf.py, perf2.py) with only _EDGE_OPEN possessive-ized
# already brings every one under 0.1 s -- so _EDGE_CLOSE keeps its original backtracking, limited, bounded
# repetition. Making it possessive too was tried and reverted: on a repeated disclaimer with 40 characters of
# separator whitespace before the next occurrence, a possessive close cannot give back the whitespace it
# committed to when the trailing lookahead then fails, so it drops the current match instead of falling back to a
# shorter one -- and that shifted *which* occurrence gets matched, which a differential test over 80,000 random
# boundary shapes caught as a genuine new match (never acceptable per this module's own fail-closed contract).
# Left exactly as before this fix.
_EDGE_CLOSE = rf"[ \t]{{0,{_EDGE_SPACE}}}(?:[*_]{{1,3}}|[{_EDGE_CLOSE_QUOTES}]){{0,4}}"
# Right boundary, no-period case: end of text, or a blank line. Nothing else. A bare "\n" onto a lower-case
# continuation line ("...success\nfor people who don't work...") was already rejected; review round 3 (N3)
# tightened this further to also reject a next line that merely LOOKS structural ("**for people who don't
# work.**", "- for people who don't work; ..."), which is still the same sentence continuing, just formatted --
# only a genuine blank line or the end of the text ends it.
_NO_PERIOD_END = r"\Z|[ \t]*\n[ \t]*(?:\n|\Z)"
_ENGLISH_GUARANTEE = re.compile(r"(?a)guarantee\w*", re.IGNORECASE)


def _words(sentence: str) -> list[str]:
    return re.findall(r"[^\W_]+(?:['’][^\W_]+)*", sentence)


def _variant_regex(sentence: str) -> re.Pattern[str]:
    """Build a linear-time whole-sentence regex for one approved variant."""
    words = [re.escape(w) for w in _words(sentence)]
    seps = re.split(r"[^\W_]+(?:['’][^\W_]+)*", sentence)
    body = ""
    for i, w in enumerate(words):
        if i:
            sep = seps[i]
            if sep.strip() == "":
                body += r"\s+"
            else:
                body += r"\s*" + re.escape(sep.strip()) + r"\s+"
        body += w
    # Left boundary: start of text, or immediately after a sentence-ending
    # punctuation + space (optionally through closing quote/emphasis marks),
    # or immediately after a line break. Never after ':' ',' ';' or a word
    # character on the same line without a sentence boundary between them.
    left = (
        r"(?:(?<=\A)|(?<=[.!?][ \t])|(?<=[.!?][\"”'’*_][ \t])"
        r"|(?<=[.!?][\"”'’*_]{2}[ \t])|(?<=\n))"
    )
    # Right boundary: optional final period, optional closing quotes/
    # emphasis, then end of text, a line break, or whitespace before the
    # next sentence (only when a period was present).
    right = rf"(?:(?P<p>{_EDGE_CLOSE}\.{_EDGE_CLOSE})(?=\s|\Z)|{_EDGE_CLOSE}(?={_NO_PERIOD_END}))"
    return re.compile(left + _EDGE_OPEN + "(?P<core>" + body + ")" + right, re.IGNORECASE)


_COMPILED: list[tuple[str, re.Pattern[str]]] | None = None


def _compiled() -> list[tuple[str, re.Pattern[str]]]:
    global _COMPILED
    if _COMPILED is None:
        _COMPILED = [(vid, _variant_regex(text)) for vid, (_, _, text) in ACTIVE_VARIANTS.items()]
    return _COMPILED


# F3 left-boundary post-filter. The compiled regex's own left lookahead accepts any bare "\n" (fixed-width
# lookbehinds can't inspect a whole, variable-length previous line), so a genuine match is re-checked here: when the
# match is only reachable by crossing a line break, the line break is a real sentence boundary only if the previous
# non-blank line ends with sentence punctuation (optionally through closing marks) or is itself blank/absent. This
# can only discard a match the regex already found (fail closed, judged exactly as an unmatched sentence today);
# it never manufactures a new match. Validated against R10E, must-catch, and the adversarial/round2 datasets
# (scratchpad/income_step2/fable_review/fix_experiment.py).
_LEFT_EDGE_CHARS = " \t*_\"“”„«'‘’>-•+.)0123456789"
# N3 (review round 3): the previous NON-BLANK LINE must actually END its own sentence -- [.!?:] optionally
# followed by a run of closing quote/emphasis marks -- not merely end in some character that happened to be in an
# ad hoc accepted set (the old set accepted a bare ")" or "*", which let "Nobody believes (as everyone knows)"
# and "Nobody believes *this*" wrongly open a new sentence on the next line). A blank previous line is still fine
# (paragraph break).
_PREV_LINE_END_RE = re.compile(r"[.!?:][*_\"“”'‘’]*$")


def _left_boundary_ok(text: str, start: int) -> bool:
    i = start
    while i and text[i - 1] in _LEFT_EDGE_CHARS:
        i -= 1
    if i and text[i - 1] == "\n":
        newline_pos = i - 1
        line_start = text.rfind("\n", 0, newline_pos) + 1
        line = text[line_start:newline_pos].rstrip(" \t")
        if line and not _PREV_LINE_END_RE.search(line):
            return False
    return True


def find_spans(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, variant_id) for every approved-variant sentence match, sorted by position."""
    out: list[tuple[int, int, str]] = []
    for vid, rx in _compiled():
        for m in rx.finditer(text):
            start = m.start("core")
            if not _left_boundary_ok(text, start):
                continue
            out.append((start, m.end("core"), vid))
    return sorted(out)


# ---------------------------------------------------------------------------
# Fail-closed adjacency guard (ported from scratchpad/income_step2/guard_proto.py)
# ---------------------------------------------------------------------------
# The exemption is withheld -- today's refusing behaviour kept -- when the
# sentence immediately before or immediately after a matched disclaimer
# contrasts with it, dismisses it, or refers back to it. This can only make
# a match MORE conservative (turn an exemption back off); it never grants
# an exemption the sentence match itself did not find.
_GUARD_CUES = re.compile(
    r"(?<!\w)(?:"
    # contrast / pivot
    r"but|however|still|yet|though|although|that\s+said|even\s+so|nevertheless|nonetheless|in\s+(?:practice|reality|fact)"
    r"|actually|realistically|honestly|truth\s+is|the\s+good\s+news"
    r"|except|unless|other\s+than|officially|on\s+paper|technically|of\s+course|regardless|sure"
    # dismissal
    r"|ignore|disregard|forget|boilerplate|lawyers?|legal(?:ese|ities)?|fine\s+print|formality|technicality|outdated"
    r"|not\s+true|untrue|false|myth|nonsense|joke|yeah,?\s+right|seriously|don'?t\s+worry|lies?|wink"
    # back-reference to the disclaimer itself
    r"|(?:that|this|it)(?:'s|\s+is|\s+was)?\s+(?:just|only|merely|simply|wording|statement|line|disclaimer|sentence|rule|bit|part)"
    r"|(?:that|this)\s+(?:wording|statement|line|disclaimer|sentence|rule|bit|part)"
    # Spanish cues (harmless to keep even though ES-1 itself is not enabled)
    r"|pero|sin\s+embargo|aun\s+as[ií]|no\s+obstante|en\s+(?:la\s+)?(?:pr[aá]ctica|realidad)|de\s+hecho|realmente"
    r"|ignor\w*|olv[ií]d\w*|abogados?|letra\s+peque[nñ]a|no\s+es\s+(?:cierto|verdad)|falso|mito|tonter[ií]a"
    r")(?!\w)",
    re.IGNORECASE,
)
# F4: a "." only ends the guard's neighbouring sentence when it is followed by whitespace AND an upper-case
# letter, a digit (the start of the next numbered item), or nothing (end of text) -- mirroring
# income_projection.sentences()'s own abbreviation-safe split. A lower-case letter after the whitespace means the
# "." was an abbreviation ("U.S.", "e.g.") and the sentence continues past it, so the guard keeps scanning. A bare
# line break is still always a boundary (unambiguous, not abbreviation-prone).
_SENT_END = re.compile(r"[.!?](?=[\"”'’*_)\]]*(?:\s+[A-Z0-9]|\s*$))|\n")


_PREV_EDGE = " \t*_\"“”'’>-•"
# F4: also skip a leading numbered-list marker ("2. ") before searching for the next sentence end, so the marker's
# own period is never mistaken for the end of the (empty) "sentence" it introduces -- see
# "1. {EN1}\n2. But everyone makes money." in the module's fixtures.
_NEXT_LEAD = re.compile(r"[.\s\"“”'’*_]*(?:\d{1,2}[.)][ \t]*)?")


# N1 (2026-09-25 review round 3, blocking performance): _SENT_END (F4) only ends a sentence at an upper-case/digit
# boundary, so a text where a period is always followed by a lower-case letter ("forever makes no guarantees
# regarding income or success. " repeated) never ends a sentence at all -- the neighbour scan below would then walk
# to the edge of the whole text for every span, and so would every cue/earnings/money regex run over that scan
# (measured: 85-104 s on a 200 KB repeat of exactly that shape). Each direction is therefore capped at
# _NEIGHBOUR_CAP characters: if no sentence boundary is found within the cap, the scan gives up and the caller
# withholds the exemption (fail closed -- this can only turn a would-be-allowed span into a refused one, since the
# uncapped scan would have kept looking for cues/earnings/money in exactly the text the capped scan gave up on).
_NEIGHBOUR_CAP = 4000
# N2 (review round 3, blocking): a paragraph break ("\n\n") before or after the disclaimer used to fill a
# neighbour slot with an empty or punctuation-only fragment (the text between two adjacent "\n" sentence-ends),
# which trivially passes every cue/earnings/money check and so silently disabled the guard on that side. Neighbours
# are therefore the two NEAREST sentences that contain at least one word character in each direction, skipping any
# empty or punctuation-only fragment (blank lines, a bare "---", etc.) -- headings and short fragments like
# "Really." still count, since they do contain a word character; only truly empty/punctuation-only stretches are
# skipped.
_HAS_WORD = re.compile(r"\w")
_MAX_SKIPPED_FRAGMENTS = 6


# Both helpers work on offsets into the whole text and never copy the text before or after a match, so the guard
# costs time proportional to the neighbouring sentences, not to the answer: an answer repeating the disclaimer
# thousands of times would otherwise be quadratic. Each returns (begin, end), or None when no sentence boundary
# was found within _NEIGHBOUR_CAP characters (N1: fail closed, see above).
def _prev_sentence_bounds(text: str, start: int) -> tuple[int, int] | None:
    head_end = start
    while head_end and text[head_end - 1] in _PREV_EDGE + "\n":
        head_end -= 1
    stop = max(0, head_end - 1)
    begin = max(0, stop - _NEIGHBOUR_CAP)
    ends = [m.end() for m in _SENT_END.finditer(text, begin, stop)]
    if not ends and begin > 0:
        return None
    return (ends[-1] if ends else 0), head_end


def _prev_sentence(text: str, start: int) -> str:
    bounds = _prev_sentence_bounds(text, start)
    return text[bounds[0]:bounds[1]] if bounds else ""


def _next_sentence_bounds(text: str, end: int) -> tuple[int, int] | None:
    begin = _NEXT_LEAD.match(text, end).end()
    limit = min(len(text), begin + _NEIGHBOUR_CAP)
    m = _SENT_END.search(text, begin, limit)
    if m is not None and limit < len(text):
        # N7 (review round 4): with endpos=limit, the "\s*$" lookahead also matches at the cap itself, so a period
        # sitting just before the cap looked like a sentence end even when a lower-case run-on continues past it.
        # Only the first match can be such a phantom (it needs the cap right after it), so re-check it against the
        # whole text.
        m = _SENT_END.match(text, m.start())
    if m is None and limit < len(text):
        return None
    return begin, (m.end() if m else len(text))


def _next_sentence(text: str, end: int) -> str:
    bounds = _next_sentence_bounds(text, end)
    return text[bounds[0]:bounds[1]] if bounds else ""


def _prev_neighbours(text: str, start: int) -> list[str] | None:
    """Up to two nearest word-bearing sentences before `start`. None means the cap was exceeded (fail closed)."""
    out: list[str] = []
    pos = start
    for _ in range(_MAX_SKIPPED_FRAGMENTS):
        bounds = _prev_sentence_bounds(text, pos)
        if bounds is None:
            return None
        sentence = text[bounds[0]:bounds[1]]
        if _HAS_WORD.search(sentence):
            out.append(sentence)
            if len(out) == 2:
                return out
        pos = bounds[0]
        if pos == 0:
            return out
    # N8 (review round 4): the fragment budget ran out before two word-bearing neighbours were found and before
    # the edge of the text, so the guard would check nothing on this side. Withhold instead (fail closed).
    return None


def _next_neighbours(text: str, end: int) -> list[str] | None:
    """Up to two nearest word-bearing sentences after `end`. None means the cap was exceeded (fail closed)."""
    out: list[str] = []
    pos = end
    for _ in range(_MAX_SKIPPED_FRAGMENTS):
        bounds = _next_sentence_bounds(text, pos)
        if bounds is None:
            return None
        sentence = text[bounds[0]:bounds[1]]
        if _HAS_WORD.search(sentence):
            out.append(sentence)
            if len(out) == 2:
                return out
        pos = bounds[1]
        if pos >= len(text):
            return out
    # N8 (review round 4): the fragment budget ran out before two word-bearing neighbours were found and before
    # the edge of the text, so the guard would check nothing on this side. Withhold instead (fail closed).
    return None


def _money_elsewhere(text: str, spans: list[tuple[int, int, str]]) -> bool:
    """Whether a currency-anchored amount (MONEY_RE) appears anywhere in the text outside every disclaimer span.

    A single O(n) scan over the whole text, done once per call (not once per span), so this stays linear even
    when the text holds many disclaimer occurrences. None of the approved disclaimer sentences themselves contain
    an amount, so in practice this never has to check a match against the span list at all -- but the check is
    kept correct (and cheap: spans is typically 1-2 entries) rather than assumed.
    """
    for m in _AMOUNT_RE.finditer(text):
        if not any(s <= m.start() < e for s, e, _ in spans):
            return True
    return False


def guarded_spans(text: str) -> list[tuple[int, int, str]]:
    """find_spans(text), with the adjacency guard withholding contested matches."""
    # F2: deferred import. income_claim_policy imports mask_approved_disclaimers from this module at its own
    # top level, so importing its _NEARBY_EARNINGS_RE back at *this* module's top level would be circular (this
    # module would be asked to resolve a name in income_claim_policy before income_claim_policy has finished
    # defining it). Importing inside the function instead runs after both modules have fully loaded.
    from app.risk.policies.income_claim_policy import _NEARBY_EARNINGS_RE

    spans = find_spans(text)
    if not spans:
        return []
    # 2026-09-25 review round 2: a currency-anchored amount ANYWHERE else in the answer -- not just adjacent to
    # the disclaimer -- also withholds the exemption for every span in the text. This can only make the guard
    # more conservative (it never grants an exemption the per-span checks below did not already allow).
    if _money_elsewhere(text, spans):
        return []

    out = []
    for s, e, vid in spans:
        prevs = _prev_neighbours(text, s)
        nexts = _next_neighbours(text, e)
        if prevs is None or nexts is None:
            # N1: no sentence boundary within the cap in one direction -- withhold rather than guess.
            continue
        # An earnings word or a currency-anchored amount within the two nearest word-bearing neighbouring
        # sentences of the disclaimer (either direction) means the exemption is withheld, exactly like a
        # contrast/dismissal cue: "Except for Managers, who all earn $5,000 a month.", "I promise you will earn
        # money.", or the same cue one short filler sentence/heading further away ("... success. Really. But
        # everyone makes money."). A bare amount (e.g. a year or a phone number) does not count -- MONEY_RE
        # requires a currency symbol/word/code, never bare digits.
        neighbours = prevs + nexts
        if (
            any(_GUARD_CUES.search(n) for n in neighbours)
            or any(_NEARBY_EARNINGS_RE.search(n) for n in neighbours)
            or any(_AMOUNT_RE.search(n) for n in neighbours)
        ):
            continue
        out.append((s, e, vid))
    return out


# ---------------------------------------------------------------------------
# Masking
# ---------------------------------------------------------------------------


def _is_guarantee_word(word: str) -> bool:
    return bool(_ENGLISH_GUARANTEE.fullmatch(word) or GUARANTEE_RE.fullmatch(fold(word)))


def mask_approved_disclaimers(text: str) -> str:
    """Blank the guarantee word(s) inside each approved, unguarded disclaimer sentence.

    Only characters that are part of a "guarantee..." word are replaced (with
    same-length filler, so every other character offset in the text is
    preserved). Every other word of the matched sentence, including its own
    "income" word, is left completely unchanged.
    """
    if not text:
        return text
    spans = guarded_spans(text)
    if not spans:
        return text
    chars = list(text)
    for start, end, _vid in spans:
        for m in re.finditer(r"\w+", text[start:end]):
            if _is_guarantee_word(m.group(0)):
                for i in range(start + m.start(), start + m.end()):
                    chars[i] = "x"
    return "".join(chars)
