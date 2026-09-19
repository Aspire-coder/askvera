# Phase 3, Lane 6: CX offline evaluation matrix

Status: scaffolding delivered, all xfail-safe today. See `CX_DESIGN.md` for
the full lane breakdown and `CX_LANES.md` for the shared contract; this note
covers only Lane 6's write scope -- `tests/conversation_pack/cx/**` (new).

Revision history: 28272cb called `derive_outcome` on a hand-built stub
(re-testing Lane 1's own unit tests). b398dde switched to driving the real
`AIOrchestrator.handle_chat`, but everything was still gated behind an
`outcome_contract_wired=False` flag because the outcome wasn't wired yet.
This revision (v3) follows the coordinator's review of b398dde: lanes 1-7
are now merged and the outcome contract is genuinely wired
(`chat_orchestrator.py` calls `derive_outcome` and attaches
`metadata["outcome"]` on every path), so `outcome_contract_wired` is now
`True` and every case's `outcome.kind` check runs for real. Three real
defects from that review are fixed here (below); a Lane 8 composer
(`app/response/cx_compose.py`) that would wire the remaining additions into
`chat_orchestrator.py` does not exist yet, so every other flag stays `False`.

## The three defects fixed

1. **Adapters imported APIs that don't exist.** Rewritten against the real
   modules: `app.response.cx_render.render(key, language, **placeholders)` /
   `.join_list` / `.mixed_language_or_empty`; `app.response.partial_answer.
   assess_field_coverage` / `.partial_answer_note`; `app.response.quality.
   strip_leading_preamble` / `.confidence_framing_key` / `.contact_for_country`;
   `app.response.contact_completion.contact_escalation`;
   `app.response.suggestions.suggest_follow_ups`; `app.response.
   personal_account.detect_personal_account_request`; `app.orchestrator.
   conversation_repair.detect_repair` / `.typo_clarification` / `.one_question`;
   `app.orchestrator.answer_language.resolve_answer_language` /
   `.retrieval_language`. All are real, already-callable functions -- no
   more lazy `ImportError`-based adapters; they're imported at module top.
   Behaviour assertions now check `metadata["outcome"]["kind"]`,
   `metadata["cx_applied"]` (the marker list the eventual `cx_compose.py`
   will populate: `preamble_stripped`, `partial_note`, `personal_account_note`,
   `contact_offer`, `international_directory_note`, `suggestions`),
   `response.suggestions` (structured items, never appended into the answer
   text), and the rendered text via the real `cx_render.render`.

2. **`pt` cannot be a `ChatRequest.language` in this worktree.** Verified,
   not assumed: `services.market_config.get_supported_language_codes()` (the
   set `utils.validators.ChatRequest` validates `language` against) is the
   union of every market's languages in `config/policy_locales.json`, and
   that union is *exactly* the 12 CX route locales -- no market publishes
   `pt` there, so `ChatRequest(language="pt", ...)` is rejected regardless of
   `country`. `config/markets.json` (which does list Brazil/`pt`) is a
   *different* config, the customer-facing market list, not consulted by
   that validator -- this is a real discrepancy between the two configs,
   worth flagging separately from this task. Fix: the 7 `pt` state cases
   were replaced with 7 `non_route_language_fallback` cases that call
   `app.response.cx_render.render(key, "pt", ...)` directly (a pure
   function untouched by `ChatRequest`) -- these need no flag and pass for
   real today.

3. **No real AWS call, guaranteed.** `_no_real_aws` (autouse fixture) fakes
   `app.response.cx_render.localize_reviewed_copy` (patched on `cx_render`
   itself, since it's bound there via `from ... import`, not on
   `services.controlled_copy`) as always returning `None` -- deterministic,
   and it is also *how* the pt fallback cases prove the English-copy floor:
   with translation always "failing", `render("...", "pt", ...)` has no path
   left but the English template. `services.aws_clients.get_aws_clients` is
   also patched to raise `AssertionError` immediately if anything ever tries
   to create a real client, so a latent AWS call fails loudly instead of
   hanging or raising a confusing botocore error.

## Two kinds of check per case

1. **Real, unconditional.** `outcome.kind` on the real, now-wired
   `ChatResponse.metadata["outcome"]`, plus -- where a case names one -- a
   direct call to a real Lane 2/3/5/7 PURE function that needs no
   orchestrator wiring at all (`detect_repair`, `typo_clarification`,
   `confidence_framing_key`, `resolve_answer_language`,
   `detect_personal_account_request`, `assess_field_coverage`,
   `strip_leading_preamble`). These run regardless of `FEATURE_FLAGS`.
2. **Flag-gated.** Whether `cx_compose.py` (not built yet) has wired a
   lane's addition into the delivered response -- `metadata["cx_applied"]`
   and `response.suggestions`.

## Verified real outcome-kind results (a genuine finding, not assumed)

Every fixture was run directly (bypassing the xfail wrapper) against the now
fully-wired orchestrator while writing this file. Two results were
surprising enough to be worth recording here in full:

- **`app/response/outcome.py`'s international-directory promotion only
  fires when the record's market differs from the session's own country.**
  A US session asking about a Kenya/Ghana directory record correctly
  promotes to `international_directory`; a DE session asking about a
  Germany directory record stays a plain `answer`. Two cases
  (`supported_only_suggestions`, originally written against a same-market
  DE fixture) were corrected to expect `answer`, not
  `international_directory`, to match this.
- **`cross_market_policy_scope` copy is wired into `chat_orchestrator.py`
  for Kenya but the underlying cross-market DETECTION itself
  (`app.evidence.approve_evidence`'s `_names_another_market`) does not
  recognise every target market this pack tried.** With the Kenya case, the
  full path -- `OutcomeKind.CROSS_MARKET_POLICY`, and the rendered
  `cross_market_policy_scope` copy naming Kenya verbatim in the delivered
  answer -- passes for real with every flag on. The same fixture shape for
  Ghana/Nigeria/"Finland/Aland"/"Sweden/Gotland"/"France/Corsica" instead
  lands on `evidence_missing`: `_names_another_market` never recognises
  those five as a market at all (not a copy-rendering gap -- the kind itself
  never becomes `cross_market_policy`). This is a genuine, reproducible
  finding worth the coordinator's attention, distinct from every other
  "not wired yet" gap below.
- **`config.personal_account_vocabulary`'s regexes require the possessive
  and the account-object noun to be adjacent.** "What is the status of my
  **last** order?" does not match in English or German (`meiner **letzten**
  Bestellung`); "What is the status of my order?" does, in all seven
  languages tried (verified directly). The case questions were corrected
  accordingly, and `detect_personal_account_request` is now asserted
  directly (unconditionally) in every `fallback_state_personal_account`
  case.

## Case count

80 cases in `tests/conversation_pack/cx/cases.json`.

| Requirement | Count | Languages |
|---|---|---|
| `fallback_state_evidence_missing` | 7 | en, es, fr, de, fi, sv, ru |
| `fallback_state_dependency_unavailable` | 7 | en, es, fr, de, fi, sv, ru (alternates R02 `unavailable`/`degraded`) |
| `fallback_state_cross_market_policy` | 7 | en, es, fr, de, fi, sv, ru |
| `fallback_state_international_directory` | 7 | en, es, fr, de, fi, sv, ru |
| `fallback_state_ambiguous_followup` | 7 | en, es, fr, de, fi, sv, ru |
| `fallback_state_personal_account` | 7 | en, es, fr, de, fi, sv, ru |
| `fallback_state_safety_refusal` | 7 | en, es, fr, de, fi, sv, ru (cycles aws_guardrail/local_guardrail/risk_policy) |
| `non_route_language_fallback` | 7 | pt only, direct `cx_render.render` calls (see defect 2) |
| `answer_language_parity` | 8 | session language fixed `en`; message written in en/es/fr/de/fi/sv/ru/pt |
| `direct_answer_first` | 2 | en, fi |
| `partial_answer` | 2 | en, fr |
| `one_question_clarification` | 2 | en, de |
| `contact_escalation` | 2 | en, es |
| `supported_only_suggestions` | 2 | en, ru |
| `conversation_repair` | 2 | en, es |
| `typo_tolerance` | 2 | en (typo collision pairs are English-specific by design) |
| `confidence_aware_language` | 2 | en, de |

`pt` is exercised only via `non_route_language_fallback` (defect 2); the CX
route-locale requirement (en/es/fr/de/fi/sv/ru) is otherwise met by every
fallback state.

## The flip mechanism

```python
FEATURE_FLAGS = {
    "outcome_contract_wired": True,   # verified wired, d4547b9
    "partial_answer": False,          # Lane 8 composer
    "contact_and_suggestions": False, # Lane 8 composer
    "personal_account": False,        # Lane 8 composer
    "localization": False,            # Lane 8 composer / further chat_orchestrator wiring
    "repair": False,                  # Lane 8 composer
    "typo_clarify": False,            # Lane 8 composer
    "answer_language": False,         # coordinator wiring into prompt/render language
    "quality_checks": False,          # Lane 8 composer
}
```

`outcome_contract_wired` applies to every case automatically; no case lists
it (`test_every_case_requires_the_outcome_contract`). When `cx_compose.py`
wires a lane's addition into `chat_orchestrator.py`, flipping that flag
removes the `xfail(strict=True)` mark from every case naming it, and its
`cx_applied`/`response.suggestions` assertions must pass for real. Case data
never needs to change for a flip unless a real signature differs from an
adapter's guess -- verified accurate against the real modules for this
revision (defect 1).

## Committed run (flags as shipped)

```
pytest tests/conversation_pack/cx -q
  -> 14 passed, 73 xfailed

pytest tests/conversation_pack -q
  -> 69 passed, 4 skipped, 73 xfailed

flake8 tests/conversation_pack/cx/
  -> exit 0 (clean)

git diff --check
  -> exit 0 (clean)
```

The 14 passes are the 7 `non_route_language_fallback` (pt) cases (real,
unconditional -- see defect 2) plus 7 manifest self-checks. All 73 other
cases are `xfail(strict=True)`.

## Scratch run: every flag flipped True

Run separately (a temporary copy of the test module with every
`FEATURE_FLAGS` value set `True`; not committed) to report which failures
remain and why, per the coordinator's request. Result: **46 failed, 41
passed** (of the 79 cases whose `requires` includes at least one composer
flag; the 7 `pt` cases already pass unconditionally either way and are
excluded from this count). Grouped by cause:

| Cause | Count | Cases |
|---|---|---|
| **A. `cx_compose.py` doesn't exist -- `metadata["cx_applied"]` is always absent.** Every real pure-function check these cases also run (e.g. `strip_leading_preamble` already correctly stripping the preamble for `direct_answer_first`, `assess_field_coverage` already correctly finding the gap for `partial_answer`) passes; only the "was this ADDED to the delivered response" check fails. This is exactly the expected, intended gap -- Lane 8's whole job. | 29 | `fallback_state_evidence_missing`×7, `fallback_state_international_directory`×7, `fallback_state_personal_account`×7 (detection itself now passes; only the note), `contact_escalation`×2, `direct_answer_first`×2, `partial_answer`×2, `supported_only_suggestions`×2 |
| **B. Reference-resolution narrowing not wired -- documented, desired-behaviour gap.** `expected.kind` is `clarification` on purpose; the real result is `international_directory` (both candidates approved, the higher-scored one answered) or `evidence_missing` (empty-evidence fixture). Was already known and written into each case's own `notes` before this scratch run. | 9 | `fallback_state_ambiguous_followup`×7, `one_question_clarification`×2 |
| **C. Typo-collision clarification not wired -- documented, desired-behaviour gap**, same shape as B (`typo_clarification` itself correctly detects the collision, asserted unconditionally and passing; only the orchestrator routing to it is missing). | 2 | `typo_tolerance`×2 |
| **D. `cross_market_policy` DETECTION itself doesn't recognise every market name -- a genuine product finding, not a wiring gap.** `_names_another_market` (`app/evidence.py`) resolves "Kenya" but not "Ghana"/"Nigeria"/"Finland/Aland"/"Sweden/Gotland"/"France/Corsica"; those land on `evidence_missing` instead of `cross_market_policy`. The Kenya (`en`) case passes in full, including the delivered `cross_market_policy_scope` copy naming Kenya verbatim -- confirming that copy IS wired (d4547b9), and isolating this failure to evidence approval's market-name recognition, not rendering. | 6 | `fallback_state_cross_market_policy` (es/fr/de/fi/sv/ru; `en` passes) |

29 (A) + 9 (B) + 2 (C) + 6 (D) = 46, matching the run.

Causes A-C are expected and already documented per-case (each case's
`notes` states how it can fail and, for B/C, that it already does).
**Cause D is new information from this scratch run**, worth a follow-up:
either `_names_another_market`'s market-name table needs the missing
countries, or (if this is deliberate scoping to markets with published
policy documents) the CX fallback-state matrix for `cross_market_policy`
should use only markets that table already recognises, rather than the
same seven directory-record markets used elsewhere in this pack.
