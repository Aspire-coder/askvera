# Phase 3, Lane 6: CX offline evaluation matrix

Status: scaffolding delivered, all xfail-safe today. See `CX_DESIGN.md` for
the full lane breakdown and `CX_LANES.md` for the shared contract; this note
covers only Lane 6's write scope -- `tests/conversation_pack/cx/**` (new).

## What this is

A data-driven offline test matrix covering the required CX case list, plus a
runner (`tests/conversation_pack/cx/test_cx_pack.py`) that is safe to run on
this branch *before* any of Lanes 2-5 and 7 are wired into
`chat_orchestrator.py`. It checks two different things honestly, never
conflating them:

1. **`app.response.outcome.derive_outcome` (Lane 1) is real code, already
   wired.** Every case's expected `OutcomeKind` is asserted against it for
   real, today.
2. **Everything downstream of the outcome is not wired yet.** Localized
   message keys, the partial-answer note, contact dedup, suggestion topics,
   repair acknowledgement, typo clarification wording and answer-language
   detection all route through one small adapter function apiece
   (`_render_cx`, `_partial_answer`, `_contact_supplement`, `_suggestions`,
   `_repair`, `_answer_language`), each importing the real lane module by the
   exact path `CX_LANES.md`'s write-scope table assigns it. Those modules do
   not exist in this worktree, so the import itself fails -- which is the
   correct signal, not a workaround.

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
| `fallback_state_safety_refusal` | 8 | en, es, fr, de, fi, sv, ru, pt |
| `answer_language_parity` | 8 | session language fixed `en`; message written in en/es/fr/de/fi/sv/ru/pt |
| `direct_answer_first` | 2 | en, fi |
| `partial_answer` | 2 | en, fr |
| `one_question_clarification` | 2 | en, de |
| `contact_escalation` | 2 | en, es |
| `supported_only_suggestions` | 2 | en, ru |
| `conversation_repair` | 2 | en, es |
| `typo_tolerance` | 2 | en (typo collision pairs are English-specific by design) |
| `confidence_aware_language` | 2 | en, de |

Every one of the seven required fallback states (evidence missing,
dependency unavailable, cross-market policy, international directory,
ambiguous follow-up, personal account, safety refusal) is covered in all
seven CX_LANES.md route locales this brief names (en, es, fr, de, fi, sv,
ru) plus `pt`, a non-route locale, to exercise the English-copy fallback
path (`services.controlled_copy.localize_reviewed_copy` / English source),
per `CX_DESIGN.md`'s "Rendering" section. `test_every_fallback_state_has_multilingual_parity`
enforces both the seven-language floor and the non-route-language presence
per state, so a new state added without full parity fails collection-time
self-checks, not silently.

`dependency_unavailable` alternates `retrieval_availability` between
`"unavailable"` and `"degraded"` across its eight language cases (R02's two
values), so both reach the matrix without doubling the case count.

## Runner design

`test_cx_pack.py` has one parametrized test, `test_cx_case`, over all 80
cases, plus four manifest self-checks (required fields present, every
required matrix item covered, every fallback state has multilingual parity,
`answer_language_parity` covers every message language, and no case id is
hardcoded in the runner itself -- mirroring
`tests/unit/test_conversation_outcome.py`'s own such check).

Per case, `_run_case`:

1. Builds a duck-typed `metadata` dict / `EvidenceDecision`-shaped stub from
   `case["stub"]` (same stub shape `tests/unit/test_conversation_outcome.py`
   already uses) and calls the real `derive_outcome`. Asserts
   `outcome.kind` matches `case["expected"]["kind"]` -- for real, always,
   regardless of any flag.
2. If any flag in `case["requires"]` is still `False` in `FEATURE_FLAGS`,
   fails cleanly naming which lane(s) are missing (this is the failure an
   `xfail(strict=True)` mark, applied at parametrize time in `_case_params`,
   expects).
3. Otherwise (today, only `direct_answer_first`'s two cases, whose
   `requires` is `["outcome_contract"]` alone) proceeds to
   `_assert_behaviour`, which calls the adapters for whatever the case's
   `requires` list actually names.

## The flip mechanism

`FEATURE_FLAGS` at the top of `test_cx_pack.py`:

```python
FEATURE_FLAGS = {
    "outcome_contract": True,   # Lane 1 -- already wired
    "partial_answer": False,    # Lane 2
    "contact_and_suggestions": False,  # Lane 3
    "personal_account": False,  # Lane 3
    "localization": False,      # Lane 4
    "repair": False,            # Lane 5
    "typo_clarify": False,      # Lane 5
    "answer_language": False,   # Lane 7
}
```

When a lane lands and its module is reachable the way the corresponding
adapter expects, flip its flag to `True`. That alone removes the
`xfail(strict=True)` mark from every case naming that flag in `requires`, so
those cases must pass for real from then on -- `strict=True` means a case
that keeps passing only by accident (the old xfail silently no longer
applying) is caught immediately as a regression if the underlying behaviour
is wrong, and a case that still fails after the flip is caught as an
unresolved defect rather than silently staying green under xfail.

If a lane's real function signature differs from what an adapter guessed
(e.g. `render_outcome`'s actual parameter names), only that one adapter
function needs editing -- never the case data, and never more than one
lane's cases at a time, since each case's `requires` list only names the
flags its own assertions actually call.

## Cases needing LIVE validation

None of these 80 cases claim anything about live model prose; every
assertion is about the typed `OutcomeKind`, message-key presence/absence,
question counts, contact/suggestion sets, and detected languages -- never
exact English wording, per `CX_LANES.md`'s "Copy is data" rule. Once every
`FEATURE_FLAGS` entry is `True` and these cases pass for real, they still
only prove the *offline* rendering/routing/detection layer is correct, the
same limitation `tests/conversation_pack/README.md` documents for Lane G:
"a case that passes here has only been shown correct at the layer its
mechanism actually exercises... never at the layer of 'did the live model
say the right sentence.'"

For the prepared live-run manifest, the CX section should include one live
check per fallback state (does the model's actual prose match the intended
tone for `evidence_missing_detail` / `dependency_unavailable` /
`cross_market_policy_scope` / `international_directory_note` /
`clarify_field` / `personal_account_limit`, and does the safety-refusal path
actually decline rather than comply) plus one live check for
`answer_language_parity` per non-English language (does the model's answer
actually come out in the detected message language, not just get tagged
that way) -- these are not run by this lane.

## Test run

```
pytest tests/conversation_pack/cx -q
  -> 7 passed, 78 xfailed

pytest tests/conversation_pack -q
  -> 62 passed, 4 skipped, 78 xfailed

flake8 tests/conversation_pack/cx/test_cx_pack.py
  -> exit 0 (clean)

git diff --check
  -> exit 0 (clean)
```

The 7 passes are the 2 `direct_answer_first` cases (the only ones whose
`requires` is satisfied by Lane 1 alone) plus the 5 manifest self-checks. The
78 xfails are every other case, each failing for the documented reason
("CX lane not wired: ..."), with `strict=True` so an unexpected pass would
fail the suite instead of hiding a stale flag.
