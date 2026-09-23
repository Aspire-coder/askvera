"""Row 17: the prompt asks for an income disclaimer the income policy can deliver.

A US question about the contract terms for becoming a distributor was refused as
an income claim. The model added the disclaimer "There is no guaranteed income",
and the income policy refuses any answer that pairs "guarantee" with an earnings
word. A code exemption for that disclaimer was withheld after three safety reviews
(handoff 2026-09-12_0220). Instead, the system prompt now tells the model how to
say earnings are not assured without the refused wording. Safety code is
unchanged; whether the live model follows the instruction is checked in the live
journey run.
"""

import pytest

from app.governance import governance_engine
from app.prompts.templates import SYSTEM_PROMPT


def _allowed(answer: str) -> bool:
    return governance_engine.evaluate(
        text=answer, country="US", language="en", correlation_id="cid", is_generated_answer=True
    ).allowed


def _normalized_prompt() -> str:
    return " ".join(SYSTEM_PROMPT.split()).casefold()


def test_system_prompt_gives_the_deliverable_disclaimer_wording():
    prompt = _normalized_prompt()

    assert "income depends on each fbo's own effort and sales" in prompt
    assert 'never "guarantee(d)"' in prompt
    assert 'never "guarantee(d)", even quoted' in prompt


def test_the_prompted_disclaimer_is_delivered_in_a_contract_terms_answer():
    answer = (
        "To become a Forever Business Owner in the US you sign the FBO application and agree to the "
        "Company Policy. Income depends on each FBO's own effort and sales."
    )

    assert _allowed(answer) is True


@pytest.mark.parametrize("answer", [
    "To become an FBO you agree to the Company Policy. There is no guaranteed income.",
    "Income depends on each FBO's own effort and sales, but you will have guaranteed income from bonuses.",
    "Income depends on each FBO's own effort and sales. This is a path to financial freedom.",
])
def test_refused_wording_is_still_refused(answer):
    assert _allowed(answer) is False
