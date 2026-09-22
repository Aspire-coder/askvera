# R08 - Evidence-First V2 adapter inventory

Read-only inventory. Source: `askvera-v2-work` at commit `e3b399a` (V2 package
and docs `V2-01`..`V2-10`, `CURRENT_STATUS.md`), read from disk except
`app/orchestrator/chat_orchestrator.py` and
`tests/evidence_first_v2/test_r03_context_capture.py`, which were read via
`git show e3b399a:<path>` because another worker has them checked out live.
Comparison target: `askvera-conv-quality` at `HEAD 06be221`
(`AIOrchestrator`, `app/evidence.py`, `app/evidence_contract.py`,
`app/prompts/`, `app/response/`, `app/validation/`,
`app/orchestrator/reference_resolution.py`,
`app/risk/policies/medical_claim_policy.py`).

## 0. Headline

**Zero wiring today.** `app/experimental/evidence_first_v2/__init__.py:1-5`
states the package "has no dependency on the existing application pipeline...
not imported by routes or production configuration," and this was confirmed
by grep: no occurrence of `evidence_first_v2` or `experimental` in
`app/orchestrator/chat_orchestrator.py` (via `git show`),
`app/retrieval/providers.py`, or `app/retrieval/opensearch_sections.py` in the
V2 snapshot. Every public V2 type is synthetic (`V2Request`,
`StructuredContext`, `ScopeDecision`, `StandaloneRequest`,
`InterpreterOutput`, `ComposerOutput`, `FusionResult` — see
`app/experimental/evidence_first_v2/__init__.py:7-19`). The one thing that
*is* already live is a set of pure, non-persisted provenance fields
(`runtime_scope_intent`, `authorized_policy_market`, `context_resolution`)
computed on every retrieval request but only captured/persisted when
`DIAGNOSTIC_CAPTURE_ENABLED` (default `False`) is on — see §3.

## 1. Module/function inventory, stage, and input-contract classification

Classification key: **(a)** accepts real production objects today; **(b)**
accepts only V2-internal/synthetic contracts or injected fake
interpreter/composer/evaluator callables; **(c)** wired into the live request
path now.

| Module | Function/Class | file:line | Stage | Class | Evidence |
|---|---|---|---|---|---|
| `contracts.py` | `Turn`, `TurnSpeaker`, `V2Request` | 62-101 | request/context capture | (b) | Plain dataclasses/enums, no `app.*` imports |
| `contracts.py` | `EvidenceAccess`, `EvidenceReference`, `FactQualifiers`, `EvidenceFact` | 104-176 | evidence approval | (b) | V2-internal only |
| `contracts.py` | `ResultStatus`, `EvidenceFirstResult` | 179-204 | composition | (b) | V2-internal only |
| `context.py` | `ContextSource`, `ContextField`, `PlaceStatus`, `AmbiguityCode`, `ContextUse`, `Ambiguity`, `StructuredContext` | 16-152 | context capture | (b) | Imports only `.contracts` (context.py:8) |
| `scope.py` | `ScopeIntent`, `ScopeCompatibility`, `ScopeDecision`, `resolve_scope` | 11-125 | scope authorization | (b) | Imports only `.contracts` (scope.py:8); operates on `V2Request`/`ScopeIntent` |
| `standalone.py` | `InterpreterOutput`, `StandaloneRequest`, `StandaloneRequestBuilder.build`, `resolve_standalone_scope` | 81-379 | scope authorization / request build | (b) | `Interpreter: Callable[[V2Request, StructuredContext], InterpreterOutput]` (standalone.py:141) — an **injected fake/replay** interpreter, never a real NLU/model call |
| `capture_provenance.py` | `validate_runtime_scope_intent`, `validate_authorized_policy_market`, `validate_context_resolution`, `validate_capture_provenance` | 23-76 | capture/provenance validation | (b)/leaf | Accepts plain `Mapping`/`str`/`Any`; imports only `re`, `typing` — **no** app or V2-type imports at all |
| `scope_aware_fusion.py` | `DocumentIdentity`, `FusionResult`, `fuse` | 20-261 | ranking/fusion | (b) | Docstring (lines 1-6): "consumes captured retrieval lists... no route, provider, network, index, or model dependency and is deliberately not wired into the application." Operates on raw `Mapping[str, Any]` hit dicts shaped like OpenSearch hits, not real `RetrievedDocument`/`RetrievalResult` |
| `evidence.py` | `SourceCatalog.admit`, `GoverningManifest`, `FactCandidate`/`ValidatedFact`/`validate_facts`, `CoverageBranch`/`assess_coverage` | 70-547 | evidence approval / coverage | (b) | Imports only `.contracts`, `.scope` (evidence.py:17-18) |
| `orchestration.py` | `CompositionInput`, `ComposerOutput`, `EvidenceFirstOrchestrator.run` | 13-121 | composition/validation | (b) | `Composer = Callable[[CompositionInput], ComposerOutput]` (orchestration.py:41) — **injected fake composer**, not the real answer builder. Reaches `evidence.py` via `__import__(__package__+".evidence", fromlist=(...))` (orchestration.py:11) rather than a normal import |
| `ranking.py`, `ranking_fixture.py`, `ranking_ledger.py` | `run_owned`, `validate_owned`, `authority()` | ranking.py:197-222 | ranking/fusion (offline experiment) | (b) | Pinned to hand-authored synthetic `Capture`/`Hit` fixtures (`ranking_fixture.py`), never real retrieval output |
| `comparison.py`, `comparison_exposure.py`, `comparison_fixture.py` | `admit_owned`, `run_owned`, `validate_report`, `summarize` | comparison.py:184-253 | composition/comparison harness | (b) | Takes injected `baseline`/`candidate`/`evaluator` callables (comparison.py:228) — synthetic harness adapters, not the real composer/retriever |
| `audit.py` | `INTEGRATION_CONTRACT`, `execute_offline`, `CUTOVER` (`CutoverSpec`) | 54-123 | audit / future cutover spec | (b) | "closed offline audit and future specification; no production wiring" (audit.py:1). `feature_flag="evidence_first_v2_shadow"` (audit.py:121) is a **planned name in a spec dataclass**, not a runtime flag |

No V2 module falls into class **(a)** or **(c)**: none accepts a real
`ChatRequest`, `RetrievalResult`/`RetrievedDocument`, real session-history
string, or real source-version metadata, and none is called from any
production import (confirmed by grep across
`chat_orchestrator.py`/`providers.py`/`opensearch_sections.py`). The single
exception worth flagging separately is the *provenance-producing* code that
now lives in the real production files — see §3.

### Import-mechanism note (relevant to §5)

`evidence.py` and `orchestration.py`'s legitimate intra-package dependencies
(`.contracts`, `.scope`, `.standalone`) use ordinary `from .x import y`.
Everything that reaches a module **not** on the isolation test's allowlist
(`evidence`, again via orchestration.py) does so through
`__import__(__package__ + ".evidence", fromlist=(...))` (orchestration.py:11)
— a call expression, not an `ast.Import`/`ast.ImportFrom` node, so it is
invisible to the AST-walking checker in
`tests/evidence_first_v2/test_offline_isolation.py:29-41`. The same pattern
recurs in `ranking.py:212,219`, `comparison.py:174`, `comparison_fixture.py:4,26`,
and `ranking_fixture.py:4`. `scope_aware_fusion.py:14`
(`from .capture_provenance import validate_capture_provenance`) is the only
module reaching a non-allowlisted sibling through an ordinary, AST-visible
relative import — which is exactly why it is the one caught by the test. See
§5.

## 2. Adapters needed per synthetic stage, and REUSE recommendation

For every stage below, production already has a working, real-input
implementation. The recommendation is to **reuse the production logic**
(feed it through a thin adapter that maps V2 contract fields onto production
contracts, or better, retire the parallel V2 stage) rather than let V2 grow
an independently evolving second implementation.

### 2.1 Context / follow-up resolution — REUSE, do not re-adapt V2-02

- V2 side: `standalone.py`'s "history market fallback" (bounded continuation
  grammar `telephone|phone|contact|what about [the] telephone...`, one
  value-bound use from the newest retained turn — see
  `docs/evidence_first_v2/V2-02-standalone-request.md:9`) and V2-10's
  `context_resolution` capture field (`capture_provenance.py:47-63`,
  closed enum `not_dependent|resolved_dependent_follow_up|unresolved|unknown`).
- Production already does this, on real session history: `resolve_reference`
  in `askvera-conv-quality/app/orchestrator/reference_resolution.py:180`
  (`resolve_reference(message: str, history: str, language: str) ->
  ReferenceResolution`), reading the actual rendered session-history string
  (docstring: "the same string `services.session.get_session_history`
  returns"), called from
  `AIOrchestrator._resolve_unresolved_reference` at
  `chat_orchestrator.py:3115` (invoked at `chat_orchestrator.py:993`, via
  `outcome = resolve_reference(scrubbed_input, history, body.language)` at
  `chat_orchestrator.py:3138`). This already handles ordinal/contrastive
  back-reference disambiguation across multiple named markets in a real
  multi-turn session — a strict superset, on real data, of what V2-02's
  synthetic history-fallback grammar attempts on a fake interpreter's output.
- **Adapter, if any is still wanted**: none needed for the actual decision.
  If V2's offline replay wants a `context_resolution` record for capture
  parity, map `ReferenceResolution`'s resolved/unresolved outcome directly to
  V2-10's closed enum instead of reimplementing resolution logic in V2.
  Do not port V2-02's bounded grammar into runtime code; it is a narrower,
  synthetic-only re-derivation of what `reference_resolution.py` already does
  against real history.

### 2.2 Scope authorization — REUSE, express V2's three-way split via existing metadata

- V2 side: `scope.py`'s `ScopeIntent` (`policy`/`directory`/
  `international_sponsoring`/`ambiguous`/`unknown`) and V2-10's
  `runtime_scope_intent`/`authorized_policy_market` capture contract
  (`capture_provenance.py:9-18`, `docs/evidence_first_v2/V2-10-runtime-capture-provenance-contract.md:30-63`).
- Production already expresses the same three-way split, just through
  existing fields rather than a named enum:
  `app/evidence.py:150` `approve_evidence(query, retrieval_result, country,
  language)` performs the cross-market policy rejection via
  `_names_another_market` (`app/evidence.py:249`, called at
  `app/evidence.py:162`) and the global/local split via
  `document.metadata.get("access_scope") == "global"` checks at
  `app/evidence.py:167,219,375`; `chat_orchestrator.py` layers
  `_scope_query` (`chat_orchestrator.py:3439`),
  `_is_cross_market_local_evidence` (`chat_orchestrator.py:3445`, called at
  `chat_orchestrator.py:3352`), and the reapprove-globals-only branch inside
  `_route_or_approve_evidence` (`chat_orchestrator.py:3335`, invoked at
  `chat_orchestrator.py:1164`) on top.
- **This work is in fact already partially real in the V2 snapshot itself**:
  `app/retrieval/providers.py:175-200` (`_runtime_scope_intent`) computes
  exactly V2-10's closed enum today, from real query text and real
  deterministic-route booleans, and unconditionally attaches it to
  `RetrievalQueryPlan` (`providers.py:279-280`, populated at
  `providers.py:578,592,691,778`); `providers.py:169-172`
  (`_authorized_policy_market`) derives the authorized market straight from
  `country`. This is the real adapter V2-10 asked for — it already exists on
  this branch, in production files, not in the V2 package. See §3 for why it
  is still safe.
- **Adapter needed**: none for decision logic. If V2's package wants to
  consume this, the adapter is: read `RetrievalQueryPlan.runtime_scope_intent`
  / `.authorized_policy_market` (already real, already computed) and pass
  them into `scope_aware_fusion.fuse`'s `scope_intent`/
  `authorized_policy_market` parameters, exactly as
  `scripts/offline_retrieval_replay.py:92` already imports
  `validate_capture_provenance` to do offline. No new field derivation is
  needed; do not reinvent `_runtime_scope_intent` inside the V2 package.

### 2.3 Composition contract — REUSE two existing layers, do not add a third

- V2 side: `orchestration.py`'s `CompositionInput`/`ComposerOutput`/
  `EvidenceFirstOrchestrator.run` (orchestration.py:13-121) binds accepted
  facts to citations against an **injected fake composer** callable
  (orchestration.py:41).
- Production already has this in two real layers:
  1. `app/evidence_contract.py:29` `parse_evidence_contract(text: str,
     documents: list[RetrievedDocument]) -> EvidenceContractResult` — strict
     claim/sentence-to-`evidence_ids` binding against real
     `RetrievedDocument` objects, gated off by default
     (`config/settings.py:470`
     `EVIDENCE_GATED_OUTPUT_ENABLED = _env_bool(..., False)`, checked at
     `chat_orchestrator.py:1981`).
  2. `app/response/builder.py:134` `class ResponseBuilder`, `.build`
     (`response/builder.py:137`) and `.reconcile_citations`
     (`response/builder.py:285`) — always on, real composition/citation
     reconciliation path.
- **Adapter needed**: none for logic reuse. Where V2-04's stricter
  exact-claim/citation renderer (`docs/evidence_first_v2/V2-04-composition-and-validation.md:5-7`)
  goes further than production (e.g. the bounded refusal-pattern gate, the
  format-character/confusable-script checks in §2.4 below), the adapter
  should be: extract those specific *validators* as pure functions callable
  from `parse_evidence_contract`/`ResponseBuilder`, not stand up a second,
  independently evolving composition contract fed by a fake composer.

### 2.4 Validation (safety/refusal gate) — partial REUSE, partial genuine addition

- V2 side: `orchestration.py`'s bounded refusal-pattern/format-character/
  confusable-script checks (`docs/evidence_first_v2/V2-04-composition-and-validation.md:9-19`,
  e.g. guaranteed-income, diabetes-elimination, Cyrillic-`і` confusable,
  Latin/Cyrillic script mixing).
- Production has an analogous but topic-specific safety policy:
  `app/risk/policies/medical_claim_policy.py` (structural/bounded medical-claim
  refusal, comparable in shape to V2-04's clause-bounded income/medical
  gate) and `app/validation/validators/numeric_grounding_validator.py`
  (numeric-claim grounding, comparable to V2-04's short-number preservation
  requirement).
- **Recommendation**: the *income-guarantee* and *script-confusable* checks
  in V2-04 do not appear to have a production equivalent today — this is a
  genuine candidate for porting a validator *function* (not the V2 pipeline)
  into `app/validation/validators/` or `app/risk/policies/`, callable
  directly by `ResponseBuilder`/`parse_evidence_contract`, rather than only
  reachable through the synthetic V2 orchestrator.

### 2.5 Ranking/fusion — genuine V2 addition, not present in production

- Production fusion is **weighted additive**, not RRF:
  `opensearch_sections.py:1828` `_merge_hits` merges `text_hits` and
  `vector_hits` by adding `settings.OPENSEARCH_VECTOR_WEIGHT`-weighted vector
  scores onto text scores (`opensearch_sections.py:1849`,
  `score_weight=settings.OPENSEARCH_VECTOR_WEIGHT`); there is no RRF and no
  scope-aware-fusion flag anywhere in `opensearch_sections.py`/`providers.py`.
- V2's `scope_aware_fusion.fuse` (RRF plus a global-record protection rule
  gated on `runtime_scope_intent`, plus a continuity signal — see
  `docs/evidence_first_v2/V2-09-sol-corrected-scope-aware-fusion-handoff.md:20-27`)
  is therefore **not a reimplementation of an existing production
  capability** — it is a genuinely new ranking strategy. It measured better
  recall than current production and than plain RRF on the saved 24-case
  capture (`V2-09`: 14/19, 16/19, 18/19 at k=5/10/30 vs. current's 11/19,
  13/19, 17/19), but that capture has **no trusted
  `runtime_scope_intent`/`authorized_policy_market` field on any case**
  (V2-09 doc lines 55-58), so the reported global-protection behavior is a
  fail-closed no-op on old data, not evidence the mechanism works on live
  intent. This stage has no REUSE option; it needs its own approval-gated
  live-capture evidence per `V2-07`/`V2-10`, not a production analogue.

## 3. Default-off requirements

- **No V2-specific runtime flag exists anywhere.** Grepping
  `app/experimental/evidence_first_v2/*.py` for
  `flag|enabled|FEATURE|shadow|V2_ENABLED|toggle` finds only: (1)
  `audit.py:118,120-121`, the literal string `"evidence_first_v2_shadow"`
  inside the frozen `CutoverSpec` instance `CUTOVER` — a **documentation
  record of a hypothetical future flag name**, not a flag anything reads;
  every other field on that same record (`owner`, `escalation`,
  `reenable_authority`) is literally set to `"APPROVAL_REQUIRED"`; and (2) an
  unrelated local Boolean named `enabled` inside `audit.py`'s own synthetic
  stage machine (`audit.py:107,109,113`).
- **The V2 package cannot make a live call when disabled, because it cannot
  make a live call at all.** Every module's imports are stdlib-only (`re`,
  `hashlib`, `unicodedata`, `dataclasses`, `enum`, `typing`) plus intra-package
  references; there is no `requests`/`boto3`/`opensearchpy`/HTTP-client
  import anywhere in the package. Every external input arrives as an
  **injected callable** (`Interpreter` in `standalone.py:141`, `Composer` in
  `orchestration.py:41`, `baseline`/`candidate`/`evaluator` in
  `comparison.py:228`) or a **pre-captured data structure**
  (`Mapping` hit dicts in `scope_aware_fusion.py:197-198`, frozen fixtures in
  `ranking_fixture.py`/`comparison_fixture.py`). There is no guard to audit
  for a disabled-flag bypass because the I/O capability the guard would
  protect does not exist in this package, by construction.
- **The one thing that is real and unconditional today**: the
  provenance-field computation in production files —
  `providers.py:175-200` `_runtime_scope_intent`, `providers.py:169-172`
  `_authorized_policy_market`, and the `context_resolution` plumbing through
  `chat_orchestrator.py` (`set_rank_list_context_resolution`/
  `_build_retrieval_query_with_provenance`, `chat_orchestrator.py:1033-1060`
  via `git show`) — run on **every** retrieval request regardless of any
  flag, because they are plain pure functions folded into building
  `RetrievalQueryPlan`. This is safe (no I/O, no side effect, negligible
  cost) but it is real production code, already changed, already on this
  branch, and already inside the request path — the coordinator's finding
  that this overlaps V2's scope split is correct and should be recorded as
  "(c) partially wired" for `runtime_scope_intent`/`authorized_policy_market`
  specifically, distinct from the rest of the V2 inventory which is fully
  (b).
- **Persistence of that data is gated off by default.**
  `chat_orchestrator.py:719` `DIAGNOSTIC_CAPTURE_ENABLED = False`; `handle_chat`
  (`chat_orchestrator.py:933-936`, via `git show`) returns
  `self._handle_chat(body, correlation_id)` immediately when the flag is
  `False`, before touching `_DIAGNOSTIC_CAPTURE`/`enable_rank_list_capture`.
  Downstream, `opensearch_sections.py:275-276`
  (`if not _rank_list_capture_enabled.get(): return None`) makes every
  rank-list record function a no-op when capture is off, so `_rank_list_fields`
  (`opensearch_sections.py:400-409`) returns `{}` and nothing is captured or
  logged.
- **What shadow mode would need to guarantee zero extra live calls**: (1)
  keep the V2 package import-free of any client/network module — enforced
  today by the (currently broken, see §5) isolation test; (2) gate any new
  V2-package call site behind the same "compute pure metadata unconditionally,
  gate only persistence/consumption" pattern already used for
  `runtime_scope_intent` — i.e. a shadow evaluation of `scope_aware_fusion.fuse`
  over already-fetched hits, never triggering an additional OpenSearch/Bedrock
  call, gated by a flag read once per request the way
  `services/candidate_control.py:39-51` `get_candidate_flags()` already does
  (fails open to `_DEFAULT_FLAGS` on any DB error, gated by
  `settings.CANDIDATE_MODE_LOOKUP_ENABLED`, itself default off, and cached for
  `_CACHE_TTL_SECONDS = 5.0`); and (3) confirm any shadow-mode composer/ranking
  invocation is logged only, never returned to the user, mirroring how
  `DIAGNOSTIC_CAPTURE_ENABLED` gates persistence today without gating the
  (harmless) computation.

## 4. Rollback and compatibility

- **Today**: rollback is trivial because there is nothing wired to roll back
  — the V2 package is not imported by any production module. Turning it "off"
  is the default state.
- **The provenance fields already in production files are themselves new
  behavior on this branch** relative to the base commit named in
  `CURRENT_STATUS.md:11-12` (`base 5b1d33fe...`). Rolling back to that base
  would remove `_runtime_scope_intent`/`_authorized_policy_market` from
  `RetrievalQueryPlan` and the `context_resolution` plumbing from
  `chat_orchestrator.py`/`opensearch_sections.py`. Since these fields are
  currently unconsumed by anything except the diagnostic-capture path (itself
  off by default) and the offline replay script, removing them has no
  observable production effect today — confirming `CURRENT_STATUS.md`'s
  characterization that these changes are "preserved" but "not a claim that
  they are merged, released or production-ready."
- **Audit-module's own cutover spec** (`audit.py:116-123`, `CutoverSpec`
  `CUTOVER`) is the only place a rollback procedure is documented, and it is
  explicit that this is a future-state placeholder, not an implemented
  mechanism: `feature_flag="evidence_first_v2_shadow"`,
  `traffic_action="shadow:disable flag; traffic:restore existing route"`,
  `recovery_checks=("flag_or_route_restored", "existing_path_serving",
  "safety_scope_citation_baseline_recovered",
  "captures_retained_for_approved_review")`, `reenable_authority=
  "APPROVAL_REQUIRED"`. Any real cutover must implement, not just cite, these
  four recovery checks.
- **Shared state/caches needing invalidation if a future shadow flag is
  added**: the only existing precedent, `services/candidate_control.py`'s
  in-process `_cached_flags`/`_cache_expires_at` (candidate_control.py:22-23),
  self-expires every 5 seconds and fails open to all-`False` on any DB error
  (candidate_control.py:45-51) — a new V2 flag following this pattern would
  need no explicit invalidation beyond that TTL. If diagnostic capture is
  ever turned on broadly, the `ContextVar`-based rank-list capture state
  (`_rank_list_capture_enabled`, `_rank_list_context_resolution`,
  `opensearch_sections.py:250-271`) is per-request/per-context already and
  needs no cross-request invalidation, but `enable_rank_list_capture`/
  `disable_rank_list_capture` (imported at `chat_orchestrator.py:936` per
  `git show`) must remain paired (enable/reset) on every code path, including
  exceptions, or a leaked `ContextVar` state could bleed into an unrelated
  request on the same worker.

## 5. The isolation-allowlist failure

`tests/evidence_first_v2/test_offline_isolation.py:16-17` defines:

```python
ALLOWED_ABSOLUTE_IMPORTS = {"__future__", "dataclasses", "enum", "hashlib", "re", "typing", "unicodedata"}
ALLOWED_RELATIVE_IMPORTS = {"context", "contracts", "scope", "standalone"}
```

`test_package_imports_use_a_narrow_allowlist` (lines 29-41) AST-walks every
`*.py` in the package and asserts every `ast.Import`/`ast.ImportFrom` target
is in one of these two sets. `scope_aware_fusion.py:14`
(`from .capture_provenance import validate_capture_provenance`) fails this
because `"capture_provenance"` is not in `ALLOWED_RELATIVE_IMPORTS`.

**Root cause, not just symptom**: the allowlist was written when the package
had four modules (`context`, `contracts`, `scope`, `standalone`) and was
never updated as `evidence.py`, `orchestration.py`, `ranking.py`,
`ranking_fixture.py`, `ranking_ledger.py`, `comparison.py`,
`comparison_exposure.py`, `comparison_fixture.py`, `audit.py`, and
`capture_provenance.py` were added. Every one of those newer modules that
needs to reach a non-allowlisted sibling does so via a same-package
`__import__(__package__ + ".<module>", fromlist=(...))` call expression
(e.g. `orchestration.py:11` reaching `evidence.py`; also
`ranking.py:212,219`, `comparison.py:174`, `comparison_fixture.py:4,26`,
`ranking_fixture.py:4`) — which is **invisible to the AST walk** because it
is a plain function call, not an `Import`/`ImportFrom` node. `evidence.py`
and `orchestration.py`'s *legitimate* allowlisted dependencies
(`.contracts`, `.scope`, `.standalone`) do use ordinary imports and pass
fine. `scope_aware_fusion.py` is the *only* module that reaches a
non-allowlisted sibling (`capture_provenance`) through an ordinary,
AST-visible `from .x import y` — which is exactly why it is caught while the
others (which have the identical structural problem, reaching modules the
allowlist doesn't know about) are not.

`capture_provenance.py` itself is a clean leaf: its own imports are only
`re` and `typing` (both already in `ALLOWED_ABSOLUTE_IMPORTS`), it has no
`app.*` or cross-package dependency, and per V2-10's own doc
(`docs/evidence_first_v2/V2-10-sol-provenance-correction-handoff.md:15-17`)
it is deliberately "the one strict validator used by rank-list conversion,
direct replay, and direct fusion" — a shared cross-cutting boundary module by
design, not an accident.

**Recommendation: narrow allowlist addition, not a code move.**

- Add `"capture_provenance"` to `ALLOWED_RELATIVE_IMPORTS`. Justification:
  (1) the module is a pure, dependency-free validator that exists specifically
  to be a shared strict-validation boundary for multiple callers (per its own
  design doc), so moving its code into `scope_aware_fusion.py` would either
  duplicate the same three validator functions into every future consumer
  (rank-list conversion in `scripts/offline_retrieval_replay.py` already
  imports it too, at `scripts/offline_retrieval_replay.py:92`) or force an
  awkward re-export path; (2) it does not weaken the isolation guarantee the
  test exists to enforce — `capture_provenance.py` adds zero new absolute
  imports and zero new external coupling; (3) it is factually already
  "present" per `CURRENT_STATUS.md:87-91` ("the already-present relative
  import... This was observed during R01... It needs a separately reviewed
  V2-boundary decision, not a quiet test edit") — i.e. the docs already
  anticipate exactly this allowlist-addition decision, just withholding it
  pending independent review, which this inventory is not authorized to grant.
- **Do not stop at just adding `capture_provenance`.** The same review should
  also close the `__import__()` blind spot, since it is a strictly worse
  problem than the one the test currently catches: those calls hide real
  intra-package dependencies (`orchestration.py` -> `evidence.py`, etc.) from
  the very audit this test performs. Either (a) convert those `__import__()`
  calls to ordinary `from .x import y` imports and add each target module
  name to `ALLOWED_RELATIVE_IMPORTS`, restoring the allowlist's ability to see
  the package's real dependency graph, or (b) extend the AST walker to also
  inspect `ast.Call` nodes whose func is `__import__` and validate their
  first argument. Both are code/test changes outside this read-only worker's
  mandate — flagging for the reviewing agent (Sol/Astra) rather than
  implementing here.
- A pure code-move (relocating `capture_provenance`'s functions into
  `scope_aware_fusion.py`) was considered and rejected: it would make
  `scope_aware_fusion.py` the second definition site for validators that
  `scripts/offline_retrieval_replay.py` also needs, reintroducing exactly the
  duplication risk the shared-module design in V2-10 was written to avoid.

## Handoff summary

1. **Inventory**: every V2 module/function is class (b) — synthetic-only
   input, zero wiring into any live route or client. The one exception is
   `_runtime_scope_intent`/`_authorized_policy_market` in
   `app/retrieval/providers.py:169-200`, which is real, unconditional,
   already-in-production pure metadata computation (class "c, compute-only")
   feeding `RetrievalQueryPlan`, consumed today only by the (default-off)
   diagnostic-capture path and the offline replay script — not by the V2
   package itself.
2. **REUSE, not reimplement**, for three of the four synthetic stages:
   context/follow-up resolution (`reference_resolution.py:180`
   `resolve_reference`, real session history), scope authorization
   (`app/evidence.py:150` `approve_evidence` + `chat_orchestrator.py`'s
   `_scope_query`/`_is_cross_market_local_evidence`/
   `_route_or_approve_evidence`, already the same three-way split as V2's
   `ScopeIntent`), and composition/citation binding
   (`app/evidence_contract.py:29` `parse_evidence_contract` +
   `app/response/builder.py:134/137/285`). Only the income-guarantee/
   script-confusable safety checks in V2-04 look like a genuine gap worth
   porting as standalone validator functions. Ranking/fusion
   (`scope_aware_fusion.fuse` vs. production's weighted-additive
   `_merge_hits`, `opensearch_sections.py:1828`) is a genuinely new
   capability with promising offline recall numbers but zero live evidence,
   because the saved 24-case capture has no trusted scope-intent field on any
   case (V2-09 doc).
3. **Default-off is structurally guaranteed** for the V2 package itself (no
   I/O capability exists in the code, not merely behind a flag); the one live
   pure-computation exception (`_runtime_scope_intent`) is safe but should be
   named explicitly as "already partially wired" rather than folded into the
   "fully synthetic" bucket when this inventory is used for the actual R04+
   adapter design.
4. **Rollback** is a non-event today (nothing consumes the new fields except
   the off-by-default diagnostic path); a future real shadow flag should copy
   `services/candidate_control.py`'s fail-open, TTL-cached,
   env-gated pattern, and any `ContextVar`-based capture state
   (`opensearch_sections.py:250-271`) must keep its enable/reset pairing
   exception-safe.
5. **Isolation-allowlist recommendation**: add `"capture_provenance"` to
   `ALLOWED_RELATIVE_IMPORTS` in `test_offline_isolation.py:17` (narrow,
   justified, doesn't weaken isolation) — and separately flag, for reviewer
   attention rather than action here, that `__import__()` calls in
   `orchestration.py`, `ranking.py`, `comparison.py`, `comparison_fixture.py`,
   and `ranking_fixture.py` already bypass this same check today for other
   modules, which is a bigger blind spot than the one currently failing.

No files were modified. No network, AWS, or model calls were made.
