# AskVera Retrieval Overnight Review

**Date:** 2026-08-26
**Branch:** `feat/retrieval-shadow-quality`
**Starting commit:** `2c37f41513642f5d56bb4d53c1a6ab8cb8fc60d9`
**Status:** Local review candidate only. **Not committed, pushed, indexed, deployed, or enabled in production.**

**Isolated review branch:** `feat/retrieval-measurement-only`, created from the starting commit with measurement/audit changes only.

## 1. Executive decision

The safe local work is complete enough for review, but it is **not ready to deploy**.

- The corrected benchmark shows that the experimental Candidate retrieval profile is worse than Current on Recall@5, Recall@10, Recall@20, selector success, and answer delivery. Keep Candidate and hardening features disabled.
- Benchmark labels were reconciled against both the supplied source documents and the live Current/Candidate indexes. The normalized v4 fixture supports exact live-index aliases and source constraints without broadening matches to neighboring sections.
- Two general ingestion improvements were implemented locally: redundant atomic-fact deduplication and complete wrapped-bullet extraction.
- A chunk-quality auditor and a fixed-checkpoint selector evaluator were added so future changes can be measured without confusing retrieval variance with selector variance.
- No confidence threshold was lowered, no country-specific answer was hardcoded, and no production resource was changed.

## 2. Safety boundary followed overnight

The work intentionally did **not**:

- deploy to EC2 or any other environment;
- create, publish, alias, or delete an OpenSearch index;
- change SSM, Secrets Manager, Bedrock, Redis, Cognito, DNS, or production environment values;
- commit or push the dirty worktree;
- enable Candidate, hardening, RRF, reranking, neighbor expansion, evidence selection, or semantic-cache reuse;
- lower the live `0.47` confidence threshold;
- add question-specific or country-specific answer hardcoding.

AWS access was used only for read-only metadata audits and fixed-checkpoint evaluation. No document text from the Candidate profile was written to the reports.

## 3. Completed fixes and improvements

### 3.1 Correct benchmark scoring for abstentions

Updated the offline rescoring path so `must_abstain` cases are evaluated as successful when the system safely abstains, rather than being counted as retrieval failures.

Files:

- `scripts/rescore_profile_evaluation.py`
- `scripts/analyze_profile_failures.py`
- their focused unit tests

### 3.2 Fixed-checkpoint selector evaluation

Added a tool that retrieves candidates once, freezes them, and then replays only the managed evidence selector. This separates:

1. candidate retrieval quality;
2. selector variability;
3. evidence approval;
4. final answer delivery.

It does not write to production, alter indexes, generate customer answers, or use answer-cache results.

Files:

- `scripts/run_fixed_checkpoint_selector_evaluation.py`
- `tests/unit/test_fixed_checkpoint_selector_evaluation.py`

### 3.3 Source and live-index label reconciliation

Added a repeatable reconciliation packet generator, then verified the corrected labels against source extraction and live index metadata. The v4 fixture adds exact live-index aliases and source-file constraints where index IDs differ from canonical source IDs.

| Case | Old label | Corrected source label |
|---|---|---|
| `PARA-RALLY-CA-020` | `12.01-a` | `12.01-part-1` |
| `PARA-INTL-UK-026` | synthetic global label | UK policy `15` |
| `PARA-INTL-DIR-034` | `sponsoring-directory-p1` | Canada `15.01-b`, with parent `15.01` |
| `PARA-INTL-DIR-035` | `sponsoring-directory-p1` | Canada `15.01-b`, with parent `15.01` |
| `PARA-INTL-DIR-036` | `sponsoring-directory-p1` | Canada `15.01-b`, with parent `15.01` |

The live-index audit added these exact, non-broadening representations:

| Case | Canonical source | Exact live-index representation or constraint |
|---|---|---|
| `PARA-LVL-CA-005` | `4.01-a` | Candidate alias `4.01-part-1-a` |
| `PARA-LB-CA-009` | `6.03-a` | Complete parent passage `6.03` |
| `PARA-RESP-CA-017` | `14.01-a` | Complete parent passage `14.01` |
| `PARA-EAGLE-CA-018` | `8.04-a` | Candidate alias `8.04-part-1-a` |
| `PARA-F2D-CA-019` | `10.01-c` | Candidate alias `10.01-part-1-c` |
| `PARA-INTL-DIR-037` | Sponsoring-directory country index | Require `International-Sponsoring-Directory.pdf` |
| `PARA-INTL-DIR-038` | `sponsoring-029-china` | Exact China sponsoring record and sponsoring-directory source |

The key source finding is that the International Sponsoring Directory contains country operational records. General international-sponsoring procedure, ID, and level rules live in the country policy documents, so the old synthetic global label was not valid ground truth.

Files and artifacts:

- `scripts/build_fixture_reconciliation_packet.py`
- `scripts/apply_fixture_label_corrections.py`
- `tests/fixtures/paraphrase_label_corrections_v4.json`
- `exports/paraphrase-phase0-repeat-20260825/normalized-fixture-v4.json`
- `exports/paraphrase-phase0-repeat-20260825/source-reconciliation-v3/fixture-reconciliation.md`
- `exports/paraphrase-phase0-repeat-20260825/live-index-label-verification-v4-20260826/index-label-audit.md`

Live-index metadata result:

| Profile | Present | Missing | Not applicable |
|---|---:|---:|---:|
| Current | 43 | 1 | 2 |
| Candidate | 42 | 2 | 2 |

The remaining gaps are genuine index-coverage issues, not stale fixture labels:

- Both profiles lack a retrievable International Sponsoring Directory table-of-contents/country-index record for `PARA-INTL-DIR-037`.
- Candidate lacks the China sponsoring record for `PARA-INTL-DIR-038`; nearby China records belong to the office directory and must not satisfy the sponsoring-directory question.

### 3.4 Corrected Current versus Candidate benchmark

After applying corrected labels and abstention semantics:

| Metric | Current | Candidate |
|---|---:|---:|
| Must-answer cases | 44 | 44 |
| Must-abstain cases | 2/2 | 2/2 |
| Answers delivered | 40 | 34 |
| Selector successes | 23 | 15 |
| Must-answer passes | 23/44 | 14/44 |
| Overall passes | 25/46 | 16/46 |
| Recall@1 | 15.91% | 18.18% |
| Recall@5 | 40.91% | 36.36% |
| Recall@10 | 52.27% | 43.18% |
| Recall@20 | 63.64% | 54.55% |
| MRR | 0.2806 | 0.2732 |

Decision: **HOLD Candidate.** Its small Recall@1 gain does not compensate for the material regressions at every broader recall depth, selector success, and delivery.

### 3.5 Fixed-checkpoint selector verification

Ran retrieval once per case/profile, froze the top 20 candidates, and replayed only the managed selector three times.

| Profile | Governing evidence in checkpoint | Stable cases | All replays valid and relevant | Invalid responses |
|---|---:|---:|---:|---:|
| Current | 27/46 | 39/46 | 21/46 | 3 |
| Candidate | 24/46 | 36/46 | 16/46 | 0 |

The report now separates a safe invalid-response fallback from a successful selector choice. Three invalid Current responses occurred on `PARA-PC-CA-010`; the runtime retained all candidates safely, but those responses are no longer counted as selector successes.

Additional Current selector misses despite governing evidence being present occurred on `PARA-LVL-CA-007`, `PARA-ORD-CA-013`, `PARA-MGR-UK-024`, `PARA-ISO-043`, and `PARA-ADV-046`. Managed-selector variability remains a measured limitation, not a reason to promote Candidate.

Artifact:

- `exports/paraphrase-phase0-repeat-20260825/fixed-checkpoint-selector-v4-20260826-enriched/selector-checkpoint.md`

### 3.6 Chunk-quality audit

Added an ingestion audit for:

- missing required metadata;
- invalid page ranges;
- chunk-size ceilings;
- broken parent references;
- mojibake;
- dangling directory labels;
- possible mid-sentence starts;
- duplicate IDs and duplicate content.

Files:

- `scripts/audit_extracted_chunks.py`
- `tests/unit/test_audit_extracted_chunks.py`

Initial source audit:

- 5,808 records
- 0 errors
- 137 warnings
- 60 repeated-content groups
- 70 abstract parent references that are not separately materialized
- 7 possible mid-sentence starts

Warnings are review signals, not automatic proof of bad chunks.

### 3.7 Deterministic atomic-fact deduplication

Updated policy extraction to remove repeated atomic facts within the same parent section while preserving the stable ID of the first retained chunk.

Effect on the isolated rebuild:

- approximately 90 redundant chunks removed;
- duplicate-content warnings reduced from 60 to 2;
- no production index or source document changed.

The two remaining duplicate groups appear to be source-level repetition:

- Germany front matter matching its outline;
- repeated Netherlands section `10` occurrences.

### 3.8 Complete wrapped-bullet extraction

Updated policy extraction so a bullet spanning multiple visual lines becomes one complete `list_item` chunk. Numeric-fact extraction no longer emits separate fragments from inside that bullet span.

This directly reduces evidence such as a numeric phrase being retrieved without the continuation that explains its subject, condition, or exception.

Isolated rebuild result:

- 5,620 policy chunks
- 0 audit errors
- 79 warnings
- 2 duplicate-content groups
- 70 abstract parent-reference warnings
- 7 possible mid-sentence-start warnings

### 3.9 Review-time compatibility fixes

The full-suite review found and fixed two evaluator regressions:

- Restored the locked governing-policy wording used by the joining-cost prompt contract.
- Made evaluation report merging backward-compatible with older rows that do not contain `expected_behavior` or precomputed expectation fields. Legacy rows safely default to must-answer behavior; current explicit abstention behavior remains authoritative.

### 3.10 Clean-branch evaluator compatibility

The isolated branch exposed a hidden dependency in the fixed-checkpoint evaluator: it imported reviewed retrieval intents and passed optional selector arguments that do not exist at the reviewed base commit. The evaluator now discovers those optional runtime capabilities safely and falls back to the base selector interface without changing runtime code.

This compatibility change is confined to the evaluation script and has a regression test using the strict base selector signature.

## 4. Artifact integrity

The hashes below identify the reviewed local evidence bundle. Generated exports were **not added to the measurement-only Git branch** because they contain sanitized internal benchmark questions and labels. They may be retained as policy-approved CI/PR artifacts. The v4 correction fixture under `tests/fixtures` is included in the branch.

| Artifact | SHA-256 |
|---|---|
| v4 label corrections | `f93e9dc2ae6bcea2de019d56f853e1704965779ccaa609f99b9f8dde0dbb4a6b` |
| v4 normalized fixture | `22ded7aaf4face793acbcbcca357d400e2d4141cffdc8c0d83e4484a399921dd` |
| v4 corrected raw comparison | `898acc32255247102573526ed0ead300efa7f0ecbee191dc5ea02b071aad2939` |
| v4 corrected rescoring | `08ab242b5b32e229319fe2f7e2d9426c69d606133d3079b54a5382d8705b9890` |
| v4 live-index audit | `f63dbd3b5a2f15e027e2bb5455103399ad6d85db467c123e0ec67f58bb0059ed` |
| Enriched selector checkpoint JSON | `fff0a4128389725177fc478df2796345cbc3b7468a056f353656433ab1baacf5` |
| Enriched selector checkpoint Markdown | `07efe9c7f107693438cefc191131dda15e6e8324916ff45bd76c5c7309fde05b` |
| Label corrections | `6046b15e33b72b3ece49d904d760bb943a15015960f7da0e0ceae0a28825ab8a` |
| Normalized 46-case fixture | `fefcf72a193c847295b08a0d3d34582227ed03ad577bbe0e7f210a8ca77a7633` |
| Corrected raw comparison | `8470c8667124a5cb47e1612d5549bf3abaf83eca2bc309572200c1c7cba2eae8` |
| Corrected rescoring | `59ca6456296a22dc369a52ebf9c58d3f3412082c715dabe9b704d8541b693de6` |
| Source reconciliation | `bad43d74b3b73263d7387c4f60fe6fb767ba9c969a1db447ca383379f366b1d7` |
| Initial chunk audit | `a04448fc8960e6187e39ca7c6ebf580b1f6f8be039352f6357272b926eb9d2c8` |
| Deduplicated chunk audit | `41df6b88de9eea4ddc4c4e8f7b536cf430589cae10aa45316e6b53c3483a3c22` |
| Wrapped-bullet chunk audit | `c859efafbf6cd1f29dd3ec933461b8b886fe19674ecb02c6599a91eb075b0f18` |

## 5. Review and approval decisions

### Approved for a future isolated commit

- Label-correction fixture and application tool.
- Source-reconciliation packet generator.
- Offline rescoring and failure taxonomy.
- Chunk-quality auditor.
- Live-index metadata verifier with content-free nearby-ID diagnostics.
- Fixed-checkpoint selector evaluator and corrected validity accounting.
- The accompanying focused tests and the v4 correction fixture.

These are evaluation or audit changes and do not alter customer retrieval behavior.

### Conditionally approved after live verification

- Atomic-fact deduplication.
- Wrapped-bullet extraction and its paragraph-boundary guard.

Conditions:

1. Commit only the intended hunks; the parser and its test file contain older local work that must not be swept into the same commit accidentally.
2. For ingestion changes, build and test an isolated index before any alias or profile change.
3. Preserve the Current profile and production alias while the isolated parser candidate is evaluated.

### Rejected for promotion

- The current experimental Candidate retrieval profile. Its broader recall, selector-success, and delivery metrics are worse than Current.

### Still on hold

- The remainder of the dirty branch, including authority ranking, confidence behavior, evidence-contract changes, orchestration changes, glossary expansion, and production configuration examples. These changes predate or extend beyond the focused overnight work and must receive separate reviews and attribution.

## 6. Validation completed

- Fixture correction, reconciliation, rescoring, and failure-analysis tests: **14 passed**.
- Chunk-auditor tests: **4 passed**.
- Policy extraction tests: **22 passed**, including the final-bullet paragraph-boundary regression.
- Dirty integration-worktree suite before isolation: **790 passed**. This count includes tests for held runtime/parser work and is not the measurement-only branch baseline.
- Clean measurement-only focused suite: **49 passed**.
- Clean measurement-only complete suite: **729/729 passed**.
- Python compilation of `app`, `config`, `scripts`, and `tests`: passed.
- Linting of the new and edited tools: passed.
- Git whitespace/error check: passed; only the existing Windows line-ending warning remains for `deployment/production.env.example`.

The clean branch was tested with the project's cached Python environment and a workspace-local test directory. Every collected test passed: **729/729**. The only warning is a third-party Starlette deprecation notice about its current `httpx` compatibility shim.

## 7. Remaining work, in safe priority order

### Completed verification group

1. Verified all 46 corrected cases against source extraction and live Current/Candidate metadata.
2. Ran the fixed-checkpoint selector protocol with three selector replays.
3. Recorded retrieval presence, selector validity/relevance, stability, evidence approval, and delivery separately.
4. Preserved the passing **729-test clean-branch baseline** and the earlier **790-test dirty integration baseline** as separate measurements.

### Morning approval group B: isolated candidate-index experiment

Only after the measurement-only commit is reviewed:

1. Build a new isolated index from the wrapped-bullet/deduplicated extraction output.
2. Do not repoint production or the Current profile.
3. Compare it against Current using the frozen fixture and fixed-checkpoint protocol.
4. Require no Recall@5/10/20 regression, no country leakage, and full safety/abstention success.
5. Delete or retain the candidate index only after review; do not publish it automatically.

The parser-only build must clone Current's global-directory inventory unchanged. `PARA-INTL-DIR-038` (China) must remain present or the build is rejected as non-parity. `PARA-INTL-DIR-037` remains a shared, explicitly annotated coverage gap; raw benchmark metrics must not be adjusted after the run.

### Subsequent systemic improvements

These remain valuable but should not be implemented blindly before the reliable baseline:

1. **Entity, question-type, and authority tags** at ingestion, with human review of governing sections.
2. **Bounded authority-aware ranking** that prefers governing rules over definitions only for the matching intent.
3. **Reviewed concept expansion** for paraphrases and typos, without free-form query invention.
4. **Evidence-contract tuning** that distinguishes missing evidence from over-strict claim binding.
5. **Parent-child expansion** for complete multi-clause answers.
6. **Metadata/routing normalization** across market aliases and global-directory records.
7. **Cross-market must-abstain fixtures** for countries lacking the requested governing statement.
8. **Encoding and excerpt-boundary cleanup** for mojibake and mid-word citations.
9. **Confidence recalibration last**, using authority, scope, coverage, and conflict signals. Do not lower the global threshold.
10. **Conversation memory and follow-up rewriting** as a separate track after retrieval is stable.

## 8. Items deliberately not implemented

- Broad authority-ranking changes, because the corrected baseline is not yet live-index verified.
- Confidence recalibration, because it is the highest-risk safety lever and must be last.
- A new embedding model, vector database, Graph RAG, or OCR service, because current evidence does not identify these as the primary bottleneck.
- Semantic cache serving, because cache reuse can hide retrieval regressions; keep it shadow-only during evaluation.
- Automatic publication or production toggles.

## 9. Morning review checklist

- [ ] Review the ingestion deduplication and wrapped-bullet changes.
- [x] Confirm no unrelated dirty-worktree changes are included: 18 approved paths, zero runtime/parser/config/deployment paths.
- [x] Authenticate to AWS and run read-only live-index label verification.
- [x] Run the fixed-checkpoint selector protocol.
- [x] Run the complete clean-branch test suite: 729/729 passed; 49/49 focused tests passed.
- [x] Review Current/Candidate metrics and keep Candidate off.
- [ ] Decide whether to authorize an isolated candidate-index build.
- [ ] If authorized, run all retrieval, safety, country-isolation, legal, and response-quality gates.
- [ ] Commit each approved systemic change separately.
- [ ] Do not deploy until the candidate clears every promotion gate and production parity has a rollback plan.

## 10. Final overnight status

The local changes improve measurement trustworthiness and chunk structure without altering production. Live-index labels and fixed-checkpoint selector behavior are now verified. They do **not yet prove** that end-user answer quality has improved, because the new parser output has not been evaluated in an isolated index.

**Recommended decision:** approve the measurement/audit changes as an isolated commit; keep Candidate off; evaluate parser behavior in a separate isolated index before considering any deployment.
