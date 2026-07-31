from __future__ import annotations

import pytest

from scripts import backfill_legacy_generation_metadata as backfill


def _record(
    document_id: str,
    *,
    country: str = "CA",
    language: str = "fr",
    access_scope: str = "",
    ingestion_id: str = "",
    logical_document_id: str = "",
):
    return {
        "_id": document_id,
        "_source": {
            "country": country,
            "language": language,
            "source_file": "Company Policy.pdf",
            "document_type": "policy",
            "access_scope": access_scope,
            "ingestion_id": ingestion_id,
            "logical_document_id": logical_document_id,
        },
    }


def test_repairs_missing_country_scope_and_generation_deterministically() -> None:
    repairs = backfill.legacy_metadata_repairs(
        [_record("one"), _record("two")]
    )

    assert len(repairs) == 2
    assert {repair.access_scope for repair in repairs} == {"country"}
    assert len({repair.ingestion_id for repair in repairs}) == 1
    assert repairs[0].ingestion_id.startswith("legacy-")
    assert repairs[0].logical_document_id == (
        "country:CA:fr:policy:company-policy"
    )
    assert repairs[0].update == {
        "access_scope": "country",
        "ingestion_id": repairs[0].ingestion_id,
        "logical_document_id": repairs[0].logical_document_id,
    }


def test_repairs_reuse_single_existing_generation_without_overwriting_it() -> None:
    repairs = backfill.legacy_metadata_repairs(
        [
            _record("one", ingestion_id="existing-run"),
            _record("two", ingestion_id="existing-run"),
        ]
    )

    assert {repair.ingestion_id for repair in repairs} == {"existing-run"}
    assert all("ingestion_id" not in repair.update for repair in repairs)


def test_repairs_infer_global_scope_from_global_country() -> None:
    repairs = backfill.legacy_metadata_repairs(
        [_record("one", country="GLOBAL", language="en")]
    )

    assert repairs[0].access_scope == "global"
    assert repairs[0].logical_document_id.startswith(
        "global:GLOBAL:en:policy:"
    )


def test_repairs_reject_multiple_active_generations() -> None:
    with pytest.raises(ValueError, match="Multiple active generations"):
        backfill.legacy_metadata_repairs(
            [
                _record("one", ingestion_id="run-one"),
                _record("two", ingestion_id="run-two"),
            ]
        )


def test_repairs_reject_conflicting_logical_document_id() -> None:
    with pytest.raises(ValueError, match="Conflicting logical document ID"):
        backfill.legacy_metadata_repairs(
            [_record("one", logical_document_id="wrong:identity")]
        )


class _SearchClient:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.calls = []

    def search(self, *, index, body):
        self.calls.append((index, body))
        return next(self.pages)


def test_load_active_records_uses_search_after(monkeypatch) -> None:
    monkeypatch.setattr(backfill.settings, "OPENSEARCH_INDEX", "sections")
    first = [_record("one"), _record("two")]
    first[0]["sort"] = ["one"]
    first[1]["sort"] = ["two"]
    second = [_record("three")]
    second[0]["sort"] = ["three"]
    client = _SearchClient(
        [
            {"hits": {"hits": first}},
            {"hits": {"hits": second}},
        ]
    )

    records = list(backfill.load_active_records(client=client, page_size=2))

    assert records == [*first, *second]
    assert client.calls[0][1]["sort"] == [{"_id": "asc"}]
    assert client.calls[1][1]["search_after"] == ["two"]
