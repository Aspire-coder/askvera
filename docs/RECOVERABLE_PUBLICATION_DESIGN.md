# Recoverable publication — design

Local design note. Nothing here is applied, merged or deployed.

## What controls visibility

Established by reading the code, not assumed:

`_generation_filters` in `app/retrieval/opensearch_sections.py` restricts every
retrieval to `ingestion_id ∈ active_generation_ids(...)`, and
`active_generation_ids` reads the PostgreSQL table
`knowledge_active_generations`. So **when
`ADMIN_INGESTION_GENERATION_POINTER_ENABLED` is on, the database pointer is the
authority.** OpenSearch holds both the old and the new generation; the pointer
decides which one a reader can reach.

When the flag is off there is no generation filter, and visibility is whatever
is in the index — activation flips section status and older sections are then
deleted. That mode has no atomic commit point, and the design below says so
rather than pretending otherwise.

This is the existing mechanism. No second source of truth is introduced.

## Why the current ordering is already recoverable, with the pointer on

`publish_ingestion_job` activates staged sections and then moves the pointer.
That order matters more than it looks:

| Step | Reader sees |
|---|---|
| 1. Sections written, staged | nothing — not in the pointer |
| 2. `_activate_staged_sections` flips status | **still nothing** — not in the pointer |
| 3. Pointer row updated | the new generation, atomically |

Everything before step 3 is invisible, because the pointer has not moved. **The
pointer update is the commit point**, and it is a single-row database write.
There is no window in which half a generation is readable.

That is the property the recoverable design should preserve, not replace.

## States

Recorded on the job, alongside the review columns:

| State | Meaning | Retry does |
|---|---|---|
| `not_started` | no attempt | begin one |
| `in_progress` | attempt began, outcome unknown | **inspect the pointer**, then finish or fail |
| `succeeded` | pointer names this ingestion id | nothing; already published |
| `failed_recoverable` | attempt ended before the pointer moved | begin a new attempt |

`in_progress` is the only interesting one. A worker that dies between steps 2
and 3 leaves it set, and the next attempt must **read the pointer to find out
what actually happened** rather than assume the exception meant failure. That is
the whole point of item 5 in the brief: an exception is not evidence that
activation did not occur — a timeout on the response says nothing about whether
the write landed.

## Idempotency

The attempt is keyed by `(job_id, review_revision)`. A duplicate publication
request for a revision already `succeeded` is a no-op returning the existing
result, not a second activation. Because the key includes the revision, a
metadata edit produces a different key, so a retry after an edit cannot
complete an attempt that was authorised for different content.

## Concurrency

Publication takes a conditional update on the job row:

```
UPDATE ingestion_jobs
   SET publication_state = 'in_progress', publication_attempt = :attempt
 WHERE job_id = :job_id
   AND review_revision = :revision
   AND publication_state IN ('not_started', 'failed_recoverable')
```

Zero rows updated means someone else is publishing, or the revision moved under
us. Either way this attempt stops. A metadata edit racing with publication
changes `review_revision`, so the `WHERE` no longer matches and the edit wins —
which is the safe direction, because the alternative publishes content a
reviewer approved in a different form.

## Failure points, and what each leaves behind

| Failure | Left behind | Recovery |
|---|---|---|
| Before activation | staged sections, no pointer change | nothing visible; retry |
| Between activation and pointer | active sections, old pointer | **nothing visible**; retry is safe |
| After pointer, before recording | new generation live, state `in_progress` | retry reads the pointer, records success |
| Concurrent metadata edit | revision changed | conditional update matches nothing; attempt abandoned |
| Duplicate request | — | second request sees `succeeded`, returns |
| Worker restart | state `in_progress` | recovery reads the pointer, not the exception |

## Unresolved, and it changes publication policy

**With the generation pointer disabled there is no commit point.** Activation
flips status and deletes the previous generation's sections, so a failure
between those can leave a market with both generations or with content removed
and nothing to replace it.

Two options, and this is a decision rather than a technical choice:

1. Require the pointer for publication — refuse to publish when the flag is off.
   Safe, and it makes a configuration flag load-bearing for correctness.
2. Accept the window when the flag is off, and record it.

I have not chosen. The implementation guards the pointer-enabled path and
reports the other as unprotected, so the gap is visible rather than silently
carried.

## Corrections to earlier statements

**Two environment variables reduce accidental targeting; they do not prevent
someone supplying the wrong values.** Both can be set to a real database by
someone who believes it is disposable. The refusal check on the configured RDS
host narrows it further and is still not a guarantee — it only recognises the
database this application knows about, not every database that matters.

**Contradiction enforcement is implemented and its API-boundary test is
pending.** `evaluate_publication` collects contradiction reasons before it
consults any resolution, so a submitted approval cannot reach them. That is a
property of the control flow, verified at the service level and not yet at the
boundary where a reviewer's approval actually arrives.
