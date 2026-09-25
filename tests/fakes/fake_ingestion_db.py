"""Minimal in-memory relational fake for the ingestion pointer/job tables.

Dispatches on SQL text substrings, the same way the small ad hoc MagicMock
fakes elsewhere in tests/unit stub the DB, but keeps real state so the
generation-pointer tests can run production code end-to-end (write -> await
-> activate -> publish -> rollback -> delete) without hand-crafting a
distinct mock return value for every call in the sequence.

Covers exactly the statements issued by services/knowledge_ingestion.py and
scripts/backfill_active_generation_pointers.py against:
- ingestion_jobs
- knowledge_active_generations
- knowledge_document_generations
- knowledge_documents
"""
from __future__ import annotations

from typing import Any


class _Result:
    def __init__(self, rows: list[Any] | None = None, scalar_value: Any = None, rowcount: int = 0) -> None:
        self._rows = rows if rows is not None else []
        self._scalar = scalar_value
        self.rowcount = rowcount

    def scalar(self) -> Any:
        return self._scalar

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return self._rows

    def mappings(self) -> "_Result":
        return self


class _FakeConn:
    def __init__(self, db: "FakeIngestionDB") -> None:
        self.db = db

    def __enter__(self) -> "_FakeConn":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Result:
        sql = " ".join(str(statement).split())
        p = dict(params or {})
        for handler in (self._jobs, self._generations, self._documents):
            result = handler(sql, p)
            if result is not None:
                return result
        raise AssertionError(f"FakeIngestionDB: unhandled SQL: {sql}")

    def _jobs(self, sql: str, p: dict[str, Any]) -> _Result | None:
        db = self.db
        if sql.startswith("INSERT INTO ingestion_jobs"):
            db.jobs.setdefault(p["job_id"], self._new_job(p))
            return _Result()

        if "UPDATE ingestion_jobs" in sql and "RETURNING job_id" in sql:
            return self._claim_job(db, p)

        if sql.startswith("SELECT attempt_count FROM ingestion_jobs"):
            job = db.jobs.get(p["job_id"])
            return _Result(scalar_value=job.get("attempt_count") if job else None)

        if sql.startswith("SELECT status, attempt_count"):
            job = db.jobs.get(p["job_id"])
            return _Result(rows=[dict(job)] if job else [])

        if "SET status = 'failed_terminal'" in sql:
            job = db.jobs.get(p["job_id"])
            if job is not None:
                job.update(status="failed_terminal", lease_owner="", lease_expires_at=None)
            return _Result()

        if "SET status = 'deleting'" in sql:
            job = db.jobs.get(p["job_id"])
            if job is not None:
                job.update(status="deleting", progress=10, error_message="")
            return _Result()

        if sql.startswith("UPDATE ingestion_jobs"):
            job = db.jobs.setdefault(p["job_id"], self._new_job({"job_id": p["job_id"]}))
            job.update({key: value for key, value in p.items() if key != "job_id"})
            return _Result()

        if sql.startswith("SELECT job_id FROM ingestion_jobs"):
            rows = [(job_id,) for job_id, job in db.jobs.items() if job["status"] != "ready"]
            return _Result(rows=rows)

        if sql.startswith("SELECT job_id, filename"):
            limit = p.get("limit", 200)
            rows = sorted(db.jobs.values(), key=lambda j: j.get("job_id", ""))[:limit]
            return _Result(rows=[dict(row) for row in rows])

        return None

    @staticmethod
    def _claim_job(db: "FakeIngestionDB", p: dict[str, Any]) -> _Result:
        job = db.jobs.get(p["job_id"])
        excluded = {
            "ready", "completed", "cancelled", "failed_terminal", "dead_lettered",
            "ready_for_review", "deleting", "deleted", "deletion_failed",
        }
        eligible = (
            job is not None
            and job["status"] not in excluded
            and job.get("attempt_count", 0) < p["max_attempts"]
            and not job.get("lease_owner")
        )
        if eligible:
            job["lease_owner"] = p["worker_id"]
            job["attempt_count"] = job.get("attempt_count", 0) + 1
            job["status"] = "extracting"
            return _Result(rows=[{"job_id": job["job_id"]}])
        return _Result(rows=[])

    def _generations(self, sql: str, p: dict[str, Any]) -> _Result | None:
        db = self.db
        if "pg_advisory_xact_lock" in sql:
            return _Result()

        if sql.startswith("SELECT active_ingestion_id"):
            row = db.active_generations.get(p["logical_document_id"])
            return _Result(scalar_value=row["active_ingestion_id"] if row else None)

        if sql.startswith("SELECT logical_document_id, active_ingestion_id"):
            rows = [
                (logical_id, row["active_ingestion_id"])
                for logical_id, row in db.active_generations.items()
            ]
            return _Result(rows=rows)

        if sql.startswith("SELECT country, language, document_type, access_scope"):
            rows = [
                {
                    "country": row["country"],
                    "language": row["language"],
                    "document_type": row["document_type"],
                    "access_scope": row["access_scope"],
                    "active_ingestion_id": row["active_ingestion_id"],
                }
                for row in db.active_generations.values()
                if row["active_ingestion_id"]
            ]
            return _Result(rows=rows)

        if sql.startswith("UPDATE knowledge_document_generations"):
            return self._update_generation(db, sql, p)

        if sql.startswith("INSERT INTO knowledge_active_generations"):
            self._upsert_active_pointer(db, p)
            return _Result()

        if sql.startswith("UPDATE knowledge_active_generations"):
            row = db.active_generations.get(p["logical_document_id"])
            if row is not None:
                row["previous_ingestion_id"] = row["active_ingestion_id"]
                row["active_ingestion_id"] = p["target"]
                row["activated_by"] = p["actor"]
            return _Result()

        if sql.startswith("DELETE FROM knowledge_active_generations"):
            db.active_generations.pop(p["logical_document_id"], None)
            return _Result()

        if sql.startswith("INSERT INTO knowledge_document_generations"):
            db.document_generations[p["ingestion_id"]] = {
                "ingestion_id": p["ingestion_id"],
                "logical_document_id": p["logical_document_id"],
                "country": p["country"],
                "language": p["language"],
                "source_file": p["source_file"],
                "document_type": p["document_type"],
                "access_scope": p["access_scope"],
                "status": "active",
                "activated_at": None,
                "retired_at": None,
                "activated_by": p["activated_by"],
            }
            return _Result()

        if sql.startswith("SELECT g.ingestion_id"):
            return _Result(rows=self._document_generation_rows(db, p["logical_document_id"]))

        return None

    @staticmethod
    def _update_generation(db: "FakeIngestionDB", sql: str, p: dict[str, Any]) -> _Result:
        if "'retired'" in sql:
            key = "current" if "ingestion_id = :current" in sql else "ingestion_id"
            gen = db.document_generations.get(p[key])
            if gen is not None:
                gen["status"] = "retired"
                gen["retired_at"] = None
        elif "'active'" in sql:
            gen = db.document_generations.get(p["target"])
            if gen is not None:
                gen["status"] = "active"
                gen["retired_at"] = None
                gen["activated_by"] = p["actor"]
        elif "'deleted'" in sql:
            gen = db.document_generations.get(p["job_id"])
            if gen is not None:
                gen["status"] = "deleted"
                gen.setdefault("retired_at", None)
        return _Result()

    @staticmethod
    def _upsert_active_pointer(db: "FakeIngestionDB", p: dict[str, Any]) -> None:
        existing = db.active_generations.get(p["logical_document_id"])
        db.active_generations[p["logical_document_id"]] = {
            "logical_document_id": p["logical_document_id"],
            "country": p["country"],
            "language": p["language"],
            "source_file": p["source_file"],
            "document_type": p["document_type"],
            "access_scope": p["access_scope"],
            "previous_ingestion_id": existing["active_ingestion_id"] if existing else "",
            "active_ingestion_id": p["ingestion_id"],
            "activated_by": p["activated_by"],
        }

    @staticmethod
    def _document_generation_rows(db: "FakeIngestionDB", logical_document_id: str) -> list[dict[str, Any]]:
        rows = []
        for gen in db.document_generations.values():
            if gen["logical_document_id"] != logical_document_id or gen["status"] == "deleted":
                continue
            job = db.jobs.get(gen["ingestion_id"])
            rows.append(
                {
                    "ingestion_id": gen["ingestion_id"],
                    "status": gen["status"],
                    "activated_at": gen.get("activated_at"),
                    "retired_at": gen.get("retired_at"),
                    "activated_by": gen.get("activated_by"),
                    "filename": job.get("filename") if job else None,
                    "document_version": job.get("document_version") if job else None,
                    "section_count": job.get("section_count") if job else None,
                    "effective_date": job.get("effective_date") if job else None,
                    "expiry_date": job.get("expiry_date") if job else None,
                    "malware_scan_status": job.get("malware_scan_status") if job else None,
                    "created_at": job.get("created_at") if job else None,
                }
            )
        return rows

    def _documents(self, sql: str, p: dict[str, Any]) -> _Result | None:
        db = self.db
        if sql.startswith("UPDATE knowledge_documents"):
            if "document_id <> :new_document_id" in sql:
                self._retire_other_logical_rows(db, p)
            elif "document_id = :document_id" in sql:
                doc = db.documents.get(p["document_id"])
                if doc is not None and doc.get("status") == "active":
                    doc["status"] = "retired"
            elif "CASE WHEN document_id" in sql:
                for doc in db.documents.values():
                    if doc.get("logical_document_id") == p["logical_document_id"]:
                        doc["status"] = "active" if doc["document_id"] == p["target"] else "retired"
            elif "status = 'deleted'" in sql:
                doc = db.documents.get(p["job_id"])
                if doc is not None:
                    doc["status"] = "deleted"
            return _Result()

        if sql.startswith("INSERT INTO knowledge_documents"):
            db.documents[p["job_id"]] = {**p, "document_id": p["job_id"], "status": "active"}
            return _Result()

        return None

    @staticmethod
    def _retire_other_logical_rows(db: "FakeIngestionDB", p: dict[str, Any]) -> None:
        """WHERE logical_document_id = :l AND document_id <> :new AND status = 'active'."""
        for doc in db.documents.values():
            if (
                doc.get("logical_document_id") == p["logical_document_id"]
                and doc["document_id"] != p["new_document_id"]
                and doc.get("status") == "active"
            ):
                doc["status"] = "retired"

    @staticmethod
    def _new_job(p: dict[str, Any]) -> dict[str, Any]:
        return {
            "job_id": p["job_id"],
            "filename": p.get("filename", ""),
            "country": p.get("country", ""),
            "language": p.get("language", ""),
            "document_type": p.get("document_type", ""),
            "access_scope": p.get("access_scope", ""),
            "document_version": p.get("document_version", ""),
            "content_hash": p.get("content_hash", ""),
            "accepted_by": p.get("accepted_by", ""),
            "logical_document_id": p.get("logical_document_id", ""),
            "document_owner": p.get("document_owner", ""),
            "approval_reference": p.get("approval_reference", ""),
            "review_before_publish": p.get("review_before_publish", False),
            "effective_date": p.get("effective_date") or None,
            "expiry_date": p.get("expiry_date") or None,
            "malware_scan_status": p.get("malware_scan_status", ""),
            "status": "queued",
            "progress": 0,
            "section_count": 0,
            "source_uri": "",
            "upload_uri": "",
            "attempt_count": 0,
            "error_message": "",
            "lease_owner": "",
            "lease_expires_at": None,
            "completed_at": None,
            "created_at": None,
            "updated_at": None,
        }


class FakeIngestionDB:
    """Stands in for `get_engine()`: `.begin()` and `.connect()` both hand out
    the same live connection, since sqlite-style isolation is not needed for
    these single-threaded tests."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.active_generations: dict[str, dict[str, Any]] = {}
        self.document_generations: dict[str, dict[str, Any]] = {}
        self.documents: dict[str, dict[str, Any]] = {}

    def begin(self) -> _FakeConn:
        return _FakeConn(self)

    def connect(self) -> _FakeConn:
        return _FakeConn(self)

    def seed_job(self, job_id: str, **fields: Any) -> None:
        job = self.jobs.setdefault(job_id, _FakeConn._new_job({"job_id": job_id}))
        job.update(fields)
