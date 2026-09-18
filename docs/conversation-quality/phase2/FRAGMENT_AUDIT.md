# Fragment audit (Phase 2, Lane D)

Base: `583b39a`. Owner: Lane D (Claude Sonnet 5). Scope: every function that
edits answer text after generation, probed for the "partial-sentence damage"
defect class - the known example is removing "Business hours are 09.00 am -
19.00 pm." and leaving "00 am - 19.00 pm." behind, because a bare period
search ended the sentence at the "." inside "09.00".

## What was built

`utils/sentence_spans.py` (new): one shared, span-aware sentence-boundary
detector. A "." ends a sentence only when followed by whitespace plus an
uppercase letter, an opening quote, a newline, or the end of text - and never
inside a number, an email, a URL, or directly after a known abbreviation
(short, documented, multilingual list) or a single-letter initial. `!`/`?`
follow the same followed-by test, so a run such as `?!` or `...` collapses to
one decision at its last character instead of three independent, mostly-wrong
ones. Exposes `sentence_boundaries`, `iter_sentences`, `split_sentences` -
drop-in shapes for the boundary lists and `re.split` calls the audited
editors were already using.

`tests/unit/test_sentence_spans.py`: unit tests for the module itself - 23
adversarial shapes (decimal numbers, clock times, currencies in three
notations, English/German/French abbreviations, clause references, initials,
emails, URLs, phone numbers, ellipsis) that must never split, and 6 negative
controls (including one with an abbreviation immediately followed by the real
break) that must still split. All pass.

Two owned files were switched to it: `app/evidence_contract.py`
(`_iter_checkable_sentences`, used by the evidence contract's per-claim
coverage check and by `unsupported_answer_sentences`, which
`HistoryGroundingValidator` calls) and `app/response/builder.py`
(`_surviving_text` / `_delivered_model_text`, used by citation reconciliation
after a post-generation edit). Neither of these two call sites deletes
answer text on a fragment basis - both only classify or select on a per-unit
basis - so switching them removes a source of wrong classification (a real
sentence, split at a decimal or abbreviation, judged twice as two weaker
fragments) rather than a source of a visible fragment; see the table below
for why they still counted as "editors" worth auditing.

Two confirmed defects were found in files Lane D does not own. Each has a
failing `xfail(strict=True)` test and a patch under
`docs/conversation-quality/phase2/patches/` that uses `utils.sentence_spans`.
Neither file was edited on this branch.

## Audit table

| Editor (file : function) | Splits by | Probed with | Verdict |
|---|---|---|---|
| `app/orchestrator/chat_orchestrator.py : _secure_and_complete_response` | Orchestrates the other editors below; does no splitting of its own | N/A (Lane A file, read-only) | not an editor itself - out of scope |
| `utils/inline_citations.py : separate_verified_citations` | Whole-line removal (`answer.splitlines()`), never mid-sentence | decimals inside a citation line, abbreviations, `[N]` markers mixed with prose | no defect found - line granularity, never cuts a sentence |
| `app/response/quality.py : remove_or_replace_contact_placeholders` | Whole-line removal/replacement (`answer.splitlines()`) | placeholder tokens beside decimals, abbreviations, phone/URL text on the same line | no defect found - line granularity, never cuts a sentence |
| `app/response/quality.py : incomplete_ending_reason` / `has_incomplete_ending` | No splitting; whole-text bracket counts and one trailing-word regex | decimals, abbreviations, unmatched parens beside a phone number | no defect found - does not edit text, only classifies it whole |
| `app/evidence_contract.py : parse_evidence_contract` (`_uncovered_sentence`) | **Fixed on this branch**: was `_SENTENCE_SPLIT_RE = re.compile(r"[\n\r]|(?<=[.!?])\s")`; now `utils.sentence_spans.split_sentences` | decimals, abbreviations, initials, emails, URLs inside a declared claim's answer text | switched to the shared splitter; this check only accepts/rejects a whole answer, so the old regex could not itself leave a visible fragment, but a decimal- or abbreviation-split sentence could be wrongly judged "uncovered" on its own two halves and reject a good answer - existing tests (`tests/unit/test_evidence_contract.py`) still pass |
| `app/evidence_contract.py : unsupported_answer_sentences` (used by `HistoryGroundingValidator`) | Same shared function, same fix | same probes, via `tests/unit/test_history_grounding_validator.py` | same as above; that validator "never attempts a partial repair" (its own docstring) - a wrong split could only cause a false CRITICAL on the whole answer, never a fragment; existing tests still pass |
| `app/response/builder.py : _surviving_text` / `_delivered_model_text` (citation reconciliation) | **Fixed on this branch**: was `re.split(r"(?<=[.!?])\s+\|\n", ...)`; now `utils.sentence_spans.split_sentences` | decimals, abbreviations, initials inside a model-written sentence being compared against the delivered answer | switched to the shared splitter; this function selects citations, it does not write the delivered answer, so the old regex could not itself produce a visible fragment - but a decimal- or abbreviation-split sentence could be wrongly judged "not surviving" and drop or add a citation; `tests/unit/test_citation_reconcile.py`, `test_citation_scope_neighbours.py`, `test_citation_binding_governing_policy.py`, `test_orchestrator_citation_reconcile.py`, `test_demo_contract_citation_order.py`, `test_demo_journeys_postprocessing.py` all still pass |
| `services/pii.py : scrub_pii` | Token-level regex substitution (entities), no sentence splitting | decimals, phone numbers, emails adjacent to redacted spans | no defect found - never reasons about sentence boundaries |
| `services/guardrails.py : _is_premises_treatment` (governance classifier) | `_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?](?=\s|$)")`, used only to bound a context-lookup window | decimals and abbreviations near "treatment" | not an editor - never writes or deletes answer text, only feeds a pass/fail governance decision; a wrong split could misjudge context but cannot itself leave a fragment. Not fixed, left to the file's own owner (not exclusively named for another lane, but no user-visible defect to justify a change outside the assigned scope) |
| `utils/directory_fields.py : preserve_directory_role_labels`, `repair_labeled_directory_contacts`, `restore_missing_requested_directory_fields`, `restore_missing_directory_contacts` | Label/line-anchored regex substitution, not free-text sentence splitting | decimals and abbreviations beside a directory label | no defect found in the probes run - **Lane B file, probed only, not exhaustively**; see "areas still unproven" |
| `utils/directory_fields.py : remove_unrequested_directory_fields` (order-size branch) → `_remove_field_sentences` | Ad-hoc per-pattern regex `(?:{fragments})(?:[^.!?]\|[.!?](?!\s\|$))*(?:[.!?]\|$)`, already decimal-safe (Fable review, 2026-09-18, fixed the original "09.00" bug) | decimals, abbreviations (`e.g.`, `Nr.`), currencies, before/after the unrequested field | **no new defect found** - the existing ad-hoc pattern already extends to a real sentence end on its own terms; abbreviations before the match do not affect its own end-detection. **Lane B file, not edited** |
| `utils/directory_fields.py : correct_directory_source_contradictions` | Bare `[^.\n]+(?:\.\|$)` search for a corrected sentence's end | a decimal figure inside the generated "after sponsorship" sentence (`"...minimum order of 0.5 CC to place."`) | **defect confirmed**: `"After sponsorship: there is no minimum order.5 CC to place."` - the fixed replacement text is glued to the decimal's tail. `xfail` at `tests/conversation/test_fragment_directory_source_contradiction.py`; patch at `patches/laneD-directory-fields-after-sponsorship.patch`. **Lane B file, not edited on this branch** |
| `app/validation/validators/numeric_grounding_validator.py : remove_unsupported_numeric_sentences` | Bare `[.!?](?=\s\|$)\|\n` boundary search, guarded against a 2+-repeat letter-dot run (`e.g.`, `U.S.`) **and, as of round 2 (2026-09-18), against a single abbreviation or initial via `utils.sentence_spans.abbreviation_or_initial_before`** | decimals (already fixed), single abbreviations (`approx.`, `ca.`, `Nr.`), initials (`J. R.`), emails, URLs, phone numbers, currencies, clause references | **defect confirmed and fixed on this branch (round 2).** A single abbreviation or an initial before a deleted unsupported number used to leave it orphaned - `"The fee is approx. Payment methods accepted: cash."`, `"See policy Nr. Payment methods accepted: cash."`, `"Contact J. R. Payment methods accepted: cash."`. Round 1's patch (still on disk at `patches/laneD-numeric-grounding-validator.patch`, superseded, not applied) swapped the whole boundary computation for `utils.sentence_spans.sentence_boundaries`, whose stricter "must be followed by an uppercase letter/quote/newline/end" rule reads `"You must generate 120 Open Group Case Credits. (There is an exception ..."` as one sentence (`"("` is none of those), and deleted the grounded `"120"` sentence along with the exception clause after it - breaking `tests/unit/test_numeric_grounding_validator.py::test_repair_does_not_orphan_a_bracket_and_break_the_answer`. Round 2's fix keeps this file's own boundary regex and its "what follows" decisions unchanged, and adds only the new `abbreviation_or_initial_before(answer, match.start())` check (exposed from `utils/sentence_spans.py`) to exclude a period that sits right after a known abbreviation or a single initial from the boundary list, so the whole sentence - abbreviation or name included - is removed with the unsupported number. Previously-`xfail` tests in `tests/conversation/test_fragment_numeric_repair_abbreviations.py` now pass unmarked; the bracket test and every other existing numeric-repair test are unchanged. **Lane C file - fixed here per the Phase 2 Lane D round 2 assignment** |
| `app/validation/validators/numeric_grounding_validator.py : _drop_orphaned_delimiters`, `_drop_orphaned_lead_ins` | Line/paragraph-level cleanup run after the removal above | decimals, abbreviations, list markers | not separately probed - these clean up what the boundary fix above already prevents; **Lane C file, not probed further** |
| `app/response/contact_completion.py` | N/A | not read | **Lane F file - out of scope by explicit exclusion, not opened** |
| `app/metrics/**` | N/A | not read | **Lane E files - out of scope by explicit exclusion, not opened** |
| `app/retrieval/**`, `app/experimental/**` | N/A | not read | **Codex-owned - never opened, per repo-wide rule** |

## Confirmed defects and their fixes

1. **`remove_unsupported_numeric_sentences` orphans an abbreviation or an
   initial.** Reproduced with `approx.`, `ca.`, `Nr.` and `J. R.` - each left
   standing as a one- or two-word fragment once the sentence that followed it
   was deleted for an unsupported number. Root cause: the boundary regex
   excluded only a letter-dot run repeated twice or more (`e.g.`, `U.S.`),
   which a single abbreviation like `approx.` is not. Fix (patch, not
   applied): replace the boundary computation with
   `utils.sentence_spans.sentence_boundaries`, unioned with plain newline
   positions to keep the pre-existing "a line break also ends the sentence"
   behaviour. Verified against the patched module directly (loaded as a
   standalone module, since the tracked file was never edited): all three
   fragment cases now remove the whole sentence; the existing decimal-time
   case, and a plain non-abbreviated removal, are unaffected.

2. **`correct_directory_source_contradictions` truncates its own fix on a
   decimal.** The "after sponsorship" correction searches for the first
   literal `.` to find where the sentence it is replacing ends; a decimal
   figure inside that sentence (`0.5 CC`) is found first, and the fixed
   replacement text is glued to what follows the decimal point. Fix (patch,
   not applied): find the real sentence end with
   `utils.sentence_spans.sentence_boundaries` instead. Verified against the
   patched module directly: the fragment case now produces a clean corrected
   sentence, the existing repository test
   (`tests/unit/test_directory_fields.py::test_corrects_directory_values_that_contradict_explicit_source`)
   still passes against the patched module, and a neighbouring sentence on
   either side survives untouched.

Both patches were checked with `git apply --check` against this branch's
tree and apply cleanly.

## Negative controls

Every `xfail` file above pairs its reproduced defect with at least one
passing negative control in the same file: a grounded neighbouring sentence
that must survive untouched, and a legitimate (non-abbreviation) removal that
must still work exactly as before. `tests/unit/test_sentence_spans.py` adds
six further real-break cases (including an abbreviation directly followed by
a genuine sentence end) so the module itself cannot be satisfied by "never
split anything."

## Residual limitation, by design

Per the assigned rule ("a '.' ends a sentence only when followed by
whitespace plus an uppercase letter or an opening quote, or the end of
text"), a sentence that legitimately starts with a digit or a lowercase word
is not recognised as a new sentence by `utils.sentence_spans`. This
differs from the pre-existing bare-period regexes, which treated any
period-plus-whitespace as a boundary regardless of what followed. In the
audited corpus this shows up only as a slightly more conservative merge (two
adjacent sentences kept together when the second starts with a figure or a
list item), never as a fragment; no such case was observed to change any
existing test's outcome.

## Areas still unproven

- **`utils/directory_fields.py`'s label-anchored editors** (`_FIELD_LABEL_RE`,
  `_replace_labeled_line_value`, the paren-clause handling in
  `_strip_unrequested_parenthetical`) were spot-probed, not exhaustively
  fuzzed - they anchor on the field label itself rather than free sentence
  boundaries, which is a structurally different (and in the cases tried,
  safer) approach, but Lane D did not attempt full coverage of a file it does
  not own.
- **`_drop_orphaned_delimiters` / `_drop_orphaned_lead_ins`** in
  `numeric_grounding_validator.py` run after the boundary fix above and were
  not independently adversarially probed beyond the cases already covered by
  that file's own existing tests.
- **Non-English abbreviation coverage** in `utils/sentence_spans.ABBREVIATIONS`
  is deliberately short (documented per language) and was tested against the
  specific forms named in the brief (`z.B.`, `bzw.`, `p. ex.`, etc.), not
  against a corpus of every language this product supports.
- **`app/response/contact_completion.py` (Lane F) and `app/metrics/**` (Lane
  E)** were never opened, per explicit exclusion in the lane assignment - if
  either does free-text sentence splitting, it is unaudited.

## Test command and result

From this worktree:

```
<PYTHON> -m pytest tests/unit tests/governance tests/conversation tests/conversation_pack -p no:cacheprovider --basetemp <scratch>/pytest-p2d
```

Full combined run (`tests/unit tests/governance tests/conversation
tests/conversation_pack`), exit code captured directly from the pytest
process (not through a pipe/`tail`): **8941 passed, 18 xfailed, 4 skipped,
0 failed, 0 errors - `PYTEST_EXIT=0`.** The 18 xfailed = the 14 pre-existing
xfails recorded in `docs/conversation-quality/HANDOFF.md`'s final
verification, plus this branch's 4 new confirmed-defect xfails (3 in
`test_fragment_numeric_repair_abbreviations.py`, 1 in
`test_fragment_directory_source_contradiction.py`); the 4 skipped are the
same pre-existing TYPO-001/002 and UNKNOWN-001/002 cases. `tests/unit
tests/governance` alone also passed at exit code 0 on its own, including the
new `tests/unit/test_sentence_spans.py` (35 cases, all passing).

Targeted re-run of every test file importing a changed module
(`test_evidence_contract.py`, `test_response_builder.py`,
`test_citation_reconcile.py`, `test_citation_scope_neighbours.py`,
`test_citation_binding_governing_policy.py`,
`test_orchestrator_citation_reconcile.py`,
`test_demo_contract_citation_order.py`, `test_demo_journeys_postprocessing.py`,
`test_history_grounding_validator.py`, `test_legal_qa_regression_contract.py`,
`test_answer_fact_preservation_scrub_placeholder.py`,
`test_demo_contact_cleanup_containers.py`,
`test_demo_contact_supplement_separation.py`,
`test_demo_directory_field_parentheses.py`,
`test_demo_support_contact_wiring.py`, `test_inline_citations.py`,
`test_numeric_grounding_validator.py`, `test_numeric_notation_coverage.py`,
`test_response_quality.py`,
`tests/conversation/test_contacts_type_and_country_fidelity.py`): all pass.

`flake8` on every changed `.py` file
(`app/evidence_contract.py`, `app/response/builder.py`,
`utils/sentence_spans.py`, `tests/unit/test_sentence_spans.py`,
`tests/conversation/test_fragment_numeric_repair_abbreviations.py`,
`tests/conversation/test_fragment_directory_source_contradiction.py`): no
output, clean.

`git diff --check` on the same changed files: exit code 0, clean. (The two
new `.patch` files under `docs/conversation-quality/phase2/patches/` trip
`git diff --check`'s trailing-whitespace/EOF-blank-line heuristics on their
own diff-formatted content - e.g. a context line that is a single space
representing an unchanged blank source line - which is normal unified-diff
syntax, not a defect in the files they describe.)

## Files changed on this branch

- `utils/sentence_spans.py` (new)
- `tests/unit/test_sentence_spans.py` (new)
- `tests/conversation/test_fragment_numeric_repair_abbreviations.py` (new)
- `tests/conversation/test_fragment_directory_source_contradiction.py` (new)
- `app/evidence_contract.py` (switched `_iter_checkable_sentences` to the
  shared splitter)
- `app/response/builder.py` (switched `_surviving_text` /
  `_delivered_model_text` to the shared splitter)
- `docs/conversation-quality/phase2/FRAGMENT_AUDIT.md` (this file)
- `docs/conversation-quality/phase2/patches/laneD-numeric-grounding-validator.patch` (new, for Lane C/coordinator)
- `docs/conversation-quality/phase2/patches/laneD-directory-fields-after-sponsorship.patch` (new, for Lane B/coordinator)

No file outside Lane D's write scope was edited. `app/validation/validators/numeric_grounding_validator.py`
(Lane C) and `utils/directory_fields.py` (Lane B) were read and probed only;
their fixes exist solely as the two patch files above.
