"""Regression tests for document-driven section scoring."""

from app.retrieval.section_index import _source_score


def _row(section_id: str, title: str, content: str) -> dict[str, object]:
    return {
        "rank": 0.5,
        "section_id": section_id,
        "section_title": title,
        "content": content,
        "search_text": f"{title}\n{content}",
    }


def test_exact_rank_phrase_beats_adjacent_rank_section() -> None:
    """A literal rank name should prefer its governing section, not a nearby mention."""
    recognized = _row(
        "5.01",
        "Recognized Manager",
        "5.01 Recognized Manager requirements and recognition.",
    )
    nearby = _row(
        "8.04",
        "Gem Manager",
        "A Recognized Manager may later qualify for a Gem Manager award.",
    )

    question = "What is a Recognized Manager?"
    assert _source_score(recognized, question) > _source_score(nearby, question)


def test_distinctive_program_name_beats_generic_policy_text() -> None:
    """A document's own branded program name receives an exact-match preference."""
    program = _row(
        "10.01",
        "Earned Incentive Program / Forever2Drive",
        "Forever2Drive is part of the Earned Incentive Program.",
    )
    generic = _row(
        "9.01",
        "Leadership Bonus",
        "Managers can qualify for leadership bonuses.",
    )

    question = "What is Forever2Drive?"
    assert _source_score(program, question) > _source_score(generic, question)


def test_document_title_match_is_unicode_safe() -> None:
    """Scoring must use the document language rather than an English term list."""
    governing = _row(
        "7.03",
        "Conditions pour devenir Manager",
        "Les conditions pour devenir Manager sont decrites dans cette section.",
    )
    nearby = _row(
        "7.04",
        "Programme de reconnaissance",
        "Un Manager peut recevoir une reconnaissance ulterieure.",
    )

    question = "Quelles sont les conditions pour devenir Manager?"
    assert _source_score(governing, question) > _source_score(nearby, question)
