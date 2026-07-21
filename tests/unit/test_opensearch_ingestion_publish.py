"""Tests for safe cache-version rotation after knowledge publication."""

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
