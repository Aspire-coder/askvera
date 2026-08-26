from __future__ import annotations

import copy

import pytest

from scripts.apply_fixture_label_corrections import apply_corrections


def test_apply_corrections_changes_only_allowed_label_fields() -> None:
    fixture = {
        "cases": [
            {
                "id": "CASE-1",
                "question": "unchanged",
                "relevant_sections": ["old"],
                "governing_section": "old",
                "label_verified": False,
            }
        ]
    }
    original = copy.deepcopy(fixture)
    corrections = {
        "version": "3.0",
        "corrections": {
            "CASE-1": {
                "relevant_sections": ["new"],
                "relevant_section_ids": ["new-part-1"],
                "governing_section": "new",
                "notes": "reviewed",
                "required_source_files": ["Policy.pdf"],
                "target_country": "CA",
            }
        },
    }

    result = apply_corrections(fixture, corrections)

    assert result["cases"][0]["question"] == original["cases"][0]["question"]
    assert result["cases"][0]["relevant_sections"] == ["new"]
    assert result["cases"][0]["relevant_section_ids"] == ["new-part-1"]
    assert result["cases"][0]["governing_section"] == "new"
    assert result["cases"][0]["required_source_files"] == ["Policy.pdf"]
    assert result["cases"][0]["target_country"] == "CA"
    assert result["cases"][0]["label_verified"] is True
    assert result["label_corrections_applied"] == ["CASE-1"]


def test_apply_corrections_rejects_non_label_changes() -> None:
    fixture = {"cases": [{"id": "CASE-1", "question": "original"}]}
    corrections = {
        "corrections": {"CASE-1": {"question": "silently changed"}}
    }

    with pytest.raises(ValueError, match="Unsupported correction fields"):
        apply_corrections(fixture, corrections)


def test_apply_corrections_rejects_unknown_case() -> None:
    fixture = {"cases": [{"id": "CASE-1"}]}
    corrections = {"corrections": {"CASE-2": {"notes": "missing"}}}

    with pytest.raises(ValueError, match="Unknown correction case IDs"):
        apply_corrections(fixture, corrections)
