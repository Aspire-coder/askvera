"""Regression coverage for deterministic retrieval classifications."""

from app.retrieval.classification import classify_question, classify_section


def test_question_classifies_precise_entity_and_qualification_intent() -> None:
    result = classify_question("What do I need to become a Recognized Manager?")

    assert result.entities == ("recognized_manager",)
    assert result.question_type == "qualification"


def test_question_classifies_multilingual_contact_intent() -> None:
    result = classify_question("Qual e il telefono dell'ufficio?")

    assert "contact_details" in result.entities
    assert result.question_type == "contact"


def test_governing_rule_beats_definition_shape_at_classification_time() -> None:
    governing = classify_section(
        title="Joining requirements",
        content="No minimum capital investment is required. An applicant must register.",
    )
    definition = classify_section(
        title="FBO Support Fee",
        content="FBO Support Fee: a fee deducted from earned bonuses.",
        chunk_type="definition",
    )

    assert governing.authority == "governing"
    assert definition.authority == "definition"
    assert "joining" in governing.entities
    assert "fees" in definition.entities


def test_directory_records_are_tagged_as_directory_authority() -> None:
    result = classify_section(
        title="United Kingdom",
        content="Telephone Office: +44 1234 567890",
        document_type="office_directory",
    )

    assert result.authority == "directory"
    assert result.question_types[0] == "contact"


def test_unknown_content_remains_safe_and_backward_compatible() -> None:
    question = classify_question("Please explain this")
    section = classify_section(title="Additional information", content="Approved information.")

    assert question.entities == ("general",)
    assert question.question_type == "general"
    assert section.entities == ("general",)
    assert section.authority == "supporting"
