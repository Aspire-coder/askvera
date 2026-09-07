import pytest

from scripts.run_selector_fixed_comparison import assess, current_prompt, parse_output


CASE = {"expected": True, "governing_sections": ["4.03"],
        "blocks": ["Candidate 1\nSection: 4.03\nText:\nMust qualify each month."]}


def decision():
    return {"answer_supported": True, "selected_ranks": [1], "missing_facts": [],
            "support": [{"rank": 1, "quote": "Must qualify each month."}]}


def test_reads_current_prompt_without_running_application():
    prompt = current_prompt()
    assert prompt.startswith("You select evidence for ASK Vera.")
    assert "directly_answers_top_rank" in prompt
    assert "Before returning JSON, check consistency" not in prompt


def test_valid_quoted_rule_is_accepted():
    assert assess(decision(), CASE, "candidate")[0]


@pytest.mark.parametrize("change", [
    {"selected_ranks": [True]}, {"selected_ranks": [2]}, {"selected_ranks": [1, 1]},
    {"answer_supported": "true"}, {"missing_facts": ["activity rule"]},
    {"support": [{"rank": 1, "quote": "Guaranteed monthly income."}]},
    {"support": [{"rank": 1, "quote": "4.03"}]}, {"support": []},
])
def test_invalid_candidate_cannot_pass(change):
    payload = decision()
    payload.update(change)
    assert not assess(payload, CASE, "candidate")[0]


def test_negative_control_rejects_supported_decision():
    assert not assess(decision(), {**CASE, "expected": False}, "candidate")[0]


def test_fenced_json_parses_without_using_prose():
    assert parse_output('```json\n{"answer_supported":false}\n```') == {"answer_supported": False}
    with pytest.raises(ValueError):
        parse_output("The answer is supported")


@pytest.mark.parametrize("verdict,expected", [
    ("ANSWER_NO", True), ("ANSWER_YES", False), ("INSUFFICIENT_EVIDENCE", False), ("unknown", False),
])
def test_polarity_is_a_validated_enum_not_free_text(verdict, expected):
    payload = decision()
    del payload["answer_supported"]
    payload.update(decision=verdict, draft_answer="No. Monthly qualification is required.")
    assert assess(payload, {**CASE, "polarity": "ANSWER_NO"}, "candidate")[0] is expected


def test_mixed_polarity_and_boolean_schemas_rejected():
    payload = {**decision(), "decision": "ANSWER_NO", "draft_answer": "No."}
    assert not assess(payload, {**CASE, "polarity": "ANSWER_NO"}, "candidate")[0]
