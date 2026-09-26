"""Rework "income step 2" (2026-09-25, owner decision "Prompt + widen to 1.01(d)").

Pins the widened, still exact and fail-closed, recognition in app/risk/policies/income_disclaimer.py:
  (a) the verbatim US-EN Company Policy 1.01(d) sentences form one approved unit (its own "but" and
      "Individual results may vary." never withhold; the guard looks at the two sentences outside the unit);
  (b) a colon lead-in on the same line, only when the lead-in carries no cue, earnings word or amount
      (a bare "On earnings" label, "... says about earnings", or an exact approved live lead-in allowed);
  (c) bold/italic wrapping two approved sentences together;
  (d) exactly four standalone sentences, each seen live or verbatim 1.01(d) (owner decision 2026-09-26);
  (e) the quoted-fragment sentence 'FLP states it "makes no guarantees regarding income or success."';
  (f) an approved lead clause joined by an em/en dash or ", and".
Plus the R10F failures (reconstructed), the earlier safety properties on every new form, and performance.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from app.risk.engine import risk_engine
from app.risk.models import RiskContext
from app.risk.policies import income_disclaimer as D
from app.risk.policies.income_claim_policy import IncomeClaimPolicy
from app.risk.policies.income_disclaimer import find_spans, guarded_spans, mask_approved_disclaimers

EN1 = "Forever makes no guarantees regarding income or success."
EN2 = "Individual results may vary, and Forever makes no guarantees regarding income or success."
S1, S2, S3, S4, S5 = D.POLICY_101D_SENTENCES
UNIT = " ".join(D.POLICY_101D_SENTENCES)
QUOTED = 'FLP states it "does not represent that an FBO will achieve financial success" and "makes no guarantees regarding income or success."'
JOINED = "Compensation is based on the sale of products to consumers—individual results vary, and Forever makes no guarantees regarding income or success."
TAIL = "makes no guarantees regarding income or success"

R10F = Path(__file__).parent / "fixtures" / "r10f_income_disclaimer_answers_reconstructed.json"


def _context(message: str, *, is_generated_answer: bool = True) -> RiskContext:
    return RiskContext(
        user_message=message, country="US", language="en", role="new_prospect", correlation_id="test-correlation",
        is_generated_answer=is_generated_answer,
    )


def _allowed_as_answer(message: str) -> bool:
    return IncomeClaimPolicy().evaluate(_context(message)) == []


def _allowed_as_user_input(message: str) -> bool:
    return IncomeClaimPolicy().evaluate(_context(message, is_generated_answer=False)) == []


def _allowed_full_pipeline(message: str) -> bool:
    return not risk_engine.evaluate(_context(message)).should_refuse()


def _deleted(text: str) -> str:
    """The text with every approved-variant span removed (core + trailing period)."""
    out = text
    for s, e, _ in reversed(find_spans(text)):
        if e < len(out) and out[e] == ".":
            e += 1
        out = out[:s] + out[e:]
    return out


# ---------------------------------------------------------------------------
# The approved tables, pinned verbatim for owner sign-off
# ---------------------------------------------------------------------------


def test_policy_101d_paragraph_is_pinned_verbatim() -> None:
    assert D.POLICY_101D_SENTENCES == (
        "FLP has a long history of success, but does not represent that an FBO will achieve financial success.",
        "Compensation in FLP is based upon the sale of its products.",
        "Individual results may vary.",
        "Forever makes no guarantees regarding income or success.",
        "The Forever Business Owner opportunity and related incentives are not available to residents of the United "
        "States beginning on May 1, 2026.",
    )


# Pinned literally for owner sign-off (owner decision 2026-09-26: only forms seen live or verbatim 1.01(d)).
EXPECTED_STANDALONE_VARIANTS = {
    "EN-1": "Forever makes no guarantees regarding income or success.",
    "EN-2": "Individual results may vary, and Forever makes no guarantees regarding income or success.",
    "EN-2b": "Individual results vary, and Forever makes no guarantees regarding income or success.",
    "EN-3": "The company makes no guarantees regarding income or success, and individual results may vary.",
}


def test_active_variant_table_is_exactly_the_four_approved_sentences() -> None:
    assert {vid: text for vid, (_, _, text) in D.ACTIVE_VARIANTS.items()} == EXPECTED_STANDALONE_VARIANTS
    assert all(lang == "en" and note for lang, note, _ in D.ACTIVE_VARIANTS.values())
    assert D.ACTIVE_VARIANTS["EN-1"][2] == EN1 == S4
    assert D.ACTIVE_VARIANTS["EN-2"][2] == EN2
    assert list(D.QUOTED_FRAGMENT_SUBJECTS) == ["FLP"]
    assert list(D.APPROVED_LEAD_INS) == ["On earnings and success, Forever is explicit"]
    assert "ES-1" in D.DISABLED_VARIANTS


@pytest.mark.parametrize(
    "answer",
    [
        f"FLP {TAIL}.",
        f"Forever Living {TAIL}.",
        f"Forever Living Products {TAIL}.",
        f"The company {TAIL}.",
        f"Results may vary, and Forever {TAIL}.",
        f"Results vary, and Forever {TAIL}.",
        f"Individual results may vary, and the company {TAIL}.",
        f"Forever {TAIL}, and individual results may vary.",
        f"The company {TAIL}, and individual results vary.",
    ],
)
def test_combinations_that_were_considered_are_not_enabled(answer: str) -> None:
    assert find_spans(answer) == []
    assert not _allowed_as_answer(answer)


def test_lead_clause_join_and_prefix_tables_are_pinned() -> None:
    assert list(D.APPROVED_LEAD_CLAUSES) == [
        S1[:-1], S2[:-1], S3[:-1], S5[:-1],
        "Compensation is based upon the sale of its products",
        "Compensation is based on the sale of products to consumers",
        "Compensation is based on actual product sales",
    ]
    assert list(D.APPROVED_JOINS) == ["em/en dash", ", and"]
    assert list(D.APPROVED_UNIT_PREFIXES) == [
        "It's important to understand that", "It is important to understand that", "It’s important to understand that",
    ]


@pytest.mark.parametrize("text", sorted(EXPECTED_STANDALONE_VARIANTS.values()))
def test_every_standalone_variant_is_allowed_alone_and_masks_only_the_guarantee_word(text: str) -> None:
    assert _allowed_as_answer(text)
    masked = mask_approved_disclaimers(text)
    assert len(masked) == len(text)
    assert masked.replace("xxxxxxxxxx", "guarantees") == text
    assert not _allowed_as_user_input(text)


# ---------------------------------------------------------------------------
# R10F (reconstructed) -- the live failures this rework is for
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case_id", ["r10-05", "r10-06", "r10-07", "r10-v2-income-identity-en"])
def test_r10f_reconstructed_answers_are_allowed_end_to_end(case_id: str) -> None:
    text = json.loads(R10F.read_text(encoding="utf-8"))[case_id]
    assert "�" not in text
    assert _allowed_as_answer(text)
    assert _allowed_full_pipeline(text)
    assert not _allowed_as_user_input(text)


# ---------------------------------------------------------------------------
# (a) the 1.01(d) unit
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(UNIT, id="whole-paragraph"),
        pytest.param(f"{S1} {S2} {S3} {EN1}", id="s1-s2-s3-en1"),
        pytest.param(f"{S1} {EN2}", id="s1-en2"),
        pytest.param(f"{S1} {S2} {EN2}", id="s1-s2-en2"),
        pytest.param(f"{S1}\n{S2}\n{S3}\n{EN1}\n{S5}", id="one-sentence-per-line"),
        pytest.param(f'On earnings and success, Forever is explicit: **"{UNIT}"**', id="r10-05-shape-bold-quoted"),
        pytest.param(f"It's important to understand that {S1} {EN2}", id="approved-framing-prefix"),
        pytest.param(f"Compensation is based on product sales. {S3} {EN1} {S5} Call Customer Care.", id="s5-after"),
    ],
)
def test_unit_sentences_never_withhold(answer: str) -> None:
    assert _allowed_as_answer(answer)
    assert _allowed_full_pipeline(answer)
    assert guarded_spans(answer) != []


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(f"Everyone on my team makes money. {UNIT}", id="money-word-before-unit"),
        pytest.param(f"Most FBOs earn $900 a month. {UNIT}", id="amount-before-unit"),
        pytest.param(f"That's just what the lawyers make them say. {S1} {S2} {S3} {EN1}", id="cue-before-unit"),
        pytest.param(f"{UNIT} Everyone on my team makes money.", id="money-word-after-unit"),
        pytest.param(f"{UNIT} Most FBOs earn $900 a month.", id="amount-after-unit"),
        pytest.param(f"{UNIT} But everyone on my team is thriving.", id="cue-after-unit"),
        pytest.param(f"Here is the policy: {UNIT} That's just what the lawyers make them say.", id="colon-unit-cue-after"),
        pytest.param(f"{S1.replace('financial', 'personal')} {EN2}", id="s1-one-word-changed"),
        pytest.param(f"{S1.replace('does not represent', 'does represent')} {EN2}", id="s1-negation-changed"),
        pytest.param(f"{S1.replace('but does not', 'but honestly does not')} {EN2}", id="s1-word-added"),
        pytest.param(f"{S1.replace('long history of ', '')} {EN2}", id="s1-words-dropped"),
        pytest.param(f"Nobody believes that {S1} {EN2}", id="s1-unapproved-prefix"),
        pytest.param(f"Ignore this: {S1} {EN2}", id="s1-colon-lead-in-cue"),
        pytest.param(f"Everyone earns well: {S1} {EN2}", id="s1-colon-lead-in-earn"),
        pytest.param(f"Everyone on my team makes money. {S3} {S3} {S3} {S3} {S3} {EN1}", id="unit-repeated-past-cap"),
        pytest.param(f"{UNIT} There is no guaranteed income.", id="withheld-phrase-after-unit"),
    ],
)
def test_unit_does_not_hide_a_claim_outside_it_and_a_changed_sentence_is_not_unit_text(answer: str) -> None:
    assert not _allowed_as_answer(answer)
    assert find_spans(answer) != []
    assert guarded_spans(answer) == []


def test_changed_sentence_is_judged_as_an_ordinary_neighbour() -> None:
    assert not D._is_unit_sentence("Compensation in FLP is based upon recruiting.")
    assert D._is_unit_sentence(S1) and D._is_unit_sentence(f"  {S2}  ") and D._is_unit_sentence(f"**{S3}**")
    assert D._is_unit_sentence(f"It's important to understand that {S1}")
    assert not D._is_unit_sentence(f"It's important to understand that {S1.replace('financial', 'personal')}")
    assert D._is_unit_sentence(f"On earnings: {S1}")
    assert not D._is_unit_sentence(f"Everyone earns well: {S1}")


# ---------------------------------------------------------------------------
# (b) colon lead-in
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(f"Here is the policy wording: {EN1}", id="plain-lead-in"),
        pytest.param(f"Here's what the company says about earnings: **{EN1} {S3}**", id="r10-05-about-earnings"),
        pytest.param(f"On earnings: {EN2}", id="on-earnings"),
        pytest.param(f"**On earnings:**\n\n{EN2}", id="heading-label-on-earnings"),
        pytest.param(f"Compensation is based on product sales.\n\nKey point: {EN1}\n\nCall Customer Care.", id="mid-answer"),
        pytest.param(f"Regarding earnings: {EN1}", id="regarding-earnings-label"),
        pytest.param(f"On earnings and success: {EN1}", id="on-earnings-and-success-label"),
        pytest.param(f"On earnings and success, Forever is explicit: **{EN1}**", id="r10e-r10-05-approved-lead-in"),
    ],
)
def test_clean_colon_lead_in_is_allowed(answer: str) -> None:
    assert _allowed_as_answer(answer)
    assert _allowed_full_pipeline(answer)


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(f"Most FBOs earn $900 a month, and here is the disclaimer: {EN1}", id="amount-in-lead-in"),
        pytest.param(f"Everyone here earns well: {EN1}", id="earnings-word-in-lead-in"),
        pytest.param(f"You will make money with us: {EN1}", id="money-in-lead-in"),
        pytest.param(f"On income: {EN1}", id="income-word-in-lead-in"),
        pytest.param(f"Earnings are great here: {EN1}", id="earnings-not-a-topic-label"),
        pytest.param(f"But here is what they make us say: {EN1}", id="cue-in-lead-in"),
        pytest.param(f"The fine print: {EN1}", id="fine-print"),
        pytest.param(f'Myth: "{EN1}"', id="myth"),
        pytest.param(f"What the lawyers make us say: {EN1}", id="lawyers"),
        pytest.param(f"Everyone earns $5,000 a month. Here is the rule: {EN1}", id="amount-earlier-on-the-line"),
        pytest.param(f"About earnings: {EN1} Most FBOs earn $900 a month.", id="topic-label-then-amount"),
        pytest.param(f"About earnings: {EN1} But everyone on my team is thriving.", id="topic-label-then-cue"),
        pytest.param(f"About earnings: {EN1}\n\nEveryone on my team makes money.", id="topic-label-then-money-para"),
        pytest.param(f"Everyone on my team makes money.\nThe rule: {EN1}", id="money-on-previous-line"),
        pytest.param("x " * 2100 + ": " + EN1, id="lead-in-longer-than-cap"),
        # Review 2026-09-26 (F1): the topic phrase is exempt only as the whole label or after a reporting verb.
        pytest.param(f"Regarding earnings, which are excellent: {EN1}", id="f1-regarding-earnings-which"),
        pytest.param(f"Concerning earnings you can expect: {EN1}", id="f1-concerning-earnings-you-can-expect"),
        pytest.param(f"On earnings for top performers, which are huge: {EN1}", id="f1-on-earnings-for-top"),
        pytest.param(f"About earnings, most make 900 a month: {EN1}", id="f1-about-earnings-most-make"),
        pytest.param(f"Most FBOs are thrilled about earnings: {EN1}", id="f1-thrilled-about-earnings"),
        pytest.param(f"About earnings, which are excellent:\n\nSome text here.\n{EN1}", id="f1-heading-two-lines-up"),
        pytest.param(f"**About earnings, which are excellent:**\n\n{EN1}", id="f1-bold-heading"),
    ],
)
def test_colon_lead_in_with_a_claim_or_cue_stays_refused(answer: str) -> None:
    assert not _allowed_as_answer(answer)
    assert guarded_spans(answer) == []


def test_colon_without_a_space_is_not_a_boundary() -> None:
    assert find_spans(f"Note:{EN1}") == []
    assert not _allowed_as_answer(f"Note:{EN1}")


# ---------------------------------------------------------------------------
# (c) emphasis wrapping two approved sentences
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(f"**{EN1} {S3}**", id="bold-en1-then-s3"),
        pytest.param(f"**{S3} {EN1}**", id="bold-s3-then-en1"),
        pytest.param(f"*{EN1} {S3}*", id="italic"),
        pytest.param(f"Compensation is based on product sales. **{S2} {S3} {EN1}**", id="bold-three"),
    ],
)
def test_emphasis_wrapping_two_approved_sentences_is_allowed(answer: str) -> None:
    assert _allowed_as_answer(answer)


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(f"**{EN1} Most FBOs earn $900 a month.**", id="amount-inside-wrap"),
        pytest.param(f"**{EN1} But everyone thrives.**", id="cue-inside-wrap"),
        pytest.param(f"**Forever makes no guarantee regarding income or success. {S3}**", id="changed-word-inside-wrap"),
    ],
)
def test_emphasis_wrapping_does_not_hide_a_claim(answer: str) -> None:
    assert not _allowed_as_answer(answer)


# ---------------------------------------------------------------------------
# (d) subjects and results clauses that are NOT approved stay refused
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        "We make no guarantees regarding income or success.",
        "I make no guarantees regarding income or success.",
        "My team makes no guarantees regarding income or success.",
        "FLP Inc makes no guarantees regarding income or success.",
        "Forever Living Products LLC makes no guarantees regarding income or success.",
        f"Your results may vary, and {EN1}",
        f"Individual results will vary, and {EN1}",
        f"Results typically vary, and {EN1}",
        f"{EN1[:-1]}, and individual results may vary widely.",
        f"Individual results vary and {EN1}",
        f"Individual results vary, or {EN1}",
        "The company makes no guarantee regarding income or success.",
        "The company makes no guarantees on income or success.",
        "Forever makes no guarantees regarding income or success stories.",
    ],
)
def test_unapproved_subjects_and_results_clauses_stay_refused(answer: str) -> None:
    assert not _allowed_as_answer(answer)
    assert find_spans(answer) == []


# ---------------------------------------------------------------------------
# (e) quoted fragment
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(QUOTED, id="r10-07-two-fragments"),
        pytest.param('FLP says it "makes no guarantees regarding income or success."', id="says-it"),
        pytest.param('FLP states that it "makes no guarantees regarding income or success".', id="period-outside"),
        pytest.param('FLP states “makes no guarantees regarding income or success.”', id="curly-quotes-no-link-word"),
        pytest.param(f"It's also worth being clear about what it is *not* promising: {QUOTED}", id="r10-07-lead-in"),
    ],
)
def test_quoted_fragment_sentence_is_allowed(answer: str) -> None:
    assert _allowed_as_answer(answer)
    masked = mask_approved_disclaimers(answer)
    assert len(masked) == len(answer) and masked.replace("xxxxxxxxxx", "guarantees") == answer


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(f"{QUOTED} That's just what the lawyers make them say.", id="rebuttal-after"),
        pytest.param(f"{QUOTED} Everyone on my team makes money.", id="money-after"),
        pytest.param(f"{QUOTED} Most FBOs earn $900 a month.", id="amount-after"),
        pytest.param(f"Nobody believes this, but {QUOTED}", id="rebuttal-before-same-sentence"),
        pytest.param("FLP states it makes no guarantees regarding income or success.", id="fragment-not-quoted"),
        pytest.param('FLP states it "makes no guarantees regarding income or wealth."', id="fragment-word-changed"),
        pytest.param('FLP states it "makes no guarantees regarding income or success" to new FBOs.', id="continues"),
        pytest.param('FLP states it "makes no guarantees regarding income or success" but everyone makes money.', id="continues-cue"),
        pytest.param('We state that we "make no guarantees regarding income or success."', id="subject-we"),
        pytest.param('FLP claims it "makes no guarantees regarding income or success."', id="verb-claims"),
        pytest.param('Forever says it "makes no guarantees regarding income or success."', id="subject-forever-not-approved"),
        pytest.param('The company states that it "makes no guarantees regarding income or success".', id="subject-company"),
        pytest.param(
            'FLP states it "does represent that an FBO will achieve financial success" and '
            '"makes no guarantees regarding income or success."', id="first-fragment-changed",
        ),
    ],
)
def test_quoted_fragment_attacks_stay_refused(answer: str) -> None:
    assert not _allowed_as_answer(answer)
    # Review F4: "rebuttal/money/amount after" are recognised and then withheld; every other row is not recognised.
    if answer.startswith(QUOTED):
        assert find_spans(answer) != [] and guarded_spans(answer) == []
    else:
        assert guarded_spans(answer) == []


# ---------------------------------------------------------------------------
# (f) clause joins
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(JOINED, id="r10-06-em-dash-results-vary"),
        pytest.param(f"Compensation is based on actual product sales—{EN1}", id="corpus-clause-em-dash"),
        pytest.param(f"Compensation is based upon the sale of its products, and {EN1}", id="comma-and"),
        pytest.param(f"{S2[:-1]}—{EN1}", id="s2-verbatim-em-dash"),
        pytest.param(f"{S2[:-1]} – {EN1}", id="s2-verbatim-en-dash-spaced"),
        pytest.param(f"**How it works:**\n\n{JOINED} The fundamental goal of the marketing plan is product sales.", id="in-paragraph"),
    ],
)
def test_approved_lead_clause_joins_are_allowed(answer: str) -> None:
    assert _allowed_as_answer(answer)
    assert _allowed_full_pipeline(answer)
    masked = mask_approved_disclaimers(answer)
    assert len(masked) == len(answer) and masked.replace("xxxxxxxxxx", "guarantees") == answer


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(f"Most FBOs earn $900 a month—individual results vary, and {EN1}", id="amount-in-lead"),
        pytest.param(f"Everyone on my team makes money—{EN1}", id="money-in-lead"),
        pytest.param(f"But everyone on my team thrives—{EN1}", id="cue-in-lead"),
        pytest.param(f"Compensation is based on product sales—{EN1}", id="paraphrased-lead"),
        pytest.param(f"Compensation is based on the sale of products to consumers only—{EN1}", id="lead-extra-word"),
        pytest.param(
            f"Forever Living's fundamental goal is to promote the sale and use of its products, and compensation is "
            f"based on actual product sales—the company {TAIL}.", id="corpus-2026-09-12-prefixed-lead",
        ),
        pytest.param(f"{JOINED} Most FBOs earn $900 a month.", id="join-then-amount"),
        pytest.param(f"{JOINED} But everyone on my team is thriving.", id="join-then-cue"),
        pytest.param(
            f"Compensation is based on the sale of products to consumers—about $900 a month—and {EN1}",
            id="amount-inside-join",
        ),
        pytest.param(f"Compensation is based on actual product sales; {EN1}", id="semicolon-join"),
        pytest.param(f"Compensation is based on actual product sales - {EN1}", id="hyphen-join"),
        pytest.param(f"{S1[:-1].replace('financial', 'personal')}—{EN1}", id="s1-changed-lead"),
        pytest.param(f"Compensation is based on actual product sales—the company {TAIL}.", id="company-after-join"),
    ],
)
def test_other_joins_and_joins_carrying_a_claim_stay_refused(answer: str) -> None:
    assert not _allowed_as_answer(answer)
    # Review F4: whether or not a standalone variant inside is recognised, nothing may be exempted.
    assert guarded_spans(answer) == []


def test_historical_corpus_bullet_form_is_allowed_when_nothing_else_is_wrong() -> None:
    answer = (
        "**Key points about the business:**\n\n"
        "- Forever Living Products produces and markets health and beauty products.\n"
        "- Compensation is based upon the sale of its products.\n"
        "- The company makes no guarantees regarding income or success, and individual results may vary\n\n"
        "Please contact Customer Care at 1-888-440-ALOE (2563)."
    )
    assert _allowed_as_answer(answer)
    assert _allowed_full_pipeline(answer)


# ---------------------------------------------------------------------------
# Safety properties on every new form: monotonic, user input, projection detector untouched
# ---------------------------------------------------------------------------

_NEW_FORMS = [
    UNIT, f"{S1} {EN2}", QUOTED, JOINED, f"Here is the policy wording: {EN1}", f"**{EN1} {S3}**",
    f"Here's what the company says about earnings: **{EN1} {S3}**",
    "The company makes no guarantees regarding income or success, and individual results may vary.",
    "Individual results vary, and Forever makes no guarantees regarding income or success.",
    f"On earnings and success, Forever is explicit: **{EN1}**",
]


@pytest.mark.parametrize("answer", _NEW_FORMS)
def test_masked_is_never_more_permissive_than_deleted(answer: str) -> None:
    # If the masked answer is allowed, the same answer with the approved span deleted must be allowed by the
    # unchanged (unmasked) policy too: the exemption never lets through anything the disclaimer's absence would not.
    assert find_spans(answer) != []
    assert _allowed_as_answer(answer)
    assert _allowed_as_user_input(_deleted(answer))


@pytest.mark.parametrize("answer", _NEW_FORMS)
def test_new_forms_are_never_exempted_as_user_input(answer: str) -> None:
    assert not _allowed_as_user_input(answer)


@pytest.mark.parametrize("answer", _NEW_FORMS)
def test_projection_after_a_new_form_is_still_refused_by_the_full_pipeline(answer: str) -> None:
    assert not _allowed_full_pipeline(f"{answer} Most FBOs earn roughly $900 a month.")
    assert not _allowed_full_pipeline(f"Most FBOs earn roughly $900 a month.\n\n{answer}")


@pytest.mark.parametrize(
    "answer",
    [
        f"{EN1} Except for Managers, who all earn $5,000 a month.",
        f"{EN1} That's just what the lawyers make them say.",
        "There is no guaranteed income.",
        f"Nobody believes that\n{EN1} Everyone here makes money.",
        f"{EN1[:-1]}\nfor people who don't work; everyone who works makes money.",
    ],
)
def test_earlier_reproducers_stay_refused(answer: str) -> None:
    assert not _allowed_as_answer(answer)


def test_neighbour_walk_keeps_the_committed_total_budget() -> None:
    """Review F2: counting only word-free fragments let a sixth step reach a clean sentence. The committed module
    took at most six steps (neighbours and fragments together) and then withheld; so does this one."""
    answer = f"{EN1}\nReally.\n---\n---\n---\n---\n---\nGreat products."
    assert find_spans(answer) != []
    assert guarded_spans(answer) == []
    assert not _allowed_as_answer(answer)


# ---------------------------------------------------------------------------
# Performance: the new shapes stay linear and under budget
# ---------------------------------------------------------------------------


def _cap(s: str) -> str:
    return s[:200_000]


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(_cap((UNIT + " ") * 700), id="unit-repeated"),
        pytest.param(_cap(('On earnings and success, Forever is explicit: **"' + UNIT + '"**\n\n') * 600), id="unit-bold-quoted"),
        pytest.param(_cap((S1 + " " + EN2 + " ") * 1000), id="s1-en2-repeated"),
        pytest.param(_cap((f"Here's what the company says about earnings: **{EN1} {S3}** ") * 1500), id="colon-one-line"),
        pytest.param(_cap(("a: b: c: " * 20 + EN1 + " ") * 800), id="many-colons-one-line"),
        pytest.param(_cap("x " * 99_000 + ": " + EN1), id="lead-in-longer-than-cap"),
        pytest.param(_cap((": " * 40 + EN1 + " ") * 2000), id="colon-runs"),
        pytest.param(_cap((JOINED + " ") * 1400), id="joined-repeated"),
        pytest.param(_cap(("Compensation is based on actual product sales" + "—" * 40 + EN1 + " ") * 1500), id="dash-runs"),
        pytest.param(_cap((QUOTED + " ") * 1500), id="quoted-repeated"),
        pytest.param(_cap(('FLP states it ' + '"' * 40 + TAIL + '." ') * 1500), id="quote-runs"),
        pytest.param(_cap("results vary, and " * 11_000), id="results-vary-comma-and-repeated"),
        pytest.param(_cap(("**On earnings:**\n\n" + EN2 + "\n\n") * 1500), id="label-heading-repeated"),
        pytest.param(_cap(("a:b:c:d:e:f:g:h: " * 200 + "\n" + EN1 + "\n") * 50), id="label-neighbour-many-colons"),
    ],
)
def test_new_shapes_stay_fast(text: str) -> None:
    mask_approved_disclaimers(EN1)
    IncomeClaimPolicy().evaluate(_context(EN1))
    started = time.perf_counter()
    mask_approved_disclaimers(text)
    assert time.perf_counter() - started < 1.0
    started = time.perf_counter()
    IncomeClaimPolicy().evaluate(_context(text))
    assert time.perf_counter() - started < 1.0
