# Overnight checkpoint - September 6, 2026

## Latest attended update

Final-claim binding follow-up: new opt-in complete-answer/ordered-claims/exact-quote binding and separate semantic audit helper, neither live-wired. **1,132 local tests pass**, lint/diff checks pass. **10 additional model audit calls, two deterministic rejected controls, zero additional end-to-end requests** this turn. Raw audits were fenced JSON; offline normalization shows 10/12 control outcomes, with unasked bonus additions incorrectly accepted twice. **HOLD: semantic reviewer rejected for activation**. Production unchanged. See `../2026-09-06/FINAL_CLAIM_BINDING_REVIEW.md`. Next: explicit per-claim necessity versus entailment decisions and paired requested-bonus positive controls, then integration and fresh full gates; do not repeat or promote the failed whole-answer reviewer.

Attended scoped-writer follow-up completed: **40 additional end-to-end captures** across `scoped-writer-chat-01` and `scoped-writer-chat-02`, zero execution errors/storage-isolation violations. Monthly requirements and concise split-intent answers retained; Canada paraphrase still volunteers bonus context. Full-ID citation cleanup fixed numeric/spacing interference. Structural claim parser tightened. Explicit approved citation preservation added after chat-02 and verified in a six-case offline replay (Canada original now retains activity AND rank-retention sources); this final patch has not had a new cloud run. **1,105 unit tests pass**, targeted lint and diff checks pass. Production unchanged; **HOLD**, no overall improvement or release-readiness claim. See `../2026-09-06/SCOPED_WRITER_REVIEW.md` for full paired answers, exact test boundaries and remaining semantic citation/scope gates. These are user-approved attended runs after the overnight deadline, not resumed scheduled work.

Bound-evidence approval experiment completed: **five previously blocked policy cases now return answers** in `../2026-09-06/bound-review-chat-02` (20 paired captures, zero execution errors or storage-isolation violations). Both arms use the structural selector; neither is deployed Current. Final reviewer controls passed **18/18**, after two rejected protocols (54 reviewer-control model calls total). **1,092 local tests pass**, targeted lint and diff checks pass. **HOLD:** final generation still adds unasked bonus material, omits the concrete monthly requirement in the Canada paraphrase, and needs stronger final citation coverage. No numeric threshold changes; an exact-bound experimental review grant provides an alternative approval path only inside the isolated worker. Production unchanged. Earlier chat-01 has four incomplete captures due to blocked SDK credential refresh, not a quality result. See `../2026-09-06/BOUND_EVIDENCE_APPROVAL_REVIEW.md` and paired full answers. Next: final-answer completeness, scope and citation fidelity, followed by fresh repeated promotion gates. This supersedes the approval-blocked status immediately below; do not activate automatically.

Full-chat structural integration is now implemented and tested in an isolated worker. Corrected run `../2026-09-06/structural-chat-03` captured **20 responses, zero execution errors**, same working-tree baseline versus selector-only candidate. **HOLD:** relevant bound activity evidence is selected but the existing confidence gate still refuses five answerable policy cases, including the split-intent allowed half. No confidence threshold was lowered and diagnostic set confidence was not promoted. **1,066 local tests pass**, lint and diff checks pass. Production unchanged. See `../2026-09-06/STRUCTURAL_CHAT_REVIEW.md` and its linked full question/answer comparison. This supersedes “integration pending” below. Next: explicit, tested bound-evidence approval semantics, not another retrieval-ranking or prompt-only experiment. Three attempted runs have 47 persisted case captures (two setup runs interrupted); final valid comparison is only 20. Earlier 388 selector-only calls remain a separate count. No automatic promotion or rerun.

Source integration boundary added: real publication/content identities, canonical S3 fallback where logical ID is absent, country-policy isolation, and global sponsoring-only authorization defense. Scores and existing gate signals preserved. **1,053 tests pass**, targeted lint passes; no new AWS/model calls. Full orchestrator integration is still pending because set-level decision confidence must not silently replace first-passage confidence. See ../2026-09-06/STRUCTURAL_INTEGRATION_BOUNDARY.md. Production unchanged; totals remain 388 selector calls and zero additional end-to-end calls.

Structural candidate implemented and tested: **42/42 versus earlier compact candidate 36/42** over 14 cases repeated three times. Original CA-04 and fresh activity-carryover both recovered 3/3; eight negative controls held 24/24. 1,033 unit tests and targeted lint pass. Added 112 selector calls including smoke; total **388 selector-only calls, zero additional end-to-end calls**. Production unchanged, no live wiring. See ../2026-09-06/STRUCTURAL_DECISION_REVIEW.md. Next is isolated final-answer integration with real generation identities and the broader safety/market gates, not activation. Earlier rejected variants below remain rejected; do not conflate the new structural candidate with them.

September 6 follow-up: 40 more isolated selector calls completed, zero execution errors. Target-scope instruction change tied compact baseline at 9/10 and did not fix CA-04. Bound explicit-verdict candidate scored 6/10 versus compact baseline 9/10; rejected for source-order/binding and unsupported termination-decision failures. **1005 unit tests pass**, targeted lint passes. Total **276 selector calls; zero additional end-to-end calls**. Production unchanged. See ../2026-09-06/REMAINING_REFUSAL_REVIEW.md. Do not repeat these wording experiments or promote candidates automatically. Original refusal remains unresolved.

Isolated integration is complete: 96 four-arm selector calls plus 32 compact-ID smoke calls, zero execution errors. Ranking-only recovered the paraphrase 3/3 versus Current 0/3, but the original question still fails. Compact combined smoke scored 7/8; not a repeated promotion gate. Full local suite: **998 passed**, targeted lint passed. Totals now **236 selector-only calls, zero additional end-to-end calls**. Production remains unchanged; helpers are not live-wired. See GOVERNING_BINDING_INTEGRATION_REVIEW.md and both comparison folders for exact questions and raw outputs. Do not repeat completed experiments automatically or activate the candidate. Older entries below are historical.

Subsequent local step: source-binding and conservative English activity-rule helpers implemented **without live-provider wiring**. Offline captured inputs now place 4.03 first for both activity questions, leave termination order unchanged, and reject wrong quote bindings. **990 unit tests pass**. See GOVERNING_BINDING_PROGRESS.md. No additional AWS calls: totals remain 108 selector-only calls and zero end-to-end calls. Next is isolated integration and final-answer verification, not production activation.

The user returned and approved continued work. Three isolated selector experiments have now completed: **108 selector-only model calls**, zero execution errors, no production changes. These are not end-to-end requests; additional end-to-end count remains zero. Stop repeating prompt variants on this reused set. All three were rejected for promotion. See SELECTOR_EXPERIMENT_REVIEW.md and each experiment's COMPARISON.md for full paired model outputs and limitations. Current fixed-input checks were 12/18 in each run; candidates scored 6/18, 12/18 and 13/18 under their stricter quote-binding schema. No overall quality improvement claim is warranted. Full local tests now **960 passed**. Next priority is governing-rule selection and stable source binding, not further approval-threshold relaxation. The historical checkpoint below records the starting state before these runs.

## Scope and deadline

Continue local retrieval fixes and already-authorized bounded AWS comparisons until 09:20 America/Toronto. No deployment, commit, push, merge, live-index publication, shared-cache deletion, infrastructure or permission changes. Preserve the extensive existing dirty tree. Additional overnight end-to-end AWS requests used so far: **0 of 120**. No new AWS calls in this checkpoint.

## Verified starting state

- Comparison-03 is rejected, not a promotion candidate. Both Current and candidate refused the original Canada activity-versus-rank question 3/3. See its REVIEW.md for caveats.
- Final narrow income policy is local only; its revised implementation was not the version used in comparison-03.
- Rechecked the full unit suite: **943 passed**, two existing dependency deprecation warnings. Initial sandbox run had 25 Windows temporary-folder setup errors; the approved outside-sandbox rerun passed all tests. Do not report the initial setup failures as chatbot regressions.
- Targeted selector-capture plus income tests: 23 passed. Targeted new-file lint passed.

## New work retained

`scripts/prepare_selector_replay.py` freezes exactly one captured selector call per input file, preserves exact system/user text and model output, records input and source-file hashes, rejects missing/ambiguous captures, and refuses output overwrite. It does not call AWS or interpret a model answer as gold truth.

`tests/unit/test_selector_replay_capture.py` adds six tests covering input preservation, stable/content-sensitive hashing and rejected malformed/ambiguous captures.

`canada-selector-fixed-inputs.json` freezes three first-repeat candidate captures from comparison-03: CA-04, its paraphrase, and CA-status-loss. Expected decisions are deliberately unscored. Those captures include the subsequently rejected prompt wording; preserve that provenance and use the actual current prompt as a distinct experimental baseline, not an unnoticed substitution.

## Next work

1. Ground expected decisions and required evidence against the captured policy text, including wrong-action and missing-evidence controls. Never infer approval from the selector's prose reason.
2. Implement an isolated fixed-input selector experiment, using current prompt and a candidate decision schema with identical evidence/model settings. This experiment is not wired into production.
3. Only after repeated grounded controls pass, consider a runtime change and run end-to-end comparisons. Do not lower confidence or disable safeguards to gain answers.
4. Verify the final income fix end-to-end and review the Canada status-loss numeric refusal; continue remaining market-policy failures and offline parser tests.
5. Save question/answer comparisons, retained and rejected changes, limitations, request counts and any approval blockers here for the next heartbeat and morning review.

## Tool limitation

No graphify graph exists and `graphify update .` was unavailable because the executable is not installed/on PATH. No generated wiki was edited.

## Honest status

The additional work prepares reproducible experiments; it is **not yet a demonstrated retrieval-quality improvement**. No deployment or cloud state changes occurred.
