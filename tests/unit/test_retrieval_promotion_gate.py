from scripts.check_retrieval_promotion import evaluate_gates


def _summary(*, recall_1=0.86, recall_5=0.99, recall_10=0.99, latency=1200.0):
    return {
        "current_retrieval": {
            "reviewed_document_relevance": {"recall_at_1": 0.98},
            "retrieval_coverage": {"retrieval_errors": 0},
        },
        "vnext_retrieval": {
            "reviewed_section_relevance": {
                "recall_at_1": recall_1,
                "recall_at_5": recall_5,
                "recall_at_10": recall_10,
            },
            "reviewed_document_relevance": {"recall_at_1": 0.98},
            "retrieval_coverage": {"retrieval_errors": 0},
            "latency_ms": {"p95": latency},
        },
    }


def test_promotion_gate_passes_only_when_every_threshold_passes() -> None:
    assert evaluate_gates(_summary())["promote"] is True
    assert evaluate_gates(_summary(recall_1=0.8448))["promote"] is False
    assert evaluate_gates(_summary(recall_5=0.97))["promote"] is False
    assert evaluate_gates(_summary(latency=None))["promote"] is False
