# V2-10 runtime capture provenance contract

Date: 2026-09-18

## Decision

**Experimental diagnostic capture only.** This change is not retrieval
promotion, a model run, a deployment, or a change to the frozen evaluation
pack. It records the actual decisions that a later offline V2 replay needs in
order to fail closed rather than reconstructing intent from a question or a
test label.

## Contract

`retrieval_rank_lists` remains version `1`. The three fields below are
optional for backward compatibility. A legacy record may omit them or contain
`null`; an offline replay must then treat policy authorization, global-record
protection, and follow-up continuity as unavailable rather than guessing.

| Field | Exact accepted shape | Runtime origin | Fail-closed behavior |
| --- | --- | --- | --- |
| `runtime_scope_intent` | `{"provenance":"runtime","intent":<closed enum>,"decision_source":<closed enum>}` | `RetrievalQueryPlan`, after the real query planner and deterministic scope backstops have run | Anything absent, malformed, or not explicitly directory-compatible cannot protect a global record. |
| `authorized_policy_market` | `null` or an uppercase ASCII two-letter code | The request country accepted by the retrieval-plan boundary | `null` means country-policy candidates are ineligible. Replay never substitutes the case country. |
| `context_resolution` | `{"provenance":"runtime","status":<closed enum>}`; only `resolved_dependent_follow_up` may add nonempty `prior_user_turn_id` | The orchestrator's real history-resolution path, immediately before retrieval | Missing, unresolved, or malformed context cannot activate the continuity fallback. |

Every non-null record is strict: unexpected keys, a mismatched intent/source
pair, an untrusted provenance label, or a malformed turn ID is rejected at
conversion, direct replay, and direct fusion boundaries.

### Closed scope-intent enum

- `policy`
- `directory`
- `international_sponsoring`
- `ambiguous`
- `unknown`

Only these exact pairs are accepted:

| Intent | Allowed decision source | V2 global protection |
| --- | --- | --- |
| `policy` | `deterministic_policy_route`, `deterministic_policy_safety_route`, `local_policy_only` | never |
| `directory` | `deterministic_directory_route` | at most one matching global record |
| `international_sponsoring` | `deterministic_sponsoring_route` | at most one matching global record |
| `ambiguous` | `planner_global_scope_only` | never |
| `unknown` | `planner_disabled`, `planner_unavailable` | never |

A named market or shared-office alias may still retain the existing global
search behavior, but it is recorded as `ambiguous` unless the runtime also
fired one of the deterministic directory routes. This prevents country-named
policy questions from becoming trusted directory requests.

### Closed decision-source enum

- `deterministic_policy_route`
- `deterministic_policy_safety_route`
- `deterministic_sponsoring_route`
- `deterministic_directory_route`
- `local_policy_only`
- `planner_global_scope_only`
- `planner_disabled`
- `planner_unavailable`

The model planner's bare global-document suggestion is recorded as
`ambiguous` plus `planner_global_scope_only`; it is observable but never
trusted for V2 protection.

### Closed context-resolution status enum

- `not_dependent`
- `resolved_dependent_follow_up`
- `unresolved`
- `unknown`

When the orchestrator genuinely carries a selected prior question into the
retrieval query, it derives an opaque `history-user-...` identifier from the
actual session ID, selected compact-history position, and selected prior user
message. The capture never includes that message itself. A prior-turn ID is
emitted only in this resolved state and must match
`history-user-[1-9][0-9]*-[0-9a-f]{16}`. The resolved record must have exactly
`provenance`, `status`, and `prior_user_turn_id`; every other status must have
exactly `provenance` and `status`.

## Flow

```text
request country + runtime planner/backstops
  -> RetrievalQueryPlan(runtime_scope_intent, authorized_policy_market)
orchestrator actually resolves a dependent follow-up
  -> context_resolution(status, opaque prior_user_turn_id)
rank-list diagnostic capture
  -> retrieval_rank_lists
offline converter
  -> copied fields, with no inference
scope-aware replay
  -> accepts only trusted, explicitly recorded fields
```

## Existing-runtime limitation

The stored session transcript has no durable per-turn database identifier; it
contains compact `user:` and `vera:` strings. V2-10 therefore emits an opaque,
capture-only identifier for the exact prior compact-history item that the
runtime selected. It is sufficient to prove that this capture came from an
actual resolution, but it is not a durable session-schema key. A future
session-schema migration would be required if cross-capture turn identity is
needed.

The existing saved 24-case capture has none of these fields. It remains
development/regression evidence, but it cannot establish protected global
ranking or trusted follow-up continuity under this contract. A new authorized
development capture is required before reevaluating those outcomes.

## Changed paths

- `app/retrieval/providers.py`
- `app/retrieval/opensearch_sections.py`
- `app/orchestrator/chat_orchestrator.py`
- `app/experimental/evidence_first_v2/scope_aware_fusion.py`
- `scripts/offline_retrieval_replay.py`
- `tests/evidence_first_v2/test_scope_aware_fusion.py`
- `tests/unit/test_retrieval_rank_list_capture.py`

## Verification

Using the repository's absolute `.codex-py311-venv` Python, task-owned pytest
temporary directories, and no pytest cache:

| Check | Result |
| --- | --- |
| V2 fusion, rank-list capture, and offline replay | **81 passed** |
| Orchestrator, retrieval-plan, OpenSearch, and diagnostic-capture compatibility | **222 passed** |
| Targeted flake8 | clean |
| `git diff --check` | clean |

## Promotion status

**Not deployable.** This is diagnostic plumbing in the V2 candidate only. It
requires a new development capture and independent review before any runtime
ranking decision could be considered for promotion.
