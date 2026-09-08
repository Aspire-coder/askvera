# Publication: rollout and recovery

Written for whoever is holding this when something goes wrong.

## Before this ships

**Cleared.** The migrations have been executed. All 14 checks in
`tests/integration/test_review_migration_postgres.py` pass against PostgreSQL
16 (`postgres:16-alpine`, throwaway container), including the concurrency ones.
That says nothing about the production RDS instance — different major version,
different extensions, different existing data — so the first application to a
non-throwaway database is still the first application to that database.

Running them found a defect in the harness rather than the migrations: it split
each file on `;` and ran the pieces through `sqlalchemy.text()`, which read the
`:1` inside a JSON example in a `COMMENT` as a bind parameter. The deploy does
neither — `run_db_migrations` uses `exec_driver_sql` on the whole file. The
harness now applies migrations the same way.

**Required, not assumed.** `ingestion_review_decisions` is append-only in the
application — no code issues an UPDATE or DELETE against it, and there is a
test that keeps it that way. That is one layer. The other is the database
grant: if the application role holds UPDATE and DELETE on that table, a bug, a
migration or a console session can still rewrite the record. Revoking them is
an infrastructure change nobody in this repository can make, and it has not
been made.

**Not yet run.** The combined candidate comparison — canary and benchmark
against the live pipeline. It needs paid model calls and separate approval.

## How ownership works

Three separate things, and conflating any two of them was a defect:

| | |
|---|---|
| `publication_idempotency_key` | `job_id:revision`. Is this the same logical publication? |
| `publication_attempt_key` | A fresh uuid per attempt. The fencing token. |
| `publication_lease_expires_at` | When this attempt may be taken over. |

A second request may take over an attempt **only** when the lease has expired,
and it does so by swapping the token — so of two simultaneous recoveries,
exactly one wins. Every later write is conditioned on the token, so a worker
that lost its lease updates nothing.

**The residual risk, stated plainly.** A worker that is alive but stuck past
its lease can be taken over while still running, and both could then reach
activation. What that cannot corrupt: the pointer update takes a PostgreSQL
advisory lock and is a single row write, so the outcome is one pointer value,
not a mixture; and only the current token holder can record an outcome. What it
does mean is that a stuck worker's activation work may be redone. Raising
`LEASE_SECONDS` trades recovery latency for a smaller window.

## Order of operations

The deploy applies migrations before restarting the application, which is the
order this needs: `_update_job` writes `review_revision`, `review_findings` and
`review_evaluated_at` in the same statement that sets `ready_for_review`, and
those columns must exist first. If they do not, the update fails, the exception
is swallowed by `_update_job`, and the job stays in `indexing` rather than
becoming reviewable. That fails safe — nothing publishes — but it looks like a
stuck worker.

## Reading the state of a stuck publication

```sql
SELECT job_id, status, publication_state, publication_detail,
       publication_attempt_key, publication_lease_expires_at,
       publication_attempted_at, publication_settled_at, review_revision
FROM ingestion_jobs
WHERE publication_state <> 'not_started'
ORDER BY publication_attempted_at DESC;
```

| `publication_state` | What happened | What to do |
|---|---|---|
| `in_progress`, lease in the future | A worker is running now. | Wait. |
| `in_progress`, lease past | The worker is gone or stuck. | Retry the publish; it takes over and works out what was achieved. |
| `failed_recoverable` | Ended without completing. | Fix the cause, retry. |
| `succeeded` | Live, verified, and fully finalized. | Nothing. |

`succeeded` means finished, not activated. It is written after the document
record and the job status, so a job in that state needs no follow-up. There is
no "succeeded but unverified" — an outcome that cannot be verified is never
recorded as success.

**Do not** clear `in_progress` by hand to "unstick" a job. That is the
information recovery depends on, and it is what stops a retry assuming an
outcome. Retrying is safe; editing the row is not.

## What is live, according to the authority

```sql
SELECT logical_document_id, active_ingestion_id, previous_ingestion_id, activated_at
FROM knowledge_active_generations
WHERE logical_document_id = '<slot>';
```

This is what retrieval filters on when `ADMIN_INGESTION_GENERATION_POINTER_ENABLED`
is on. With it off there is no pointer, and visibility is the index itself —
publication then verifies by counting active sections for the ingestion id and
comparing to the expected count. Both deployments verify; they verify different
things.

Note the lag: `active_generation_ids` caches for 15 seconds per process, so a
freshly published document can take that long to appear in a given worker.
`clear_active_generation_cache()` runs at the end of a successful publication in
the process that published — not in the others.

## Rolling back

Rollback is the existing `rollback_document_generation` path, unchanged. Because
the pointer is the authority, it takes effect without touching the index.

## What a retry does not do

A retry does not republish a document that is already live and finalized. It
does not proceed while another attempt's lease is live. It does not proceed
after a metadata edit — the revision changed, so the approval no longer
describes the document, and it returns 409.

## The grounding fixes need re-ingestion

Carrying a table's currency heading onto its continuation chunks happens **at
ingestion**. Documents already in the index keep the chunking they were
ingested with, so the defect it fixes persists for them until they are
re-ingested. The other half — rejecting a unit that never precedes the figure —
is validation and applies immediately to every answer.

## Still open

- The combined candidate comparison against the live pipeline (needs approval).
- The append-only grant.
- Whether 300 characters is the right unit lookback for real layouts.
