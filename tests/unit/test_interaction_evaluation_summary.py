from scripts.evaluate_interaction_history import _result_summary


def _retrieval(status: str, intent: str) -> dict[str, object]:
    return {
        "status": status,
        "conversation_intent": intent,
        "documents": [],
    }


def test_result_summary_does_not_count_intentional_routes_as_retrieval_misses() -> None:
    rows = [
        {
            "current_retrieval": _retrieval("RESULT", "knowledge"),
            "vnext_retrieval": _retrieval("RESULT", "knowledge"),
        },
        {
            "current_retrieval": _retrieval("NO_RESULT", "assistant_meta"),
            "vnext_retrieval": _retrieval("NO_RESULT", "assistant_meta"),
        },
        {
            "current_retrieval": _retrieval("NO_RESULT", "off_topic"),
            "vnext_retrieval": _retrieval("NO_RESULT", "off_topic"),
        },
    ]

    summary = _result_summary(rows)
    coverage = summary["vnext_retrieval"]["retrieval_coverage"]

    assert summary["vnext_retrieval"]["document_result_rate_all_interactions"] == 0.3333
    assert coverage == {
        "retrieval_required_cases": 1,
        "returned_evidence": 1,
        "knowledge_no_evidence": 0,
        "retrieval_errors": 0,
        "retrieval_required_coverage_rate": 1.0,
        "intentionally_routed_cases": 2,
        "routed_by_intent": {"assistant_meta": 1, "off_topic": 1},
    }


def test_result_summary_counts_empty_knowledge_results_as_retrieval_gaps() -> None:
    rows = [
        {
            "current_retrieval": _retrieval("NO_RESULT", "knowledge"),
            "vnext_retrieval": _retrieval("ERROR", "knowledge"),
        }
    ]

    summary = _result_summary(rows)

    assert summary["current_retrieval"]["retrieval_coverage"]["knowledge_no_evidence"] == 1
    assert summary["vnext_retrieval"]["retrieval_coverage"]["retrieval_errors"] == 1
    assert summary["vnext_retrieval"]["retrieval_coverage"]["retrieval_required_coverage_rate"] == 0.0


def test_current_and_vnext_answers_receive_parallel_grounding_metrics() -> None:
    rows = [
        {
            "current_retrieval": _retrieval("RESULT", "knowledge"),
            "current_answer": {"status": "SAFE_ABSTENTION"},
            "vnext_retrieval": _retrieval("RESULT", "knowledge"),
            "vnext_answer": {"status": "APPROVED"},
        }
    ]

    summary = _result_summary(rows)

    assert summary["current_grounded_answer_coverage"]["safe_abstentions"] == 1
    assert summary["current_grounded_answer_coverage"]["approved_rate"] == 0.0
    assert summary["vnext_grounded_answer_coverage"]["approved"] == 1
    assert summary["vnext_grounded_answer_coverage"]["approved_rate"] == 1.0
