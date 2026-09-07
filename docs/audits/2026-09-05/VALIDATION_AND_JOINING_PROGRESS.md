# Validation and joining-evidence progress - 2026-09-06

## Decision

HOLD deployment. Concrete validation defects have local regression coverage, but joining-cost interpretation and requested-answer scope are not fixed end to end. No thresholds, deployed configuration, index contents, commits or remote branches were changed in this turn. Existing unrelated worktree changes were preserved.

## Implemented fixes

1. Numeric sentence repair no longer treats decimal/time separators as sentence endings. The captured Belgium response previously became an orphaned `00 pm Monday through Friday.` fragment. The offline replay now removes that entire unsupported sentence and preserves the earlier phone answer.
2. Numeric extraction and source matching now distinguish a decimal continuation from a sentence-final period. Unsupported values such as `18.75.` previously escaped extraction. Tests cover integers, decimal points and decimal commas.
3. Repair boundaries preserve dotted initialisms such as `U.S.` inside a sentence, preventing a dependent clause from being cut at the abbreviation.
4. Inline Markdown citations are removed before numeric validation only when both the source number and URI match the corresponding retrieved document. Previously `[Source 1](...)` could be interpreted as numeric claim `1`, causing the supported qualification sentence to be removed. Unknown indices, incorrect URIs and mismatched index/URI pairs remain untouched.
5. Empty parenthesized citation groups no longer leave `()` or `(, )` in the answer.

These are specific parser/validation fixes, not relaxed numeric or confidence checks. They do not establish general claim-level semantic correctness or completeness after repair.

## Joining-evidence candidate

Extended the existing bounded English joining-cost ranking feature to include short explicit opt-in eligibility and purchase-qualification clauses. Large parent/glossary blocks do not receive the new qualification boost. Added selector guidance to retain prerequisites alongside entry/support-fee clauses and distinguish requirements from benefits.

The live run now includes a purchase qualification in all three UK joining answers. However, the first two still infer no joining/upfront fee and the answers do not consistently explain the full local opt-in pathway. This is not a correct-answer PASS or a promotion candidate. The ranking/selector changes remain an uncommitted experiment requiring further evaluation, not a verified multilingual solution.

## Experiments and evidence

| Folder | Change relative to preceding retained candidate | Result |
|---|---|---|
| scope-prompt-05 | Generation prompt wording only | Incomplete: 19 answer captures, then AWS refresh blocked at repeat 2 discount. Completed outputs still overstate free entry/add benefits. Prompt change was reverted; evaluated template preserved in folder |
| numeric-repair-06 | Initial decimal repair/extraction fixes; generation prompt restored to governing-fixed-04 | 30 captures, no execution errors or isolation violations. No numeric-refusal outcomes in Belgium-phone or US-rank repeats, but this is not correctness scoring; unasked content remains |
| joining-evidence-07 | Joining ranking plus selector prerequisite coverage | 30 captures, no execution errors or isolation violations. Identified citation-induced loss of the correct rank sentence, incomplete sentence repair around U.S., continued scope failures and one rank numeric refusal |

The final citation and abbreviation fixes were implemented AFTER joining-evidence-07 and are covered by local tests, not by that live run. Do not label its answers as outputs of the final working tree.

All comparisons reuse the earlier Current captures from matched-full-01, with the same frozen model/settings and publication/index checks. Current was not rerun concurrently. The actual model remains global Claude Haiku 4.5; these are code-profile comparisons, not two different model families. Synthetic sessions, caches and shared writes remain isolated. This is not deployed widget/HTTP verification or the full market/language/safety release suite.

## Verification

- Final full unit suite: **881 passed**, two dependency deprecation warnings.
- Targeted lint: passed after correcting indentation.
- Graphify update attempted but unavailable because the executable is not installed.
- Medical and guaranteed-income refusals and explicit foreign-policy blocking held in the completed live runs. Do not infer full safety-suite success from these three scenarios.
- Confidence thresholds and safety boundaries were not lowered.

## Still open, next actions

Update: cleanup-recheck-08 completed the 30-capture live-code rerun after the final cleanup fixes. See cleanup-recheck-08/REVIEW.md. The test recorder now retains exact generation evidence even on refused answers; 887 unit tests pass. Joining interpretation and scope failures persist, including one split-intent refusal. HOLD remains in effect.

1. Replay final cleanup/validation against the exact approved evidence for captured failures, then repeat the live comparison. The lightweight numeric diagnostic intentionally uses a superset of captured hits and is not an approval gate.
2. Complete joining evidence coverage, including local opt-in prerequisites, and stop interpreting support-fee collection rules as proof of free joining. Check each claim against its supporting clause; do not infer an absent fee.
3. Resolve unasked upgrades/benefits and unsupported directory-operation inferences. Do not solve this by blindly trimming everything after the first sentence, which could discard required conditions.
4. Ensure repaired answers still answer the question and retain necessary conditions; a nonempty repaired answer is not proof of completeness.
5. Complete obsolete global-office-directory wording cleanup across claim-safety response translations. The active global source remains the sponsoring directory; legacy type labels are not proof that the retired document is active.
6. Reconfirm full regression, held-out, market/language and safety gates. Legal wording remains a separate approval dependency. No deployment until these pass.

## Full answers

- [Numeric-only comparison](numeric-repair-06/ANSWERS_SIDE_BY_SIDE.md)
- [Joining-evidence comparison](joining-evidence-07/ANSWERS_SIDE_BY_SIDE.md)
- Corresponding CSV files include full questions, answers, citations and timings with manual review columns.
