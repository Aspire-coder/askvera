# Phase 2 Lane F: contact completion

Worktree: `askvera-p2-f-contacts`, branch `p2/f-contacts-20260918`, base
`583b39a`. Wrote only: `app/response/contact_completion.py` (new),
`tests/conversation/test_contact_completion*.py` (new, 3 files),
`docs/conversation-quality/phase2/patches/laneF-multilingual-and-fax-contact.patch`,
this file. `utils/directory_fields.py`, `config/public_contacts.json` and
`app/orchestrator/chat_orchestrator.py` were read but never edited.

## Method

Every requirement in the brief was probed by calling the real,
already-existing machinery - `AIOrchestrator._secure_and_complete_response`
/ `_apply_support_contact_supplement`, `build_support_contact_supplement`,
and `app.evidence.approve_evidence` - with realistic fixtures, mocking only
the Comprehend PII boundary (the same pattern
`tests/unit/test_demo_contact_supplement_separation.py` already uses). No
fix was written before a reproduction showed the real code returning the
wrong answer.

## Requirement-by-requirement disposition

| # | Requirement | Disposition | Evidence |
|---|---|---|---|
| 1 | Never invent a phone, email, address or website | already-holds, pinned | `tests/conversation/test_contact_completion_unit.py::test_no_fields_at_all_still_returns_none_never_fabricates` (new) plus the pre-existing `tests/unit/test_demo_support_contact_helper.py::test_no_approved_contact_returns_none` and `tests/conversation/test_contacts_type_and_country_fidelity.py::test_no_approved_fields_never_fabricates_a_contact` |
| 2 | Keep the contact's country and purpose | already-holds, pinned | `tests/conversation/test_contact_completion_country_scope.py` (new); relies on `_find_matching_support_contact_record`'s whole-segment `record_country` match, unchanged here |
| 3 | Distinguish office phone, ordering phone, Customer Care, fax and email | **violated and fixed** (fax was silently dropped, not mislabelled) | see "Defect 2" below |
| 4 | Append nothing when the user did not ask and the answer doesn't recommend contact | already-holds, pinned | `tests/conversation/test_contact_completion_unit.py::test_answer_without_a_care_recommendation_gets_no_fax_fallback_either`; pre-existing `_CARE_CONTACT_RECOMMENDATION_RE` gate for English, unchanged |
| 5 | When evidence lacks the detail, still say who to contact, without fabricating | already-holds, pinned | pre-existing `support_contact_unavailable` metadata path leaves the model's own answer text untouched; the model's own sentence (e.g. "contact customer care") is what names the channel, not this module |
| 6 | Cover multilingual answers | **violated and fixed** | see "Defect 1" below |
| 7 | Sponsoring-directory contacts usable from any session country; company-policy facts restricted to the authorized market | already-holds, pinned | `tests/conversation/test_contact_completion_country_scope.py` (new), mirroring the existing negative control in `tests/unit/test_demo_followup_resolution.py::test_us_session_cannot_get_france_policy_after_a_sponsoring_exchange` |

## Defect 1: "recommends contact" detection was English-only

`_CARE_CONTACT_RECOMMENDATION_RE` in `app/orchestrator/chat_orchestrator.py`
only matches English verb+noun phrasing ("contact customer care", "reach
out to support", ...). Reproduced end to end: a Kenya directory record with
an approved phone and email, and an answer that recommends contacting
"le service client" / "den Kundenservice" / "atención al cliente" / etc.,
entirely in French, German, Spanish, Dutch, Italian, Portuguese, Finnish,
Swedish or Norwegian, produces **no supplement at all** -
`_secure_and_complete_response`'s metadata carries neither
`support_contact_supplemented` nor `support_contact_unavailable`; the
eligibility check itself returns early. Confirmed for all nine languages
(see git history of this branch for the throwaway repro script; captured
permanently as `tests/conversation/test_contact_completion_orchestrator_wiring.py::test_a_non_english_care_recommendation_gets_the_supplement`,
xfail(strict=True) until the patch is applied).

Fix: `app/response/contact_completion.py::recommends_contact_in_language`
adds ONE bounded, documented per-language table for exactly those nine
languages (mirroring the English regex's own shape: a contact verb phrase
followed by a customer-care/support/office noun phrase - not a loose
keyword list, verified by matching negative controls in the same
languages). English is deliberately absent from the table: the
orchestrator's own regex keeps owning English detection, so the two never
duplicate the same vocabulary. An unrecognised or unlisted language returns
`False` - append nothing, per the "fail conservatively" instruction.

## Defect 2: a fax-only approved contact was silently dropped

`utils.directory_fields.build_support_contact_supplement` only ever picks a
phone, then an email/website, then (only if hours were requested) business
hours - it never considers a fax value. Reproduced end to end: a Kenya
record whose ONLY approved field is `{"Fax": "+254 20 999999"}`, with an
answer that recommends contacting customer care, leaves the answer
unchanged and sets `support_contact_unavailable: True` in the metadata -
even though the approved evidence does carry a usable contact detail. This
is not a mislabelling (fax is never presented as a phone; the existing
`order_phone`-vs-`phone` distinction was reproduced as already correct, see
`tests/conversation/test_contacts_type_and_country_fidelity.py`), it is an
omission that understates what the evidence contains.

Fix: `app/response/contact_completion.py::build_contact_supplement_with_fax_fallback`
wraps the existing function unchanged and, ONLY when it returns `None`
because nothing else qualified, offers a fax value under its own "Fax"
label as a last resort. A real phone/email/website in the same record still
wins every time (pinned by
`tests/conversation/test_contact_completion_unit.py::test_a_phone_still_wins_over_a_fax_in_the_same_record`
and, end to end,
`tests/conversation/test_contact_completion_orchestrator_wiring.py::test_the_fax_fallback_still_never_beats_a_real_phone_end_to_end`,
which already passes today - that guarantee predates this lane and is
merely re-proven end to end here).

## Patch

`docs/conversation-quality/phase2/patches/laneF-multilingual-and-fax-contact.patch`
is a 3-hunk unified diff against `app/orchestrator/chat_orchestrator.py`
(the sole-writer file this lane may not edit directly):

1. imports `build_contact_supplement_with_fax_fallback` and
   `recommends_contact_in_language` from the new module;
2. widens the eligibility check in `_apply_support_contact_supplement` to
   also try `recommends_contact_in_language(answer, language)` when the
   existing English regex does not match;
3. swaps the `build_support_contact_supplement` call for
   `build_contact_supplement_with_fax_fallback` (same call signature, same
   return contract).

Verified:

- `git apply --check` against this worktree's `583b39a` HEAD: clean.
- Flip proof: copied the worktree into a scratch git repo (never touching
  this worktree's own git state), applied the patch there, removed the
  `xfail` markers from the copied test file only, and re-ran
  `tests/conversation/test_contact_completion_orchestrator_wiring.py`:
  11 passed (was 10 xfailed + 1 passed before the patch).

Note on `git diff --check`: staging the patch file itself reports two
"trailing whitespace" lines inside the `.patch` file. Both are unified-diff
context lines representing a genuinely empty line in the source (a
context line's leading space marker with no further content) - required
patch syntax, not an actual whitespace defect introduced by this change.
The changed Python files themselves have no such lines (see the run log
below).

## Test run

```
<PYTHON> -m pytest tests/conversation/test_contact_completion_unit.py \
  tests/conversation/test_contact_completion_orchestrator_wiring.py \
  tests/conversation/test_contact_completion_country_scope.py \
  tests/unit/test_demo_contact_supplement_separation.py \
  tests/unit/test_demo_contact_block_rendering.py \
  tests/unit/test_answer_fact_preservation_scrub_placeholder.py \
  tests/unit/test_cross_market_refusal_explanation.py \
  tests/conversation \
  tests/unit/test_chat_orchestrator.py \
  -p no:cacheprovider --basetemp <scratchpad>/pytest-p2f
253 passed, 11 xfailed
PYTEST_EXIT=0
```

(11 xfailed = 10 new multilingual/fax-fallback cases in
`test_contact_completion_orchestrator_wiring.py`, plus one pre-existing
xfail already in `tests/conversation` unrelated to this lane.)

```
<PYTHON> -m flake8 app/response/contact_completion.py \
  tests/conversation/test_contact_completion_unit.py \
  tests/conversation/test_contact_completion_orchestrator_wiring.py \
  tests/conversation/test_contact_completion_country_scope.py
FLAKE8_EXIT=0
```

`git diff --check` on the changed Python files: clean (see note above about
the patch file's own unified-diff context lines).

## Limitations

- The nine-language vocabulary is reviewed for shape and tested with
  positive and negative controls, but it is not a native-speaker legal or
  marketing review of the phrasing - the same caveat every other
  per-language table in this codebase (e.g.
  `utils.directory_fields._SUPPORT_CONTACT_LABEL_TRANSLATIONS`) already
  carries.
- Detection is scoped to the answer's own `language` parameter (the same
  value `_apply_support_contact_supplement` already threads through for
  label rendering), not to auto-detecting the language of arbitrary text.
  An answer generated in a language the selector was not set to (a known,
  already-documented limitation elsewhere in this project, see
  `TASK_BOARD.md`'s A6 note) would still be missed - this lane does not add
  language auto-detection.
- No other language beyond the nine listed is covered. A tenth language
  would need its own reviewed pattern added to the same table, per the
  brief's "one bounded vocabulary" instruction, not a general-purpose
  translation lookup.
