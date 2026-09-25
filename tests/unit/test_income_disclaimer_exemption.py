"""Tests for the approved income-disclaimer exemption (app/risk/policies/income_disclaimer.py).

Covers: the exemption applying only to the two approved variants and only on
the generated-answer pass, the exact normalisation rules, adjacency-guard
cues, the "There is no guaranteed income." must-catch phrase, and the R10E
regression fixtures (r10-05/06/07).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from app.risk.engine import risk_engine
from app.risk.models import RiskContext
from app.risk.policies.income_claim_policy import IncomeClaimPolicy
from app.risk.policies.income_disclaimer import find_spans, guarded_spans, mask_approved_disclaimers

EN1 = "Forever makes no guarantees regarding income or success."
EN2 = "Individual results may vary, and Forever makes no guarantees regarding income or success."

FIXTURES = Path(__file__).parent / "fixtures" / "r10e_income_disclaimer_answers.json"


def _context(message: str, *, is_generated_answer: bool) -> RiskContext:
    return RiskContext(
        user_message=message,
        country="US",
        language="en",
        role="new_prospect",
        correlation_id="test-correlation",
        is_generated_answer=is_generated_answer,
    )


def _allowed_as_answer(message: str) -> bool:
    policy = IncomeClaimPolicy()
    return policy.evaluate(_context(message, is_generated_answer=True)) == []


def _allowed_as_user_input(message: str) -> bool:
    policy = IncomeClaimPolicy()
    return policy.evaluate(_context(message, is_generated_answer=False)) == []


def _allowed_full_pipeline(message: str, *, is_generated_answer: bool = True) -> bool:
    """Run the whole risk-policy pipeline (IncomeClaimPolicy + IncomeProjectionPolicy + ...)."""
    decision = risk_engine.evaluate(_context(message, is_generated_answer=is_generated_answer))
    return not decision.should_refuse()


# ---------------------------------------------------------------------------
# Each approved variant, alone and inside a realistic answer paragraph
# ---------------------------------------------------------------------------


def test_en1_allowed_alone_as_generated_answer() -> None:
    assert _allowed_as_answer(EN1)


def test_en2_allowed_alone_as_generated_answer() -> None:
    assert _allowed_as_answer(EN2)


def test_en1_allowed_inside_multi_sentence_answer() -> None:
    answer = (
        "Forever Living Products sells health and beauty products through independent Forever "
        "Business Owners. Compensation is based upon the sale of its products. "
        f"{EN1} Call Customer Care at 1-888-440-ALOE (2563) for more information."
    )
    assert _allowed_as_answer(answer)


def test_en2_allowed_inside_multi_sentence_answer() -> None:
    answer = (
        "FLP does not represent that an FBO will achieve financial success. Compensation is "
        f"based upon the sale of its products. {EN2}\n\nIf you have questions, contact Customer Care."
    )
    assert _allowed_as_answer(answer)


# ---------------------------------------------------------------------------
# Edge normalisations that must still be recognised
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        # curly quotes wrapping the sentence, after a sentence boundary
        f"Compensation is based on product sales. “{EN1}”",
        # bold markdown emphasis, after a sentence boundary
        f"Compensation is based on product sales. **{EN1}**",
        # bullet list marker
        f"Key points:\n- {EN1}",
        # blockquote marker
        f"> {EN1}",
        # line-wrapped sentence (internal whitespace run, including a newline)
        "Compensation is based upon the sale of its products. Forever makes no guarantees\nregarding income or success.",
        # missing final period
        f"Compensation is based upon the sale of its products. {EN1[:-1]}",
        # upper case
        "COMPENSATION IS BASED UPON THE SALE OF ITS PRODUCTS. FOREVER MAKES NO GUARANTEES REGARDING INCOME OR SUCCESS.",
    ],
)
def test_normalised_variants_are_still_recognised(answer: str) -> None:
    assert _allowed_as_answer(answer)


# ---------------------------------------------------------------------------
# Non-matches: any deviation from the exact approved sentence must stay refused
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        # a word changed inside the sentence
        "Compensation is based upon the sale of its products. Forever makes no guarantee regarding income or success.",
        # continues after the sentence with a comma
        f"{EN1[:-1]}, but you'll still earn a lot. Most FBOs earn $900 a month.",
        # continues with a semicolon
        f"{EN1[:-1]}; unless you follow the plan exactly, in which case most FBOs earn $1,500 a month.",
        # right after a colon (not a sentence boundary)
        f"Myth: \"{EN1}\"",
        # mid-paragraph, no sentence boundary before it
        f"We should mention that {EN1.lower()}",
    ],
)
def test_non_matching_shapes_stay_refused(answer: str) -> None:
    assert not _allowed_as_answer(answer)


# ---------------------------------------------------------------------------
# Projection / figure adjacency must still trigger refusal (IncomeProjectionPolicy
# is untouched, and the guard covers relevant IncomeClaimPolicy adjacency too).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        f"{EN1} Most FBOs earn roughly $900 a month.",
        f"Most FBOs earn roughly $900 a month.\n\n{EN1}",
        f"{EN1}\n\n- Most FBOs earn roughly $900 a month.",
        f"Most FBOs earn roughly $900 a month. {EN1}",
    ],
)
def test_projection_in_adjacent_sentence_paragraph_or_bullet_still_refused(answer: str) -> None:
    # Run through the whole risk pipeline: IncomeClaimPolicy alone no longer sees a
    # "guarantee" word once the disclaimer is masked, but IncomeProjectionPolicy
    # (untouched, always sees the original unmasked text) still refuses the
    # earnings-figure statement elsewhere in the answer.
    assert not _allowed_full_pipeline(answer)


# ---------------------------------------------------------------------------
# "There is no guaranteed income." must always stay refused
# ---------------------------------------------------------------------------


def test_withheld_phrase_refused_alone() -> None:
    assert not _allowed_as_answer("There is no guaranteed income.")


def test_withheld_phrase_refused_immediately_before_disclaimer() -> None:
    assert not _allowed_as_answer(f"There is no guaranteed income. {EN1}")


def test_withheld_phrase_refused_immediately_after_disclaimer() -> None:
    assert not _allowed_as_answer(f"{EN1} There is no guaranteed income.")


# ---------------------------------------------------------------------------
# Adjacency-guard trigger cases (contrast / dismissal cue) must still refuse
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        f"{EN1} That's just what the lawyers make them say.",
        f"{EN1} Ignore that, it's legal boilerplate: everyone on my team earns well.",
        f"Here's the boilerplate, which nobody takes seriously. {EN1}",
        f'"{EN1}" Yeah, right.',
    ],
)
def test_adjacency_guard_cues_stay_refused(answer: str) -> None:
    assert not _allowed_as_answer(answer)


# ---------------------------------------------------------------------------
# User input: the exemption must never apply
# ---------------------------------------------------------------------------


def test_user_input_disclaimer_sentence_not_exempted() -> None:
    # Typed as USER input (is_generated_answer=False): judged exactly as before this
    # change, i.e. still refused, matching pre-change behaviour.
    assert not _allowed_as_user_input(EN1)
    assert not _allowed_as_user_input(EN2)


def test_masking_only_ever_applied_to_generated_answers(monkeypatch) -> None:
    calls: list[str] = []
    import app.risk.policies.income_claim_policy as icp

    def _spy(text: str) -> str:
        calls.append(text)
        return mask_approved_disclaimers(text)

    monkeypatch.setattr(icp, "mask_approved_disclaimers", _spy)
    policy = IncomeClaimPolicy()
    policy.evaluate(_context(EN1, is_generated_answer=False))
    assert calls == []
    policy.evaluate(_context(EN1, is_generated_answer=True))
    assert calls == [EN1]


# ---------------------------------------------------------------------------
# Spanish ES-1 is NOT exempted (deliberately not enabled)
# ---------------------------------------------------------------------------


def test_spanish_es1_sentence_not_exempted() -> None:
    es1 = "Forever no ofrece garantía de ingresos o éxito."
    context = RiskContext(
        user_message=es1,
        country="ES",
        language="es",
        role="new_prospect",
        correlation_id="test-correlation",
        is_generated_answer=True,
    )
    issues = IncomeClaimPolicy().evaluate(context)
    assert issues != []


# ---------------------------------------------------------------------------
# Performance: linear time, no catastrophic backtracking
# ---------------------------------------------------------------------------


def test_mask_is_linear_time_on_pathological_input() -> None:
    near_miss = (
        "Forever makes no guarantee regarding income or success, but you'll still earn a lot. " * 5000
    )
    started = time.perf_counter()
    mask_approved_disclaimers(near_miss)
    elapsed = time.perf_counter() - started
    assert elapsed < 1.0


_EN1 = "Forever makes no guarantees regarding income or success."


def _repeat_to(unit: str, size: int) -> str:
    return (unit * (size // len(unit) + 1))[:size]


_S40 = " " * 40
# F1 reviewer shapes: an open-marker run, an emphasis run, and a right-boundary that ultimately fails to match,
# forcing the (now possessive) edge groups to be retried across a long run of edge whitespace. Measured before the
# fix: 28.5 s on 200 KB for the last shape below.
_F1_SHAPES = {
    "marker-spaces-stars8-then-core-fail": ". " + _S40 + "- " + _S40 + "********" + _S40 + _EN1[:-1] + "x" + " ",
    "marker-stars8-right-close-fail": (
        ". " + _S40 + "- " + _S40 + "********" + _S40 + _EN1[:-1] + _S40 + "****" + _S40 + "x "
    ),
}


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(_EN1 + " " * 200_000 + _EN1, id="long-space-run-between-disclaimers"),
        pytest.param(_EN1[:-1] + " " * 200_000, id="long-space-run-after-unterminated-disclaimer"),
        pytest.param(_EN1 + "\t" * 200_000, id="long-tab-run"),
        pytest.param((_EN1 + " ") * 16_000, id="disclaimer-repeated-16000-times"),
        pytest.param(("\n" + " " * 39) * 20_000 + _EN1, id="many-lines-of-edge-whitespace"),
        pytest.param('"' * 100_000 + _EN1, id="long-quote-run"),
        pytest.param(
            _repeat_to(_F1_SHAPES["marker-spaces-stars8-then-core-fail"], 200_000),
            id="marker-spaces-stars8-then-core-fail-200kb",
        ),
        pytest.param(
            _repeat_to(_F1_SHAPES["marker-stars8-right-close-fail"], 200_000),
            id="marker-stars8-right-close-fail-200kb",
        ),
        pytest.param(
            _repeat_to(f"{_EN1} Really. Officially. Managers earn $5,000 a month.\n\n", 200_000),
            id="review-round2-many-disclaimers-many-sentences-200kb",
        ),
    ],
)
def test_mask_stays_fast_on_long_whitespace_and_repetition(text: str) -> None:
    # Measured before the fix: 200,000 spaces took 170 s, 16,000 repeated disclaimers 4.9 s, and the
    # marker-stars8-right-close-fail shape (edge markers + emphasis + a right boundary that ultimately fails) 28.5 s.
    # The last shape (review round 2) stresses the widened two-neighbour-sentence guard and the whole-text
    # MONEY_RE-elsewhere scan on a 200 KB text made of many short sentences and many repeated disclaimers.
    started = time.perf_counter()
    mask_approved_disclaimers(text)
    assert time.perf_counter() - started < 2.0


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(
            _repeat_to(_F1_SHAPES["marker-spaces-stars8-then-core-fail"], 200_000),
            id="marker-spaces-stars8-then-core-fail-200kb",
        ),
        pytest.param(
            _repeat_to(_F1_SHAPES["marker-stars8-right-close-fail"], 200_000),
            id="marker-stars8-right-close-fail-200kb",
        ),
        pytest.param(
            _repeat_to(f"{_EN1} Really. Officially. Managers earn $5,000 a month.\n\n", 200_000),
            id="review-round2-many-disclaimers-many-sentences-200kb",
        ),
    ],
)
def test_mask_and_full_policy_evaluate_stay_fast_on_f1_shapes(text: str) -> None:
    # mask_approved_disclaimers AND the full IncomeClaimPolicy.evaluate (which also lower-cases and runs the
    # guarantee/earnings pairing check) must both stay under budget on every F1 perf shape.
    started = time.perf_counter()
    mask_approved_disclaimers(text)
    assert time.perf_counter() - started < 1.0
    policy = IncomeClaimPolicy()
    started = time.perf_counter()
    policy.evaluate(_context(text, is_generated_answer=True))
    assert time.perf_counter() - started < 1.0


def test_edge_whitespace_beyond_the_cap_is_not_exempted() -> None:
    # A capped edge run can only fail to match; the answer is then judged exactly as before (refused).
    assert mask_approved_disclaimers(" " * 200 + _EN1) == " " * 200 + _EN1
    assert "guarantees" not in mask_approved_disclaimers(" " * 10 + _EN1)


# ---------------------------------------------------------------------------
# F2: an earnings word or a currency-anchored amount next to the disclaimer withholds the exemption, exactly like
# a contrast/dismissal cue.
# ---------------------------------------------------------------------------


# Same-line shapes: the disclaimer sentence itself still matches (find_spans != []); the earnings/amount word in
# the adjacent sentence is what withholds the exemption (guarded_spans == []) -- this pins the F2 guard mechanism.
_F2_SAME_LINE = [
    pytest.param(f"{EN1} Except for Managers, who all earn $5,000 a month.", id="except-earn-amount"),
    pytest.param(f"{EN2} Except for Managers, who all earn $5,000 a month.", id="en2-except-earn-amount"),
    pytest.param(f"{EN1} I promise you will earn money.", id="promise-earn-money"),
    pytest.param(f"{EN1} You will make money with us.", id="make-money-with-us"),
    pytest.param(f"{EN1} Everyone on my team makes money.", id="everyone-makes-money"),
    pytest.param(f'"{EN1}" is a lie; everyone here makes money.', id="is-a-lie-everyone-makes-money"),
]
# Line-break shapes: review round 3's N3 tightened the no-period right boundary (F3) to require a blank line or
# end of text, so these -- a "\n" straight onto a lower-case money continuation -- now fail to match at all
# (find_spans == []), the same as any other F3 continuation. They stay in this F2 suite because they were
# originally written to probe the earnings/amount guard specifically; the outcome (refused) is unchanged, only
# which mechanism produces it.
_F2_LINE_BREAK = [
    pytest.param(f"{EN1[:-1]}\nabove $2,000 a month.", id="nl-above-amount"),
    pytest.param(f"{EN1[:-1]}\nunder $10,000 a month, which most Managers reach.", id="nl-under-amount"),
    pytest.param(f"{EN1[:-1]}\nexcept for Managers, who all earn $5,000 a month.", id="nl-except-earn-amount"),
    pytest.param(f"{EN1[:-1]}\nso the typical $900 a month is only an average.", id="nl-so-amount"),
    pytest.param(f"{EN2[:-1]}\nabove $2,000 a month.", id="en2-nl-above-amount"),
]


@pytest.mark.parametrize("answer", _F2_SAME_LINE)
def test_f2_earnings_or_amount_adjacent_to_disclaimer_stays_refused(answer: str) -> None:
    assert not _allowed_as_answer(answer)
    assert find_spans(answer) != []
    assert guarded_spans(answer) == []


@pytest.mark.parametrize("answer", _F2_LINE_BREAK)
def test_f2_earnings_or_amount_across_line_break_stays_refused(answer: str) -> None:
    assert not _allowed_as_answer(answer)
    # N3 (review round 3) tightened the no-period right boundary so these no longer match at all (find_spans ==
    # []); guarded_spans is then trivially empty too. Either mechanism refuses the answer.
    assert find_spans(answer) == []
    assert guarded_spans(answer) == []


# ---------------------------------------------------------------------------
# F3: a bare line break only closes the disclaimer sentence when the previous/next line actually ends/begins a new
# sentence; a continuing sentence across the line break must NOT match.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(
            f"{EN1[:-1]}\nfor people who don't work; everyone who works makes money.",
            id="right-continuation-no-comma",
        ),
        pytest.param(
            f"{EN1[:-1]}\nunless you join our team, where income is certain.", id="right-continuation-unless"
        ),
        pytest.param(
            f"{EN1[:-1]}\nexcept for Managers, who all earn $5,000 a month.", id="right-continuation-except"
        ),
        pytest.param(
            f"Nobody believes that\n{EN1} Everyone here makes money.", id="left-continuation-nobody-believes"
        ),
        pytest.param(f"We do not accept that\n{EN1} Everyone here makes money.", id="left-continuation-we-do-not"),
    ],
)
def test_f3_line_break_continuation_stays_refused(answer: str) -> None:
    assert not _allowed_as_answer(answer)
    assert find_spans(answer) == []


# ---------------------------------------------------------------------------
# F4: the guard's neighbouring-sentence search must not be truncated by an abbreviation's period or a numbered
# list marker's period.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(
            f"{EN1} In the U.S. but not elsewhere, everyone makes money.", id="abbreviation-us-but-money"
        ),
        pytest.param(f"1. {EN1}\n2. But everyone makes money.", id="numbered-list-but-money"),
        pytest.param(
            f"{EN1} Consider e.g. my team, but everyone there makes money.", id="abbreviation-eg-but-money"
        ),
    ],
)
def test_f4_guard_window_not_truncated_by_abbreviation_or_list_marker(answer: str) -> None:
    assert not _allowed_as_answer(answer)
    assert find_spans(answer) != []
    assert guarded_spans(answer) == []


# ---------------------------------------------------------------------------
# Review round 2 (2026-09-25): the guard now also looks at the SECOND neighbouring sentence on each side (a short
# filler sentence, heading, or emphasis-only line must not hide the actual cue/claim behind it), and withholds the
# exemption whenever a currency-anchored amount appears anywhere else in the answer, however far from the
# disclaimer.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(f"{EN1} Really. But everyone makes money.", id="guard-2away-cue-past-filler-sentence"),
        pytest.param(
            f"{EN1}\n\n**Reality**\n\nEveryone makes money.", id="guard-heading-between-cue-past-heading"
        ),
        pytest.param(
            f"{EN1}\n\n**Heading**\n\nExcept for Managers, who all earn $5,000 a month.",
            id="money-sentence-two-away-after-heading",
        ),
        pytest.param(
            f"{EN1}\n\nP1.\n\nP2.\n\nP3.\n\nAbove $2,000 a month.",
            id="amount-five-paragraphs-away",
        ),
    ],
)
def test_review_round2_second_neighbour_and_amount_anywhere_stay_refused(answer: str) -> None:
    assert not _allowed_as_answer(answer)
    assert find_spans(answer) != []
    assert guarded_spans(answer) == []


# ---------------------------------------------------------------------------
# Review round 3 (2026-09-25).
# N2 (blocking): a paragraph break ("\n\n", "\n\n\n", "\n \n") before the disclaimer used to fill both previous
# neighbour slots with empty fragments (each bare "\n" ends a "sentence"), silently disabling the previous-sentence
# guard. Neighbours are now the two nearest sentences that contain a word character, skipping empty or
# punctuation-only fragments (see _prev_neighbours/_next_neighbours).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(f"Everyone on my team makes money.\n\n{EN1}", id="para-money-before"),
        pytest.param(f"I promise you will earn money.\n\n{EN1}", id="para-promise-before"),
        pytest.param(f"That's just what the lawyers make them say.\n\n{EN1}", id="para-cue-before"),
        pytest.param(f"Everyone on my team makes money.\n\n\n{EN1}", id="para-money-before-triple-nl"),
        pytest.param(f"Everyone on my team makes money.\n \n{EN1}", id="para-money-before-nl-space-nl"),
        pytest.param(f"Everyone on my team makes money.\n\n**Note**\n\n{EN1}", id="para-heading-money-before"),
    ],
)
def test_n2_paragraph_break_before_disclaimer_stays_refused(answer: str) -> None:
    assert not _allowed_as_answer(answer)
    assert find_spans(answer) != []
    assert guarded_spans(answer) == []


# ---------------------------------------------------------------------------
# N1 (blocking, performance): _SENT_END (F4) only ends a sentence at an upper-case/digit boundary, so a text where
# every period is followed by a lower-case letter never ends a sentence -- the (pre-round-3) neighbour scan then
# walked to the edge of the whole text for every span. Measured before the fix: 85-104 s on this 200 KB shape.
# ---------------------------------------------------------------------------

_N1_LOWER_REPEAT_200KB = ("forever makes no guarantees regarding income or success. " * 3500)[:200_000]


def test_n1_lowercase_repeat_shape_is_refused() -> None:
    # "forever" lower-case never matches an ACTIVE_VARIANTS sentence (case-insensitive matching still needs the
    # exact word sequence; the point of this shape is purely to stress the neighbour scan, not to match).
    assert not _allowed_as_answer(_N1_LOWER_REPEAT_200KB)


def test_n1_lowercase_repeat_shape_stays_fast() -> None:
    # Warm up regex compilation (a one-time cost on first use) so the timed section below measures matching work,
    # not module/pattern setup.
    mask_approved_disclaimers(EN1)
    IncomeClaimPolicy().evaluate(_context(EN1, is_generated_answer=True))
    started = time.perf_counter()
    mask_approved_disclaimers(_N1_LOWER_REPEAT_200KB)
    assert time.perf_counter() - started < 2.0
    started = time.perf_counter()
    IncomeClaimPolicy().evaluate(_context(_N1_LOWER_REPEAT_200KB, is_generated_answer=True))
    assert time.perf_counter() - started < 2.0


# ---------------------------------------------------------------------------
# N3 (F3 boundary tightening). Left: a previous non-blank line must actually END its own sentence ([.!?:],
# optionally through closing marks) -- a bare ")" or "*" no longer counts. Right (no-period case): only a blank
# line or the end of the text closes the sentence -- a next line that merely LOOKS structural ("**...**", "- ...",
# "N) ...") no longer does, since it is still the same sentence, just formatted.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(
            f"Nobody believes (as everyone knows)\n{EN1} Everyone here is thriving.", id="left-prev-line-ends-paren"
        ),
        pytest.param(
            f"{EN1[:-1]}\n**for people who don't work.** Everyone who works thrives.", id="right-next-line-bold"
        ),
        pytest.param(
            f"{EN1[:-1]}\n- for people who don't work; everyone who works is thriving.", id="right-next-line-dash"
        ),
    ],
)
def test_n3_tightened_boundary_reproducers_do_not_match(answer: str) -> None:
    assert find_spans(answer) == []
    assert not _allowed_as_answer(answer)


# ---------------------------------------------------------------------------
# R10E regression fixtures (r10-05, r10-06, r10-07)
# ---------------------------------------------------------------------------


def _load_r10e_fixtures() -> dict[str, str]:
    with FIXTURES.open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.mark.parametrize("case_id", ["r10-05", "r10-06", "r10-07"])
def test_r10e_income_disclaimer_answers_are_allowed(case_id: str) -> None:
    texts = _load_r10e_fixtures()
    text = texts[case_id]
    assert "�" not in text
    assert _allowed_as_answer(text)


# ---------------------------------------------------------------------------
# Review round 4: N7 (phantom sentence end at the neighbour cap) and N8 (fragment budget exhausted)
# ---------------------------------------------------------------------------


def test_n7_period_just_before_the_neighbour_cap_is_not_a_sentence_end() -> None:
    run_on = "a" * 3998 + ". "
    text = EN1 + " " + run_on * 2 + "But everyone on my team makes money."
    assert find_spans(text) != []
    assert guarded_spans(text) == []
    assert not _allowed_as_answer(text)


def test_n8_many_word_free_lines_withhold_instead_of_checking_nothing() -> None:
    text = EN1 + "\n|---|---|" * 7 + "\nEveryone makes money."
    assert find_spans(text) != []
    assert guarded_spans(text) == []
    assert not _allowed_as_answer(text)
