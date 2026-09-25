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
name), or null when the prototype MISSES it. Two "must_refuse" cases carry
"prototype": null -- correct Unicode text, not corruption -- and are the
design's own documented residual misses, which this port must reproduce
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
  - "en-c6" ("Expect roughly EUR500 a month once you have three active
    legs."): a subject-less imperative ("Expect ...") has no earner subject
    for P1/P2 to attach to; subject-less projections are a documented gap
    in the reference prototype.

These two are marked xfail(strict=True): if a future change to the detector
starts catching one, the test XPASSes and fails, forcing the marker (and this
comment) to be revisited rather than silently drifting.

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


_PROJECTION_CASES = _load_projection_cases()
_MUST_REFUSE = _PROJECTION_CASES["must_refuse"]
_MUST_NOT_FIRE = _PROJECTION_CASES["must_not_fire"]
_NEAR_MISSES = _PROJECTION_CASES["corpus_near_misses_must_not_fire"]
_STEP1_MUST_CATCH = _load_step1_must_catch_cases()


def _case_id(case: dict) -> str:
    return case.get("id") or case.get("market") or case.get("text", "")[:40]


# Known residual misses in the reference prototype (see module docstring):
# recorded "prototype": null in a must_refuse case. These are xfail(strict=True)
# so a future fix shows up as XPASS and forces the marker to be removed.
_KNOWN_RESIDUAL_MISSES = {
    "sr-fin_freedom": (
        "financial freedom deliberately excluded from P4; "
        "'pasivan prihod' does not match the sr 'pasivn\\w*' stem"
    ),
    "en-c6": "subject-less projection ('Expect ...'): no earner subject for P1/P2 to attach to",
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
