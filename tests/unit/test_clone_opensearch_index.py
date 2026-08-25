"""Tests for safe ranking-only OpenSearch index cloning."""

import pytest

from scripts.ingestion.clone_opensearch_index import (
    _iter_source_documents,
    _source_index_body,
    _validate_targets,
    clone_index,
    verify_clone,
)


class _Indices:
    def __init__(self, existing: set[str]) -> None:
        self.existing = existing
        self.created: list[tuple[str, dict]] = []

    def exists(self, *, index: str) -> bool:
        return index in self.existing

    def create(self, *, index: str, body: dict) -> None:
        self.created.append((index, body))
        self.existing.add(index)

    def get_mapping(self, *, index: str) -> dict:
        return {
            index: {
                "mappings": {
                    "properties": {
                        "id": {"type": "keyword"},
                        "metadata": {
                            "properties": {
                                "document_version": {"type": "text"},
                            }
                        },
                    }
                }
            }
        }

    def refresh(self, *, index: str) -> None:
        assert index in self.existing


class _Client:
    def __init__(self) -> None:
        self.indices = _Indices({"current"})
        self.search_requests: list[dict] = []
        self.counts = {"current": 2, "candidate": 2}

    def search(self, *, index: str, body: dict) -> dict:
        self.search_requests.append({"index": index, "body": body})
        after = body.get("search_after")
        if after is None:
            return {
                "hits": {
                    "hits": [
                        {
                            "_id": "one",
                            "_source": {"id": "one", "content": "First"},
                            "sort": ["one"],
                        },
                        {
                            "_id": "two",
                            "_source": {"id": "two", "content": "Second"},
                            "sort": ["two"],
                        },
                    ]
                }
            }
        return {"hits": {"hits": []}}

    def count(self, *, index: str) -> dict[str, int]:
        return {"count": self.counts.get(index, 2)}


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
    captured: list[dict] = []

    def fake_bulk(_client, actions, **_kwargs):
        captured.extend(actions)
        return len(captured), []

    monkeypatch.setattr(
        "scripts.ingestion.clone_opensearch_index.helpers.bulk",
        fake_bulk,
    )

    result = clone_index(client, source="current", destination="candidate")

    assert all("_id" not in action for action in captured)
    assert [action["_source"]["id"] for action in captured] == ["one", "two"]
    assert captured[0]["_source"] == {"id": "one", "content": "First"}
    assert result["source_count"] == result["destination_count"] == 2
    assert client.search_requests[-1]["body"]["search_after"] == ["two"]
    created_body = client.indices.created[0][1]
    assert created_body["mappings"]["properties"]["metadata"]["properties"][
        "document_version"
    ] == {"type": "text"}


def test_source_mapping_is_required() -> None:
    client = _Client()
    client.indices.get_mapping = lambda **_kwargs: {"current": {"mappings": {}}}

    with pytest.raises(RuntimeError, match="mapping is unavailable"):
        _source_index_body(client, source="current")


def test_serverless_pagination_requires_a_sort_value() -> None:
    class MissingSortClient:
        def search(self, **_kwargs):
            return {"hits": {"hits": [{"_id": "one", "_source": {"id": "one"}}]}}

    with pytest.raises(RuntimeError, match="pagination sort value"):
        list(_iter_source_documents(MissingSortClient(), source="current"))


def test_clone_can_resume_only_an_empty_destination(monkeypatch) -> None:
    client = _Client()
    client.indices.existing.add("candidate")
    client.counts["candidate"] = 0

    def fake_bulk(_client, actions, **_kwargs):
        copied = len(list(actions))
        client.counts["candidate"] = copied
        return copied, []

    monkeypatch.setattr(
        "scripts.ingestion.clone_opensearch_index.helpers.bulk",
        fake_bulk,
    )

    result = clone_index(
        client,
        source="current",
        destination="candidate",
        allow_empty_destination=True,
        verification_timeout_seconds=0,
    )

    assert not client.indices.created
    assert result["source_count"] == 2


def test_clone_refuses_to_resume_nonempty_destination() -> None:
    client = _Client()
    client.indices.existing.add("candidate")

    with pytest.raises(ValueError, match="already exists"):
        clone_index(
            client,
            source="current",
            destination="candidate",
            allow_empty_destination=True,
        )


def test_verify_clone_detects_count_mismatch() -> None:
    client = _Client()
    client.indices.existing.add("candidate")
    client.counts["candidate"] = 1

    with pytest.raises(RuntimeError, match="count verification failed"):
        verify_clone(client, source="current", destination="candidate")


def test_verify_clone_detects_content_mismatch() -> None:
    client = _Client()
    client.indices.existing.add("candidate")
    original_search = client.search

    def different_destination(*, index: str, body: dict) -> dict:
        response = original_search(index=index, body=body)
        if index == "candidate" and response["hits"]["hits"]:
            response["hits"]["hits"][0]["_source"]["content"] = "Changed"
        return response

    client.search = different_destination

    with pytest.raises(RuntimeError, match="content verification failed"):
        verify_clone(client, source="current", destination="candidate")
