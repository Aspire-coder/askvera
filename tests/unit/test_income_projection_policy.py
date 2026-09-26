"""Unit coverage for the income-projection detector and risk policy.

app/risk/policies/income_projection.py is a faithful port of the offline
prototype (income_design/proto2_final.py + proto2_vocab_final.py): a
detector for earnings-projection language (a specific or estimated amount
attributed to FBOs/roles/"you"/"most") in a GENERATED answer. It is a
tightening only: it can only add refusals to model-generated text, never
change the input-side pass.

tests/fixtures/income_projection_cases.json and
tests/fixtures/step1_must_catch.json are verbatim copies of the design's own
fixtures. Each income_projection_cases.json case carries the field
"prototype": the rule the reference prototype fired on the case (a rule
name), or null when the prototype MISSES it. One "must_refuse" case carries
"prototype": null -- correct Unicode text, not corruption -- and is the
design's own documented residual miss, which this port must reproduce
exactly (see the parity check reported separately; this port must never
"fix" a gap the reference implementation itself has):

  - "sr-fin_freedom" ("Forever vam pruza finansijsku slobodu i pasivan
    prihod."): "financial freedom" phrasing is deliberately excluded from
    rule P4 (see income_projection.py's module docstring); "pasivan prihod"
    (passive income, masculine indefinite form) also does not match the sr
    vocabulary's "pasivn\\w*\\s+prihod\\w*" stem. Covered elsewhere: the
    translated income-claim phrase list in income_claim_translations.py
    refuses this same sentence today (see the governance-level test in
    tests/governance/test_income_projection_governance.py).

It is marked xfail(strict=True): if a future change to the detector starts
catching it, the test XPASSes and fails, forcing the marker (and this
comment) to be revisited rather than silently drifting.

Step 1b (tests/fixtures/income_projection_1b_cases.json) closes several
recall gaps the step-1 detector had -- spelled-out amounts, more currency
names/codes/symbols, markdown/"Heading:" tables, comparisons against an
outside pay benchmark (P7), subject-less "expect"/"count on" phrasing (P8),
income-noun forms (P3b/P3c folded into P3's rule id), and "will be worth ...
a month" (P9) -- plus a clause-scoped hedge suppression so a contrast word
("but", "however", ...) earlier in the sentence no longer blanks out a
projection that follows it. One of step 1b's new paths is P8 (the
subject-less "expect"/"count on" detector), which now also catches "en-c6"
("Expect roughly EUR500 a month once you have three active legs.") --
formerly the second documented residual miss above. "en-c6" is therefore
removed from _KNOWN_RESIDUAL_MISSES below and its income_projection_cases.json
fixture entry's "prototype" field is updated from null to "P8" (the only
change to that fixture's recorded verdicts/rule ids; see the parity check).

Everything here is local; sockets and boto3 clients raise if used.
"""

from __future__ import annotations

import json
import socket
import time
from pathlib import Path

import pytest

from app.risk.models import PolicyAction, RiskContext, RiskLevel
from app.risk.policies import IncomeClaimPolicy, IncomeProjectionPolicy
from app.risk.policies.income_projection import detect_earnings_projection

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _refuse(*_: object, **__: object):
        raise AssertionError("network access attempted in an offline test")

    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


def _load_projection_cases():
    with open(FIXTURES / "income_projection_cases.json", encoding="utf-8") as handle:
        return json.load(handle)


def _load_step1_must_catch_cases():
    with open(FIXTURES / "step1_must_catch.json", encoding="utf-8") as handle:
        data = json.load(handle)
    return [case for case in data["cases"] if case.get("gate") == "step1_must_refuse"]


def _load_1b_cases():
    with open(FIXTURES / "income_projection_1b_cases.json", encoding="utf-8") as handle:
        return json.load(handle)


_PROJECTION_CASES = _load_projection_cases()
_MUST_REFUSE = _PROJECTION_CASES["must_refuse"]
_MUST_NOT_FIRE = _PROJECTION_CASES["must_not_fire"]
_NEAR_MISSES = _PROJECTION_CASES["corpus_near_misses_must_not_fire"]
_STEP1_MUST_CATCH = _load_step1_must_catch_cases()

_1B_CASES = _load_1b_cases()
_1B_MUST_REFUSE = _1B_CASES["must_refuse"]
_1B_MUST_NOT_FIRE = _1B_CASES["must_not_fire"]
_1B_KNOWN_FP_PARITY = _1B_CASES["known_fp_parity"]


def _case_id(case: dict) -> str:
    return case.get("id") or case.get("market") or case.get("text", "")[:40]


# Known residual misses in the reference prototype (see module docstring):
# recorded "prototype": null in a must_refuse case. These are xfail(strict=True)
# so a future fix shows up as XPASS and forces the marker to be removed.
#
# "en-c6" was removed from this dict in step 1b: it now fires (rule P8, the
# new subject-less "expect"/"count on" detector), so the case's fixture entry
# was updated to "prototype": "P8" and it is asserted like any other
# must_refuse case above.
_KNOWN_RESIDUAL_MISSES = {
    "sr-fin_freedom": (
        "financial freedom deliberately excluded from P4; "
        "'pasivan prihod' does not match the sr 'pasivn\\w*' stem"
    ),
}


def _must_refuse_param(case: dict):
    reason = _KNOWN_RESIDUAL_MISSES.get(case.get("id"))
    marks = [pytest.mark.xfail(strict=True, reason=f"known residual miss: {reason}")] if reason else []
    return pytest.param(case, marks=marks, id=_case_id(case))


# --- (a) income_projection_cases.json -----------------------------------------

@pytest.mark.parametrize("case", [_must_refuse_param(c) for c in _MUST_REFUSE])
def test_must_refuse_cases_fire(case: dict) -> None:
    """Fires, and on the recorded rule, for every must-refuse case.

    The two known residual misses (see _KNOWN_RESIDUAL_MISSES) are marked
    xfail(strict=True): this assertion still states the INTENDED behaviour
    (fires), not the miss, so a future fix is caught as an XPASS failure.
    """
    hit = detect_earnings_projection(case["text"], case.get("lang"))
    expected_rule = case.get("prototype")
    assert hit is not None, f"expected a match for case {case.get('id')!r}, got no match"
    if expected_rule is not None:
        assert hit[0] == expected_rule, f"expected rule {expected_rule!r}, got {hit[0]!r} for {case.get('id')!r}"


@pytest.mark.parametrize("case", _MUST_NOT_FIRE, ids=[_case_id(c) for c in _MUST_NOT_FIRE])
def test_hard_negative_cases_do_not_fire(case: dict) -> None:
    hit = detect_earnings_projection(case["text"], case.get("lang"))
    assert hit is None, f"expected no match for hard-negative case {case.get('id')!r}, got {hit!r}"


@pytest.mark.parametrize("case", _NEAR_MISSES, ids=[_case_id(c) for c in _NEAR_MISSES])
def test_real_corpus_near_miss_cases_do_not_fire(case: dict) -> None:
    hit = detect_earnings_projection(case["text"], case.get("lang"))
    assert hit is None, f"expected no match for near-miss case {_case_id(case)!r}, got {hit!r}"


# --- (b) step1_must_catch.json (gate == step1_must_refuse) --------------------

@pytest.mark.parametrize("case", _STEP1_MUST_CATCH, ids=[_case_id(c) for c in _STEP1_MUST_CATCH])
def test_step1_must_refuse_cases_fire(case: dict) -> None:
    hit = detect_earnings_projection(case["text"], case.get("language"))
    assert hit is not None, f"expected a match for step1_must_refuse case {case.get('id')!r}"


# --- (c) income_projection_1b_cases.json (step 1b recall extensions) ----------
#
# must_refuse (150): Fable's 47 step-1 detector-level recall misses, 43 step-1b dev
# cases, 60 held-out cases -- each carries the rule id the 1b detector must return
# ("table"/"list" markdown-table hits still return rule "P5"; only the pseudo-lang
# in position [1] of the tuple differs, which these tests don't assert on).
# must_not_fire (157): step-1b dev/held-out compliant negatives and the synthetic
# rule-answer battery -- these must never fire.
# known_fp_parity (6, asserted separately below): NOT new false positives. Each is
# the spelled-out-number or hedge-prefixed twin of an FP shape the step-1 detector
# already had (e.g. "can earn up to $N" worked examples); step 1b's spelled-number
# and hedge-scope extensions make the detector see these twins too. They are
# asserted to fire, as documented, not exempted -- fixing them is a P1/P2 change,
# out of scope for step 1b (see income_projection_1b_cases.json's "known_fp_parity").

@pytest.mark.parametrize("case", _1B_MUST_REFUSE, ids=[_case_id(c) for c in _1B_MUST_REFUSE])
def test_1b_must_refuse_cases_fire(case: dict) -> None:
    hit = detect_earnings_projection(case["text"], case.get("lang"))
    assert hit is not None, f"expected a match for step-1b case {case.get('id')!r}, got no match"
    assert hit[0] == case["rule"], f"expected rule {case['rule']!r}, got {hit[0]!r} for {case.get('id')!r}"


@pytest.mark.parametrize("case", _1B_MUST_NOT_FIRE, ids=[_case_id(c) for c in _1B_MUST_NOT_FIRE])
def test_1b_hard_negative_cases_do_not_fire(case: dict) -> None:
    hit = detect_earnings_projection(case["text"], case.get("lang"))
    assert hit is None, f"expected no match for step-1b hard-negative case {case.get('id')!r}, got {hit!r}"


@pytest.mark.parametrize(
    "case",
    [pytest.param(c, marks=pytest.mark.xfail(strict=True, reason="known FP exposure, see 'twin'")) for c in _1B_KNOWN_FP_PARITY],
    ids=[_case_id(c) for c in _1B_KNOWN_FP_PARITY],
)
def test_1b_known_fp_parity_cases_do_not_fire(case: dict) -> None:
    """Known FP exposures (see the comment above and income_projection_1b_cases.json's "description"): these are
    compliant rule answers the step-1 detector already misclassified in digit/undecorated form (its documented
    "fp.json" set); step 1b's spelled-number/currency/hedge extensions surface the SAME shapes written with spelled
    numbers or a hedge prefix. This states the INTENDED behaviour (does not fire), marked xfail(strict=True) so a
    future fix that stops one of these firing shows up as an XPASS -- forcing this marker (and the case) to be
    revisited -- instead of a "must fire" test quietly breaking. Fixing them for real is a P1/P2 rule-context
    change, out of scope here; no exemption was added to force this result."""
    hit = detect_earnings_projection(case["text"], case.get("lang"))
    assert hit is None, f"expected known FP exposure {case.get('id')!r} not to fire (see 'twin': {case.get('twin')!r})"


# --- policy-level behaviour -----------------------------------------------------

def _context(message: str, *, is_generated_answer: bool, allow_claim_topics: bool = False, language: str = "en") -> RiskContext:
    return RiskContext(
        user_message=message,
        country="US",
        language=language,
        role="new_prospect",
        correlation_id="test-correlation",
        allow_claim_topics=allow_claim_topics,
        is_generated_answer=is_generated_answer,
    )


def test_policy_is_noop_when_not_a_generated_answer() -> None:
    policy = IncomeProjectionPolicy()
    text = "Most FBOs earn roughly 900 dollars a month."
    assert policy.evaluate(_context(text, is_generated_answer=False)) == []


def test_policy_fires_on_generated_answer() -> None:
    policy = IncomeProjectionPolicy()
    text = "Most FBOs earn roughly 900 dollars a month."
    issues = policy.evaluate(_context(text, is_generated_answer=True))
    assert len(issues) == 1
    assert issues[0].code == "INCOME_PROJECTION_RISK"
    assert issues[0].level == RiskLevel.HIGH
    assert issues[0].action == PolicyAction.REFUSE
    assert issues[0].source == "business_policy"
    assert issues[0].policy == "income_projection"
    assert issues[0].policy_version


def test_policy_is_not_a_claim_topic() -> None:
    """allow_claim_topics must never forgive this policy's own finding."""
    assert IncomeProjectionPolicy().metadata.is_claim_topic is False


def test_policy_defers_when_income_claim_policy_already_refuses() -> None:
    """No duplicate finding, and no change to IncomeClaimPolicy's own outcome."""
    text = "Can I get guaranteed income with this business?"
    ctx = _context(text, is_generated_answer=True)
    assert IncomeClaimPolicy().evaluate(ctx) != []
    assert IncomeProjectionPolicy().evaluate(ctx) == []


def test_policy_still_runs_when_allow_claim_topics_is_true() -> None:
    """Even if IncomeClaimPolicy's issue would be forgiven, this policy still runs its own check."""
    text = "Most FBOs earn roughly 900 dollars a month."
    ctx = _context(text, is_generated_answer=True, allow_claim_topics=True)
    issues = IncomeProjectionPolicy().evaluate(ctx)
    assert [i.code for i in issues] == ["INCOME_PROJECTION_RISK"]


# --- performance: _seg_start/_seg_end must be O(log n) per lookup, not O(n) ----

def test_a_sentence_with_2000_amounts_evaluates_well_under_one_second() -> None:
    """Pins the _ClauseIndex/bisect fix.

    _seg_start/_seg_end used to rescan the sentence from position 0 (or from
    `pos`) on every call. Called once per money match in P6, an unpunctuated
    sentence with N amounts was O(N) per lookup and O(N^2) overall: locally,
    500/1,000/2,000 amounts (P1/P2/P6 pipeline only, bypassing the
    per-language dispatch in detect_earnings_projection) measured roughly
    0.06s / 0.22s / 0.92s before this fix and 0.003s / 0.007s / 0.014s after.
    A generous 1.0s bound (well over 10x this port's own post-fix timing on
    the slowest measured machine) keeps this stable on a slow CI box while
    still catching a real regression back to quadratic behaviour.
    """
    text = "The catalog lists " + " ".join(f"${100 + i} dollars" for i in range(2000)) + " as reference prices."
    started = time.perf_counter()
    result = detect_earnings_projection(text, "en")
    elapsed = time.perf_counter() - started
    assert result is None  # a catalog of reference prices is not an earnings projection
    assert elapsed < 1.0, f"expected well under 1.0s, took {elapsed:.3f}s (possible quadratic regression)"


def test_a_sentence_with_2000_income_nouns_evaluates_well_under_one_second() -> None:
    """Pins the step-1b fix to the PRE-EXISTING quadratic path in P3 (not a 1b regression: found while adding 1b).

    P3 built `list(re.finditer(r"[\\w'’]+", s[:n.start()]))` for every income-noun match to find the last 3
    word-tokens before it, rescanning from position 0 each time: a sentence with N unpunctuated income nouns was
    O(N) per lookup and O(N^2) overall -- measured ~5.2s for 2,000 in the pre-fix detector. The fix bounds that
    rescan to `s[max(0, n.start() - WIN_BEFORE):n.start()]`, the same windowing P1/P2/P3b already use, for an
    identical `near` value. Measured locally: ~4.1s before this fix, ~0.16s after. A generous 1.0s bound keeps this
    stable on a slow CI box while still catching a regression back to quadratic behaviour.
    """
    text = (
        "There is " + " ".join("no income of about $500 a month for anyone here," for _ in range(2000)) + " truly."
    )
    started = time.perf_counter()
    result = detect_earnings_projection(text, "en")
    elapsed = time.perf_counter() - started
    assert result is None  # every mention is explicitly negated ("no income ...")
    assert elapsed < 1.0, f"expected well under 1.0s, took {elapsed:.3f}s (possible quadratic regression)"


def test_a_sentence_with_2000_hedge_words_evaluates_well_under_one_second() -> None:
    """Pins the step-1b hedge-scope (`_report_lo`) and `_reported`/`_subordinate` fix.

    1b's hedge scope added `CONTRAST_RE[lang].finditer(s, 0, pos)` / `_QUOTE.search(s, 0, pos)` inside
    `_report_lo`, and `_reported` itself already had the pre-existing `V[lang]["report"].search(s, 0, pos)` /
    `POST_BAN_RE[lang].search(s, end)` -- each re-run from 0 (or to the end of the sentence) for every
    verb/noun/rank/amount match, the same O(N)-per-lookup / O(N^2)-overall shape _ClauseIndex already exists to
    avoid for clause lookups. `_ClauseIndex` now also precomputes contrast/quote/report/post-ban match offsets once
    per (sentence, lang) so all four are O(log N) per lookup. Measured locally: ~4.1s before this fix (dominated by
    `_reported`'s report-vocabulary scan), well under 1s after. Each "but" is comma-preceded (clause-initial, see
    `_clause_initial`/Fable B1) so all 2,000 are genuine re-scoping candidates, not filtered out; the filler clause
    ("the weather changes daily") is deliberately neither a HEDGE nor a PROHIBITION word, so the final clause after
    the last "but" still fires.
    """
    text = (
        "I cannot promise anything, " + "but the weather changes daily, " * 2000 + "but you will earn $900 a month."
    )
    started = time.perf_counter()
    result = detect_earnings_projection(text, "en")
    elapsed = time.perf_counter() - started
    assert result is not None and result[0] == "P1"  # the final clause after the last "but" is a real projection
    assert elapsed < 1.0, f"expected well under 1.0s, took {elapsed:.3f}s (possible quadratic regression)"


def test_a_3000_word_answer_evaluates_well_under_one_second() -> None:
    """A realistic-length generated answer (many ordinary sentences, no earnings projection) stays fast: step 1b
    adds four more per-sentence detectors (P7/P8/P3b-c/P9) plus the table pre-scan, so a plain answer's total cost
    should still grow linearly with its length, not with the number of new detectors squared against it."""
    sentence = "This paragraph describes how the business opportunity works for everyone who joins the team today."
    text = " ".join([sentence] * 200)  # 200 sentences of 15 words each = 3,000 words total
    assert 2900 <= len(text.split()) <= 3100
    started = time.perf_counter()
    result = detect_earnings_projection(text, "en")
    elapsed = time.perf_counter() - started
    assert result is None
    assert elapsed < 1.0, f"expected well under 1.0s, took {elapsed:.3f}s (possible quadratic regression)"


def test_a_200_row_table_evaluates_well_under_one_second() -> None:
    """Pins `_detect_tables`' linearity: a 200-row markdown table (income-header column, rank rows) must stay fast
    -- it is run once per answer (not once per sentence) before the sentence loop, so it must not itself become the
    bottleneck as the table grows."""
    rows = "\n".join(f"| Supervisor | ${100 + i} |" for i in range(200))
    text = "| Rank | Typical monthly income |\n|---|---|\n" + rows
    started = time.perf_counter()
    result = detect_earnings_projection(text, "en")
    elapsed = time.perf_counter() - started
    assert result is not None and result[0] == "P5"
    assert elapsed < 1.0, f"expected well under 1.0s, took {elapsed:.3f}s (possible quadratic regression)"


# --- performance: Fable's review-round pathological shapes (item 2 / perf addendum) ---------------------------
#
# Fable's own perf1b.py measured these BEFORE the fixes below landed: "but prohibited you earn $900 a month, " *
# N (comma form) was already fast; the no-comma form was 17.9s at N=2000 (pre-existing in step 1 too, at 10.1s --
# made worse by 1b); "FBOs who earn more than a teacher and " * N was CUBIC (14.7s / 114s / 919s at N=500/1,000/
# 2,000). Each was traced to an unbounded prefix/clause slice (`_negated`'s `before`, `_report_lo`'s post-contrast
# window when `lo` stays pinned at one early contrast, and `_detect_p6`'s `clause = s[lo:hi]`) that grew with the
# sentence instead of staying windowed -- see the comments at each fix. All four are windowed now; step 1's own
# numbers (used as the baseline to beat, per the addendum) were themselves non-trivial for the P6 shape (10.1s),
# so "under 1.0s" is a real improvement there too, not just parity.

def test_hedge_report_p1_comma_2000_evaluates_well_under_one_second() -> None:
    text = "but prohibited you earn $900 a month, " * 2000 + "end."
    started = time.perf_counter()
    result = detect_earnings_projection(text, "en")
    elapsed = time.perf_counter() - started
    assert result is None  # "prohibited" (PROHIBITION) governs every repetition; none is a real projection
    assert elapsed < 1.0, f"expected well under 1.0s, took {elapsed:.3f}s (possible quadratic regression)"


def test_hedge_report_p1_no_comma_2000_evaluates_well_under_one_second() -> None:
    """The no-comma form: `_negated`'s `before` and `_report_lo`'s post-contrast window both stayed unbounded when
    `lo` never advances (no comma/clause-break anywhere) -- see the comments in `_negated` and `_report_lo`."""
    text = "but prohibited you earn $900 a month and " * 2000 + "end."
    started = time.perf_counter()
    result = detect_earnings_projection(text, "en")
    elapsed = time.perf_counter() - started
    assert result is None
    assert elapsed < 1.0, f"expected well under 1.0s, took {elapsed:.3f}s (possible quadratic regression)"


def test_compare_subordinate_no_comma_2000_evaluates_well_under_one_second() -> None:
    """Pins the `_subordinate`/`_negated` windowing fix on the shape Fable measured as CUBIC (14.7s / 114s / 919s
    at N=500/1,000/2,000) before it: with no comma to advance `lo`, every "who"/"and" match rescanned the whole
    growing prefix."""
    text = "FBOs who earn more than a teacher and " * 2000 + "end."
    started = time.perf_counter()
    result = detect_earnings_projection(text, "en")
    elapsed = time.perf_counter() - started
    assert result is None  # "who earn" is a relative clause (_subordinate) on every repetition
    assert elapsed < 1.0, f"expected well under 1.0s, took {elapsed:.3f}s (possible quadratic/cubic regression)"


def test_compare_negated_no_comma_2000_evaluates_well_under_one_second() -> None:
    text = "you never earn more than a teacher and " * 2000 + "end."
    started = time.perf_counter()
    result = detect_earnings_projection(text, "en")
    elapsed = time.perf_counter() - started
    assert result is None  # "never earn" is negated (_negated) on every repetition
    assert elapsed < 1.0, f"expected well under 1.0s, took {elapsed:.3f}s (possible quadratic/cubic regression)"


def test_currency_period_p6_no_comma_2000_evaluates_well_under_one_second() -> None:
    """Pins the `_detect_p6` windowing fix (`clause = s[lo:hi]`, and the `rel` search below it): pre-existing in
    step 1 (10.1s at N=2000 there too, per Fable's addendum), not introduced by 1b, but still required to be fast."""
    text = "$900 a month and " * 2000 + "end."
    started = time.perf_counter()
    result = detect_earnings_projection(text, "en")
    elapsed = time.perf_counter() - started
    assert result is None  # no earner word anywhere in the text
    assert elapsed < 1.0, f"expected well under 1.0s, took {elapsed:.3f}s (possible quadratic regression)"


# --- performance: digit-group runs (_NUM thousands groups, RANGE's bare-figure branch) ---------------------------
#
# `_NUM`'s "(?:[ .,' ]\d{3})+" thousands-group run was retried from every group of a long run of groups, and each
# try rescanned the rest of the run before the suffix ("%" here) failed it: O(n^2) per MONEY_RE scan. Measured on
# the pre-fix detector: detect_earnings_projection(("123 " * n) + "%", "en") took ~1.0s / 4.4s / 16.9s at n = 500 /
# 1,000 / 2,000 (8 KB). RANGE's bare-figure branch "(?<!\w)\d[\d .,]*" had the same shape (reachable through P2's
# unwindowed `span`). The 200 KB bound is on the number scans themselves: the whole detector's ordinary linear cost
# on a 200 KB answer of any kind (plain prose included) is itself around 1s, so the detector-level bound below uses
# the 8 KB input the quadratic path was reported on.

@pytest.mark.parametrize("sep", [" ", ",", ".", "'"])
def test_number_scans_over_a_200kb_run_of_digit_groups_take_well_under_one_second(sep: str) -> None:
    from app.risk.policies.income_projection import MONEY_RE, RANGE

    text = ("123" + sep) * 50_000 + "%"
    assert len(text) > 200_000
    started = time.perf_counter()
    money = list(MONEY_RE.finditer(text))
    found_range = RANGE.search(text)
    elapsed = time.perf_counter() - started
    assert money == [] and found_range is None  # a run ending in "%" is neither an amount nor a range
    assert elapsed < 1.0, f"expected well under 1.0s, took {elapsed:.3f}s (possible quadratic regression)"


def test_detector_on_an_8kb_run_of_digit_groups_evaluates_well_under_one_second() -> None:
    text = "123 " * 2000 + "%"  # 16.9s before the fix
    started = time.perf_counter()
    result = detect_earnings_projection(text, "en")
    elapsed = time.perf_counter() - started
    assert result is None
    assert elapsed < 1.0, f"expected well under 1.0s, took {elapsed:.3f}s (possible quadratic regression)"


def test_range_check_over_a_long_run_of_digit_groups_evaluates_well_under_one_second() -> None:
    """P2's estimate check runs RANGE over the whole segment before the verb (3.3s here before the fix)."""
    text = "fbos " + "123 " * 2000 + "x receive $500 a month"
    started = time.perf_counter()
    result = detect_earnings_projection(text, "en")
    elapsed = time.perf_counter() - started
    assert result is None  # no estimate word and no range: a bare "receive $500" is not a projection
    assert elapsed < 1.0, f"expected well under 1.0s, took {elapsed:.3f}s (possible quadratic regression)"


@pytest.mark.parametrize(
    ("text", "amounts"),
    [
        ("1 000 000 dollars", ["1 000 000 dollars"]),
        ("12345 123 dollars", ["123 dollars"]),  # a 4+ digit head cannot start a grouped number; its tail can
        ("1.5 123 euros", ["5 123 euros"]),
        ("123 456k a month", ["456k"]),
        ("$1 000 000x", ["$1 000"]),
        ("$1 000 000dollars", ["$1 000", "000dollars"]),
        # more than 8 thousands groups after a head that cannot start the number: still one unbounded run
        ("88648,361 418 615 329 631 603 263 602 012 156 396 338 dollars",
         ["361 418 615 329 631 603 263 602 012 156 396 338 dollars"]),
        ("a1 000 000 000 000 000 000 000 000 000 000 dollars", ["000 000 000 000 000 000 000 000 000 000 dollars"]),
    ],
)
def test_money_matches_inside_digit_group_runs_are_unchanged_by_the_linear_scan(text: str, amounts: list[str]) -> None:
    """Pins the pre-fix MONEY_RE matches (computed with the pre-fix module) on the shapes the linear-scan guard
    distinguishes: where a thousands-group run may start, and where it may not."""
    from app.risk.policies.income_projection import MONEY_RE

    assert [m.group() for m in MONEY_RE.finditer(text)] == amounts


@pytest.mark.parametrize(
    ("text", "is_range"),
    [
        ("12 - 15 dollars", True),
        ("between 1 000 and 2 000 euros", True),
        ("x , 5 to 6 euros", True),
        ("a123 123 - 5 dollars", True),  # the first digit not glued to a word is after "a123 "
        ("a123 - 5 dollars", False),  # no digit that can start a figure
        ("1 2 3 4", False),
    ],
)
def test_range_verdicts_are_unchanged_by_the_linear_scan(text: str, is_range: bool) -> None:
    from app.risk.policies.income_projection import RANGE

    assert bool(RANGE.search(text)) is is_range
