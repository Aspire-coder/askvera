import copy

import pytest

from app.retrieval.governing_rules import asks_activity_qualification, prioritize_activity_rule


RULE = {"access_scope": "country", "document_type": "policy", "section_title": "Activity Qualification.",
        "content": "To be considered Active for the Month, an FBO must have 4 Active Case Credits.", "score": 0.4}
BENEFIT = {**RULE, "section_title": "Earned Incentive Program", "score": 0.95}


@pytest.mark.parametrize("question", [
    "Does keeping my sales level mean I'm automatically active every month?",
    "I already earned my sales rank. Do I still need to qualify as Active again this month?",
    "What counts as Active status?", "How do I become Active?", "Explain activity qualification.",
])
def test_governing_condition_precedes_benefit_without_changing_scores(question):
    rows = copy.deepcopy([BENEFIT, RULE])
    original = copy.deepcopy(rows)
    assert prioritize_activity_rule(question, rows, "en") == [RULE, BENEFIT]
    assert rows == original


@pytest.mark.parametrize("question", [
    "Do I lose my rank if I am not active?", "What bonus do I get for being Active?",
    "Explain the Earned Incentive payments.", "Is termination automatic if I am not active?",
    "How do I stay Active and retain my rank?", "What does it cost to join?",
    "What is Active status and what does it cost to join?",
    "How do I become Active? What is the joining fee?",
])
def test_other_and_compound_targets_preserve_order(question):
    assert prioritize_activity_rule(question, [BENEFIT, RULE], "en") == [BENEFIT, RULE]


def test_unsupported_language_does_not_silently_use_english_classifier():
    assert not asks_activity_qualification("What is Active status?", "de")


def test_global_record_never_gets_local_policy_priority():
    global_row = {**RULE, "access_scope": "global"}
    assert prioritize_activity_rule("What is Active status?", [BENEFIT, global_row], "en") == [BENEFIT, global_row]


def test_missing_rule_never_creates_evidence():
    assert prioritize_activity_rule("What is Active status?", [BENEFIT], "en") == [BENEFIT]
