import copy

import pytest

from scripts.prepare_selector_replay import extract_selector


def capture():
    return {"id": "test", "country": "CA", "question": "Am I active?", "model_calls": [
        {"operation": "Converse", "model": "test-model", "input_text": {
            "system": ["You select evidence for ASK Vera. Do not answer."],
            "messages": [{"role": "user", "text": ["Candidate evidence"]}],
        }, "output_text": '{"directly_answers_top_rank":false}'}]}


def test_freezes_exact_inputs_without_turning_output_into_gold():
    row = capture()
    original = copy.deepcopy(row)
    result = extract_selector(row)
    assert result["input_text"] == row["model_calls"][0]["input_text"]
    assert result["expected_decision"] is None
    assert result["recorded_output"] == row["model_calls"][0]["output_text"]
    assert row == original
    assert result["input_sha256"] == extract_selector(row)["input_sha256"]


def test_hash_changes_when_candidate_changes():
    row = capture()
    before = extract_selector(row)["input_sha256"]
    row["model_calls"][0]["input_text"]["messages"][0]["text"] = ["Other evidence"]
    assert extract_selector(row)["input_sha256"] != before


@pytest.mark.parametrize("failure", ["missing", "duplicate", "messages", "output"])
def test_incomplete_or_ambiguous_capture_is_rejected(failure):
    row = capture()
    if failure == "missing":
        row["model_calls"] = []
    elif failure == "duplicate":
        row["model_calls"] *= 2
    elif failure == "messages":
        row["model_calls"][0]["input_text"]["messages"] = []
    else:
        row["model_calls"][0]["output_text"] = ""
    with pytest.raises(ValueError):
        extract_selector(row)
