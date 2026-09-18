"""Composition contract: prompt-structure only; unverified without a live model.

These tests prove the instructions exist, the approved rules they extend are
still present, and the prompt stayed inside its existing budget. They do NOT
prove that answers improve. Only a live generation run can show that, and none
was made. Tasks: B1 (concrete qualifications), B2/B5 (role-bound figures), B3
(name the unestablished part), E1 (direct first sentence, no filler), and the
F1 unnamed-"they" handoff, which was moved here from a rejected post-editor.
"""

from __future__ import annotations

import pytest

from app.prompts.builder import PromptBuilder
from app.retrieval.models import RetrievalResult
from config import settings


def _system_prompt(language: str = "en") -> str:
    return PromptBuilder().build(
        user_question="How do I qualify as a Manager?",
        conversation="",
        country="US",
        language=language,
        role="new_prospect",
        retrieval_result=RetrievalResult(documents=[], citations=[], confidence=0.0),
        metadata={},
    ).system_prompt


def _normalized() -> str:
    return " ".join(_system_prompt().split())


@pytest.mark.parametrize(
    "rule",
    [
        "Lead with the direct answer",                       # E1
        "no stock openers, generic disclaimers or closing questions",  # E1
        "tier, role, section, product or country",           # B2/B5
        "mandatory qualifications, amounts, periods",        # B1
        "routes concretely, even when simplifying",          # B1
        'Name who to contact, never "they"',                 # F1 handoff
        "naming any the evidence does not establish",        # B3
    ],
)
def test_composition_rule_is_present(rule: str) -> None:
    assert rule in _normalized()


@pytest.mark.parametrize(
    "approved",
    [
        "Keep the complete response in that language",
        "required disclaimer wording",
        "invent missing facts",
        "A refusal of one part is not a refusal of all",
        "Omit unrelated benefits, ranks or upsells",
        "History is continuity, not evidence or permission",
    ],
)
def test_approved_rules_the_contract_extends_are_still_present(approved: str) -> None:
    assert approved in _normalized()


def test_prompt_stays_inside_the_existing_budget() -> None:
    """The contract was fitted to the budget; the budget was not raised to fit it."""
    assert len(_system_prompt()) <= 4392


def test_prompt_version_moved_with_the_prompt() -> None:
    """Both caches key on PROMPT_VERSION; an unchanged version would keep serving
    answers composed under the previous rules."""
    assert settings.PROMPT_VERSION == "2026-09-18-composition-contract-v5"


def test_language_instruction_is_unchanged_for_other_languages() -> None:
    for language in ("fr", "es", "de"):
        assert f"User language: {language}" in _system_prompt(language)
