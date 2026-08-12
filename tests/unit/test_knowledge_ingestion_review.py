from services.knowledge_ingestion import summarize_ingestion_chunks


def test_chunk_review_reports_quality_signals_and_preview_limits():
    chunks = [
        {"content": "Recognized Manager requirements", "page": "12"},
        {"content": "Recognized Manager requirements", "page": "13"},
        {"content": "", "page": "14"},
        {"content": "x" * 11, "page": "15"},
    ]

    summary = summarize_ingestion_chunks(chunks, total_count=6, max_chunk_chars=10)

    assert summary["chunk_count"] == 6
    assert summary["preview_count"] == 4
    assert summary["page_count"] == 4
    assert summary["empty_chunks"] == 1
    assert summary["oversized_chunks"] == 1
    assert summary["duplicate_chunks"] == 1
    assert any("Preview shows 4 of 6" in warning for warning in summary["warnings"])
    assert any("duplicate" in warning for warning in summary["warnings"])


def test_chunk_review_is_clean_for_complete_unique_chunks():
    summary = summarize_ingestion_chunks(
        [
            {"content": "First approved section", "page": "1"},
            {"content": "Second approved section", "page": "2"},
        ],
        total_count=2,
    )

    assert summary["warnings"] == []
    assert summary["empty_chunks"] == 0
    assert summary["duplicate_chunks"] == 0


def test_chunk_review_does_not_infer_unseen_chunks_are_empty():
    summary = summarize_ingestion_chunks(
        [{"content": "Visible approved section", "page": "1"}],
        total_count=3,
    )

    assert summary["preview_count"] == 1
    assert summary["chunk_count"] == 3
    assert summary["empty_chunks"] == 0
