"""Regression coverage for conservative typo-tolerant retrieval ranking."""

from pathlib import Path

import pytest

from app.retrieval.opensearch_sections import OpenSearchSectionProvider
from app.retrieval.typo_safety import safe_typo_ranking_queries
from scripts.run_retrieval_canary import load_fixture


def _hit(identifier: str, title: str, score: float = 5.0) -> dict[str, object]:
    return {
        "_id": identifier,
        "_score": score,
        "_source": {
            "id": identifier,
            "section_id": "5.01",
            "section_title": title,
            "content": f"{title} requirements and recognition policy.",
            "search_text": f"{title} requirements and recognition policy.",
            "country": "US",
            "language": "en",
            "status": "active",
        },
    }


@pytest.mark.parametrize(
    ("original", "candidate", "expected"),
    [
        (
            "How can I become a recognizd manager?",
            "recognized manager requirements",
            "how can i become a recognized manager",
        ),
        (
            "What are the requirments to become a recognised manager?",
            "requirements to become recognised manager",
            "what are the requirements to become a recognised manager",
        ),
        (
            "How can I become a member in Mexcio through internationl sponsring?",
            "international sponsoring Mexico membership",
            "how can i become a member in mexico through international sponsoring",
        ),
        (
            "How can I become a recognizedmanager?",
            "recognized manager",
            "how can i become a recognized manager",
        ),
        (
            "Quelles sont les conditons pour devenir Manager?",
            "conditions pour devenir Manager",
            "quelles sont les conditions pour devenir manager",
        ),
    ],
)
def test_accepts_only_bounded_spelling_repairs(
    original: str,
    candidate: str,
    expected: str,
) -> None:
    assert safe_typo_ranking_queries(original, [candidate]) == [expected]


@pytest.mark.parametrize(
    ("original", "candidate"),
    [
        ("What is the minimum order of 50 CC?", "minimum order 500 CC"),
        ("What are FPC requirements?", "preferred customer requirements"),
        ("How can I become a manager?", "leadership bonus qualification criteria"),
        ("What is the weather today?", "recognized manager qualification"),
        ("What is a recognized manager?", "recognized manager"),
    ],
)
def test_rejects_semantic_numeric_and_acronym_rewrites(original: str, candidate: str) -> None:
    assert safe_typo_ranking_queries(original, [candidate]) == []


def _generated_typo_questions() -> list[tuple[str, str]]:
    canonical = "How can I become a recognized manager?"
    return [
        (canonical.replace("recognized", "recognizd"), canonical),
        (canonical.replace("recognized", "recoginzed"), canonical),
        (canonical.replace("recognized", "recognizzed"), canonical),
        (canonical.replace("recognized manager", "recognizedmanager"), canonical),
    ]


@pytest.mark.parametrize(("original", "candidate"), _generated_typo_questions())
def test_generated_deletion_transposition_duplication_and_joined_variants(
    original: str,
    candidate: str,
) -> None:
    assert safe_typo_ranking_queries(original, [candidate]) == [
        "how can i become a recognized manager"
    ]


def test_typo_ranking_uses_safe_repair_without_changing_original_score() -> None:
    provider = OpenSearchSectionProvider()
    original = "How can I become a recognizd manager?"
    rows = provider._merge_hits(
        [_hit("recognized", "Recognized Manager")],
        [],
        original,
        ranking_queries=safe_typo_ranking_queries(original, ["become recognized manager"]),
    )

    row, final_score = rows[0]
    assert row["ranking_query_used"] == "how can i become a recognized manager"
    assert row["typo_ranking_applied"] is True
    assert final_score > row["original_question_score"]


def test_unsafe_semantic_expansion_cannot_change_ranking() -> None:
    provider = OpenSearchSectionProvider()
    original = "How can I become a manager?"
    safe_queries = safe_typo_ranking_queries(original, ["leadership bonus qualification criteria"])
    rows = provider._merge_hits(
        [_hit("recognized", "Recognized Manager")],
        [],
        original,
        ranking_queries=safe_queries,
    )

    row, final_score = rows[0]
    assert safe_queries == []
    assert row["ranking_query_used"] == original
    assert row["typo_ranking_applied"] is False
    assert final_score == row["original_question_score"]


def test_deployment_canary_fixture_is_versioned_and_complete() -> None:
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "retrieval_canary.json"
    cases, fixture_hash = load_fixture(fixture)

    assert len(cases) >= 6
    assert len(fixture_hash) == 64
    assert {case["id"] for case in cases} >= {
        "recognized-manager-baseline",
        "recognized-manager-missing-letter",
        "belgium-minimum-order-typo",
        "mexico-sponsoring-multiple-typos",
    }
