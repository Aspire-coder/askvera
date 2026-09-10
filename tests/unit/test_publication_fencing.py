"""A paused worker resuming after it lost the job.

The attempt machinery refuses a stale worker's completion record. That is not
the same as refusing its WRITES, and the difference is the whole question: a
worker paused between activation and the pointer, or between the pointer and
finalization, wakes up holding a token that is no longer current and proceeds
to write. An advisory lock does not help - it serialises writers, and a stale
worker takes it perfectly legitimately.

So every write that decides what a reader sees, or what the portal shows, has
to check ownership in the same transaction as the write itself.
"""

from __future__ import annotations

import pytest

from services import knowledge_ingestion
from services.publication_attempt import Claim, OwnershipLost

OWNER = Claim(job_id="job-1", revision="rev-a", token="worker-a")
STALE = Claim(job_id="job-1", revision="rev-a", token="worker-a-expired")


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None

    def mappings(self):
        return self

    def one(self):
        return self.rows[0]


class _Connection:
    """A connection that answers the ownership probe and records the rest."""

    def __init__(self, current_token: str, current_revision: str = "rev-a"):
        self.current_token = current_token
        self.current_revision = current_revision
        self.statements: list[str] = []

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.statements.append(sql)
        if "publication_attempt_key = :token" in sql and sql.startswith("SELECT 1"):
            matches = (
                params["token"] == self.current_token
                and params["revision"] == self.current_revision
            )
            return _Result([(1,)] if matches else [])
        return _Result([])

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _engine(connection):
    class _Engine:
        def begin(self):
            return connection

    return _Engine()


def _ownership_probe(connection) -> str:
    return next(s for s in connection.statements if s.startswith("SELECT 1"))


# --- the ownership check itself -------------------------------------------


def test_the_owner_may_write() -> None:
    connection = _Connection(current_token="worker-a")

    knowledge_ingestion._assert_publication_owner(
        connection, job_id="job-1", owner=OWNER
    )


def test_a_worker_that_lost_the_job_may_not_write() -> None:
    connection = _Connection(current_token="worker-b")

    with pytest.raises(OwnershipLost):
        knowledge_ingestion._assert_publication_owner(
            connection, job_id="job-1", owner=STALE
        )


def test_a_revision_change_also_revokes_the_right_to_write() -> None:
    """A metadata edit during publication invalidates the attempt."""
    connection = _Connection(current_token="worker-a", current_revision="rev-b")

    with pytest.raises(OwnershipLost):
        knowledge_ingestion._assert_publication_owner(
            connection, job_id="job-1", owner=OWNER
        )


def test_the_check_locks_the_row_so_a_takeover_cannot_interleave() -> None:
    """Without FOR UPDATE the check describes a moment already gone.

    A takeover committing between the SELECT and the write would leave the
    stale worker writing anyway, which is exactly the case this exists for.
    """
    connection = _Connection(current_token="worker-a")
    knowledge_ingestion._assert_publication_owner(
        connection, job_id="job-1", owner=OWNER
    )

    assert "FOR UPDATE" in _ownership_probe(connection)


# --- the pointer write -----------------------------------------------------


def test_the_pointer_write_checks_ownership_before_anything_else(monkeypatch) -> None:
    """The authoritative write. It decides what readers see."""
    connection = _Connection(current_token="worker-b")
    monkeypatch.setattr(knowledge_ingestion, "get_engine", lambda: _engine(connection))

    with pytest.raises(OwnershipLost):
        knowledge_ingestion._activate_generation_pointer(
            logical_document_id="country:DZ:fr:policy:charges",
            ingestion_id="job-1",
            country="DZ",
            language="fr",
            source_file="DZ-FR-Charges.pdf",
            document_type="policy",
            access_scope="country",
            activated_by="reviewer@example.com",
            owner=STALE,
        )

    # Nothing was written: the ownership probe is the only statement issued.
    assert len(connection.statements) == 1
    assert connection.statements[0].startswith("SELECT 1")


def test_the_pointer_write_is_checked_in_the_same_transaction() -> None:
    """A check in the caller is a check about a moment that has passed."""
    import inspect

    source = inspect.getsource(knowledge_ingestion._activate_generation_pointer)
    body = source[source.index("with get_engine().begin()"):]

    assert "_assert_publication_owner" in body
    assert body.index("_assert_publication_owner") < body.index("pg_advisory_xact_lock")


def test_the_advisory_lock_is_not_relied_on_for_ownership() -> None:
    """Documented, because it is the intuition that produced the defect.

    An advisory lock serialises writers. A worker whose lease expired takes it
    legitimately and then writes stale state, so serialisation is not
    ownership.
    """
    import inspect

    source = inspect.getsource(knowledge_ingestion._assert_publication_owner)

    assert "advisory lock" in source.lower()


# --- finalization ----------------------------------------------------------


def test_finalization_is_refused_after_a_takeover(monkeypatch) -> None:
    """Finding 1's second half.

    _record_document and the job status update ran in transactions of their
    own, before the fenced completion call, so a stale worker could write both
    over a newer attempt's state.
    """
    connection = _Connection(current_token="worker-b")
    monkeypatch.setattr(knowledge_ingestion, "get_engine", lambda: _engine(connection))

    with pytest.raises(OwnershipLost):
        knowledge_ingestion._finalize_publication(
            job={"filename": "DZ-FR-Charges.pdf", "country": "DZ", "language": "fr"},
            job_id="job-1",
            count=4,
            accepted_by="reviewer@example.com",
            logical_document_id="country:DZ:fr:policy:charges",
            owner=STALE,
        )

    assert len(connection.statements) == 1


def test_finalization_writes_both_rows_under_one_ownership_check(monkeypatch) -> None:
    """Separately they are two windows a stale worker can write through."""
    connection = _Connection(current_token="worker-a")
    monkeypatch.setattr(knowledge_ingestion, "get_engine", lambda: _engine(connection))

    knowledge_ingestion._finalize_publication(
        job={"filename": "DZ-FR-Charges.pdf", "country": "DZ", "language": "fr"},
        job_id="job-1",
        count=4,
        accepted_by="reviewer@example.com",
        logical_document_id="country:DZ:fr:policy:charges",
        owner=OWNER,
    )

    assert connection.statements[0].startswith("SELECT 1")
    assert any("INSERT INTO knowledge_documents" in s for s in connection.statements)
    assert any("UPDATE ingestion_jobs" in s and "status = 'ready'" in s for s in connection.statements)
    # One probe, so one transaction covering both writes.
    assert sum(1 for s in connection.statements if s.startswith("SELECT 1")) == 1


def test_publication_passes_its_claim_to_every_fenced_write() -> None:
    """A parameter that defaults to None is only useful if callers pass it."""
    import inspect

    source = inspect.getsource(knowledge_ingestion.publish_ingestion_job)
    activation = inspect.getsource(knowledge_ingestion._publish_activated_generation)

    assert "owner=claim" in source
    assert "_finalize_publication(" in source
    assert "owner=owner" in activation


# --- the legacy replacement mode, and why it is refused --------------------


class _RecordingClient:
    """An OpenSearch client that records what would have been done to the index."""

    def __init__(self):
        self.activated: list[str] = []
        self.deleted: list[str] = []
        self.indices = self

    def refresh(self, index):
        return None

    def count(self, index, body):
        return {"count": 0}

    def search(self, index, body):
        return {"hits": {"hits": []}}


def _legacy(monkeypatch, client=None) -> _RecordingClient:
    client = client or _RecordingClient()
    monkeypatch.setattr(
        knowledge_ingestion.settings,
        "ADMIN_INGESTION_GENERATION_POINTER_ENABLED",
        False,
        raising=False,
    )
    monkeypatch.setattr(knowledge_ingestion, "_client", lambda: client)
    return client


READY_JOB = {
    "job_id": "job-1",
    "status": "ready_for_review",
    "filename": "DZ-FR-Charges.pdf",
    "country": "DZ",
    "language": "fr",
    "document_type": "policy",
    "access_scope": "country",
    "document_version": "2026-07",
    "effective_date": "2026-07-01",
    "expiry_date": "",
    "content_hash": "abc123",
    "section_count": 2,
    "logical_document_id": "country:DZ:fr:policy:charges",
}


def test_a_paused_legacy_worker_cannot_resume_because_the_mode_is_refused(
    monkeypatch,
) -> None:
    """The scenario: a worker paused before it touched the index, its lease
    expired, someone else republished, and now it wakes up.

    In the legacy mode it would activate its own sections - immediately
    reader-visible, because nothing filters them - and then delete every
    section for that source carrying a different ingestion id. The newer
    generation is exactly that. It would delete the live document and reinstate
    a stale one.

    No ownership check can prevent it. The two writes go to OpenSearch, the
    ownership record is in PostgreSQL, and nothing spanning the two is atomic:
    a check can only narrow the window between deciding and writing. So the
    mode is refused rather than protected, and this is the test that says so.
    """
    client = _legacy(monkeypatch)
    monkeypatch.setattr(knowledge_ingestion, "_ingestion_job", lambda job_id: dict(READY_JOB))

    with pytest.raises(ValueError) as raised:
        knowledge_ingestion.publish_ingestion_job("job-1", accepted_by="reviewer@example.com")

    assert "ADMIN_INGESTION_GENERATION_POINTER_ENABLED" in str(raised.value)
    # Nothing reached the index at all.
    assert client.activated == []
    assert client.deleted == []


def test_the_publication_path_holds_no_branch_that_deletes_by_source(monkeypatch) -> None:
    """Defence in depth: the destructive branch is gone, not merely unreachable.

    The refusal is one guard, and a guard can be removed by someone who does
    not know what it protects. _older_source_actions - the call that selected
    "every section for this source with a different ingestion id" - is no
    longer in the reviewed publication path at all.
    """
    import inspect
    import re

    source = inspect.getsource(knowledge_ingestion._publish_activated_generation)
    # Comments and docstrings stripped. Both explain what was removed and why,
    # and matching the raw text finds the explanation rather than the code -
    # the same mistake that has now shown up in SQL, in a docstring, and here.
    code = "\n".join(re.sub(r"#.*$", "", line) for line in source.splitlines())
    code = re.sub(r'"""(?:.|\n)*?"""', "", code)

    assert "_older_source_actions" not in code
    assert "delete" not in code.lower()


def test_the_activation_path_refuses_the_unsupported_mode_on_its_own(monkeypatch) -> None:
    """If the entry guard is ever bypassed, this fails loudly rather than deleting."""
    _legacy(monkeypatch)

    with pytest.raises(RuntimeError) as raised:
        knowledge_ingestion._publish_activated_generation(
            job=dict(READY_JOB),
            job_id="job-1",
            first={"country": "DZ", "language": "fr", "sourceFile": "DZ-FR-Charges.pdf"},
            expected=2,
            documents=[{"id": "s1"}, {"id": "s2"}],
            logical_document_id="country:DZ:fr:policy:charges",
            accepted_by="reviewer@example.com",
            owner=OWNER,
        )

    assert "GENERATION_POINTER" in str(raised.value)


def test_ownership_is_checked_before_the_index_is_touched(monkeypatch) -> None:
    """Narrowing the window that cannot be closed.

    A stale worker still cannot be stopped mid-write, but it can be stopped
    before the first one. With the pointer enabled the sections it would have
    activated are invisible anyway, so what this really buys is that the index
    is not churned by a worker with no right to publish.
    """
    connection = _Connection(current_token="worker-b")
    monkeypatch.setattr(
        knowledge_ingestion.settings,
        "ADMIN_INGESTION_GENERATION_POINTER_ENABLED",
        True,
        raising=False,
    )
    monkeypatch.setattr(knowledge_ingestion, "get_engine", lambda: _engine(connection))
    client = _RecordingClient()
    monkeypatch.setattr(knowledge_ingestion, "_client", lambda: client)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("the index was touched by a worker that lost the job")

    monkeypatch.setattr(knowledge_ingestion, "_activate_staged_sections", _fail_if_called)

    with pytest.raises(OwnershipLost):
        knowledge_ingestion._publish_activated_generation(
            job=dict(READY_JOB),
            job_id="job-1",
            first={"country": "DZ", "language": "fr", "sourceFile": "DZ-FR-Charges.pdf"},
            expected=2,
            documents=[{"id": "s1"}, {"id": "s2"}],
            logical_document_id="country:DZ:fr:policy:charges",
            accepted_by="reviewer@example.com",
            owner=STALE,
        )


def test_the_index_check_is_not_claimed_to_be_transactional() -> None:
    """The claim that started this round was that a stale worker cannot write.

    It could: activation ran before any ownership check, and in legacy mode the
    deletion ran without one at all. The code now says what the check does and
    does not do, because the overstatement is what hid the hole.
    """
    import inspect

    source = inspect.getsource(knowledge_ingestion._publish_activated_generation)

    assert "cannot make the index write" in source
    assert "second system" in source


def test_the_document_level_check_runs_before_the_deployment_level_one() -> None:
    """A reviewer should hear about a contradiction whatever the mode is.

    Both refuse publication. Reporting the fact about the document first is
    more use than reporting a configuration flag to someone holding a document
    whose dates contradict each other.
    """
    import inspect

    source = inspect.getsource(knowledge_ingestion.publish_ingestion_job)

    assert source.index("_enforce_publication_gate") < source.index(
        "_require_supported_publication_mode"
    )


def test_the_refusal_explains_the_risk_rather_than_naming_a_flag() -> None:
    """Whoever hits this has to decide whether to enable the pointer."""
    import inspect

    source = inspect.getsource(knowledge_ingestion._require_supported_publication_mode)

    assert "stale worker can delete a newer version" in source


def test_automatic_publication_is_withheld_when_the_mode_is_unsafe(monkeypatch) -> None:
    """The remaining exposure, closed.

    Reviewed publication refuses the legacy mode. Automatic publication took
    the same destructive path and was only disclosed, not contained. It is now
    routed to review instead, which withholds ACTIVATION rather than ingestion.
    """
    monkeypatch.setattr(
        knowledge_ingestion.settings,
        "ADMIN_INGESTION_GENERATION_POINTER_ENABLED",
        False,
        raising=False,
    )

    assert knowledge_ingestion._automatic_publication_is_unsafe("job-1") is True


def test_automatic_publication_is_allowed_when_the_pointer_is_on(monkeypatch) -> None:
    """Containment must not become a blanket refusal of automatic ingestion."""
    monkeypatch.setattr(
        knowledge_ingestion.settings,
        "ADMIN_INGESTION_GENERATION_POINTER_ENABLED",
        True,
        raising=False,
    )

    assert knowledge_ingestion._automatic_publication_is_unsafe("job-1") is False


def test_the_indexing_path_holds_no_branch_that_deletes_by_source() -> None:
    """The destructive call is gone from the automatic path too.

    _older_source_actions selected every section for a source with a different
    ingestion id. It is no longer imported by this module at all, so neither
    publication path can reach it.
    """
    import inspect
    import re

    source = inspect.getsource(knowledge_ingestion._index_sections)
    code = "\n".join(re.sub(r"#.*$", "", line) for line in source.splitlines())
    code = re.sub(r'"""(?:.|\n)*?"""', "", code)

    assert "_older_source_actions" not in code
    assert "_older_source_actions" not in dir(knowledge_ingestion)


def _prose(function) -> str:
    """A docstring as one line, so an assertion is not defeated by wrapping.

    Prose assertions kept failing on where the line happened to break, which
    tests the formatter rather than the statement.
    """
    import inspect

    return " ".join((inspect.getdoc(function) or "").split())


def test_withholding_activation_is_not_withholding_ingestion() -> None:
    """The operational impact has to be the true one.

    An earlier note said restricting this path would block all automatic
    ingestion. It does not: the document is still uploaded, extracted, indexed
    as staging and queued for review. What is withheld is reaching readers.
    """
    prose = _prose(knowledge_ingestion._automatic_publication_is_unsafe)

    assert "queued for review" in prose
    assert "Nothing is lost" in prose


def test_the_operational_impact_of_a_disabled_pointer_is_stated() -> None:
    """With the flag off, nothing reaches readers by any route. Say so."""
    prose = _prose(knowledge_ingestion._automatic_publication_is_unsafe)

    assert "no document reaches readers by any route" in prose
