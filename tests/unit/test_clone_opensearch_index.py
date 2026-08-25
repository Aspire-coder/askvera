"""Tests for safe ranking-only OpenSearch index cloning."""

import pytest

from scripts.ingestion.clone_opensearch_index import _validate_targets, clone_index


class _Indices:
    def __init__(self, existing: set[str]) -> None:
        self.existing = existing
        self.created: list[tuple[str, dict]] = []

    def exists(self, *, index: str) -> bool:
        return index in self.existing

    def create(self, *, index: str, body: dict) -> None:
        self.created.append((index, body))
        self.existing.add(index)

    def refresh(self, *, index: str) -> None:
        assert index in self.existing


class _Client:
    def __init__(self) -> None:
        self.indices = _Indices({"current"})

    def count(self, *, index: str) -> dict[str, int]:
        return {"count": 2}


def test_clone_rejects_current_index_as_destination() -> None:
    with pytest.raises(ValueError, match="separate"):
        _validate_targets("current", "current")


def test_clone_rejects_existing_destination() -> None:
    client = _Client()
    client.indices.existing.add("candidate")

    with pytest.raises(ValueError, match="already exists"):
        clone_index(client, source="current", destination="candidate")


def test_clone_copies_exact_ids_and_sources(monkeypatch) -> None:
    client = _Client()
    scanned = [
        {"_id": "one", "_source": {"id": "one", "content": "First"}},
        {"_id": "two", "_source": {"id": "two", "content": "Second"}},
    ]
    captured: list[dict] = []

    monkeypatch.setattr(
        "scripts.ingestion.clone_opensearch_index.helpers.scan",
        lambda *_args, **_kwargs: scanned,
    )

    def fake_bulk(_client, actions, **_kwargs):
        captured.extend(actions)
        return len(captured), []

    monkeypatch.setattr(
        "scripts.ingestion.clone_opensearch_index.helpers.bulk",
        fake_bulk,
    )

    result = clone_index(client, source="current", destination="candidate")

    assert [action["_id"] for action in captured] == ["one", "two"]
    assert captured[0]["_source"] == scanned[0]["_source"]
    assert result["source_count"] == result["destination_count"] == 2
