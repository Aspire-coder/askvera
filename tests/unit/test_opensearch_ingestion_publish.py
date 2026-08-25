"""Tests for safe cache-version rotation after knowledge publication."""

import pytest

from config import settings
from scripts.ingestion import load_policy_sections_to_opensearch as loader


def test_publish_kb_version_updates_only_the_named_parameter(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class SsmClient:
        def put_parameter(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(loader.boto3, "client", lambda service, region_name: SsmClient())

    version = loader._publish_kb_version(
        "approved-2026-07-20",
        "/askverachat/prod/KB_VERSION",
        "abcdef123456",
    )

    assert version == "approved-2026-07-20"
    assert calls == [
        {
            "Name": "/askverachat/prod/KB_VERSION",
            "Type": "String",
            "Value": "approved-2026-07-20",
            "Overwrite": True,
        }
    ]


def test_vnext_chunks_cannot_target_current_index(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_INDEX", "askvera-current")

    with pytest.raises(ValueError, match="require a separate --index"):
        loader._validate_chunk_profile_target(
            [{"chunk_profile": "vnext"}],
            "askvera-current",
        )


def test_vnext_chunks_can_target_isolated_index(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_INDEX", "askvera-current")

    loader._validate_chunk_profile_target(
        [{"chunk_profile": "vnext"}],
        "askvera-vnext",
    )


def test_semantic_v2_embedding_text_excludes_filter_metadata() -> None:
    section = {
        "source_file": "Forever Living Products U.S. Company Policy.pdf",
        "country": "US",
        "language": "en",
        "section_id": "4.01",
        "title": "Manager qualification",
        "content": "A Manager is achieved by generating the required Case Credits.",
    }

    assert loader._embedding_text(section, "semantic-v2") == (
        "Manager qualification\n"
        "A Manager is achieved by generating the required Case Credits."
    )
    assert "United" not in loader._embedding_text(section, "semantic-v2")
    assert "US" in loader._embedding_text(section, "current")


def test_semantic_v2_embedding_profile_is_isolated_from_current_index(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_INDEX", "askvera-current")

    with pytest.raises(ValueError, match="only vNext chunks"):
        loader._resolve_embedding_text_profile(
            [{"chunk_profile": "current"}],
            "semantic-v2",
            "askvera-vnext",
        )
    with pytest.raises(ValueError, match="separate OpenSearch index"):
        loader._resolve_embedding_text_profile(
            [{"chunk_profile": "vnext"}],
            "semantic-v2",
            "askvera-current",
        )


def test_auto_embedding_profile_uses_semantic_v2_only_for_vnext(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_INDEX", "askvera-current")

    assert loader._resolve_embedding_text_profile(
        [{"chunk_profile": "vnext"}],
        "auto",
        "askvera-vnext",
    ) == "semantic-v2"
    assert loader._resolve_embedding_text_profile(
        [{"chunk_profile": "current"}],
        "auto",
        "askvera-current",
    ) == "current"
