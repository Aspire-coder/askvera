# R09 capture plan: manifest schema, first manifest outline, preflight, approval text

Date: 2026-09-18. Preparation only. Nothing in this document authorizes a
live capture; see "Exact approval text" below for what a human needs to
approve before `scripts/capture_application_path.py` is ever run without
`--preflight`.

## Why this tool exists

`scripts/evidence_first_v2/capture_read_only_retrieval.py` loops over a bare
question string and never reads stored conversation turns, so a multi-turn
case (Tanzania's "And what about FBOs who live there?", Finland's "Entä jos
hän...") was captured as if it were a first turn. R03 made that runner fail
closed on any case with stored turns
(`docs/evidence_first_v2/TERRA-R03-CONTEXT-TO-CAPTURE-20260918-1400.md`).
R06's diagnosis (`docs/conversation-quality/phase2/R06_DIAGNOSIS.md`, its
"Capture requests for R09/R10" section) lists five specific cases that need a
capture through the real `AIOrchestrator` path instead. This tool is that
replacement: it drives the real orchestrator with the manifest's stored turns
seeded into the session's memory backend, so the orchestrator resolves its
own follow-up continuity rather than the tool guessing at it.

`scripts/capture_application_path.py` is new. It does not modify or replace
the V2 capture scripts, and it makes no AWS, OpenSearch, Bedrock, network, or
model call outside of an explicitly approved, non-preflight run.

## Manifest schema

A manifest is one JSON object:

```json
{
  "manifest_version": 1,
  "cases": [ { ... }, { ... } ]
}
```

No other top-level keys are accepted. `cases` must be a nonempty list. Each
case is a JSON object with **exactly** these nine keys -- extra or missing
keys reject the whole manifest before anything else runs:

| Key | Type | Meaning |
| --- | --- | --- |
| `id` | nonblank string, unique in the manifest | Stable case identifier, reused across resumed runs. |
| `split` | `"development"` or `"evaluation"` | Matches R12's dev/eval separation; evaluation cases must stay untouched by anyone reviewing development results. |
| `exposure` | nonblank string | An honest note on prior exposure, e.g. "development case, reused from the frozen R03 Tanzania fixture" or "evaluation case, never previously graded." Recorded in every output row; never a place to describe expected content. |
| `turns` | list of `{"user": string, "assistant": string}` | Prior turns, in order, oldest first. Empty list for a first-turn case. Seeded into the session's memory backend exactly as `services/session.py`'s `append_session_turn` would store a real prior turn. |
| `message` | nonblank string | The final user turn actually sent to `AIOrchestrator.handle_chat`. |
| `country` | nonblank string | The request's session country (`ChatRequest.country`); validated by the real market config at request time, same as production. |
| `language` | nonblank string | The request's language (`ChatRequest.language`). |
| `role` | nonblank string | The request's role (`ChatRequest.role`). |
| `expectations` | any JSON value | Source-reviewed expectations, stored as **data only**. The runtime path (`scripts/capture_application_path.py`'s `_runtime_fields`) strips this key before any function that touches `AIOrchestrator` ever sees the case, so it is structurally impossible for a capture run to read or act on it. It exists for a later, separate grading step -- never for this tool. |

The manifest's SHA-256 is computed over a canonical (`sort_keys=True,
ensure_ascii=True`, no extra whitespace) JSON encoding of the whole object,
including `expectations`; changing anything, including an expectation a human
adds later, changes the SHA and therefore refuses a `--resume` against an
older checkpoint.

See `tests/fixtures/capture/example_manifest.json` for a three-case synthetic
example (a first-turn case, a Tanzania-then-Uganda Finnish follow-up modeled
on the frozen R03 fixture, and an evaluation-split unknown-fact case). It is
clearly synthetic and is not proposed as real capture content.

## Proposed FIRST manifest: outline only

This is an **outline** of roughly 30 journeys to build into the first real
manifest, drawn from R12's Stage 1 smoke list
(`docs/conversation-quality/phase2/R12_ACCEPTANCE_THRESHOLDS.md`) and R06's
five capture requests. It names the journey and its source, not an expected
answer: expectations are for a source-reviewed human to write directly into
the manifest's `expectations` field, never invented by this tool or by this
plan. Language and exact wording are left to whoever builds the manifest;
this table fixes only the case count, the topic, the split, and the honest
exposure label.

| # | Journey | Split | Exposure note | Source |
| --- | --- | --- | --- | --- |
| 1 | Tanzania foreign-then-local FBO bonus follow-up (`ho-slp-04...`) | development | Reused frozen R03/R06 fixture; already partially exposed via the old retrieval-only capture, so treat any dev-only comparison to that old capture as informative, not confirmatory. | R06 §1, R03 |
| 2 | Finland 36-month inactivity then Sponsored Recognized Manager follow-up (`ho-slp-17...`) | development | Same fixture family as #1; the Finnish anaphoric-form fix (R03) is unverified live until this capture runs. | R06 §2, R03 |
| 3 | Norway former-FBO reapplication/downline, country named in the question | development | New capture; not previously exposed to any live grading. | R06 §3 |
| 4 | US "Can I pay cash?" (13.01(c) negative-inference phrasing) | development | New capture; the only related canary uses different phrasing. | R06 §4, P068 |
| 5 | US emotionally-framed 1.01(c) variant (P167) | development | New capture; source section (1.01(c)) already source-verified in R06. | R06 §5, P167 |
| 6 | US emotionally-framed 1.01(d) variant (P168) | development | Same as #5, section 1.01(d). | R06 §5, P168 |
| 7 | US emotionally-framed 1.01(e) variant (P170) | development | Same as #5, section 1.01(e). | R06 §5, P170 |
| 8 | US policy: plain company-identity question ("What is Forever Living Products?") | development | Already fixed per R06 §5a; capture is a live-confirmation replay, not a new investigation. | R12 smoke list, R06 §5a |
| 9 | International sponsoring asked from a different session country than the target market | evaluation | Untouched evaluation journey. | R12 smoke list |
| 10 | Foreign company-policy request that must be refused | evaluation | Untouched evaluation journey; refusal is the point, not a content answer. | R12 smoke list |
| 11 | Kenya office-phone follow-up ("what about the order line?") | development | Directory-contact field-narrowing case; low sensitivity. | R12 smoke list |
| 12 | Kenya order-phone follow-up (reverse of #11) | development | Same family as #11. | R12 smoke list |
| 13 | "The other one" reference resolution, two-candidate case | evaluation | Untouched evaluation journey; reference resolution accuracy is scored, not invented. | R12 smoke list |
| 14 | "The first one" reference resolution, ordinal case | evaluation | Untouched evaluation journey. | R12 smoke list |
| 15 | Finnish residence follow-up, a second configured-market variant distinct from #2 | development | Same mechanism family as #2, different market pairing, to check the fix generalizes. | R12 smoke list, R03 |
| 16 | Minimum order plus payment methods, English | development | Compound two-part question; tests answer completeness across both parts. | R12 smoke list |
| 17 | Minimum order plus payment methods, French | development | Same journey as #16, other language; per R12, no language may score worse than its own baseline. | R12 smoke list |
| 18 | Delivery timing vs approval timing, distinguishing question | evaluation | Untouched evaluation journey; frequently confused process stages. | R12 smoke list |
| 19 | Dependency outage, fault-injected | development | Only run if the fault-injection environment itself is separately approved for this candidate; otherwise this row is skipped, not faked. | R12 smoke list |
| 20 | Company identity and purchasing, checking for a stray disclaimer | development | Regression check against a known prior defect class (over-triggered disclaimer). | R12 smoke list |
| 21 | Returns question, checking for a stray disclaimer | development | Same defect class as #20, different topic. | R12 smoke list |
| 22 | A real income-claim question that must be refused | evaluation | Safety-critical untouched evaluation journey. | R12 smoke list |
| 23 | A real medical-claim question that must be refused | evaluation | Safety-critical untouched evaluation journey. | R12 smoke list |
| 24 | An unknown fact that must not be invented | evaluation | Untouched evaluation journey; the answer is "I don't know," never a fabricated figure. | R12 smoke list |
| 25 | Hong Kong delivery-fee question (global-record protection control) | development | Named regression control per R06 §4 and V2-09/V2-10; already diagnosed, this is a live-confirmation replay. | R06 §4 |
| 26 | Ghana cross-market bonus question (global-record protection control) | development | Same family as #25. | R06 §4 |
| 27 | US 6.05 forfeiture-after-a-year question (P091) | development | Already fixed per R06 §5d; live-confirmation replay. | R06 §5d |
| 28 | US 15.01(b)(6) "active everywhere" question (P078) | development | Already fixed per R06 §5c; live-confirmation replay. | R06 §5c |
| 29 | US 16.02(e)(1) "stall at a weekend market" question (P104) | development | Already fixed per R06 §5e; live-confirmation replay. | R06 §5e |
| 30 | A second, unrelated market's international-sponsoring question, to check #9 generalizes | evaluation | Untouched evaluation journey. | R12 smoke list |

Every row above needs a source-reviewed human to write its actual `message`,
`turns`, `country`/`language`/`role`, and `expectations` before it becomes a
real manifest entry; this table is the outline, not the manifest.

## Preflight command

`--preflight` never imports anything under `app/` or `services/`; it only
parses and validates the manifest and prints an estimate. It is safe to run
at any time, by anyone, without approval:

```
<PYTHON> scripts/capture_application_path.py \
  --manifest docs/conversation-quality/phase2/<first-manifest>.json \
  --preflight \
  --unit-price retrieval=<PRICE> \
  --unit-price embedding=<PRICE> \
  --unit-price planner_or_translation=<PRICE> \
  --unit-price selector=<PRICE> \
  --unit-price reranker=<PRICE> \
  --unit-price generation=<PRICE>
```

Every `--unit-price` is optional and has no built-in default; the coordinator
fills in real per-call prices before an approval request is sent, and any
category left out of `--unit-price` is left out of the cost total rather than
assumed free. Against `tests/fixtures/capture/example_manifest.json` (3
synthetic cases), this printed:

```json
{
  "manifest_sha256": "f632e86a799cea7b3dca98dab96d008f1b326250d802f54f28104a0710682cf3",
  "case_count": 3,
  "cases_per_split": {"development": 2, "evaluation": 1},
  "max_calls_per_case_by_category": {
    "retrieval": 16, "embedding": 4, "planner_or_translation": 2,
    "selector": 1, "reranker": 1, "generation": 1
  },
  "max_calls_total": {
    "retrieval": 48, "embedding": 12, "planner_or_translation": 6,
    "selector": 3, "reranker": 3, "generation": 3, "total": 75
  }
}
```

(The full command's output, including the `cost_envelope` computed from
placeholder per-call prices, is reproduced in the R09 handoff.)

## Call/cost envelope formula (placeholder)

```
max_calls[category] = MAX_CALLS_PER_CASE[category] * case_count
```

`MAX_CALLS_PER_CASE` is a documented ceiling, never a measurement --
`--preflight` makes zero calls, so it cannot count anything real:

| Category | Per-case ceiling | Reasoning |
| --- | --- | --- |
| `retrieval` | 16 | Up to 4 planned queries (`BEDROCK_QUERY_PLANNER_QUERY_COUNT`-shaped ceiling), each searching up to 4 OpenSearch channels (text, vector, global_text, global_vector). |
| `embedding` | 4 | One embedding call per vector-channel query. |
| `planner_or_translation` | 2 | One query-planner Bedrock call plus one global-document-translation Bedrock call; today these share a bucket because neither exposes a distinguishing structural label at the boundary (see "Interface requests" below). |
| `selector` | 1 | One evidence-selector Bedrock call per case. |
| `reranker` | 1 | One rerank pass per case (today a lexical helper, not a model call; kept as its own bucket so a future model-backed reranker is covered without changing this script). |
| `generation` | 1 | One final-answer model call per case. |

A live run's actual per-case call counts come from wrapping the real
boundary callables (`OpenSearchSectionProvider._search_channel`, `embed_text`,
`_planned_retrieval_plan`, `_global_search_query`, `_select_evidence_rows`,
`_rerank_documents`, and the orchestrator's own `model_router.generate`), so
the checkpoint's `call_counts` field is always an observed count, never an
estimate. `--max-calls` and `--max-cost` compare against that observed,
running total, not against this ceiling table.

`cost_envelope[category] = max_calls[category] * unit_price[category]`, for
whichever categories the coordinator supplied a `--unit-price` for; the
`total` sums only the priced categories.

## Interface requests

These fields are recorded as `"unavailable"` because nothing in the current
diagnostic-capture contract exposes them; they are not invented, and a future
change to `app/orchestrator/chat_orchestrator.py` or
`app/retrieval/opensearch_sections.py` could add them without changing this
script's manifest or output schema:

- **Resolved (coordinator, 2026-09-18, c482728):** `RetrievalResult.availability`
  (R02: available / degraded / unavailable) and the provider's
  `failed_search_channels` are now written into the orchestrator's diagnostic
  record for each retrieval (`_append_diagnostic_retrieval`; diagnostic only).
  The capture reports them as `retrieval_availability` and
  `search_channel_failures`, from the question-stage retrieval. "unavailable"
  in those two fields means no retrieval was recorded (for example, an early
  clarification), not a provider outage.
- **A "directory target" distinct from `runtime_scope_intent`.** Today
  `runtime_scope_intent`/`authorized_policy_market` (V2-10's contract) are the
  only trusted scope fields exposed; there is no separate field naming which
  directory row (if any) was the authorized target.
- **A distinguishing structural label for the query-planner call vs. the
  global-document-translation call.** Both reach
  `get_aws_clients().bedrock_runtime.converse` from
  `app/retrieval/opensearch_sections.py` without a tool name or other
  structural marker, so this script's call accounting folds them into one
  `planner_or_translation` bucket.
- **A durable per-turn session identifier.** Per V2-10's own documented
  limitation, the stored session transcript has no schema-level turn ID; this
  script's `prior_user_turn_id` is the same capture-only opaque identifier
  V2-10 already defined, not a new one.
- **An "active generation pointer" distinct from per-document `ingestion_id`.**
  This script uses the `ingestion_id` values already present on each
  retrieved document (`_CAPTURED_DOCUMENT_METADATA`) as the case's source
  identity, rather than making a separate `services.knowledge_generations`
  database call; that call was deliberately not added here to avoid a second,
  redundant path to the same information with its own DB-availability risk.

## Exact approval text a run needs

Before anyone runs `scripts/capture_application_path.py` without
`--preflight`, they must give (and this script requires, via
`--i-have-approval <approval-id>`, recorded in every output row) explicit
approval covering:

> **Scope:** run `scripts/capture_application_path.py` against the manifest
> at `<manifest path>` (SHA-256 `<sha>`), on the R09 candidate at commit
> `<HEAD>` (dirty: `<true/false>`), covering `<N>` development cases and `<M>`
> evaluation cases.
>
> **Data transmitted:** each case's `message` and stored `turns` (already
> present in the manifest) are sent to the configured retrieval and
> generation services exactly as a real chat request would send them; no
> additional user data, PII, or credentials are read or transmitted by this
> tool.
>
> **Services and models:** OpenSearch (`RETRIEVAL_PROVIDER`,
> `OPENSEARCH_INDEX` from the running configuration), Bedrock embedding
> (`BEDROCK_EMBED_MODEL_ID`), Bedrock query planner and evidence selector (if
> `BEDROCK_QUERY_PLANNER_ENABLED`/`OPENSEARCH_EVIDENCE_SELECTOR_ENABLED`), and
> Bedrock generation (`BEDROCK_FAST_MODEL_ID`/`BEDROCK_COMPLEX_MODEL_ID` per
> `MODEL_ROUTING_MODE`). No AWS write/delete/ingestion/admin API is touched.
>
> **Maximum calls:** `<max_calls total from --preflight>`, enforced live via
> `--max-calls <N>`.
>
> **Maximum cost:** `<cost_envelope total from --preflight, with real unit
> prices>`, enforced live via `--max-cost <X> --unit-price ...`.
>
> **Approval ID:** `<approval-id>`, to be passed as
> `--i-have-approval <approval-id>` and recorded in every output row.

No live run is authorized by this plan document itself; it only prepares the
exact text a human approval needs to cover.
