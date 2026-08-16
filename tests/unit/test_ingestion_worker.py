"""Tests for durable document-ingestion command validation."""

from unittest.mock import MagicMock

import pytest

from scripts import run_ingestion_worker
from scripts.run_ingestion_worker import (
    _extend_message_visibility,
    _parse_command,
    _approved_object_details,
    _s3_event_objects,
    _s3_location,
    _validate_command,
    process_message,
)


def test_approved_s3_path_maps_country_name_and_uk_alias(monkeypatch) -> None:
    monkeypatch.setattr(
        run_ingestion_worker,
        "get_widget_countries",
        lambda: [{"code": "GB", "name": "United Kingdom"}],
    )
    monkeypatch.setattr(
        run_ingestion_worker,
        "get_widget_language_codes_for_country",
        lambda country: {"en"} if country == "GB" else set(),
    )
    details = _approved_object_details(
        "approved-bucket",
        "approved/United_Kingdom_en/policies/UK-EN-Company-Policy.pdf",
    )

    assert details["country"] == "GB"
    assert details["language"] == "en"
    assert details["accessScope"] == "country"


def test_s3_event_parser_accepts_eventbridge_envelope() -> None:
    events = _s3_event_objects(
        '{"source":"aws.s3","detail":{"bucket":{"name":"bucket"},'
        '"object":{"key":"approved/Italy_it/policies/policy.pdf",'
        '"version-id":"v1"}}}'
    )

    assert events == [{
        "bucket": "bucket",
        "key": "approved/Italy_it/policies/policy.pdf",
        "versionId": "v1",
        "etag": "",
    }]


class _StopAfterOneHeartbeat:
    def __init__(self) -> None:
        self.wait_calls = 0

    def wait(self, _seconds: int) -> bool:
        self.wait_calls += 1
        return self.wait_calls > 1


def test_worker_accepts_versioned_reference_command() -> None:
    command = _parse_command(
        '{"schemaVersion":1,"jobId":"j1","uploadUri":"s3://bucket/quarantine/j1/policy.pdf",'
        '"filename":"policy.pdf","country":"CA","language":"en",'
        '"documentType":"policy","accessScope":"country","contentHash":"'
        + ("a" * 64)
        + '"}'
    )

    assert command["jobId"] == "j1"
    assert _s3_location(command["uploadUri"]) == ("bucket", "quarantine/j1/policy.pdf")


def test_worker_accepts_command_inside_approved_quarantine(monkeypatch) -> None:
    monkeypatch.setattr(run_ingestion_worker.settings, "KNOWLEDGE_UPLOAD_BUCKET", "bucket")
    monkeypatch.setattr(
        run_ingestion_worker.settings,
        "ADMIN_INGESTION_QUARANTINE_PREFIX",
        "quarantine",
    )
    command = {
        "uploadUri": "s3://bucket/quarantine/j1/policy.pdf",
        "filename": "policy.pdf",
        "country": "CA",
        "language": "en",
        "documentType": "policy",
        "accessScope": "country",
        "contentHash": "a" * 64,
    }

    assert _validate_command(command) == ("bucket", "quarantine/j1/policy.pdf")


def test_worker_rejects_unknown_schema_and_non_s3_upload() -> None:
    with pytest.raises(ValueError, match="schema"):
        _parse_command('{"schemaVersion":2}')
    with pytest.raises(ValueError, match="S3"):
        _s3_location("https://example.com/policy.pdf")


def test_worker_rejects_upload_outside_quarantine(monkeypatch) -> None:
    monkeypatch.setattr(run_ingestion_worker.settings, "KNOWLEDGE_UPLOAD_BUCKET", "approved-bucket")
    monkeypatch.setattr(
        run_ingestion_worker.settings,
        "ADMIN_INGESTION_QUARANTINE_PREFIX",
        "quarantine",
    )
    command = {
        "uploadUri": "s3://other-bucket/quarantine/policy.pdf",
        "filename": "policy.pdf",
        "country": "CA",
        "language": "en",
        "documentType": "policy",
        "accessScope": "country",
        "contentHash": "a" * 64,
    }

    with pytest.raises(ValueError, match="quarantine"):
        _validate_command(command)


def test_worker_extends_visibility_while_processing(monkeypatch) -> None:
    clients = MagicMock()
    monkeypatch.setattr(run_ingestion_worker, "get_aws_clients", lambda: clients)
    monkeypatch.setattr(
        run_ingestion_worker.settings,
        "ADMIN_INGESTION_QUEUE_URL",
        "https://sqs.us-east-1.amazonaws.com/123456789012/ingestion",
    )
    monkeypatch.setattr(
        run_ingestion_worker.settings,
        "ADMIN_INGESTION_WORKER_VISIBILITY_SECONDS",
        60,
    )

    _extend_message_visibility(
        _StopAfterOneHeartbeat(),
        receipt_handle="receipt-1",
    )

    clients.sqs.change_message_visibility.assert_called_once_with(
        QueueUrl="https://sqs.us-east-1.amazonaws.com/123456789012/ingestion",
        ReceiptHandle="receipt-1",
        VisibilityTimeout=60,
    )


def test_terminal_job_command_is_removed_without_reprocessing(monkeypatch) -> None:
    monkeypatch.setattr(run_ingestion_worker.settings, "KNOWLEDGE_UPLOAD_BUCKET", "bucket")
    monkeypatch.setattr(
        run_ingestion_worker.settings,
        "ADMIN_INGESTION_QUARANTINE_PREFIX",
        "quarantine",
    )
    monkeypatch.setattr(
        run_ingestion_worker,
        "claim_ingestion_job",
        lambda *_args, **_kwargs: "terminal",
    )
    monkeypatch.setattr(
        run_ingestion_worker,
        "get_aws_clients",
        lambda: (_ for _ in ()).throw(
            AssertionError("terminal jobs must not access document storage")
        ),
    )
    body = (
        '{"schemaVersion":1,"jobId":"j1",'
        '"uploadUri":"s3://bucket/quarantine/j1/policy.pdf",'
        '"filename":"policy.pdf","country":"CA","language":"en",'
        '"documentType":"policy","accessScope":"country","contentHash":"'
        + ("a" * 64)
        + '"}'
    )

    assert process_message({"Body": body}) is True
