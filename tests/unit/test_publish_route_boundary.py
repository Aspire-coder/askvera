"""The publish endpoint, entered the way a reviewer enters it.

The gate has service-level tests, and they establish that evaluate_publication
collects contradiction reasons before it consults a resolution. What they do
not establish is that a reviewer's approval, submitted through the actual
endpoint, reaches that code at all - the route could pass the wrong thing, skip
the call, or handle the refusal into a success. That is the gap these close.

The route function is called directly rather than through TestClient: what is
under test is the handler and everything below it, not the admin
authentication in front of it, which has its own tests.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from api import admin_routes
from services import knowledge_ingestion

# expiry before effective. No reading of these two dates makes the document
# valid, so no decision can waive it.
CONTRADICTORY = {
    "job_id": "job-c",
    "filename": "DK-EN-Company-Policy.pdf",
    "country": "DK",
    "language": "EN",
    "document_type": "policy",
    "access_scope": "country",
    "document_version": "2026-07",
    "effective_date": "2026-07-01",
    "expiry_date": "2026-01-01",
    "content_hash": "abc123",
    "status": "ready_for_review",
    "section_count": 4,
}


class _Request:
    def __init__(self) -> None:
        self.state = type("S", (), {})()
        self.headers: dict[str, str] = {}
        self.client = None
        self.url = type("U", (), {"path": "/api/admin/ingestions/job-c/publish"})()


@pytest.fixture()
def reviewer(monkeypatch):
    """An authenticated reviewer holding publish permission."""
    monkeypatch.setattr(
        admin_routes,
        "require_admin_access",
        lambda *args, **kwargs: {"email": "reviewer@example.com", "role": "admin"},
    )
    monkeypatch.setattr(
        admin_routes, "preview_ingestion_job", lambda job_id, limit=1: {"job": dict(CONTRADICTORY)}
    )
    monkeypatch.setattr(admin_routes, "_payload", lambda result, request: result)
    monkeypatch.setattr(knowledge_ingestion, "_ingestion_job", lambda job_id: dict(CONTRADICTORY))
    # A decision that reaches the database would need one; the point here is
    # whether it is even consulted, so recording is stubbed and observable.
    recorded: list[dict] = []

    def _record(**kwargs):
        from services.publication_gate import record_resolution

        recorded.append(kwargs)
        return record_resolution(
            revision=kwargs["revision"],
            decided_by=kwargs["decided_by"],
            decision=kwargs["decision"],
            reason=kwargs["reason"],
        )

    monkeypatch.setattr(knowledge_ingestion, "record_review_decision", _record)
    return recorded


def _publish(reason: str):
    return admin_routes.publish_ingestion(
        "job-c",
        _Request(),
        admin_routes.IngestionPublishRequest(reason=reason),
    )


def test_a_reviewer_approval_does_not_publish_a_contradiction(reviewer) -> None:
    """The one that matters. An approval arrives and the document still cannot go out."""
    with pytest.raises(HTTPException) as raised:
        _publish("Checked with the market team, the dates are fine.")

    assert raised.value.status_code == 400
    assert "expiry" in str(raised.value.detail).lower()


def test_the_approval_is_still_recorded_when_it_is_refused(reviewer) -> None:
    """A decision is a fact about what someone concluded.

    Discarding it because publication was then refused would lose the only
    evidence that a reviewer looked at this and approved it anyway.
    """
    with pytest.raises(HTTPException):
        _publish("Checked with the market team, the dates are fine.")

    assert len(reviewer) == 1
    assert reviewer[0]["decision"] == "publish"


def test_the_reviewer_is_taken_from_the_principal_not_the_request(reviewer) -> None:
    """A caller cannot attribute their decision to somebody else."""
    with pytest.raises(HTTPException):
        _publish("Approved.")

    assert reviewer[0]["decided_by"] == "reviewer@example.com"


def test_the_revision_is_derived_from_the_job_not_supplied(reviewer) -> None:
    """An approval cannot be presented for a revision other than this one."""
    with pytest.raises(HTTPException):
        _publish("Approved.")

    expected = knowledge_ingestion.publication_revision(dict(CONTRADICTORY))
    assert reviewer[0]["revision"] == expected


def test_the_request_body_carries_no_reviewer_or_revision_field() -> None:
    """Fields that do not exist cannot be spoofed."""
    fields = set(admin_routes.IngestionPublishRequest.model_fields)

    assert fields == {"reason"}
