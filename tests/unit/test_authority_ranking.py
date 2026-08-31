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


def test_named_country_directory_remains_authoritative_for_sponsoring_process() -> None:
    directory = {
        **_row(
            "International-Sponsoring-Directory.pdf - Forever Mexico",
            "International sponsoring information for Forever Mexico.",
        ),
        "document_type": "international_sponsoring_directory",
        "metadata": {"record_country": "Mexico"},
    }
    policy = _row(
        "International sponsoring policy",
        "An FBO can be sponsored into a country outside the home country.",
    )
    question = "How can I join Mexico through international sponsoring?"

    directory_alignment = authority_alignment(directory, question)
    policy_alignment = authority_alignment(policy, question)

    assert directory_alignment.directory_country_match is True
    assert directory_alignment.score >= policy_alignment.score


def test_unopened_product_prefers_unsold_salable_inventory_rule() -> None:
    inventory_buyback = _row(
        "Inventory buyback",
        "The company shall buy back unsold, salable product returned within the approved window.",
    )
    customer_satisfaction = _row(
        "Customer satisfaction",
        "Retail customers may return products under the satisfaction guarantee.",
    )
    question = "Can I return an unopened product, and within what window?"

    assert _source_score(
        inventory_buyback, question, authority_ranking_enabled=True
    ) > _source_score(
        customer_satisfaction, question, authority_ranking_enabled=True
    )
    assert authority_alignment(
        inventory_buyback, question
    ).entity_match_count > authority_alignment(
        customer_satisfaction, question
    ).entity_match_count


def test_runtime_classification_extends_older_stored_entity_tags() -> None:
    older_index_row = {
        **_row(
            "Inventory buyback",
            "The company shall buy back unsold, salable product within the approved window.",
        ),
        "entity_tags": ["returns"],
        "question_type_tags": ["timing"],
        "section_authority": "governing",
    }

    alignment = authority_alignment(
        older_index_row,
        "Can I return an unopened product, and within what window?",
    )

    assert "returns" in alignment.section.entities
    assert "resalable_inventory" in alignment.section.entities
    assert alignment.entity_match is True


def test_current_scoring_is_unchanged_when_authority_ranking_is_off() -> None:
    row = _row(
        "Joining requirements",
        "No minimum capital investment is required to join.",
    )
    question = "Does it cost money to join?"

    assert _source_score(row.copy(), question, authority_ranking_enabled=False) == _source_score(
        row.copy(), question, authority_ranking_enabled=False
    )
