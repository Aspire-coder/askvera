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

## Fable Phase 2 review corrections

An independent Fable review of Phase 2 returned NEEDS CORRECTION. Base for
this round: `dbc6a7a` (Phase 1's reviewed code); worked in
`p2fix/splitter-and-timing-20260918` off `fe45cdc`. Four findings, each
reproduced as a failing test first, then fixed.

### Finding 1 (BLOCKER) - a bare newline was not a unit boundary

`utils.sentence_spans.sentence_boundaries` only ever produced a boundary at a
"." "!" or "?" run; a bare `\n` with no preceding terminal punctuation was
never a boundary on its own; unlike the OLD, per-editor
`re.split(r"(?<=[.!?])\s+|\n", ...)` this module replaced, which always split
on `\n`. A label-style directory answer -
"Telephone Office: +254 20 2026869\nEmail: info@foreverea.com\nWebsite:
www.x.com" - has no `.`/`!`/`?` anywhere, so it was read as ONE unit by both
`app/response/builder.py` (`_surviving_text`/`_delivered_model_text`, used by
`reconcile_citations`) and `app/evidence_contract.py`
(`_iter_checkable_sentences`, used by `unsupported_answer_sentences` /
`HistoryGroundingValidator`). Once a directory-field filter or a numeric
repair removed ONE line from that block, the whole merged unit no longer
matched the delivered text verbatim, so `_surviving_text` returned no
surviving text at all and `reconcile_citations` dropped every citation for
the answer - even though the delivered answer still quoted the record's
phone number and email.

Fix: `sentence_boundaries` now also treats every `\n` character as an
unconditional unit boundary (skipped only inside a protected email/URL span),
independent of whether it follows terminal punctuation. Every existing
sentence_spans guarantee (decimals, abbreviations, emails, URLs, clause
references) is unaffected, since the newline rule is additive.

Tests: `tests/unit/test_sentence_spans.py`
(`test_bare_newline_is_a_boundary_even_with_no_preceding_punctuation`,
`test_bare_newline_boundary_does_not_split_a_url_or_email_across_lines`,
`test_heading_line_is_its_own_unit_and_does_not_swallow_the_next_line`,
`test_bullet_lines_are_each_their_own_unit`);
`tests/conversation/test_p2fix_newline_and_abbreviation.py` (citation
retention after a one-line directory-field removal, after a one-line
numeric-repair removal, a policy-citation variant, and a direct
`_surviving_text` check).

### Finding 2 (BLOCKER) - a heading/bullet line hid the claim after it

Same root cause as finding 1, surfacing in
`app/evidence_contract._iter_checkable_sentences` /
`unsupported_answer_sentences` (`HistoryGroundingValidator`): "## Bonus\n
Distributors in Kenya receive a guaranteed monthly income bonus of 500 USD
after sponsoring two people" was one merged unit starting with "#", so
`_is_structural_line` skipped the WHOLE thing - heading and claim together -
hiding an unsupported claim that was correctly flagged on base. Bullet lists
("- claim\n- Telephone...") merged the same way.

Fix: covered by finding 1's newline fix alone - once each line is its own
unit, the heading (or bullet marker) is skipped on its own and the sentence
after it is checked independently. No change to
`app/evidence_contract.py` was needed.

Tests: `tests/conversation/test_p2fix_newline_and_abbreviation.py`
(`test_heading_does_not_hide_the_unsupported_claim_sentence_after_it`,
`test_bullet_list_does_not_hide_the_unsupported_claim_in_the_next_bullet`,
and a negative control that the heading line itself is never reported as an
unsupported claim).

### Finding 3 (SHOULD-FIX) - timing-stage false positives and a gap

`app/validation/validators/numeric_grounding_validator.py` and
`config/timing_stage_vocabulary.py`:

- **(a) fixed**: the English `waiting_period` cue list included the bare
  verb "wait" (and every other language's table included its own bare-verb
  equivalent - "attendre", "warten", "wachten", "attendere", "esperar",
  "odottaa", "vente", "vänta"). "Please wait 3-5 working days for your
  parcel." then classified as `waiting_period` purely from that one generic
  word, while the source ("Delivery takes 3-5 working days.") classified as
  `delivery`, and the mismatch deleted a correct delivery answer. Fixed by
  removing the bare verb from every language's `waiting_period` tuple,
  keeping only phrases that name the waiting period itself ("waiting
  period", "must wait", "doit attendre", "muss warten", "on odotettava",
  "cooling-off", "not eligible until", and their per-language equivalents).
  The other stages were re-audited for a similarly generic bare verb; none
  of "processing"/"approval"/"payment"/"settlement"/"delivery"/"office_hours"
  has one that is this unqualified (each already reads as its own specific
  event or noun), so no further change was made there.
- **(b) deliberate, kept**: a bonus-payment date must not ground a
  bank-settlement-arrival time ("Your bonus is credited to your account
  within 15 days of month end." vs "Bonuses are paid within 15 days of month
  end." stays flagged), and "processing" must not ground "approval" ("The
  application process takes 10 working days." vs "Applications are approved
  within 10 working days." stays flagged). Both are documented, intentional
  trade-offs from the original Lane C design (see
  `tests/conversation/test_timing_stage_grounding.py`) and are now pinned
  with docstrings stating exactly that, so a future change does not loosen
  them by accident.
- **(c) fixed**: "Approval takes five (5) working days." against "Delivery
  takes five (5) working days." was never caught, because
  `_is_structural_reference` reads ANY `(N)` as a footnote/citation marker
  and never extracts it as a numeric claim at all - the bracketed figure
  skipped not just the stage check but every check. Fixed narrowly:
  a parenthesised figure immediately preceded by a spelled-out number word
  ("five (5)") is recognised as the common legal/policy convention of
  restating a number in digits, not a footnote, and is now extracted and
  stage-checked like any other figure. An ordinary bracketed footnote with no
  spelled-out number in front of it ("... 3 working days (1).") is still
  ignored, unchanged. Scoped to English number words only for now; extending
  the spelled-out-number list to other covered languages is future work.

Tests: `tests/conversation/test_timing_stage_fable_review_corrections.py`.

### Finding 4 (SHOULD-FIX) - a correct short neighbour was merged away

`app/validation/validators/numeric_grounding_validator.py`
(`abbreviation_or_initial_before`, called from
`remove_unsupported_numeric_sentences`'s own boundary regex) and
`utils/sentence_spans.py` (`_INITIAL_RE`, `ABBREVIATIONS`): the previous
round's fix treated ANY bare capital-letter-plus-dot as an "initial" and any
plain abbreviation as unconditionally non-terminal, regardless of what
followed. "Is the fee refundable? No. Delivery takes 5 days." (the "5" is
unsupported) was "Is the fee refundable? No." on base, but merged "No." into
the deleted sentence and became "Is the fee refundable?" - the correct "No."
answer was lost. "Take Vitamin C. Delivery takes 5 days.",
"Use Form A. Delivery takes 5 days." and "Send it by Dec. Delivery takes 5
days." were kept correctly on base and collapsed to "" once merged.

Fix, per the coordinator's rule:

1. A single capital letter before a dot counts as an initial only as part of
   a chain of two or more ("J. R. Smith"); a lone "C." or "A." is now an
   ordinary sentence end. Implemented as `_INITIAL_CHAIN_RE`, a regex
   requiring at least two whitespace-separated `letter.` tokens, replacing
   the old blanket `_INITIAL_RE` (any single letter, either case).
2. An abbreviation period is non-terminal only when the next token starts
   with a digit or a lowercase letter ("approx. 999", "Nr. 999"); before an
   uppercase word it is terminal ("No. Delivery", "Dec. Delivery").
   Implemented as a forward-continuation check (`_forward_continuation`)
   added to the plain-abbreviation branch of
   `abbreviation_or_initial_before`.
3. The dotted compound entries that could never actually match through the
   old trailing-word lookup ("e.g", "i.e", "z.b", "u.a", "d.h", "p.ex",
   "t.ex", "f.eks", "bl.a", "etc.al" - the lookup only ever sees the letters
   after the LAST internal dot, so "e.g" could never match the literal string
   "e.g") are now matched correctly: `_DOTTED_ABBREVIATION_RE` matches the
   whole compound as one case-insensitive literal (with the module's own
   trailing dot appended), and both of its dots - the internal one and the
   final one - are read as non-terminal. These entries were kept rather than
   removed, since they were doing real (if accidental) work protecting
   compounds like "e.g." and "z.B." via the old blanket initial rule that
   rule 1 above now removes.

One documented, deliberate behaviour change versus base: "St. Louis" (a
plain abbreviation, "st", before an uppercase proper noun) now splits into
two units under `sentence_boundaries`/`split_sentences`, per rule 2 above.
This is NOT a regression versus base (`dbc6a7a`): base's own abbreviation
guard in `remove_unsupported_numeric_sentences`,
`\b(?:[^\W\d_]\.){2,}`, only ever matched a run of single-LETTER-dot pairs
("J.R.", "z.B."), never a multi-letter word like "St" followed by one dot -
so base already split "St. Louis" into two sentences; this restores that
same behaviour rather than changing it. See
`tests/unit/test_sentence_spans.py::test_st_louis_now_splits_matching_base_behaviour_not_a_regression`
for the pinned repro and its reasoning.

Tests: `tests/unit/test_sentence_spans.py`
(`test_lone_initial_before_a_period_is_an_ordinary_sentence_end`,
`test_initial_chain_of_two_still_stays_whole_before_an_uppercase_name`,
`test_plain_abbreviation_before_an_uppercase_word_is_terminal`,
`test_plain_abbreviation_before_a_digit_or_lowercase_word_is_still_non_terminal`,
`test_dotted_compound_abbreviation_protects_both_of_its_own_dots`,
`test_st_louis_now_splits_matching_base_behaviour_not_a_regression`);
`tests/conversation/test_fragment_abbreviation_initial_fable_review.py`
(all four Fable repros, plus positive controls that round 2's approx./Nr./
initial-chain fixes still pass unchanged).

### Verification

Ran together: `tests/conversation`, `tests/conversation_pack`, and the named
`tests/unit` files (`test_sentence_spans`, `test_response_builder`,
`test_orchestrator_citation_reconcile`, `test_demo_contract_citation_order`,
`test_evidence_contract`, `test_history_grounding_validator`,
`test_numeric_grounding_validator`, `test_numeric_grounding_repair_corrections`,
`test_numeric_grounding_repair_defects`, `test_numeric_notation_coverage`,
`test_demo_numeric_repair_live_removals`, `test_supported_figure_preservation_c`,
`test_supported_figure_role_binding`, `test_directory_fields`,
`test_demo_journeys_postprocessing`, `test_chat_orchestrator`): 956 passed, 4
skipped, 2 xfailed. Then the whole `tests/unit` directory: 8869 passed, 13
xfailed, 0 failed. `flake8` on every changed `.py` file and `git diff
--check`: both clean.

### Files changed in this round

- `utils/sentence_spans.py` (newline-as-boundary; initial-chain and
  dotted-compound abbreviation rewrite)
- `config/timing_stage_vocabulary.py` (removed the bare "wait"-family verb
  from every language's `waiting_period` tuple)
- `app/validation/validators/numeric_grounding_validator.py`
  (`_is_structural_reference` now recognises a spelled-out-number-prefixed
  bracketed figure as a real claim)
- `tests/unit/test_sentence_spans.py` (extended)
- `tests/conversation/test_p2fix_newline_and_abbreviation.py` (new)
- `tests/conversation/test_timing_stage_fable_review_corrections.py` (new)
- `tests/conversation/test_fragment_abbreviation_initial_fable_review.py` (new)
- `docs/conversation-quality/phase2/FRAGMENT_AUDIT.md` (this section)

No existing test was weakened or deleted. `app/evidence_contract.py` and
`app/response/builder.py` were re-verified against this round's fix but
needed no code change of their own - the newline fix in
`utils/sentence_spans.py` was sufficient for both.

## Independent re-review correction (2026-09-18): title abbreviations and empty newline units

The independent re-review of the round above (findings 1 and 2) found that
the "St. Louis now splits, not a regression" call recorded in the previous
section was itself wrong, and that the newline-boundary fix left a small,
harmless-looking artifact of its own.

### Finding 1: a title abbreviation before a capitalised name was wrongly split

The previous round's rule 2 (a plain abbreviation's "." is terminal before
an uppercase word, non-terminal only before a digit or lowercase letter) is
right for "No." and "Dec." but wrong for personal/place TITLES: the
capitalised word that follows a title is the name it attaches to, not a new
sentence. "Call Dr. Smith. Delivery takes 3 days." regressed to
`["Call Dr.", "Smith. Delivery takes 3 days."]` - the name was severed from
the sentence that named it. The same shape hit "Mr. Jones", "Mrs. Kim",
"Prof. Lee" and "St. Louis office"; directory contacts and addresses carry
exactly these shapes.

Fixed by `TITLE_ABBREVIATIONS` in `utils/sentence_spans.py`: a small, CLOSED,
documented subset of `ABBREVIATIONS` - Dr, Mr, Mrs, Ms, Prof, St, Mt, Sr, Jr
(English) plus the configured-language equivalents Hr (German), Mme/Mlle
(French), Sra (Spanish/Portuguese), Dott/Ing (Italian) - whose period is
non-terminal before a capitalised word specifically.
`abbreviation_or_initial_before` now checks, in order: the dotted-compound
rule, the initial-chain rule, the existing digit-or-lowercase continuation
rule (unchanged, applies to every abbreviation), and finally - only for a
word in `TITLE_ABBREVIATIONS` - a new capitalised-word continuation rule
(`_title_continuation`). Every abbreviation NOT in the closed title set
(`no`, `nr`, `dec`, `approx`, etc.) keeps the previous round's
terminal-before-uppercase behaviour unchanged.

**Before/after:**

| Text | Before this fix | After this fix |
| --- | --- | --- |
| `Call Dr. Smith. Delivery takes 3 days.` | `["Call Dr.", "Smith. Delivery takes 3 days."]` | `["Call Dr. Smith.", "Delivery takes 3 days."]` |
| `Ask Mr. Jones. Delivery takes 3 days.` | split at `Mr.` | `["Ask Mr. Jones.", "Delivery takes 3 days."]` |
| `Take the train to St. Louis for the conference.` | `["Take the train to St.", "Louis for the conference."]` | `["Take the train to St. Louis for the conference."]` |
| `Is the fee refundable? No. Delivery takes 5 days.` | unchanged | unchanged: `["Is the fee refundable?", "No.", "Delivery takes 5 days."]` |
| `Send it by Dec. Delivery takes 5 days.` | unchanged | unchanged: `["Send it by Dec.", "Delivery takes 5 days."]` |

**The "St." trade-off.** "St." is genuinely ambiguous: "Saint" before a name
continues the sentence ("St. Louis office"), but "Street" at a real sentence
end does not ("...on Main St. Delivery takes 3 days."). Both shapes look
identical to this module - a plain abbreviation immediately before a
capitalised word - and there is no local signal (a gazetteer of street vs.
place names, lookahead past the next word) that this module has access to.
The rule chosen keeps "St." in `TITLE_ABBREVIATIONS`, because "St.
<Capitalised City>" is the shape actually observed in directory data (this
finding's own repro), so the fix is biased toward not truncating a directory
address at the cost of leaving the rarer "Main St. <new sentence>" shape
merged instead of split. Both shapes are covered by tests, with the "Main
St." case asserted as a documented, accepted limitation rather than a silent
regression - see
`tests/unit/test_sentence_spans.py::test_st_street_at_a_real_sentence_end_is_a_documented_known_limitation`
and
`tests/conversation/test_p2fix_title_abbreviations.py::test_main_st_street_ending_a_sentence_is_a_documented_known_limitation`.

The previous section's `test_st_louis_now_splits_matching_base_behaviour_not_a_regression`
is superseded by
`test_st_louis_no_longer_splits_after_the_independent_review_correction` in
the same file, which records why the earlier expectation was itself the bug
this finding fixes.

### Finding 2: an empty unit between a period and the newline that follows it

`sentence_boundaries("A.\nB.")` returned `[2, 3, 5]`: a real boundary right
after `"A."` (offset 2), another right after the `"\n"` that immediately
follows it (offset 3), and nothing but whitespace in between - an empty
`"\n"` unit that `iter_sentences` turned into its own (blank) `SentenceSpan`.
`split_sentences` already filtered it out by stripping and dropping empty
candidates, so no caller observed a visible defect, but `sentence_boundaries`
and `iter_sentences` themselves carried the redundant boundary.

Fixed by `_drop_empty_units`, a small post-processing pass over the sorted
boundary list: a boundary is dropped when the text between it and the
previously-KEPT boundary is empty or whitespace-only, which merges the blank
stretch into whatever unit follows instead of emitting it as its own. Every
boundary that closes a non-empty unit is left exactly where it was -
`sentence_boundaries("A.\nB.")` now returns `[2, 5]`.

### Tests

`tests/unit/test_sentence_spans.py`:
`test_title_abbreviation_before_a_capitalised_name_is_non_terminal`,
`test_title_abbreviation_language_equivalents_are_non_terminal_too`,
`test_st_street_at_a_real_sentence_end_is_a_documented_known_limitation`,
`test_plain_abbreviation_before_uppercase_stays_terminal_when_not_a_title`,
`test_st_louis_no_longer_splits_after_the_independent_review_correction`
(supersedes the earlier, now-corrected expectation),
`test_sentence_boundaries_drops_the_empty_unit_between_a_period_and_a_newline`,
`test_sentence_boundaries_drop_empty_unit_does_not_move_a_real_boundary`.

`tests/conversation/test_p2fix_title_abbreviations.py` (new): the same
findings exercised through `remove_unsupported_numeric_sentences` and
`split_sentences` together, including the "Contact Dr. Smith" and "St.
Louis" repros against a real numeric-repair deletion, the "No."/"Dec."
negative control, and the documented "Main St." limitation.

`tests/unit/test_market_config.py`: `test_market_display_name_covers_directory_only_markets`
had its `assert market_display_name("") == ""` line (dropped in an unrelated
earlier commit, `c15eee6`) restored; `market_display_name` already returned
`""` for an empty code, so this is a test-integrity fix with no production
code change.

### Verification

Ran together: `tests/conversation`, `tests/conversation_pack`, and the named
`tests/unit` files (`test_sentence_spans`, `test_market_config`,
`test_response_builder`, `test_orchestrator_citation_reconcile`,
`test_evidence_contract`, `test_history_grounding_validator`,
`test_numeric_grounding_validator`, `test_numeric_grounding_repair_corrections`,
`test_numeric_grounding_repair_defects`, `test_directory_fields`,
`test_demo_journeys_postprocessing`). Then the whole `tests/unit` directory
once. `flake8` on every changed `.py` file and `git diff --check`: both
clean. Exact counts and exit codes are recorded in the handoff for this
round.

### Files changed in this round

- `utils/sentence_spans.py` (`TITLE_ABBREVIATIONS`, `_title_continuation`,
  `_drop_empty_units`)
- `tests/unit/test_sentence_spans.py` (extended; superseded the "St. Louis
  now splits" expectation)
- `tests/unit/test_market_config.py` (restored one dropped assertion)
- `tests/conversation/test_p2fix_title_abbreviations.py` (new)
- `docs/conversation-quality/phase2/FRAGMENT_AUDIT.md` (this section)

No existing test was weakened; the one test whose EXPECTED VALUE changed
(`test_st_louis_now_splits_matching_base_behaviour_not_a_regression` ->
`test_st_louis_no_longer_splits_after_the_independent_review_correction`)
changed because the behaviour it pinned was the bug this round fixes, per
this round's own coordinator instruction - not a loosening of coverage.

## Fable re-review (finding F3): hr/fr/ing/mt were wrongly made titles

Commit `f64f57c` (the section above) added six entries to `ABBREVIATIONS`
- `hr`, `fr`, `ing`, `mt`, `mme`, `mlle` - and put five of them (`hr`, `fr`,
`ing`, `mt` plus the already-title `mme`/`mlle`) into `TITLE_ABBREVIATIONS`,
the closed set whose period stays non-terminal even before a capitalised
word. A Fable re-review (should-fix, finding F3) found that `hr`, `fr`,
`ing` and `mt` do not belong in either set: unlike the honorifics the
`TITLE_ABBREVIATIONS` docstring asks for ("essentially never a sentence-final
word or a unit/weekday"), all four are the ordinary spelling of something
that regularly *does* end a sentence, so numeric-repair's downstream delete
step removed the wrong sentence - the supported one - instead of the
unsupported one whenever they appeared.

### Reproductions

- **`hr` = "hour".** `"Response time is 48 hr. Delivery takes 3 days."` was
  read as one merged unit (title rule fired because "Delivery" is
  capitalised). `remove_unsupported_numeric_sentences(answer,
  [doc("Response time is 48 hr.")])` then found the merged unit only
  partially supported (the "48 hr" half is grounded, the "3" half is not)
  and deleted the whole unit, returning `("", ["3"])` - the correctly
  supported "48 hr" sentence vanished along with the unsupported one. Before
  `f64f57c`, this case correctly split into two sentences and only the
  unsupported one was removed.
- **`fr` = "Friday"/"franc"/"Frau".** `"Geoeffnet Mo.-Fr. Lieferung dauert 3
  Tage."` (an opening-hours range followed by a delivery-time sentence)
  merged into one unit, because German capitalises every common noun, so the
  word after "Fr." is capitalised in the overwhelming majority of real
  sentences - the title rule effectively fired on every "Fr." in German
  text, not just the rare "Frau" case it might have been intended for.
- **`ing`.** `"Ask Ing. Delivery takes 3 days."` merged for the same
  reason - "ing" is a common word-final fragment (and an Italian engineering
  title, "Ingegnere"), not an abbreviation that is unambiguous before a
  capitalised word.
- **`mt` = "Mount".** No reproduced defect motivated its addition in
  `f64f57c`; removed for the same reason as the other three - it is a unit
  ("mt" for metric tons in some markets) and a place-name abbreviation
  ("Mt." for "Mount") with no local signal to tell them apart, and unlike
  "St." there was no directory-data repro to justify accepting that
  trade-off.

### Decision

Removed `hr`, `fr`, `ing`, `mt` from both `ABBREVIATIONS` and
`TITLE_ABBREVIATIONS`, restoring `ABBREVIATIONS` to its pre-`f64f57c`
membership for these four entries exactly (confirmed against `git show
f64f57c^:utils/sentence_spans.py`). `mme` and `mlle` are kept in both sets:
they are unambiguous French honorifics ("Madame", "Mademoiselle") with no
competing everyday-word reading, the same shape as `dott` (Italian "Dottore"),
which is also kept. The final `TITLE_ABBREVIATIONS` set is: `dr`, `mr`,
`mrs`, `ms`, `prof`, `st` (English, "St." trade-off documented above), `jr`,
`sr` (English), `mme`, `mlle` (French), `sra` (Spanish/Portuguese), `dott`
(Italian).

**Should the title rule apply at all in a noun-capitalising language like
German?** Considered and rejected as a blanket per-language carve-out: the
simpler, equally correct fix is that `TITLE_ABBREVIATIONS` no longer
contains any German-specific entry at all (its one German entry, `hr`, is
removed along with `fr`). A title that is genuinely unambiguous in German
(none currently proposed) could still be added later, but it would need its
own reproduced defect and its own scrutiny of how often German capitalisation
makes the word after it look like a name - not a blanket exemption for the
language.

### Tests

`tests/unit/test_sentence_spans.py`:
`test_hr_fr_ing_mt_are_no_longer_titles_and_still_split` (new: the four direct
repros); `test_title_abbreviation_language_equivalents_are_non_terminal_too`
trimmed to the entries that are still titles (`mme`, `mlle`, `sra`, `dott`) -
its `hr`/`fr`/`ing` assertions (added by `f64f57c`, asserting they merged)
are removed, not loosened, because merging was the defect this finding
fixes; every other assertion in that file is unchanged.

`tests/conversation/test_p2fix_title_abbreviations.py`:
`test_removing_an_unsupported_figure_after_hr_does_not_delete_the_supported_sentence`
(the real `remove_unsupported_numeric_sentences` repro for "48 hr"),
`test_mo_fr_opening_hours_range_still_splits_before_the_next_sentence`,
`test_ing_title_before_a_name_still_splits` (new); the `"Ask Hr. Müller."`
case is removed from
`test_title_before_uppercase_name_stays_joined_to_its_own_sentence` for the
same reason.

### Verification

Ran together: `tests/conversation`, `tests/unit/test_sentence_spans.py`,
`test_numeric_grounding_validator`, `test_numeric_grounding_repair_corrections`,
`test_numeric_grounding_repair_defects`, `test_response_builder`,
`test_evidence_contract` (665 passed, 2 xfailed, exit 0). Then the whole
`tests/unit` directory once (see handoff for the exact count/exit code).
`flake8` on `utils/sentence_spans.py`, `tests/unit/test_sentence_spans.py`
and `tests/conversation/test_p2fix_title_abbreviations.py`: clean, exit 0.
`git diff --check`: clean, exit 0.

### Files changed in this round

- `utils/sentence_spans.py` (`ABBREVIATIONS`, `TITLE_ABBREVIATIONS`, and the
  docstrings that named the removed entries)
- `tests/unit/test_sentence_spans.py` (trimmed the `hr`/`fr`/`ing` title
  assertions added by `f64f57c`; added the four-entry repro test)
- `tests/conversation/test_p2fix_title_abbreviations.py` (removed the `Hr`
  case from the title-joining test; added the real numeric-repair repro and
  two split-still-works cases)
- `docs/conversation-quality/phase2/FRAGMENT_AUDIT.md` (this section)

No existing test's EXPECTED VALUE was loosened toward merging; every change
in this round moves `hr`/`fr`/`ing`/`mt` from "non-terminal" back to
"terminal" (ordinary sentence end), which is a strictly more conservative
default than the one `f64f57c` shipped.
