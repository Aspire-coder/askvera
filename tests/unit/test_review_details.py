"""What the review endpoint tells a reviewer.

The database is faked. What this establishes is the shaping - which is where
the mistakes that matter live, because every one of them is a reviewer being
shown something that reads as reassurance.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from services import knowledge_ingestion

NOW = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)

FINDINGS = {
    "schema": 1,
    "findings": [
        {"field": "expiry_date", "severity": "contradiction", "detail": "Expiry precedes effective date."},
        {"field": "effective_date", "severity": "unresolved", "detail": "Historical applicability cannot be verified."},
    ],
    "uncertain_pages": [4, 11],
}


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class _Connection:
    def __init__(self, job_row, decision_rows):
        self.job_row = job_row
        self.decision_rows = decision_rows

    def execute(self, statement, params=None):
        sql = str(statement)
        if "ingestion_review_decisions" in sql:
            return _Result(self.decision_rows)
        return _Result([self.job_row] if self.job_row else [])

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _engine(job_row, decision_rows=()):
    class _Engine:
        def connect(self):
            return _Connection(job_row, list(decision_rows))

    return _Engine()


def _job_row(**overrides):
    row = {
        "review_revision": "rev-a",
        "review_findings": json.dumps(FINDINGS),
        "review_evaluated_at": NOW,
        "publication_state": "not_started",
        "publication_detail": "",
    }
    row.update(overrides)
    return row


def test_a_legacy_job_reads_as_never_assessed(monkeypatch) -> None:
    """The distinction the whole column design exists for.

    A job from before review persistence has NULL findings. Reporting that as
    an empty list would show a reviewer a clean bill of health for an
    assessment that never ran.
    """
    monkeypatch.setattr(
        knowledge_ingestion,
        "get_engine",
        lambda: _engine(_job_row(review_findings=None, review_evaluated_at=None, review_revision="")),
    )

    result = knowledge_ingestion.review_details("job-legacy")

    assert result["assessed"] is False
    assert result["findings"] == []


def test_an_assessed_clean_document_is_distinguishable_from_an_unassessed_one(monkeypatch) -> None:
    monkeypatch.setattr(
        knowledge_ingestion,
        "get_engine",
        lambda: _engine(
            _job_row(review_findings=json.dumps({"schema": 1, "findings": [], "uncertain_pages": []}))
        ),
    )

    result = knowledge_ingestion.review_details("job-clean")

    assert result["assessed"] is True
    assert result["findings"] == []


def test_contradictions_are_separated_from_what_a_reviewer_may_resolve(monkeypatch) -> None:
    """Presenting them as one list invites approving the unwaivable one."""
    monkeypatch.setattr(knowledge_ingestion, "get_engine", lambda: _engine(_job_row()))

    result = knowledge_ingestion.review_details("job-1")

    assert [finding["field"] for finding in result["contradictions"]] == ["expiry_date"]
    assert [finding["field"] for finding in result["unresolved"]] == ["effective_date"]


def test_the_affected_pages_are_named(monkeypatch) -> None:
    """"Some pages may be incomplete" is not something anyone can act on."""
    monkeypatch.setattr(knowledge_ingestion, "get_engine", lambda: _engine(_job_row()))

    assert knowledge_ingestion.review_details("job-1")["affectedPages"] == [4, 11]


def test_a_decision_on_an_earlier_revision_is_marked_as_such(monkeypatch) -> None:
    """Otherwise the history reads as though this revision was already approved."""
    decisions = [
        {
            "review_revision": "rev-a",
            "decided_by": "reviewer@example.com",
            "decision": "publish",
            "reason": "Confirmed with the market.",
            "decided_at": NOW,
        },
        {
            "review_revision": "rev-old",
            "decided_by": "someone@example.com",
            "decision": "reject",
            "reason": "Wrong effective date.",
            "decided_at": NOW,
        },
    ]
    monkeypatch.setattr(
        knowledge_ingestion, "get_engine", lambda: _engine(_job_row(), decisions)
    )

    result = knowledge_ingestion.review_details("job-1")

    assert [d["appliesToCurrentRevision"] for d in result["decisions"]] == [True, False]
    assert result["decisions"][1]["reason"] == "Wrong effective date."


def test_an_unknown_job_is_a_missing_job_not_an_empty_review(monkeypatch) -> None:
    monkeypatch.setattr(knowledge_ingestion, "get_engine", lambda: _engine(None))

    with pytest.raises(KeyError):
        knowledge_ingestion.review_details("nope")


def test_findings_already_decoded_by_the_driver_are_accepted(monkeypatch) -> None:
    """psycopg returns JSONB as a dict; a JSON string is the sqlite-ish case."""
    monkeypatch.setattr(
        knowledge_ingestion, "get_engine", lambda: _engine(_job_row(review_findings=FINDINGS))
    )

    assert len(knowledge_ingestion.review_details("job-1")["findings"]) == 2
