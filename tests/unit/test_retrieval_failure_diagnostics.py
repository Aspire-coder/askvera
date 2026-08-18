from scripts.diagnose_retrieval_failures import diagnose_rows


def test_no_result_without_evidence_label_is_classified_as_route() -> None:
    rows = [
        {
            "case_index": 1,
            "case_id": "route-1",
            "country": "US",
            "language": "en",
            "question": "hi",
            "current_retrieval": {
                "status": "NO_RESULT",
                "conversation_intent": "assistant_meta",
                "documents": [],
            },
        }
    ]

    diagnostics = diagnose_rows(rows, {}, "current_retrieval")

    assert len(diagnostics) == 1
    assert diagnostics[0]["classification"] == "INTENTIONALLY_ROUTED"
    assert diagnostics[0]["root_cause"] == "intentional_route"
    assert diagnostics[0]["threshold_result"] == "not applicable: intentionally routed"


def test_labeled_knowledge_result_keeps_rank_classification() -> None:
    rows = [
        {
            "case_index": 2,
            "case_id": "knowledge-1",
            "country": "US",
            "language": "en",
            "question": "What is PC?",
            "current_retrieval": {
                "status": "RESULT",
                "conversation_intent": "knowledge",
                "documents": [
                    {"rank": 1, "section": "2", "id": "doc-2"},
                ],
                "candidate_evidence": [],
            },
        }
    ]
    labels = {
        "knowledge-1": {
            "expected_section_ids": ["2"],
        }
    }

    diagnostics = diagnose_rows(rows, labels, "current_retrieval")

    assert diagnostics[0]["classification"] == "TOP_1"
    assert diagnostics[0]["final_rank"] == 1
