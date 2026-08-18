from types import SimpleNamespace

import pytest

from config import settings
from scripts.clone_retrieval_candidate_index import (
    _clone_actions,
    _clone_current_index,
    _document_digest,
    _iter_documents,
    _source_index_body,
    _unique_keyword_count,
    _validate_candidate_index,
    _wait_for_count,
)


def test_candidate_index_must_be_isolated(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_INDEX", "askvera-current")
    monkeypatch.setattr(settings, "OPENSEARCH_VNEXT_INDEX", "askvera-vnext")

    with pytest.raises(ValueError, match="must differ"):
        _validate_candidate_index("askvera-current")
    with pytest.raises(ValueError, match="contain both"):
        _validate_candidate_index("askvera-test")

    _validate_candidate_index("askvera-vnext-candidate-r5")


def test_source_index_body_copies_mapping_and_only_safe_setting() -> None:
    indices = SimpleNamespace(
        get_mapping=lambda **_kwargs: {
            "source": {"mappings": {"properties": {"content": {"type": "text"}}}}
        },
        get_settings=lambda **_kwargs: {
            "source": {
                "settings": {
                    "index": {
                        "knn": "true",
                        "uuid": "do-not-copy",
                        "creation_date": "do-not-copy",
                    }
                }
            }
        },
    )

    body = _source_index_body(SimpleNamespace(indices=indices), "source")

    assert body == {
        "mappings": {"properties": {"content": {"type": "text"}}},
        "settings": {"index": {"knn": True}},
    }


def test_document_digest_is_stable_for_field_order_and_internal_id() -> None:
    first = {"_id": "generated-1", "_source": {"b": 2, "a": 1}}
    second = {"_source": {"a": 1, "b": 2}, "_id": "generated-2"}

    assert _document_digest(first) == _document_digest(second)


def test_clone_actions_preserve_source_id_without_internal_id(monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.clone_retrieval_candidate_index._iter_documents",
        lambda *_args: iter(
            [{"_id": "internal", "_source": {"id": "stable-source-id"}}]
        ),
    )

    actions = list(_clone_actions(object(), "source", "candidate"))

    assert actions == [
        {
            "_op_type": "create",
            "_index": "candidate",
            "_source": {"id": "stable-source-id"},
        }
    ]


def test_unique_keyword_count_uses_composite_after_key() -> None:
    responses = iter(
        (
            {
                "aggregations": {
                    "unique_values": {
                        "buckets": [{"key": {"value": "a"}}],
                        "after_key": {"value": "a"},
                    }
                }
            },
            {
                "aggregations": {
                    "unique_values": {
                        "buckets": [{"key": {"value": "b"}}],
                    }
                }
            },
        )
    )
    client = SimpleNamespace(search=lambda **_kwargs: next(responses))

    assert _unique_keyword_count(client, "source", "id") == 2


def test_iter_documents_uses_search_after() -> None:
    responses = iter(
        (
            {"hits": {"hits": [{"_id": "1", "_source": {}, "sort": ["1"]}]}},
            {"hits": {"hits": []}},
        )
    )
    bodies = []

    def search(**kwargs):
        bodies.append(kwargs["body"])
        return next(responses)

    assert list(_iter_documents(SimpleNamespace(search=search), "source"))[0][
        "_id"
    ] == "1"
    assert "search_after" not in bodies[0]
    assert bodies[1]["search_after"] == ["1"]


def test_wait_for_count_handles_eventual_consistency(monkeypatch) -> None:
    counts = iter(({"count": 0}, {"count": 2}))
    monkeypatch.setattr(
        "scripts.clone_retrieval_candidate_index.time.sleep", lambda _seconds: None
    )

    assert _wait_for_count(
        SimpleNamespace(count=lambda **_kwargs: next(counts)),
        "candidate",
        2,
    ) == 2


def test_clone_refuses_existing_candidate() -> None:
    client = SimpleNamespace(
        indices=SimpleNamespace(exists=lambda **_kwargs: True)
    )

    with pytest.raises(ValueError, match="will not be overwritten"):
        _clone_current_index(
            client=client,
            source_index="source",
            candidate_index="candidate",
        )


def test_clone_requires_count_parity(monkeypatch) -> None:
    counts = iter(({"count": 2}, {"count": 1}))
    indices = SimpleNamespace(
        exists=lambda **_kwargs: False,
        create=lambda **_kwargs: None,
        get_mapping=lambda **_kwargs: {
            "source": {"mappings": {"properties": {}}}
        },
        get_settings=lambda **_kwargs: {
            "source": {"settings": {"index": {"knn": "true"}}}
        },
        refresh=lambda **_kwargs: None,
    )
    client = SimpleNamespace(
        indices=indices,
        count=lambda **_kwargs: next(counts),
    )
    monkeypatch.setattr(
        "scripts.clone_retrieval_candidate_index.helpers.bulk",
        lambda *_args, **_kwargs: (1, []),
    )
    monkeypatch.setattr(
        "scripts.clone_retrieval_candidate_index._unique_keyword_count",
        lambda *_args, **_kwargs: 2,
    )
    monkeypatch.setattr(
        "scripts.clone_retrieval_candidate_index._wait_for_count",
        lambda *_args, **_kwargs: 1,
    )

    with pytest.raises(RuntimeError, match="count parity failed"):
        _clone_current_index(
            client=client,
            source_index="source",
            candidate_index="candidate",
            verify_content=False,
        )
