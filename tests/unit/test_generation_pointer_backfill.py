from __future__ import annotations

import pytest

from scripts import backfill_active_generation_pointers as backfill


def _record(*, country="CA", language="en", ingestion_id="run-1"):
    return {
        "_source": {
            "country": country,
            "language": language,
            "source_file": "Company Policy.pdf",
            "document_type": "policy",
            "access_scope": "country",
            "ingestion_id": ingestion_id,
        }
    }


def test_generation_candidates_group_sections_into_one_document() -> None:
    candidates = backfill.generation_candidates([_record(), _record()])

    assert len(candidates) == 1
    assert candidates[0].section_count == 2
    assert candidates[0].logical_document_id == (
        "country:CA:en:policy:company-policy"
    )


def test_generation_candidates_reject_multiple_active_generations() -> None:
    with pytest.raises(ValueError, match="Multiple active generations"):
        backfill.generation_candidates(
            [_record(ingestion_id="run-1"), _record(ingestion_id="run-2")]
        )


def test_generation_candidates_accept_pointer_selected_retained_generation() -> None:
    logical_id = "country:CA:en:policy:company-policy"
    candidates = backfill.generation_candidates(
        [_record(ingestion_id="retired-run"), _record(ingestion_id="live-run")],
        pointers={logical_id: "live-run"},
    )

    assert len(candidates) == 1
    assert candidates[0].ingestion_id == "live-run"


def test_pointer_coverage_reports_missing_mismatch_and_orphan() -> None:
    candidates = backfill.generation_candidates([_record()])

    failures = backfill.pointer_coverage_failures(
        candidates,
        {
            candidates[0].logical_document_id: "wrong-run",
            "country:US:en:policy:other": "orphan-run",
        },
    )

    assert any(item.startswith("pointer mismatch:") for item in failures)
    assert any(item.startswith("orphaned pointer:") for item in failures)
