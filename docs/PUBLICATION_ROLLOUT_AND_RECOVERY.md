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

## One supported publication mode

Reviewed publication **requires** `ADMIN_INGESTION_GENERATION_POINTER_ENABLED`.
It refuses otherwise, and that is a deployment prerequisite: the flag defaults
to false, so somebody has to set it before any document can be published
through the review workflow.

Why it is refused rather than protected. Without the pointer, publishing is
activate-then-delete against OpenSearch: flip the new sections to active, then
delete every section for that source carrying a different ingestion id. Both
writes are reader-visible immediately, and neither can join the ownership
transaction, because OpenSearch is a second system and no check spanning the
two is atomic.

The failure that makes this unacceptable: a worker paused before those writes,
whose lease expires and whose job is republished by someone else, resumes and
deletes the newer generation - "a different ingestion id" is exactly what the
newer one is - then reinstates its own stale content. Verification would report
that afterwards, having already lost the live document. Detecting a bad outcome
is not preventing it.

**The automatic path is contained too.** `process_ingestion_job` performed the
same legacy replacement when `review_before_publish` was false. It now forces
review instead, so no document activates automatically in that mode. An earlier
version of this note said restricting it would block all automatic ingestion:
that was wrong. It withholds **activation**, not ingestion - the document is
still uploaded, extracted, indexed as staging and queued for review.

**Operational impact, stated precisely.** With
`ADMIN_INGESTION_GENERATION_POINTER_ENABLED` off, **new** publication is
withheld: uploads work, extraction works, review works, and nothing new
activates by either route.

**Documents already published stay published.** Nothing here retires,
deletes or hides existing content, and with the pointer disabled retrieval
applies no generation filter at all - so what readers can already reach is
exactly what they could reach before. What is withheld is a *new* version
becoming visible, which means a market can sit on a superseded document until
the flag is enabled. That is a staleness risk, not an availability one, and it
is the reason to enable the pointer promptly rather than to leave it off.

Enabling it restores publication on both paths and is the intended fix - a
deployment change nobody in this repository can make.

The destructive call itself, `_older_source_actions`, is no longer imported by
`services/knowledge_ingestion.py` at all, so neither path can reach it.

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

Every write that decides what a reader sees, or what the portal shows, checks
ownership **inside its own transaction**, with `SELECT ... FOR UPDATE` on the
job row:

- the generation pointer update, before it takes the advisory lock;
- finalization - the document record and the job status - as one transaction.

Ownership is also checked before the index is touched. That one is **not**
transactional and is not claimed to be: OpenSearch is a second system. It stops
a worker that has already lost the job before it activates sections, and with
the pointer on those sections would have been invisible anyway.

An advisory lock alone was not enough and the reasoning that it was is the
defect this closed. It serialises writers. A worker whose lease expired takes
it perfectly legitimately and then writes stale state.

**The residual risk, stated plainly.** A worker alive but stuck past its lease
can be taken over while still running, and both could then reach activation. It
can no longer write anything afterwards - the ownership check refuses it and
raises `OwnershipLost` - so what remains is that its activation work may be
redone. Raising `LEASE_SECONDS` trades recovery latency for a smaller window.

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
is on. With it off there is no pointer, and publishing is a two-step replacement
rather than a switch: activate the new sections, then delete the old. Counting
the new sections proves they exist and not that the replacement finished, so
verification requires both halves — the expected number of new sections
reachable, and no reachable section of any older generation for the same source
file. A failure between the two steps is therefore reported rather than
recorded as success.

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

## The grounding changes reach production by two different routes

Carrying a table's currency heading onto its continuation chunks happens **at
ingestion**. Documents already in the index keep the chunking they were
ingested with, so it reaches them only on re-ingestion.

Unit attribution is **validation**, so it applies to every answer from the next
deploy, over chunks that were never shaped for it — and it is stricter than
what it replaced. A figure whose unit is neither beside it, nor stated in its
row, nor given by a heading or footer covering that row, no longer supports a
claim naming a unit. Expect more removals on documents that state a currency
far from the figures it governs, until those are re-ingested.

`tests/unit/test_existing_index_units.py` runs verbatim corpus excerpts and
shows the claims that dominate the real text still ground, because this corpus
writes the unit beside the figure. That is evidence, not a measurement of live
answers; the candidate comparison is what would measure it.

## Still open

- The combined candidate comparison against the live pipeline (needs
  approval). Prepared in `docs/GROUNDING_COMPARISON_PLAN.md` and
  `scripts/run_grounding_comparison.py`; not run.
- Enabling `ADMIN_INGESTION_GENERATION_POINTER_ENABLED`, which is now a
  prerequisite for publishing at all.
- The append-only grant.
- Whether 300 characters is the right unit lookback for real layouts.
