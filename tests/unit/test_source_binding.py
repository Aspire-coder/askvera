from dataclasses import replace

import pytest

from app.retrieval.source_binding import EvidenceSource, validate_support


def source():
    return EvidenceSource("canada-policy", "generation-1", "4.03-b", "CA", "Must have 4 Active\nCase Credits.")


def test_binding_survives_reordering_and_whitespace_wrapped_quote():
    rule = source()
    other = replace(rule, section_id="other", content="Unrelated incentive.")
    support = [{"source_id": rule.binding_id, "quote": "4 Active Case Credits"}]
    assert validate_support(support, [rule, other]) == validate_support(support, [other, rule])


@pytest.mark.parametrize("change", [
    {"generation_id": "generation-2"}, {"document_id": "other-policy"}, {"country": "BE"},
    {"section_id": "4.03-c"}, {"content": "Must have 3 Active Case Credits."},
])
def test_stale_or_foreign_binding_rejected(change):
    original = source()
    support = [{"source_id": original.binding_id, "quote": "4 Active Case Credits"}]
    with pytest.raises(ValueError):
        validate_support(support, [replace(original, **change)])


def test_correct_quote_with_wrong_source_is_not_automatically_relocated():
    rule = source()
    wrong = replace(rule, section_id="sales-level", content="Sales Level is a rank.")
    with pytest.raises(ValueError, match="does not belong"):
        validate_support([{"source_id": wrong.binding_id, "quote": "4 Active Case Credits"}], [rule, wrong])


@pytest.mark.parametrize("quote", ["", " ", None, "3 Active Case Credits", "4 Active ... Credits"])
def test_invalid_or_changed_quote_rejected(quote):
    rule = source()
    with pytest.raises(ValueError):
        validate_support([{"source_id": rule.binding_id, "quote": quote}], [rule])


def test_duplicate_candidates_rejected():
    rule = source()
    with pytest.raises(ValueError):
        validate_support([{"source_id": rule.binding_id, "quote": "4 Active"}], [rule, rule])


def test_missing_provenance_rejected():
    with pytest.raises(ValueError):
        replace(source(), generation_id="")
