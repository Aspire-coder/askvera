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


class _SearchClient:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.calls = []

    def search(self, *, index, body):
        self.calls.append((index, body))
        return next(self.pages)


def test_load_active_records_uses_search_after_without_scroll(monkeypatch) -> None:
    monkeypatch.setattr(backfill.settings, "OPENSEARCH_INDEX", "sections")
    first = [_record(), _record()]
    first[0]["sort"] = ["doc-1"]
    first[1]["sort"] = ["doc-2"]
    second = [_record()]
    second[0]["sort"] = ["doc-3"]
    client = _SearchClient(
        [
            {"hits": {"hits": first}},
            {"hits": {"hits": second}},
        ]
    )

    records = list(backfill.load_active_records(client=client, page_size=2))

    assert records == [*first, *second]
    assert "scroll" not in client.calls[0][1]
    assert client.calls[0][1]["sort"] == [{"_id": "asc"}]
    assert "search_after" not in client.calls[0][1]
    assert client.calls[1][1]["search_after"] == ["doc-2"]


def test_load_active_records_rejects_missing_search_after_token(monkeypatch) -> None:
    monkeypatch.setattr(backfill.settings, "OPENSEARCH_INDEX", "sections")
    client = _SearchClient([{"hits": {"hits": [_record(), _record()]}}])

    with pytest.raises(RuntimeError, match="search_after token"):
        list(backfill.load_active_records(client=client, page_size=2))
