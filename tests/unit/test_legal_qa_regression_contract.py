"""Permanent contract checks derived from Legal's reviewed chatbot examples."""

import json
from pathlib import Path

from app.response.quality import (
    contains_internal_retrieval_language,
    contains_unresolved_placeholder,
    has_incomplete_ending,
)


FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "legal_qa_regression_cases.json"


def _cases() -> list[dict[str, object]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_legal_regression_catalog_is_complete_and_actionable() -> None:
    cases = _cases()
    assert len(cases) == 17
    assert len({case["id"] for case in cases}) == len(cases)
    assert all(case["question"] for case in cases)
    assert all(case["expectedRoute"] in {"knowledge", "medical_claim", "income_claim"} for case in cases)
    assert all(case["expectedOutcome"] for case in cases)
    assert all(case["sourceRequirement"] for case in cases)


def test_every_recorded_bad_answer_fragment_is_blocked_or_explicitly_forbidden() -> None:
    forbidden = {fragment for case in _cases() for fragment in case["forbidden"]}
    assert "[URL]" in forbidden
    assert "retrieved chunks" in forbidden
    assert "retrieved directory records" in forbidden
    assert "income projections" in forbidden

    assert contains_unresolved_placeholder("Visit [URL] for the current price.")
    assert contains_internal_retrieval_language("The retrieved chunks do not include that rank.")
    assert contains_internal_retrieval_language("The retrieved directory records do not include that date.")
    assert has_incomplete_ending("This applies in every U.S. state, including.", "en")
    assert has_incomplete_ending("New enrollment is not available in the.", "en")
