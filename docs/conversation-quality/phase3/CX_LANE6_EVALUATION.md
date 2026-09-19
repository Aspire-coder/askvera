# Phase 3, Lane 6: CX offline evaluation matrix

Status: scaffolding delivered, all xfail-safe today. See `CX_DESIGN.md` for
the full lane breakdown and `CX_LANES.md` for the shared contract; this note
covers only Lane 6's write scope -- `tests/conversation_pack/cx/**` (new).

Revision note: an earlier version of this doc (28272cb) described a runner
that called `app.response.outcome.derive_outcome` directly on a hand-built
stub. Coordinator review found that this only re-proved Lane 1's own unit
tests and would let a real wiring bug through undetected. This revision
describes the replacement design: every case drives the real
`AIOrchestrator.handle_chat` end to end.

## What this is

A data-driven offline test matrix covering the required CX case list, plus a
runner (`tests/conversation_pack/cx/test_cx_pack.py`) that is safe to run on
this branch *before* any of Lanes 2-5 and 7 are wired into
`chat_orchestrator.py`. Every case builds real `RetrievedDocument`/
`RetrievalResult` fixtures, a real `ChatRequest`, and calls the real
`AIOrchestrator.handle_chat` -- the same offline harness pattern
`tests/conversation_pack/test_conversation_pack.py` already uses (a fixture
retriever, a fake router/model, monkeypatched session/cache/consent/audit
hooks) -- then asserts on the real returned `ChatResponse`. This module loads
that pack's module by file path (`tests/conversation_pack` has no
`__init__.py`, so it isn't import-package-able) and reuses its fixture
builders (`_policy_row`, `_global_directory_row`) and fakes (`_Validator`,
`AIOrchestrator`, `ChatRequest`, `GovernanceDecision`, ...) rather than
redeclaring them.

`chat_orchestrator.py` does not yet attach `ChatResponse.metadata["outcome"]`
(`CX_LANE1_OUTCOME.md`: "The coordinator wires ... into `chat_orchestrator.py`;
this lane does not touch that file"), so every case's primary assertion --
`metadata["outcome"]["kind"]` -- fails today no matter how faithfully its
fixture reproduces the real trigger condition. That is what makes it safe to
gate every case behind the `outcome_contract_wired` flag without risking an
accidental full pass; message-key / contact / suggestion / repair /
answer-language / quality checks are additionally gated behind their own
lane flags on top of that.

## Verified real trigger conditions

Each fixture was run directly (bypassing pytest's xfail wrapper) against the
real `handle_chat` to confirm it reaches the intended code path, not just an
intended-looking one:

| Requirement | Real trigger, confirmed by running the fixture |
|---|---|
| `evidence_missing` | Empty `RetrievalResult` -> `app.evidence.approve_evidence` returns `reason="no_evidence"` -> `failure_layer="evidence_gate"`. |
| `dependency_unavailable` | `RetrievalResult.availability` = `UNAVAILABLE`/`DEGRADED` (R02) -> `_route_or_approve_evidence`'s two R02 sites -> `failure_layer="dependency_unavailable"`, `retrieval_availability` recorded (both values verified). |
| `cross_market_policy` | Two policy rows (target market + US) for a per-market company-policy question -> `approve_evidence` returns `reason="cross_market_policy_request"` (same mechanism as the base pack's `policy_rows_fr_us`/`policy_rows_jp_us`). |
| `international_directory` | One approved `directory_kind="international_sponsoring"` record -> evidence approved, generation proceeds, the scripted answer is delivered unmodified (verified: `failure_layer` is `None`, `response.answer` equals the scripted text). |
| `safety_refusal` (`aws_guardrail`) | Requires *approved* evidence first (confirmed: with no documents, evidence_gate short-circuits before generation ever runs) -- one approved US policy row plus a fake router returning `finish_reason="guardrail_intervened"` -> `failure_layer="aws_guardrail"`. |
| `safety_refusal` (`local_guardrail`) | Fake governance blocks with `provider="bedrock_guardrails"` -> `_governance_failure_layer` -> `"local_guardrail"` (verified). |
| `safety_refusal` (`risk_policy`) | Fake governance blocks with a non-`bedrock_guardrails` provider and `guardrail_action=REVIEW` -> `"risk_policy"` (verified). |
| `personal_account` | No `failure_layer` in this worktree reaches `PERSONAL_ACCOUNT` (confirmed, matches `CX_LANE1_OUTCOME.md`'s own finding); the fixture falls through to a plain `evidence_gate`/`no_evidence` refusal. This is the documented, expected gap, not a fixture bug. |
| `ambiguous_followup` | **Approximation, and confirmed not to reach the intended path today**: two competing approved directory candidates for a vague "the other one" follow-up are both approved and the pipeline answers with the higher-scored one instead of asking which one. The real reference-resolution trigger (`app/orchestrator/reference_resolution.py`, `candidate_flags.narrowing_fallback`) is Lane 5's, and this fixture needs revisiting once that lane exists. Documented in the case's own `notes`. |
| `partial_answer`, `contact_escalation`, `supported_only_suggestions`, `conversation_repair`, `answer_language_parity` | All reach a real, evidence-approved, delivered answer end to end (verified: `failure_layer` is `None` and `response.answer` contains the scripted content, including the appended contact detail for `contact_escalation`). |
| `direct_answer_first` | Reaches a real delivered answer whose text **starts with a deliberate preamble** ("Great question! ..."), not the fact -- built to fail the `answer_starts_with` check today on purpose (see below), not pass vacuously. |
| `one_question_clarification`, `typo_tolerance` | Approximation: empty-evidence fixtures land in the same `evidence_gate` path as `evidence_missing` today, not a clarification path, because the real ambiguous-reference/typo-collision detection they depend on isn't reproduced here. Documented per-case. |

## Case count

80 cases in `tests/conversation_pack/cx/cases.json`.

| Requirement | Count | Languages |
|---|---|---|
| `fallback_state_evidence_missing` | 8 | en, es, fr, de, fi, sv, ru, pt |
| `fallback_state_dependency_unavailable` | 8 | en, es, fr, de, fi, sv, ru, pt (alternates R02 `unavailable`/`degraded`) |
| `fallback_state_cross_market_policy` | 8 | en, es, fr, de, fi, sv, ru, pt |
| `fallback_state_international_directory` | 8 | en, es, fr, de, fi, sv, ru, pt |
| `fallback_state_ambiguous_followup` | 8 | en, es, fr, de, fi, sv, ru, pt |
| `fallback_state_personal_account` | 8 | en, es, fr, de, fi, sv, ru, pt |
| `fallback_state_safety_refusal` | 8 | en, es, fr, de, fi, sv, ru, pt (cycles aws_guardrail/local_guardrail/risk_policy) |
| `answer_language_parity` | 8 | session language fixed `en`; message written in en/es/fr/de/fi/sv/ru/pt |
| `direct_answer_first` | 2 | en, fi |
| `partial_answer` | 2 | en, fr |
| `one_question_clarification` | 2 | en, de |
| `contact_escalation` | 2 | en, es |
| `supported_only_suggestions` | 2 | en, ru |
| `conversation_repair` | 2 | en, es |
| `typo_tolerance` | 2 | en (typo collision pairs are English-specific by design) |
| `confidence_aware_language` | 2 | en, de |

Every one of the seven required fallback states is covered in all seven
CX_LANES.md route locales this brief names (en, es, fr, de, fi, sv, ru) plus
`pt`, a non-route locale exercising the English-copy fallback path.
`test_every_fallback_state_has_multilingual_parity` enforces both the
seven-language floor and the non-route-language presence per state.

`dependency_unavailable` alternates real `RetrievalAvailability.UNAVAILABLE`
and `.DEGRADED` across its eight language cases (R02's two values).

Session countries are always one of the codes
`utils.validators._country_codes()` actually accepts (`US`, `DE`, ...); target
markets named in message text or directory `record_country` metadata
(Kenya, Ghana, "Finland/Aland", ...) are free text and are not validated,
matching how the real directory data works.

## Runner design

`test_cx_pack.py` has one parametrized test, `test_cx_case`, over all 80
cases, plus six manifest self-checks (required fields present with a
"how this case can fail" note, every required matrix item covered, every
fallback state has multilingual parity, `answer_language_parity` covers
every message language, every case is subject to the shared
`outcome_contract_wired` gate, and no case id is hardcoded in the runner
itself).

Per case, `_run_case`:

1. `_run_turn` builds a `_CxRetriever`/`_CxRouter`/`_CxGovernance` from
   `case["stub"]`, wires them into a real `AIOrchestrator` (via `_base_pack`),
   monkeypatches the same session/cache/consent/audit seams
   `test_conversation_pack.py::_run_isolation_session` patches, and calls the
   real `handle_chat`.
2. Asserts `response.metadata["outcome"]["kind"] == case["expected"]["kind"]`
   -- today this always fails because the key is absent.
3. If any flag in the case's effective `requires` (its own list, plus the
   always-included `outcome_contract_wired`) is still `False`, fails cleanly
   naming which lane(s) are missing -- the failure an `xfail(strict=True)`
   mark, applied at parametrize time in `_case_params`, expects.
4. Otherwise proceeds to `_assert_behaviour`, which calls the lane adapters
   (`_render_cx`, `_partial_answer`, `_contact_supplement`, `_suggestions`,
   `_repair`, `_answer_language`) for whatever the case's `requires` list
   actually names, or -- for `direct_answer_first` -- asserts
   `response.answer.startswith(expected["answer_starts_with"])` directly.

## The flip mechanism

`FEATURE_FLAGS` at the top of `test_cx_pack.py`:

```python
FEATURE_FLAGS = {
    "outcome_contract_wired": False,  # Coordinator: chat_orchestrator attaches metadata["outcome"]
    "partial_answer": False,          # Lane 2
    "contact_and_suggestions": False, # Lane 3
    "personal_account": False,        # Lane 3
    "localization": False,            # Lane 4
    "repair": False,                  # Lane 5
    "typo_clarify": False,            # Lane 5
    "answer_language": False,         # Lane 7
    "quality_checks": False,          # Lane 2 (lead-with-the-fact / preamble stripping)
}
```

`outcome_contract_wired` applies to every case automatically
(`_effective_requires`); no case lists it explicitly
(`test_every_case_requires_the_outcome_contract` enforces this). When a lane
lands, flipping its one flag to `True` removes the xfail mark from every
case naming that flag, and those cases must pass for real from then on --
`strict=True` means a case passing only by accident is caught immediately as
a false positive, and a case that still fails after the flip is caught as an
unresolved defect. Case data never needs to change for a flip; only an
adapter function might, if the real lane module's signature differs from its
current best-effort guess -- and for `ambiguous_followup`,
`one_question_clarification` and `typo_tolerance`, the fixture's *documents
and history* likely need revisiting too, since today's approximation doesn't
reach the intended real path (documented per-case above and in `notes`).

## Every case can fail if its feature is broken

Per the coordinator's second review point, each case's `notes` field states
concretely how it can fail once wired (a defect it would actually catch),
not just what it hopes to prove. `direct_answer_first` is the clearest
example: its fixture's fake model deliberately returns a preamble before the
fact ("Great question! ..."), so `answer_starts_with` fails today on its own
merits (nothing strips the preamble yet) rather than passing vacuously
because the scripted text happened to already start with the fact.

## Cases needing LIVE validation

None of these 80 cases claim anything about live model prose; every
assertion is about the typed `OutcomeKind`, message-key presence/absence,
question counts, contact/suggestion sets, and detected languages -- never
exact English wording, per `CX_LANES.md`'s "Copy is data" rule, and the fake
router always returns a scripted answer rather than a live generation. Once
every `FEATURE_FLAGS` entry is `True` and these cases pass for real, they
still only prove the *offline* routing/rendering/detection layer is correct
-- the same limitation `tests/conversation_pack/README.md` documents for Lane
G: "a case that passes here has only been shown correct at the layer its
mechanism actually exercises... never at the layer of 'did the live model
say the right sentence.'"

For the prepared live-run manifest, the CX section should include one live
check per fallback state (does the model's actual prose match the intended
tone for `evidence_missing_detail` / `dependency_unavailable` /
`cross_market_policy_scope` / `international_directory_note` /
`clarify_field` / `personal_account_limit`, and does the safety-refusal path
actually decline rather than comply) plus one live check for
`answer_language_parity` per non-English language (does the model's answer
actually come out in the detected message language) -- these are not run by
this lane.

## Test run

```
pytest tests/conversation_pack/cx -q
  -> 6 passed, 80 xfailed

pytest tests/conversation_pack -q
  -> 61 passed, 4 skipped, 80 xfailed

flake8 tests/conversation_pack/cx/test_cx_pack.py
  -> exit 0 (clean)

git diff --check
  -> exit 0 (clean)
```

The 6 passes are this lane's manifest self-checks. All 80 cases are
`xfail(strict=True)`, each failing on the same, verified, honest reason today
(`ChatResponse.metadata` carries no `"outcome"` key), with `strict=True` so
an unexpected pass would fail the suite instead of hiding a stale flag.
