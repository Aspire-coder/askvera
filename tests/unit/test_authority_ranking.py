"""Tests for isolated authority-aware candidate scoring."""

from app.retrieval.authority_ranking import authority_alignment
from app.retrieval.section_index import _source_score


def _row(title: str, content: str, *, chunk_type: str = "section") -> dict[str, object]:
    return {
        "rank": 0.5,
        "section_title": title,
        "content": content,
        "search_text": f"{title}\n{content}",
        "chunk_type": chunk_type,
        "document_type": "policy",
    }


def test_joining_cost_prefers_governing_rule_over_fee_definition() -> None:
    governing = _row(
        "Joining requirements",
        "No minimum capital investment is required to join as a Forever Business Owner.",
    )
    definition = _row(
        "FBO Support Fee",
        "FBO Support Fee: a fee deducted from earned bonuses.",
        chunk_type="definition",
    )
    question = "Does it cost money to join as an FBO?"

    assert _source_score(
        governing, question, authority_ranking_enabled=True
    ) > _source_score(definition, question, authority_ranking_enabled=True)


def test_definition_question_keeps_definition_authority() -> None:
    definition = _row(
        "Recognized Manager",
        "Recognized Manager: a Manager who meets the approved definition.",
        chunk_type="definition",
    )
    requirement = _row(
        "Manager requirements",
        "A Manager must generate the required Case Credits.",
    )

    assert authority_alignment(definition, "What is a Recognized Manager?").score > authority_alignment(
        requirement, "What is a Recognized Manager?"
    ).score


def test_authority_cannot_rescue_unrelated_governing_section() -> None:
    unrelated = _row(
        "Return requirements",
        "Products must be returned within the approved period.",
    )

    alignment = authority_alignment(unrelated, "How do I qualify as a Manager?")

    assert alignment.score <= 0.0


def test_current_scoring_is_unchanged_when_authority_ranking_is_off() -> None:
    row = _row(
        "Joining requirements",
        "No minimum capital investment is required to join.",
    )
    question = "Does it cost money to join?"

    assert _source_score(row.copy(), question, authority_ranking_enabled=False) == _source_score(
        row.copy(), question, authority_ranking_enabled=False
    )
