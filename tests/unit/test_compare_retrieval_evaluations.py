from scripts.compare_retrieval_evaluations import compare_rows


def _row(case_id, answer_status, document_ids, *, pipeline):
    return {
        "case_id": case_id,
        "case_index": 1,
        f"{pipeline}_answer": {"status": answer_status},
        f"{pipeline}_retrieval": {
            "documents": [
                {"id": document_id} for document_id in document_ids
            ]
        },
    }


def test_comparison_reports_answer_transition_and_retrieval_overlap() -> None:
    current = {"case-1": _row("case-1", "SAFE_ABSTENTION", ["a", "b"], pipeline="current")}
    vnext = {"case-1": _row("case-1", "APPROVED", ["b", "c"], pipeline="vnext")}

    summary, details = compare_rows(current, vnext)

    assert summary["answer_status_transitions"] == {
        "SAFE_ABSTENTION -> APPROVED": 1
    }
    assert summary["vnext_approved_current_not"] == 1
    assert summary["top_result_match_rate"] == 0.0
    assert summary["mean_result_overlap"] == 1.0
    assert details[0]["comparison"] == "vnext_approved_current_not"
    assert details[0]["result_overlap"] == 1
