"""Unit tests for legal document loading from S3."""

from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError

from services import legal_service
from utils.exceptions import ConfigurationError


class FakeBody:
    """Small stand-in for the streaming body returned by boto3 S3."""

    def __init__(self, value: str) -> None:
        self.value = value

    def read(self) -> bytes:
        return self.value.encode("utf-8")


class FakeS3:
    """Fake S3 client that records requested keys."""

    def __init__(self, objects: dict[str, str]) -> None:
        self.objects = objects
        self.calls: list[tuple[str, str]] = []

    def get_object(self, Bucket: str, Key: str) -> dict[str, FakeBody]:
        self.calls.append((Bucket, Key))
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")
        return {"Body": FakeBody(self.objects[Key])}


def _legal_objects() -> dict[str, str]:
    return {
        "legal/2026.1/html/Privacy Notice.html": "<h1>Privacy</h1>",
        "legal/2026.1/html/Privacy-Addendum.html": "<h1>Addendum</h1>",
        "legal/2026.1/html/FLP Individual Arbitration and Class Action Waiver Agreement.html": "<h1>Arbitration</h1>",
    }


def test_legal_document_key_uses_configured_s3_path(monkeypatch) -> None:
    """Legal document paths are built from bucket-independent settings."""
    monkeypatch.setattr(legal_service.settings, "LEGAL_PREFIX", "legal")
    monkeypatch.setattr(legal_service.settings, "LEGAL_VERSION", "2026.1")

    assert legal_service.legal_document_key("Privacy Notice.html") == "legal/2026.1/html/Privacy Notice.html"


def test_load_legal_documents_returns_expected_response(monkeypatch) -> None:
    """The legal service returns the API response shape."""
    fake_s3 = FakeS3(_legal_objects())
    monkeypatch.setattr(legal_service.settings, "LEGAL_BUCKET", "askverachat-prod-content")
    monkeypatch.setattr(legal_service.settings, "LEGAL_PREFIX", "legal")
    monkeypatch.setattr(legal_service.settings, "LEGAL_VERSION", "2026.1")
    monkeypatch.setattr(legal_service, "get_aws_clients", lambda: SimpleNamespace(s3=fake_s3))
    legal_service.load_legal_documents.cache_clear()

    result = legal_service.load_legal_documents()

    assert result["version"] == "2026.1"
    assert [document["id"] for document in result["documents"]] == ["privacy", "privacy-addendum", "arbitration"]
    assert all(document["required"] is True for document in result["documents"])
    assert result["documents"][0]["html"] == "<h1>Privacy</h1>"


def test_load_legal_documents_caches_s3_results(monkeypatch) -> None:
    """Legal documents are fetched from S3 once and then served from memory."""
    fake_s3 = FakeS3(_legal_objects())
    monkeypatch.setattr(legal_service.settings, "LEGAL_BUCKET", "askverachat-prod-content")
    monkeypatch.setattr(legal_service.settings, "LEGAL_PREFIX", "legal")
    monkeypatch.setattr(legal_service.settings, "LEGAL_VERSION", "2026.1")
    monkeypatch.setattr(legal_service, "get_aws_clients", lambda: SimpleNamespace(s3=fake_s3))
    legal_service.load_legal_documents.cache_clear()

    first = legal_service.load_legal_documents()
    second = legal_service.load_legal_documents()

    assert first is second
    assert len(fake_s3.calls) == 3


def test_load_legal_documents_fails_when_document_missing(monkeypatch) -> None:
    """Startup validation fails if any required legal document is absent."""
    objects = _legal_objects()
    objects.pop("legal/2026.1/html/Privacy Notice.html")
    fake_s3 = FakeS3(objects)
    monkeypatch.setattr(legal_service.settings, "LEGAL_BUCKET", "askverachat-prod-content")
    monkeypatch.setattr(legal_service.settings, "LEGAL_PREFIX", "legal")
    monkeypatch.setattr(legal_service.settings, "LEGAL_VERSION", "2026.1")
    monkeypatch.setattr(legal_service, "get_aws_clients", lambda: SimpleNamespace(s3=fake_s3))
    legal_service.load_legal_documents.cache_clear()

    with pytest.raises(ConfigurationError, match="Privacy Notice.html"):
        legal_service.load_legal_documents()
