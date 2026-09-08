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


# --- replacement, when there is no generation pointer ----------------------


def _clause_field_and_values(clause: dict):
    """Read one filter clause, in any of the shapes the code actually builds.

    exact_term_query wraps its term in a bool/should over the keyword and
    text.keyword paths, so a fake that only understands {"term": {...}} matches
    nothing and every assertion passes or fails for the wrong reason.
    """
    if "term" in clause:
        field, value = next(iter(clause["term"].items()))
        return field.split(".")[0], {value}
    if "terms" in clause:
        field, values = next(iter(clause["terms"].items()))
        return field.split(".")[0], set(values)
    if "bool" in clause:
        values = set()
        field = ""
        for should in clause["bool"].get("should", []):
            path, value = next(iter(should["term"].items()))
            field = path.split(".")[0]
            values.add(value)
        return field, values
    raise AssertionError(f"unrecognised clause: {clause}")


class _FakeSearchClient:
    """Counts documents the way OpenSearch would, from a small fixture."""

    def __init__(self, sections):
        self.sections = sections
        self.indices = self

    def refresh(self, index):
        return None

    def count(self, index, body):
        clauses = body["query"]["bool"]["filter"]
        must_not = body["query"]["bool"].get("must_not", [])
        required = [_clause_field_and_values(clause) for clause in clauses]
        excluded = [_clause_field_and_values(clause) for clause in must_not]

        total = 0
        for section in self.sections:
            if any(section.get(field) not in values for field, values in required):
                continue
            if any(section.get(field) in values for field, values in excluded):
                continue
            total += 1
        return {"count": total}


IDENTITY = {"country": "DZ", "language": "fr", "source_file": "DZ-FR-Charges.pdf"}


def _section(ingestion_id: str, status: str) -> dict:
    return {**IDENTITY, "ingestion_id": ingestion_id, "status": status}


def _use_index(monkeypatch, sections, *, pointer_enabled: bool = False) -> None:
    monkeypatch.setattr(
        knowledge_ingestion.settings,
        "ADMIN_INGESTION_GENERATION_POINTER_ENABLED",
        pointer_enabled,
        raising=False,
    )
    monkeypatch.setattr(
        knowledge_ingestion, "_client", lambda: _FakeSearchClient(sections)
    )


def _verifier(monkeypatch, sections):
    _use_index(monkeypatch, sections)
    return knowledge_ingestion._visibility_verifier("new-job", 2, **IDENTITY)


def test_replacement_is_incomplete_while_the_old_generation_is_still_reachable(
    monkeypatch,
) -> None:
    """Finding 2. The new sections existing is not the outcome that matters.

    Activated new sections, old ones not yet deleted: a reader matches both
    versions of the same document. Counting the new ones alone reports success
    for exactly this state.
    """
    verify = _verifier(
        monkeypatch,
        [
            _section("new-job", "active"),
            _section("new-job", "active"),
            _section("old-job", "active"),
        ],
    )

    assert verify() is False


def test_replacement_is_complete_once_the_old_generation_is_gone(monkeypatch) -> None:
    verify = _verifier(
        monkeypatch, [_section("new-job", "active"), _section("new-job", "active")]
    )

    assert verify() is True


def test_a_staged_remnant_of_an_older_generation_also_counts_as_incomplete(
    monkeypatch,
) -> None:
    """Staging documents are not retrievable, but they are the residue of a
    half-finished replacement and the deletion pass is meant to remove them."""
    verify = _verifier(
        monkeypatch,
        [
            _section("new-job", "active"),
            _section("new-job", "active"),
            _section("old-job", "staging"),
        ],
    )

    assert verify() is False


def test_a_short_new_generation_is_not_complete_either(monkeypatch) -> None:
    """Both halves are required, not either."""
    verify = _verifier(monkeypatch, [_section("new-job", "active")])

    assert verify() is False


def test_another_document_in_the_same_market_is_not_mistaken_for_a_remnant(
    monkeypatch,
) -> None:
    """The check is scoped to one source file. Without that every market with
    more than one document would look permanently half-published."""
    other = {
        "country": "DZ",
        "language": "fr",
        "source_file": "DZ-FR-Directory.pdf",
        "ingestion_id": "other-job",
        "status": "active",
    }
    verify = _verifier(
        monkeypatch,
        [_section("new-job", "active"), _section("new-job", "active"), other],
    )

    assert verify() is True


def test_with_the_pointer_enabled_no_index_verifier_is_used(monkeypatch) -> None:
    """The pointer moves atomically, so there is no partial state to check for.

    Returning None here is what makes the attempt store read the pointer.
    """
    _use_index(monkeypatch, [], pointer_enabled=True)

    assert knowledge_ingestion._visibility_verifier("new-job", 2, **IDENTITY) is None
