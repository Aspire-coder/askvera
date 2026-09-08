# Publication: rollout and recovery

Written before deployment, for whoever is holding this when something goes
wrong. Nothing here has been executed against a real database.

## Before this ships

**Blocker.** `tests/integration/test_review_migration_postgres.py` has never
run. Five checks are skipped, so nothing establishes that PostgreSQL accepts
either migration, that they are repeatable, or that the running version keeps
working while they land. Reading SQL is not running it. This stays a release
blocker.

**Required, not assumed.** `ingestion_review_decisions` is append-only in the
application - no code issues an UPDATE or DELETE against it, and there is a
test that keeps it that way. That is one layer. The other is the database
grant: if the application role holds UPDATE and DELETE on that table, a bug, a
migration or a console session can still rewrite the record. Revoking them is
an infrastructure change nobody in this repository can make, and it has not
been made.

**Decide.** With `ADMIN_INGESTION_GENERATION_POINTER_ENABLED` off, publication
has no commit point (see the design note). Either require the pointer for
publication or accept the window knowingly. Currently the code records the
unprotected case as `succeeded` with detail saying visibility is unverified,
which makes the gap visible without choosing for you.

## Order of operations

The deploy script applies migrations before restarting the application, which
is the order this needs: `_update_job` writes `review_revision`,
`review_findings` and `review_evaluated_at` in the same statement that sets
`ready_for_review`, and those columns must exist first. If they do not, the
update fails, the exception is swallowed by `_update_job`, and the job stays in
`indexing` rather than becoming reviewable. That fails safe - nothing publishes
- but it looks like a stuck worker, so it is worth knowing.

## Reading the state of a stuck publication

```sql
SELECT job_id, status, publication_state, publication_detail,
       publication_attempted_at, publication_settled_at, review_revision
FROM ingestion_jobs
WHERE publication_state <> 'not_started'
ORDER BY publication_attempted_at DESC;
```

| `publication_state` | What happened | What to do |
|---|---|---|
| `in_progress` | Unknown. A worker began and did not finish. | Retry the publish. It reads the pointer and works out which. |
| `failed_recoverable` | Ended before the pointer moved. Nothing is visible. | Fix the cause, retry. |
| `succeeded`, detail `pointer confirmed` | Live, and verified live. | Nothing. |
| `succeeded`, detail begins `recovered:` | Live. A previous attempt died after publishing. | Nothing. |
| `succeeded`, detail says `unverified` | Published with the pointer disabled. Visibility was never confirmed. | Check the index directly. |

**Do not** clear `in_progress` by hand to "unstick" a job. That is the one
piece of information recovery has, and it is what stops a retry assuming an
outcome. Retrying is safe; editing the row is not.

## What is live, according to the authority

```sql
SELECT logical_document_id, active_ingestion_id, previous_ingestion_id, activated_at
FROM knowledge_active_generations
WHERE logical_document_id = '<slot>';
```

This table is what retrieval filters on when the pointer is enabled. The
OpenSearch document status does not decide what a reader can reach.

Note the lag: `active_generation_ids` caches for 15 seconds in each process, so
a freshly published document can take that long to appear, per worker.
`clear_active_generation_cache()` runs at the end of a successful publication in
the process that published - not in the others. A document that looks missing
immediately after publication has not necessarily failed.

## Rolling back

Rollback is the existing `rollback_document_generation` path, unchanged: point
the slot at the previous generation. Because the pointer is the authority, that
takes effect without touching the index.

## What a retry does not do

A retry does not republish a document that is already live: `begin()` sees the
pointer naming this ingestion id and settles the record instead of activating
anything. A retry after a metadata edit does not proceed at all - the revision
changed, so the approval no longer describes the document, and it returns 409.

## Still open

- PostgreSQL execution of both migrations (blocker, above).
- Whether the conditional claim actually serialises two live workers. It is
  written as a single conditional UPDATE, which is the right shape; the
  behaviour is a database property and is untested.
- The portal has no view of findings, decision history, or affected pages yet.
  The endpoint accepts a reason and records the decision; the interface that
  shows a reviewer what they are deciding about does not exist.
