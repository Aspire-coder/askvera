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

Rework "income step 2" (2026-09-25, owner decision "Prompt + widen to
1.01(d)"). In the live R10F run the model phrased the disclaimer differently
every time, so none of the four English answers matched EN-1/EN-2 exactly and
all were refused. Recognition is widened, still exact and fail-closed, to:
  (a) the sentences of the verbatim US-EN Company Policy 1.01(d) paragraph
      (POLICY_101D_SENTENCES). A neighbouring sentence that IS one of those
      sentences (edge-normalised; optionally behind a clean colon lead-in on
      the same line, or behind an APPROVED_UNIT_PREFIXES framing) is part of
      the approved unit: it never triggers the guard -- so 1.01(d)'s own "FLP
      has a long history of success, but does not represent ..." no longer
      withholds the exemption from the disclaimer that follows it (R10F
      r10-v2-income-identity-en) -- and it is stepped over, so the guard
      always inspects the two nearest word-bearing sentences OUTSIDE the unit
      (capped at _MAX_SKIPPED_UNIT_SENTENCES per side, fail closed). A unit
      sentence with one word changed is not a unit sentence: it is judged as
      an ordinary neighbour (S1's "but" then withholds as before).
  (b) a colon lead-in on the same line ("...: EN-1"). Only when the text
      before the colon on that line contains no cue, no currency amount and
      no earnings word -- with one explicit allowance: the topic noun
      "earnings" directly after on/about/regarding/concerning ("what the
      company says about earnings:", "On earnings and success ...:") is a
      label for the disclaimer, not a claim, and does not count. The guard
      still inspects the lead-in as the nearest previous neighbour under the
      same rule.
  (c) bold/italic wrapping two approved sentences together
      ("**EN-1 Individual results may vary.**") -- already handled by the
      edge rules; pinned by tests.
  (d) variant subjects and result clauses, each listed explicitly in
      APPROVED_SUBJECTS / APPROVED_RESULTS_CLAUSES and expanded into
      ACTIVE_VARIANTS (every standalone sentence is an explicit table entry).
  (e) the quoted-fragment sentence 'FLP states it "makes no guarantees
      regarding income or success."' (optionally preceded by the quoted
      1.01(d) fragment "does not represent that an FBO will achieve financial
      success" and), with the subject/verb grammar in
      APPROVED_QUOTED_FRAGMENT_GRAMMAR. The whole sentence must match; the
      fragment must be quoted.
  (f) a clause join: an APPROVED_LEAD_CLAUSES sentence (a 1.01(d) sentence,
      or compensation-based-on-sales wording copied from it) joined to a
      variant by an em/en dash or ", and" (APPROVED_JOINS). Any other lead
      clause, however innocent, stays refused.
Everything above only adds whole-sentence exact forms; the mask still blanks
only the guarantee word(s), and the guard, the money-elsewhere check and the
user-input path are unchanged.
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
# The verbatim US-EN Company Policy 1.01(d) paragraph (Company Policies and Procedures, posted April 1, 2026;
# corpus source US-EN-Company-Policy.pdf.sections.jsonl, section 1.01-part-2), sentence by sentence. S4 is EN-1.
POLICY_101D_SENTENCES: tuple[str, ...] = (
    "FLP has a long history of success, but does not represent that an FBO will achieve financial success.",
    "Compensation in FLP is based upon the sale of its products.",
    "Individual results may vary.",
    "Forever makes no guarantees regarding income or success.",
    "The Forever Business Owner opportunity and related incentives are not available to residents of the United "
    "States beginning on May 1, 2026.",
)
_S1, _S2, _S3, _S4, _S5 = POLICY_101D_SENTENCES

# (d) Approved standalone disclaimer sentences: variant id -> (language, source note, exact sentence).
# Owner decision 2026-09-26: only forms that appeared in a live answer or are verbatim 1.01(d) wording are enabled.
# Considered and deliberately NOT enabled pending live evidence (each would need a fresh owner sign-off): the
# subjects "Forever Living" and "Forever Living Products", "FLP" and "the company" in any form other than the two
# below, the clauses "Results may vary" and "Results vary", and every other subject/clause/order combination.
_GUARANTEE_TAIL = "makes no guarantees regarding income or success"
ACTIVE_VARIANTS: dict[str, tuple[str, str, str]] = {
    "EN-1": ("en", "US-EN Company Policy 1.01(d) sentence 4, verbatim", _S4),
    "EN-2": (
        "en",
        "1.01(d) sentences 3 and 4 joined by ', and' (R10E r10-06)",
        "Individual results may vary, and Forever makes no guarantees regarding income or success.",
    ),
    "EN-2b": (
        "en",
        "EN-2 with 'individual results vary' (R10F r10-06)",
        "Individual results vary, and Forever makes no guarantees regarding income or success.",
    ),
    "EN-3": (
        "en",
        "EN-1 with 'the company', followed by ', and individual results may vary' (corpus answer 2026-09-12)",
        "The company makes no guarantees regarding income or success, and individual results may vary.",
    ),
}
assert ACTIVE_VARIANTS["EN-1"][2] == "Forever makes no guarantees regarding income or success."
# (e) Subjects allowed in the quoted-fragment grammar only (never as a standalone variant): subject -> source note.
QUOTED_FRAGMENT_SUBJECTS: dict[str, str] = {
    "FLP": "R10F r10-07 ('FLP states it ... \"makes no guarantees regarding income or success.\"')",
}

# (f) Approved lead clauses that may be joined to a variant in the same sentence: clause -> source note. Each is a
# 1.01(d) sentence (without its final period) or compensation-based-on-sales wording copied from 1.01(d).
APPROVED_LEAD_CLAUSES: dict[str, str] = {
    _S1[:-1]: "US-EN 1.01(d) sentence 1, verbatim",
    _S2[:-1]: "US-EN 1.01(d) sentence 2, verbatim",
    _S3[:-1]: "US-EN 1.01(d) sentence 3, verbatim",
    _S5[:-1]: "US-EN 1.01(d) sentence 5, verbatim",
    "Compensation is based upon the sale of its products": "1.01(d) sentence 2 without 'in FLP' (R10E r10-06)",
    "Compensation is based on the sale of products to consumers": "R10F r10-06 lead clause",
    "Compensation is based on actual product sales": "corpus answer 2026-09-12 lead clause",
}
# (f) Approved joins between a lead clause and the variant: name -> regex.
APPROVED_JOINS: dict[str, str] = {
    "em/en dash": r"[ \t]{0,4}+[—–][ \t]{0,4}+",
    ", and": r"[ \t]{0,4}+,\s+and\s+",
}
# (e) Approved quoted-fragment sentence grammar (R10F r10-07):
#   <subject> states|says [that] [it] ["does not represent that an FBO will achieve financial success" and]
#   "makes no guarantees regarding income or success."
# The subject is one of QUOTED_FRAGMENT_SUBJECTS; the guarantee fragment must be quoted; the whole sentence must
# match.
APPROVED_QUOTED_FRAGMENT_GRAMMAR: dict[str, str] = {
    "verbs": "states|says",
    "optional link words": "that, it, that it",
    "optional first fragment": '"does not represent that an FBO will achieve financial success" and',
    "guarantee fragment": f'"{_GUARANTEE_TAIL}."',
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


def _body(sentence: str) -> str:
    """Regex body for one exact word sequence: words in order, whitespace runs as \\s+, punctuation kept literally.

    No word may be added, removed, changed or reordered, and no other punctuation is allowed inside the sequence.
    """
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
    return body


def _alternation(pieces) -> str:
    """Non-capturing alternation, longest piece first (each piece is a fixed word sequence, so this is linear)."""
    return "(?:" + "|".join(sorted(pieces, key=len, reverse=True)) + ")"


# Left boundary: start of text, or immediately after a sentence-ending punctuation + space (optionally through
# closing quote/emphasis marks), or immediately after a line break, or -- rework (b) -- immediately after a colon +
# space (the colon lead-in is then re-checked by _colon_lead_in/_lead_in_ok in find_spans, fail closed). Never
# after ',' ';' or a word character on the same line without a boundary between them.
_LEFT = (
    r"(?:(?<=\A)|(?<=[.!?][ \t])|(?<=[.!?][\"”'’*_][ \t])"
    r"|(?<=[.!?][\"”'’*_]{2}[ \t])|(?<=\n)|(?<=:[ \t]))"
)
# Right boundary: optional final period, optional closing quotes/emphasis, then end of text, a line break, or
# whitespace before the next sentence (only when a period was present).
_RIGHT = rf"(?:(?P<p>{_EDGE_CLOSE}\.{_EDGE_CLOSE})(?=\s|\Z)|{_EDGE_CLOSE}(?={_NO_PERIOD_END}))"
_Q_OPEN = f"[{_EDGE_OPEN_QUOTES}]"
_Q_CLOSE = f"[{_EDGE_CLOSE_QUOTES}]"
_FRAGMENT_1 = "does not represent that an FBO will achieve financial success"


def _quoted_subject_body() -> str:
    return _alternation(_body(s) for s in QUOTED_FRAGMENT_SUBJECTS)


def _standalone_body() -> str:
    """Exactly the ACTIVE_VARIANTS sentences (their final period is handled by the right boundary)."""
    return _alternation(_body(text.rstrip(".")) for _, _, text in ACTIVE_VARIANTS.values())


def _sentence_regex() -> re.Pattern[str]:
    """One linear-time regex for every standalone variant, optionally behind an approved lead clause + join (f)."""
    lead = _alternation(_body(c) for c in APPROVED_LEAD_CLAUSES)
    join = _alternation(APPROVED_JOINS.values())
    core = rf"(?:{lead}{join})?{_standalone_body()}"
    return re.compile(_LEFT + _EDGE_OPEN + "(?P<core>" + core + ")" + _RIGHT, re.IGNORECASE)


def _quoted_regex() -> re.Pattern[str]:
    """(e): '<subject> states|says [that] [it] ["<fragment 1>" and] "makes no guarantees regarding income or success."'

    The guarantee fragment must open with a quote mark; the sentence must end right after it: a period inside or
    outside the closing quote, or (no period) a blank line / end of text.
    """
    core = (
        rf"{_quoted_subject_body()}\s+(?:states|says)\s+(?:that\s+)?(?:it\s+)?"
        rf"(?:{_Q_OPEN}{_body(_FRAGMENT_1)}{_Q_CLOSE}\s+and\s+)?{_Q_OPEN}{_body(_GUARANTEE_TAIL)}"
    )
    right = (
        rf"(?:{_Q_CLOSE}?\.{_EDGE_CLOSE}(?=\s|\Z)|\.{_Q_CLOSE}{_EDGE_CLOSE}(?=\s|\Z)"
        rf"|{_Q_CLOSE}{_EDGE_CLOSE}(?={_NO_PERIOD_END}))"
    )
    return re.compile(_LEFT + _EDGE_OPEN + "(?P<core>" + core + ")" + right, re.IGNORECASE)


_COMPILED: list[re.Pattern[str]] | None = None


def _compiled() -> list[re.Pattern[str]]:
    global _COMPILED
    if _COMPILED is None:
        _COMPILED = [_sentence_regex(), _quoted_regex()]
    return _COMPILED


# --- variant id for a matched core (reporting only; never affects matching) ---
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().rstrip(".").casefold()


_NORM_INDEX: dict[str, str] = {_norm(text): vid for vid, (_, _, text) in ACTIVE_VARIANTS.items()}
_LEAD_INDEX: dict[str, str] = {_norm(c): f"L{i + 1}" for i, c in enumerate(APPROVED_LEAD_CLAUSES)}
_JOIN_SPLIT: re.Pattern[str] | None = None


def _classify(core: str) -> str:
    n = _norm(core)
    vid = _NORM_INDEX.get(n)
    if vid:
        return vid
    global _JOIN_SPLIT
    if _JOIN_SPLIT is None:
        lead = _alternation(_body(c) for c in APPROVED_LEAD_CLAUSES)
        join = _alternation(APPROVED_JOINS.values())
        _JOIN_SPLIT = re.compile(rf"\A(?P<lead>{lead})(?P<join>{join})(?P<rest>.*)\Z", re.IGNORECASE)
    m = _JOIN_SPLIT.match(n)
    if m:
        return f"JOIN/{_LEAD_INDEX.get(_norm(m.group('lead')), '?')}/{_NORM_INDEX.get(_norm(m.group('rest')), '?')}"
    return "QUOTED/" + n.split(" ")[0]


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


# Rework (b): a colon lead-in. When the match is reached through ":" + space on the same line, the text before the
# colon on that line is the lead-in. It may contain no contrast/dismissal cue, no currency-anchored amount and no
# earnings word. The only allowances are (1) the topic phrase "on/about/regarding/concerning earnings [and
# success]" when it ENDS the lead-in ("Here's what the company says about earnings:"), which labels the disclaimer
# rather than saying anything about earnings, and (2) the exact live framing in APPROVED_LEAD_INS. Review
# 2026-09-26: an allowance matched anywhere in the lead-in let "Regarding earnings, which are excellent:" and
# "About earnings, most make 900 a month:" through, so anything after the topic phrase now withholds as before.
# Any other earnings word ("Everyone earns well:") still withholds. This check can only discard a match the regex
# found (fail closed); it never manufactures one.
# The phrase is exempt only as the whole label ("On earnings") or after a reporting verb ("... says about earnings"),
# never after any other words: "Most FBOs are thrilled about earnings:" states something about earnings.
_TOPIC_EARNINGS_RE = re.compile(
    r"(?:\A[*_\"“”'‘’\s]*|(?<!\w)(?:says|states|said|stated|writes|wrote|explains|puts\s+it)\s+)"
    r"(?:on|about|regarding|concerning)\s+earnings(?:\s+and\s+success)?[*_\"“”'’)\]]*\s*\Z",
    re.IGNORECASE,
)
# Exact lead-ins seen live that name earnings in a way the topic phrase cannot express: lead-in -> source note.
APPROVED_LEAD_INS: dict[str, str] = {
    "On earnings and success, Forever is explicit": "R10E r10-05 (tests/governance/test_income_projection_governance.py)",
}
_APPROVED_LEAD_IN_NORMS = frozenset(" ".join(lead.split()).casefold() for lead in APPROVED_LEAD_INS)
_LEAD_EDGE = " \t*_\"“”'’"


def _colon_lead_in(text: str, start: int) -> str | None:
    """The lead-in text before a colon on the span's own line, or None when the span does not follow a colon.

    Only the last _NEIGHBOUR_CAP + 1 characters of the line are looked at (and copied), so a single very long
    line holding many colon-led disclaimers stays linear; a lead-in longer than the cap then fails _lead_in_ok
    (fail closed), exactly like a neighbour scan that finds no boundary within the cap.
    """
    i = start
    while i and text[i - 1] in _LEFT_EDGE_CHARS:
        i -= 1
    if i and text[i - 1] == ":":
        window_start = max(0, i - 1 - _NEIGHBOUR_CAP - 1)
        line_start = text.rfind("\n", window_start, i - 1) + 1
        return text[max(line_start, window_start):i - 1]
    return None


def _lead_in_ok(lead: str) -> bool:
    from app.risk.policies.income_claim_policy import _NEARBY_EARNINGS_RE  # deferred: circular at module level

    if len(lead) > _NEIGHBOUR_CAP or _GUARD_CUES.search(lead) or _AMOUNT_RE.search(lead):
        return False
    # A label neighbour ("**On earnings:**") arrives with its colon and closing marks; a same-line lead-in without.
    # Judge both on the text before the colon, so the topic phrase can only be exempt when it ends that text.
    lead = _LABEL_END_RE.sub("", lead)
    if " ".join(lead.strip(_LEAD_EDGE).split()).casefold() in _APPROVED_LEAD_IN_NORMS:
        return True
    return _NEARBY_EARNINGS_RE.search(_TOPIC_EARNINGS_RE.sub(" ", lead)) is None


# A previous neighbour that is a label -- it ends with ":" (optionally through closing marks) and so introduces
# what follows, whether on the disclaimer's own line ("what the company says about earnings: EN-1") or as a
# heading line ("**On earnings:**") -- is judged by the lead-in rule above instead of the plain neighbour rule.
# The only difference between the two rules is the "on/about/regarding/concerning earnings" topic-label
# allowance; cues and amounts withhold either way, and following neighbours never get the allowance.
_LABEL_END_RE = re.compile(r":[*_\"“”'’)\]]*\s*\Z")


def find_spans(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, variant_id) for every approved-variant sentence match, sorted by position."""
    out: list[tuple[int, int, str]] = []
    for rx in _compiled():
        for m in rx.finditer(text):
            start = m.start("core")
            if not _left_boundary_ok(text, start):
                continue
            lead = _colon_lead_in(text, start)
            if lead is not None and not _lead_in_ok(lead):
                continue
            out.append((start, m.end("core"), _classify(m.group("core"))))
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
# N8: the walk may take at most this many steps over word-bearing neighbours and word-free fragments together (the
# 1.01(d) unit sentences of rework (a) are budgeted separately, below); running out before two neighbours are found
# and before the edge of the text withholds. Review 2026-09-26: counting fragments alone let
# "EN-1 / Really. / five '---' lines / Great products." through, which the committed module refused.
_MAX_NEIGHBOUR_STEPS = 6


# Both helpers work on offsets into the whole text and never copy the text before or after a match, so the guard
# costs time proportional to the neighbouring sentences, not to the answer: an answer repeating the disclaimer
# thousands of times would otherwise be quadratic. Each returns (begin, end), or None when no sentence boundary
# was found within _NEIGHBOUR_CAP characters (N1: fail closed, see above).
def _prev_sentence_bounds(text: str, start: int) -> tuple[int, int] | None:
    head_end = start
    while head_end and text[head_end - 1] in _PREV_EDGE + "\n":
        head_end -= 1
    stop = max(0, head_end - 1)
    # Only the LAST sentence end before `stop` is wanted, so look in a short window first and widen up to the cap.
    # Every _SENT_END match is a single character whose lookahead is bounded by the same `stop`, so the rightmost
    # match found in a narrower window is exactly the rightmost match of the capped window (identical result);
    # this just avoids collecting ~70 earlier ends per span on answers made of many short sentences (rework
    # 2026-09-25: the 16,000-repeat perf shape went from 1.5-3.0 s to well under the budget).
    for width in (256, 1024, _NEIGHBOUR_CAP):
        begin = max(0, stop - width)
        last = None
        for m in _SENT_END.finditer(text, begin, stop):
            last = m.end()
        if last is not None:
            return last, head_end
        if begin == 0:
            return 0, head_end
    return None


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


# Rework (a): a neighbour that is itself one of the verbatim 1.01(d) sentences (S1, S2, S3, S5) belongs to the
# approved unit and is stepped over exactly like a word-free fragment, so the guard always inspects the two
# nearest sentences OUTSIDE the unit ("Everyone on my team makes money. S1 S2 S3 EN-1" is withheld even though
# three unit sentences separate the claim from the disclaimer). At most _MAX_SKIPPED_UNIT_SENTENCES are stepped
# over per side (the paragraph only has three before and one after the disclaimer); more than that -- a repeated
# unit -- withholds (fail closed), like N8 does when the fragment budget runs out.
_MAX_SKIPPED_UNIT_SENTENCES = 4


def _prev_neighbours(text: str, start: int) -> list[str] | None:
    """Up to two nearest word-bearing, non-unit sentences before `start`. None means a cap was exceeded (fail closed)."""
    out: list[str] = []
    pos = start
    fragments = units = 0
    while True:
        bounds = _prev_sentence_bounds(text, pos)
        if bounds is None:
            return None
        sentence = text[bounds[0]:bounds[1]]
        if not _HAS_WORD.search(sentence):
            fragments += 1
        elif _is_unit_sentence(sentence):
            units += 1
        else:
            out.append(sentence)
            if len(out) == 2:
                return out
        pos = bounds[0]
        if pos == 0:
            return out
        if len(out) + fragments >= _MAX_NEIGHBOUR_STEPS or units > _MAX_SKIPPED_UNIT_SENTENCES:
            # N8 (review round 4): a budget ran out before two neighbours were found and before the edge of the
            # text, so the guard would check nothing on this side. Withhold instead (fail closed).
            return None


def _next_neighbours(text: str, end: int) -> list[str] | None:
    """Up to two nearest word-bearing, non-unit sentences after `end`. None means a cap was exceeded (fail closed)."""
    out: list[str] = []
    pos = end
    fragments = units = 0
    while True:
        bounds = _next_sentence_bounds(text, pos)
        if bounds is None:
            return None
        sentence = text[bounds[0]:bounds[1]]
        if not _HAS_WORD.search(sentence):
            fragments += 1
        elif _is_unit_sentence(sentence):
            units += 1
        else:
            out.append(sentence)
            if len(out) == 2:
                return out
        pos = bounds[1]
        if pos >= len(text):
            return out
        if len(out) + fragments >= _MAX_NEIGHBOUR_STEPS or units > _MAX_SKIPPED_UNIT_SENTENCES:
            # N8 (review round 4): see _prev_neighbours.
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
        # Rework (a)/(b): the neighbours are the two nearest sentences OUTSIDE the 1.01(d) unit (unit sentences
        # were stepped over by _prev_neighbours/_next_neighbours, so 1.01(d)'s own "but" never counts). A
        # previous neighbour that is a label (ends with ":") -- the same-line colon lead-in, or a heading line --
        # is judged by the lead-in rule (same three checks, plus the "on/about earnings" topic-label allowance).
        withheld = False
        for n in prevs:
            if _LABEL_END_RE.search(n):
                if not _lead_in_ok(n):
                    withheld = True
                    break
            elif _GUARD_CUES.search(n) or _NEARBY_EARNINGS_RE.search(n) or _AMOUNT_RE.search(n):
                withheld = True
                break
        if not withheld:
            for n in nexts:
                if _GUARD_CUES.search(n) or _NEARBY_EARNINGS_RE.search(n) or _AMOUNT_RE.search(n):
                    withheld = True
                    break
        if withheld:
            continue
        out.append((s, e, vid))
    return out


# Rework (a): the four non-disclaimer sentences of the verbatim US-EN 1.01(d) paragraph (S1, S2, S3, S5), each
# recognised whole with the same edge normalisation as the variants, optionally behind a colon lead-in on the same
# line (which must itself pass the lead-in rule) or behind one of the explicitly approved framing prefixes below.
# Exact sentences only otherwise: "Nobody believes that FLP has a long history of success, but ..." is NOT a unit
# sentence, and its "but" still withholds when it is a neighbour.
# Approved framing prefixes: prefix -> source note. Seen live in R10E r10-07 (accepted fixture).
APPROVED_UNIT_PREFIXES: dict[str, str] = {
    "It's important to understand that": "R10E r10-07 (accepted fixture), before 1.01(d) sentence 1",
    "It is important to understand that": "same framing, apostrophe-free spelling",
    "It’s important to understand that": "same framing, curly apostrophe",
}
_UNIT_RX: re.Pattern[str] | None = None


def _unit_regex() -> re.Pattern[str]:
    global _UNIT_RX
    if _UNIT_RX is None:
        bodies = _alternation(_body(s[:-1]) for s in (_S1, _S2, _S3, _S5))
        prefixes = _alternation(_body(p) for p in APPROVED_UNIT_PREFIXES)
        _UNIT_RX = re.compile(
            rf"\A(?:(?P<lead>[^\n]*?):[ \t]+)?{_EDGE_OPEN}(?:{prefixes}\s+)?{bodies}(?:{_EDGE_CLOSE}\.)?{_EDGE_CLOSE}\Z",
            re.IGNORECASE,
        )
    return _UNIT_RX


def _is_unit_sentence(neighbour: str) -> bool:
    m = _unit_regex().fullmatch(neighbour.strip())
    if m is None:
        return False
    lead = m.group("lead")
    return lead is None or _lead_in_ok(lead)


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
