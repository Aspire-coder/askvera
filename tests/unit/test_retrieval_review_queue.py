from scripts.build_retrieval_review_queue import build_queue


def test_review_queue_excludes_reviewed_duplicates_and_round_robins_locales() -> None:
    rows = [
        {"case_id": "reviewed", "question_fingerprint": "a", "country": "US", "language": "en", "question": "Reviewed", "evaluation_group": "knowledge_answer"},
        {"case_id": "us-1", "question_fingerprint": "b", "country": "US", "language": "en", "question": "What is PC?", "evaluation_group": "knowledge_answer"},
        {"case_id": "us-duplicate", "question_fingerprint": "b", "country": "US", "language": "en", "question": "What is PC?", "evaluation_group": "knowledge_answer"},
        {"case_id": "de-1", "question_fingerprint": "c", "country": "DE", "language": "de", "question": "Wie setzen sich 4 CC zusammen?", "evaluation_group": "knowledge_answer"},
        {"case_id": "hello", "question_fingerprint": "d", "country": "US", "language": "en", "question": "Hello", "evaluation_group": "conversation"},
        {"case_id": "unsafe", "question_fingerprint": "e", "country": "US", "language": "en", "question": "Unsafe", "evaluation_group": "safety"},
    ]

    queue = build_queue(rows, {"reviewed"}, target=2)

    assert {row["case_id"] for row in queue} == {"us-1", "de-1"}
    assert all(row["label_status"] == "needs_review" for row in queue)
    assert all(row["reviewer"] == "" for row in queue)
