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
        (
            "What is the min imum oder size?",
            "minimum order size",
            "what is the minimum order size",
        ),
        (
            "Quel est le montant min imum de com mande?",
            "montant minimum de commande",
            "quel est le montant minimum de commande",
        ),
        (
            "Was ist die Lieferkotsen?",
            "Lieferkosten",
            "was ist die lieferkosten",
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
        ("How can I become a member?", "membership requirements"),
        ("What are the requirements?", "That is the requirements section"),
        ("What is the weather today?", "recognized manager qualification"),
        ("What is a recognized manager?", "recognized manager"),
    ],
)
def test_rejects_semantic_numeric_and_acronym_rewrites(original: str, candidate: str) -> None:
    assert safe_typo_ranking_queries(original, [candidate]) == []


def test_split_repair_does_not_merge_negation_into_a_different_word() -> None:
    assert safe_typo_ranking_queries(
        "I am not able to order",
        ["notable order"],
    ) == []


def test_split_repair_does_not_merge_or_change_numeric_boundaries() -> None:
    assert safe_typo_ranking_queries("What is the order 50?", ["order500"]) == []


def test_split_repair_does_not_merge_uppercase_acronym_boundaries() -> None:
    assert safe_typo_ranking_queries("What is service FPC?", ["servicefpc"]) == []


@pytest.mark.parametrize(
    ("original", "candidate"),
    [
        ("What are the shipping costs?", "shopping costs"),
        ("What are the shopping costs?", "shipping costs"),
    ],
)
def test_typo_repair_does_not_cross_shipping_shopping_semantic_collision(
    original: str, candidate: str
) -> None:
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


@pytest.mark.parametrize(
    ("original", "candidate"),
    [
        (
            "Can I have a stall at a weekend market?",
            "what does the policy say a member shall do at a weekend market",
        ),
        (
            "Is this the whole contract or are there other documents?",
            "whether his contract is the whole agreement or there are other documents",
        ),
    ],
)
def test_correctly_spelled_word_is_not_swapped_for_a_policy_lookalike(
    original: str, candidate: str
) -> None:
    """A near neighbour in the planner's wording is not evidence that the
    user's own, correctly spelled word was a typo. ``stall``/``shall`` and
    ``his``/``this`` are both one edit apart but neither edit has a shape
    (keyboard-adjacent substitution/transposition on a long-enough word, or
    dropping a letter that recurs elsewhere in the word) that looks like a
    genuine typing slip, so the original wording must survive untouched.
    """
    assert safe_typo_ranking_queries(original, [candidate]) == []


@pytest.mark.parametrize(
    ("original", "candidate"),
    [
        ("Please fill out the form before the trial ends.", "please fill out the from before the trail ends"),
        ("I would quite like to leave now.", "i would quiet like to leave now"),
    ],
)
def test_short_word_transposition_is_not_treated_as_a_typo(
    original: str, candidate: str
) -> None:
    """General-purpose regression: pick correct-word/lookalike pairs that are
    not in any exception list (form/from, trial/trail, quite/quiet). Each
    pair differs only by an adjacent-letter transposition, exactly like the
    genuine typo cases this module must keep repairing (e.g. Mexcio/Mexico),
    so the fix cannot rely on those pairs being individually blocked - it
    must instead recognise that transposition between two short, independently
    valid words is not, by itself, evidence of a misspelling.
    """
    assert safe_typo_ranking_queries(original, [candidate]) == []


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


def test_approved_evidence_title_can_repair_when_planner_does_not() -> None:
    provider = OpenSearchSectionProvider()
    original = "How can I become a recognizd manager?"
    rows = provider._merge_hits(
        [_hit("recognized", "Recognized Manager")],
        [],
        original,
        ranking_queries=[],
    )

    row, final_score = rows[0]
    assert row["ranking_query_used"] == "how can i become a recognized manager"
    assert row["typo_ranking_applied"] is True
    assert final_score > row["original_question_score"]


def test_locale_filtered_candidate_vocabulary_repairs_non_top_typo() -> None:
    provider = OpenSearchSectionProvider()
    original = "What are the requirments to become a recognised manager?"
    requirement_hit = _hit("requirements", "Qualification Requirements", 3.0)
    rows = provider._merge_hits(
        [
            _hit("recognized", "Recognized Manager", 6.0),
            requirement_hit,
        ],
        [],
        original,
        ranking_queries=[],
    )

    recognized_row = next(row for row, _score in rows if row["id"] == "recognized")
    assert "requirements" in recognized_row["ranking_query_used"]
    assert "recognized manager" in recognized_row["ranking_query_used"]
    assert recognized_row["typo_ranking_applied"] is True


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
        "monthly-bonus-payment-release-gate",
        "supervisor-case-credits-release-gate",
        "us-payment-methods-release-gate",
        "thailand-minimum-order-release-gate",
        "unopened-product-return-window-release-gate",
        "uruguay-phone-release-gate",
    }
