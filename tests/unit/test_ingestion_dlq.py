"""Tests for dry-run-safe ingestion dead-letter reconciliation."""

import json

import pytest

from scripts.reconcile_ingestion_dlq import job_id_from_message


def test_dlq_reconciliation_reads_supported_job_id() -> None:
    message = {
        "Body": json.dumps({"schemaVersion": 1, "jobId": "job-123"}),
    }

    assert job_id_from_message(message) == "job-123"


def test_dlq_reconciliation_rejects_unknown_commands() -> None:
    with pytest.raises(ValueError, match="schema"):
        job_id_from_message(
            {"Body": json.dumps({"schemaVersion": 2, "jobId": "job-123"})}
        )
