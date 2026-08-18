import csv

from scripts.evaluate_interaction_history import _write_answer_outcome_diagnostics


def test_answer_outcome_report_includes_only_exceptional_results(tmp_path) -> None:
    rows = [
        {
            "case_index": 1,
            "case_id": "case-safe",
            "country": "US",
            "language": "en",
            "question": "Question",
            "vnext_retrieval": {
                "status": "RESULT",
                "confidence": 0.8,
                "documents": [
                    {"id": "doc-1", "excerpt": "Evidence one"},
                    {"id": "doc-2", "excerpt": "Evidence two"},
                ],
            },
            "vnext_answer": {
                "status": "SAFE_ABSTENTION",
                "error": "answer_not_approved",
                "raw_response": '{"status":"insufficient_evidence"}',
            },
        },
        {
            "case_index": 2,
            "case_id": "case-approved",
            "vnext_retrieval": {"status": "RESULT", "documents": []},
            "vnext_answer": {"status": "APPROVED", "answer": "Answer"},
        },
    ]

    path = _write_answer_outcome_diagnostics(rows, tmp_path, "pilot")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        output = list(csv.DictReader(handle))

    assert len(output) == 1
    assert output[0]["case_id"] == "case-safe"
    assert output[0]["pipeline"] == "vnext"
    assert output[0]["diagnostic_reason"] == "model_declared_insufficient_evidence"
    assert output[0]["retrieved_source_ids"] == "doc-1 | doc-2"
    assert output[0]["human_outcome_verdict"] == ""


def test_numeric_outcome_report_exposes_unsupported_claims(tmp_path) -> None:
    rows = [
        {
            "case_index": 1,
            "case_id": "case-numeric",
            "vnext_retrieval": {"status": "RESULT", "documents": []},
            "vnext_answer": {
                "status": "NUMERIC_REVIEW_REQUIRED",
                "unsupported_numeric_claims": ["80", "15%"],
            },
        }
    ]

    path = _write_answer_outcome_diagnostics(rows, tmp_path, "pilot")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        output = list(csv.DictReader(handle))

    assert output[0]["unsupported_numeric_claims"] == "80 | 15%"
