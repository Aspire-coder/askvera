# Phase 3, Lane 1: the outcome contract

Status: implemented. See `docs/conversation-quality/phase3/CX_DESIGN.md` for
the full lane breakdown; this note covers only Lane 1's write scope --
`app/response/outcome.py` and `tests/unit/test_conversation_outcome.py`.

## What this is

`app.response.outcome.derive_outcome` is a pure function (no I/O, no model
call, no import of `app.orchestrator.chat_orchestrator`) that turns the
metadata a chat turn already produced -- `failure_layer`,
`retrieval_availability`, and an `EvidenceDecision` (or any object with a
`.reason` / `.evidence`, duck-typed so this module never imports the
orchestrator) -- into one `ConversationOutcome`. It introduces exactly one
new vocabulary: the `OutcomeKind` enum and the table that maps existing
`failure_layer` values to it. No `failure_layer`, `retrieval_availability` or
`EvidenceDecision.reason` value is renamed, removed, or given a second alias.

The coordinator wires `ChatResponse.metadata["outcome"] =
outcome.to_metadata()` into `chat_orchestrator.py`; this lane does not touch
that file.

## Mapping table (failure_layer / reason -> OutcomeKind)

| Source value | Where it's set | OutcomeKind |
|---|---|---|
| `dependency_unavailable` | `chat_orchestrator.py:1332` | `dependency_unavailable` |
| `aws_guardrail` | `chat_orchestrator.py:1538`, also `app/response/builder.py:150-151` from `guardrail_intervened` | `safety_refusal` |
| `evidence_contract` | `chat_orchestrator.py:1549` | `evidence_missing` |
| `directory_source_conflict` | `chat_orchestrator.py:1917` | `evidence_missing` |
| `candidate_narrowing_fallback` | `chat_orchestrator.py:3741` | `clarification` |
| `directory_clarification` | `chat_orchestrator.py:3910`, `4310` | `clarification` |
| `sensitive_pii_input` | `chat_orchestrator.py:3936` | `safety_refusal` |
| `document_period_not_covered` | `chat_orchestrator.py:4171` | `evidence_missing` |
| `evidence_gate` (default) | `chat_orchestrator.py:4218` | `evidence_missing` |
| `evidence_gate` + `EvidenceDecision.reason == "cross_market_policy_request"` | `chat_orchestrator.py:4202`, reason from `app/evidence.py:163` | `cross_market_policy` |
| `local_guardrail` | `chat_orchestrator.py:_governance_failure_layer` (3553-3559) | `safety_refusal` |
| `risk_policy` | `chat_orchestrator.py:_governance_failure_layer` (3553-3559) | `safety_refusal` |
| `retrieval_miss` | `chat_orchestrator.py:_low_confidence_failure_layer` (3561-3567); root cause logged in `app/models/bedrock_provider.py:191` | `evidence_missing` |
| `low_confidence` | `chat_orchestrator.py:_low_confidence_failure_layer` (3561-3567); root cause logged in `app/models/bedrock_provider.py:205` | `evidence_missing` |
| *(no `failure_layer`)* | a delivered answer | `answer` |
| *(any value not in this table)* | -- | `evidence_missing` (fail safe; never `answer`) |

`tests/unit/test_conversation_outcome.py::test_every_orchestrator_failure_layer_literal_is_mapped`
greps `chat_orchestrator.py` for every `"failure_layer": "<x>"` dict literal
and fails if one appears without an entry in
`app.response.outcome._FAILURE_LAYER_KINDS`. That grep only catches the
inline-literal sites (9 of the 13 rows above); `local_guardrail`,
`risk_policy`, `retrieval_miss` and `low_confidence` reach the response
metadata through a helper method's `return "<literal>"` instead, so they are
asserted by name in `test_every_known_failure_layer_value_maps_to_exactly_one_kind`
rather than by the grep. Both tests exist so either kind of new value gets
caught.

## `international_directory`

Included in `OutcomeKind` per this lane's assignment ("one of the user's
seven required fallback states"). **Note for the coordinator:**
`CX_DESIGN.md`'s own `kind` enum (line 35-37) lists eight kinds and does not
include `international_directory`; this lane added it as instructed, but the
two documents now disagree and should be reconciled.

It is derived from the same directory-record predicate
`chat_orchestrator.py` already uses at lines 821-823 and 873-875
(`directory_kind` / `directory_section` / a `directory_fields` dict) plus the
existing `directory_kind == "international_sponsoring"` marker
(`app/retrieval/opensearch_sections.py:2414`, and the wider grep hits across
ingestion, validators and tests). When an approved `EvidenceDecision`
contains such a record, `directory_target` is set to that record's
`record_country` and the kind becomes `international_directory` -- but only
when the turn would otherwise have been `answer`; it never overrides a real
failure kind (a directory record with no approved evidence still reports its
own failure kind, with `directory_target` still populated for diagnostics).

**Limitation found and worth flagging:** there is no existing metadata field
that records "the market this directory answer targets" independent of the
record itself. `scripts/capture_application_path.py:534-537` says so
explicitly: `"directory_target": "unavailable"`, with the comment "No field
distinct from `runtime_scope_intent` currently exposes a separate 'directory
target'; see R09_CAPTURE_PLAN.md's interface requests." `runtime_scope_intent`
itself (`app/retrieval/providers.py:219-221`) is a routing label (`policy` /
`directory` / `international_sponsoring` / `ambiguous` / `unknown`), not a
market, and it is never copied into `ChatResponse.metadata`, so
`derive_outcome` cannot read it. The `directory_kind` / `record_country`
approach above is the closest true signal that reaches this function's
inputs; a market comparison against the session's own `country` was
considered and dropped because doing it correctly requires
`services.market_config.get_document_country_codes`, which reads
`config/policy_locales.json` -- I/O this function must not perform.

## `personal_account`

Included in `OutcomeKind` per this lane's assignment. **Not currently
reachable from `derive_outcome`.** This worktree (branched from `a53dcae`)
has no personal-account refusal path: `utils/personal_claims.py` does not
exist here (it exists on `askvera-deploy`, a different, further-ahead
worktree), and even there it only removes unsupported personal claims from
already-generated answer *text* -- it never sets a `failure_layer` or any
other metadata this function reads. No `failure_layer` literal or
`EvidenceDecision.reason` value anywhere in this worktree corresponds to a
personal-account refusal. The kind stays in the enum for the contract (and is
covered by `to_metadata` round-trip tests), but no test claims it is
reachable today; wiring a real source for it is out of this lane's scope.

## `partial_answer`

Included in `OutcomeKind` (required by `CX_DESIGN.md`) but, per the lane
assignment, never returned by `derive_outcome` here -- `fields_answered` and
`fields_unsupported` are always empty frozensets. No existing metadata in
this worktree records which requested directory fields a turn's answer
actually covered vs. left unsupported (only per-document `directory_fields`
dicts describing what a *record* holds, not what a *turn* answered). Lane 2
(`app/response/partial_answer.py`, not in this lane's write scope) owns
deriving `fields_answered` / `fields_unsupported` from the answer text and
evidence.

## `fields_requested`

Reuses `utils.directory_fields._requested_directory_field_set(question,
language=language)` unchanged, per the design doc. Returns `frozenset()`
when the question isn't confidently understood as naming specific fields (the
helper returns `None` in that case) rather than guessing.

## Test run

```
pytest tests/unit/test_conversation_outcome.py -q       -> 22 passed
pytest tests/unit/test_chat_orchestrator.py tests/conversation -q
                                                          -> 462 passed
flake8 app/response/outcome.py tests/unit/test_conversation_outcome.py
                                                          -> exit 0 (clean)
git diff --check                                          -> exit 0 (clean)
```
