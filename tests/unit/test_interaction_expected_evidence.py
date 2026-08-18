import csv

import pytest

from scripts.evaluate_interaction_history import (
    EXPECTED_EVIDENCE_FIELDS,
    _apply_expected_evidence_labels,
    _load_expected_evidence_labels,
    _result_summary,
)


def _write_labels(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPECTED_EVIDENCE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def test_approved_expected_evidence_produces_recall_and_mrr(tmp_path) -> None:
    path = tmp_path / "labels.csv"
    _write_labels(
        path,
        [
            {
                "case_id": "case-1",
                "case_index": 1,
                "country": "US",
                "language": "en",
                "question": "Question",
                "expected_source_uris": "",
                "expected_document_names": "",
                "expected_document_ids": "document-2",
                "expected_section_ids": "4.7-b",
                "label_status": "approved",
                "review_notes": "Reviewed",
            }
        ],
    )
    labels = _load_expected_evidence_labels(path)
    rows = _apply_expected_evidence_labels(
        [
            {
                "case_id": "case-1",
                "current_retrieval": {
                    "status": "RESULT",
                    "conversation_intent": "knowledge",
                    "documents": [
                        {"rank": 1, "id": "wrong", "section": "2"},
                        {"rank": 2, "id": "document-2", "section": "4.7.b"},
                    ],
                },
            }
        ],
        labels,
    )

    relevance = _result_summary(rows)["current_retrieval"]["reviewed_relevance"]

    assert relevance["approved_labeled_cases"] == 1
    assert relevance["recall_at_1"] == 0.0
    assert relevance["recall_at_3"] == 1.0
    assert relevance["mean_reciprocal_rank"] == 0.5
    assert relevance["expected_evidence_not_found"] == 0


def test_unapproved_labels_are_not_used_as_ground_truth(tmp_path) -> None:
    path = tmp_path / "labels.csv"
    _write_labels(
        path,
        [
            {
                "case_id": "case-1",
                "case_index": 1,
                "country": "US",
                "language": "en",
                "question": "Question",
                "expected_source_uris": "",
                "expected_document_names": "",
                "expected_document_ids": "document-1",
                "expected_section_ids": "",
                "label_status": "needs_review",
                "review_notes": "",
            }
        ],
    )

    assert _load_expected_evidence_labels(path) == {}


def test_approved_label_requires_at_least_one_expected_id(tmp_path) -> None:
    path = tmp_path / "labels.csv"
    _write_labels(
        path,
        [
            {
                "case_id": "case-1",
                "case_index": 1,
                "country": "US",
                "language": "en",
                "question": "Question",
                "expected_source_uris": "",
                "expected_document_names": "",
                "expected_document_ids": "",
                "expected_section_ids": "",
                "label_status": "approved",
                "review_notes": "",
            }
        ],
    )

    with pytest.raises(ValueError, match="no source, document, or section IDs"):
        _load_expected_evidence_labels(path)


def test_source_filename_is_stable_across_different_chunk_ids(tmp_path) -> None:
    path = tmp_path / "labels.csv"
    _write_labels(
        path,
        [
            {
                "case_id": "case-1",
                "case_index": 1,
                "country": "US",
                "language": "en",
                "question": "Question",
                "expected_source_uris": "",
                "expected_document_names": "US-Company-Policy.pdf",
                "expected_document_ids": "",
                "expected_section_ids": "",
                "label_status": "approved",
                "review_notes": "Reviewed source file",
            }
        ],
    )
    labels = _load_expected_evidence_labels(path)
    rows = _apply_expected_evidence_labels(
        [
            {
                "case_id": "case-1",
                "vnext_retrieval": {
                    "status": "RESULT",
                    "conversation_intent": "knowledge",
                    "documents": [
                        {
                            "rank": 1,
                            "id": "new-chunk-id",
                            "section": "5.01-part-7",
                            "source": "s3://bucket/approved/US/policies/US-Company-Policy.pdf",
                        }
                    ],
                },
            }
        ],
        labels,
    )

    relevance = _result_summary(rows)["vnext_retrieval"]["reviewed_relevance"]

    assert relevance["recall_at_1"] == 1.0
    assert relevance["mean_reciprocal_rank"] == 1.0


def test_section_relevance_ignores_chunk_suffixes_and_document_only_labels(tmp_path) -> None:
    path = tmp_path / "labels.csv"
    _write_labels(
        path,
        [
            {
                "case_id": "section-case",
                "case_index": 1,
                "country": "US",
                "language": "en",
                "question": "Question",
                "expected_source_uris": "",
                "expected_document_names": "US-Company-Policy.pdf",
                "expected_document_ids": "",
                "expected_section_ids": "5.01",
                "label_status": "approved",
                "review_notes": "Reviewed section",
            },
            {
                "case_id": "document-only-case",
                "case_index": 2,
                "country": "US",
                "language": "en",
                "question": "Directory question",
                "expected_source_uris": "",
                "expected_document_names": "Directory.pdf",
                "expected_document_ids": "",
                "expected_section_ids": "",
                "label_status": "approved",
                "review_notes": "Document-level label",
            },
        ],
    )
    labels = _load_expected_evidence_labels(path)
    rows = _apply_expected_evidence_labels(
        [
            {
                "case_id": "section-case",
                "vnext_retrieval": {
                    "status": "RESULT",
                    "conversation_intent": "knowledge",
                    "documents": [
                        {
                            "rank": 2,
                            "id": "new-chunk-id",
                            "section": "5.01-part-7-definition-2",
                            "source": "s3://bucket/US-Company-Policy.pdf",
                        }
                    ],
                },
            },
            {
                "case_id": "document-only-case",
                "vnext_retrieval": {
                    "status": "RESULT",
                    "conversation_intent": "knowledge",
                    "documents": [
                        {
                            "rank": 1,
                            "id": "directory-chunk",
                            "section": "country-entry",
                            "source": "s3://bucket/Directory.pdf",
                        }
                    ],
                },
            },
        ],
        labels,
    )

    summary = _result_summary(rows)["vnext_retrieval"]

    assert summary["reviewed_document_relevance"]["approved_labeled_cases"] == 2
    assert summary["reviewed_section_relevance"]["approved_labeled_cases"] == 1
    assert summary["reviewed_section_relevance"]["recall_at_3"] == 1.0
    assert summary["reviewed_section_relevance"]["mean_reciprocal_rank"] == 0.5
