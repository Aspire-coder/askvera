# AskVera complete improvement handoff: strategy, gaps, implementation, deployment and tests

Prepared September 7, 2026. Based on the local work ledger and saved comparison results.

## 1. Executive summary

**Several safeguards and experimental fixes are implemented locally. A significant improvement in actual chatbot answer quality has NOT yet been demonstrated. Deployment remains on hold.**

- Last full local unit suite: **1,255 passed**, with two dependency deprecation warnings.
- After the latest context-size change: **17 targeted tests passed**; the full suite was not rerun at that checkpoint. These counts overlap and must not be added together.
- Latest completed model comparison is still the earlier failed comparison. We have not rerun it with the latest fixes.
- Production, shared indexes, published documents and shared caches were not changed during this work window.
- The checkout contains substantial uncommitted work, including pre-existing user/Claude changes. Not every changed file represents a newly completed or approved fix.
- Local HEAD inspected: `7d29dad`, “Merge pull request #56 from Aspire-coder/fix/candidate-mode-narrowing-loop-and-directory-address-regex”. This is not a fresh verification of the remote branch or deployed commit.

This report covers the current improvement window. It is not a claim that every historical enhancement in the conversation has been audited or deployed.

## 2. Spending: what has actually been used?

| Item | Recorded status |
| --- | --- |
| Approved additional AWS test budget | US$25 total, not per run |
| Budget window began | September 6, 2026, 17:14 UTC |
| Reserved for new tests | US$0 |
| Recorded new test spending | US$0 |
| New billable cloud test calls in this window | None launched |
| Remaining authorized test budget | US$25 |
| Existing AWS hosting costs and earlier experiments | Not measured in this report |

**US$0 refers only to the new tests in this authorization window. It does not mean your AWS account, EC2, OpenSearch, storage or earlier model experiments cost nothing.** This is a work-ledger report, not an AWS billing reconciliation. Codex subscription/usage costs are also outside this ledger.

Why the new model comparison has not run: the runner limits call counts, but that alone is not a reliable dollar cap. We still need verified pricing and a conservative allowance for model inputs/outputs, embeddings, guardrails, PII checks, search costs where applicable, retries and failed calls with unknown usage. The new context-size limit does not solve that entire cost-control requirement.

Before spending: reserve a bounded batch amount, run only within that reservation, record actual usage, and retain the reservation for unresolved calls. Stop before the cumulative US$25 authorization is exhausted.

## 3. What is implemented locally?

| Issue | Local change | Evidence and remaining limit |
| --- | --- | --- |
| Structured answers were rejected because the model returned fenced JSON | Restored a JSON schema for status, answer segments and coverage in the experimental writer adapter | 12 targeted tests passed at that checkpoint. Actual model/full-chat retest pending |
| Upload form silently selected Belgium/Dutch or the first available market/language | Requires explicit market and source-language choices and successfully loaded live configuration | Portal TypeScript check passed. Browser upload testing and server-side content/metadata consistency remain pending |
| Invalid replacement file could leave an old file selected; cancellation wording overstated what stopped | Clears stale file selection and warns that processing may already have reached the server | Local UI changes; behavioral verification pending |
| Risk of unsupported global document types | Confirmed the API already rejects unsupported types and invalid policy/directory scope combinations; added four regression cases | 32 access-control tests passed. This was an existing protection verified, not a newly discovered open loophole |
| Ingestion still accepted the retired office/staff directory parser as fallback | Removed that fallback. Only the sponsoring parser is accepted under the legacy `office_directory` type | 30 ingestion/review tests passed. Rejection tested before approved-source upload, indexing and document recording. Existing indexed content was not deleted |
| Some short follow-ups replaced the current question with an older question | Keeps the exact latest question alongside its anchor; avoids duplicating the follow-up label | 73 orchestrator tests passed at that checkpoint. Recognition and history selection are still incomplete |
| “Belgium → Germany → tell me more” could revert to Belgium | Built a separate context candidate retaining the topic chain and latest explicit country target | Local tests pass. Not enabled in the normal production path |
| Need to compare the context candidate fairly | Added `--followup-context` to the isolated comparison runner; same local code in both arms, adapter only in candidate | Two integration tests check country targeting, foreign-policy detection, fresh-request reset and patch restoration. Actual answers not yet compared |
| Long follow-up chains could grow without an experiment limit | Limits experimental context to 32 prior questions and 16,000 question characters; rejects excess instead of silently dropping the anchor | Latest candidate/adapter suite: 17 passed. Not an AWS cost cap or a polished user-facing recovery flow |

Targeted lint and whitespace checks passed at the recorded checkpoints. The optional graph update could not run because `graphify` was unavailable.

## 4. What did the last actual model test show?

The frozen `segments-followups-03` comparison scheduled 42 turns: seven three-turn conversations, tested in two arms.

- 38 actual responses were recorded.
- Two turns failed request validation, and two dependent turns were skipped.
- The candidate reached its segment writer four times; **all four outputs were rejected**.
- There were 282 successful recorded AWS calls across models, embeddings and PII checks. That is not 282 answers, and those calls predate the new budget window.
- The arm called “current” was an experimental local control, **not deployed production Current**.

The failures included lost follow-up intent, safe product-cost questions inheriting an earlier income-guarantee refusal, weak sponsoring-country/telephone follow-ups, and rejection of an English-language request with Germany selected.

Therefore: there is no defensible “retrieval improved by X%” number yet. Passing unit tests establishes useful code behavior, not successful source retrieval or correct final answers.

## 5. What remains pending?

### Retrieval and conversation: highest priority

1. Run the repaired writer and context candidates separately through real answer generation.
2. Fix safe follow-ups after unsafe requests: retain necessary product/rank references without treating an old income-guarantee request as the current intent.
3. Recognize more genuine follow-ups, including field-only requests such as “just the telephone number,” and multilingual references. Do not hardcode only the evaluation strings.
4. Check every downstream use of historical country names. The adapter fixes one directory-targeting path, but other ranking inputs still contain older countries.
5. Verify governing-rule selection: joining versus ongoing fees; monthly activity versus incentive-payment conditions; definitions versus the rule actually requested.
6. Verify completeness, no unasked escalation/details, exact numbers and contact formatting, and each claim's own supporting passage.
7. Decide supported response-language behavior separately from document-market authority. Translating a German rule must not authorize US policy substitution.
8. Test greetings, thanks, clarifications, topic resets and fresh sessions alongside medical/income refusals.

### Upload, parsing and publication

1. Detect missing or contradictory document country/language/type metadata; hold uncertain content for review rather than silently authorizing it.
2. Audit scanned and mixed PDFs, OCR failures, missing pages, tables, headings, broken characters and contact fields. Flag extraction uncertainty; do not promise zero loss without comparison to the source.
3. Test duplicate uploads, retries, failed/partial jobs, stale generations, approval transitions and approved-only visibility.
4. Test a complete isolated upload-to-answer lifecycle. Local mocks are not that test.
5. Confirm retirement protections beyond the parser. The local fallback removal does not clean up existing stored/indexed documents.

### Operations portal

The full review of Overview, Live flow, Knowledge, Market readiness, Insights, Support, Users and Widget is still pending. Check actual functionality first: loading/error/empty states, accurate live-versus-demo status, permissions, upload progress and failure recovery. Then review keyboard access, focus, responsive layout and visual consistency. A TypeScript pass is not a page-by-page browser review.

## 6. How we will improve retrieval: the procedure

### Step 1 — Freeze an identifiable baseline

Record the exact code revision plus uncommitted code hashes, document versions/hashes, active generation IDs, model, prompts, settings, selected market/language and cache behavior. Preserve old artifacts. Label a local experimental control honestly; do not call it deployed Current.

### Step 2 — Establish source-grounded test cases

For each supported market, verify expected passages against that market's own document. Cover everyday paraphrases, typos, joining/cost/qualification questions, follow-ups, returns, sponsoring contacts and negative cases. A missing joining sentence alone is not enough to label a whole question “must abstain”; inspect all relevant local rules first.

Use frozen regressions plus an independently held-out set. Once a question is used to tune a fix, it is a regression case, not truly unseen evidence. Keep factual gold answers out of model prompts.

### Step 3 — Locate the failure before changing a component

| Stage | Question to answer |
| --- | --- |
| Extraction | Is the required passage present and readable in parsed text? |
| Chunking/indexing | Is it indexed with the right scope, version and section identity? |
| Retrieval | Does it appear in the top candidates? |
| Selection | Is the governing passage chosen rather than a related definition? |
| Approval | Is valid evidence rejected, or unsupported evidence accepted? |
| Generation | Does the final answer contain the necessary facts and conditions without additions? |
| Citation/display | Does each displayed claim bind to its own source, with intact numbers and formatting? |
| Conversation | Is the current intent preserved, with only appropriate historical context? |

Fix the measured stage. Do not lower confidence merely because answers are missing.

### Step 4 — Change one factor at a time

First retest the structured writer repair and context candidate as separate experiments. Do not combine selector changes, new chunks, confidence tuning and prompt changes in one result. If ingestion representation is the cause, evaluate that on an isolated index with explicit approval; do not modify the shared index during diagnosis.

For context, keep three concepts separate: the question now being asked, relevant historical entities/topic, and the requested target country. A requested foreign country is not permission to answer its company policy.

### Step 5 — Run bounded matched comparisons

After cost verification/reservation, start with a small smoke batch. Record failures rather than silently retrying or substituting drafts. If the path works, repeat matched runs where feasible to expose model variability, then use fresh held-out cases. Keep cache-free retrieval evaluation separate from cache-hit correctness tests; cached answers can bypass the very retrieval path being measured.

For every turn save: exact question, selected market/language, actual history, control answer, candidate answer, citations/source identities, retrieved ranks, selected evidence, rejection reason, latency and usage. Retain refused, failed and skipped turns visibly.

### Step 6 — Judge retrieval and final answers separately

Report passage Recall@1/5/10/20, first-correct-passage rank, selector success, approval outcomes, and final correctness/completeness with explicit denominators. Separately report inappropriate refusals, unsafe answers, wrong-market answers, source-binding errors and latency. No single aggregate should hide a safety regression.

### Step 7 — Promotion gate, then user review

Before deployment, require documented improvement on fresh source-grounded questions, no unresolved critical safety/scope/citation regressions, verified follow-up behavior, full applicable tests/builds, and upload/publication checks for ingestion changes. Agree numeric thresholds before the final evaluation rather than choosing them after seeing results.

Prepare a review packet with changes, actual answer comparisons, remaining limitations, cost and rollback plan. Commit/push/merge/deploy and live document/index changes remain separate approval steps. After approved deployment, verify the deployed revision/configuration and run production-parity checks.

## 7. Non-negotiable boundaries

- Selected US market + Belgian company-policy request: do not answer from Belgian policy or silently substitute US rules.
- Selected US market + Belgian international sponsoring request: may answer from an approved global sponsoring record, if the required fact exists.
- Retired global office/staff directory: not an alternative source.
- Safe plus unsafe compound request: answer the supported safe part and refuse the unsafe part.
- Do not invent prices, convert credits into currency without evidence, guarantee income or generate prohibited medical claims.
- Never relax country restrictions or confidence thresholds simply to increase the answer count.

## 8. Immediate next deliverable

**A cost-bounded comparison report showing both actual answers, not another unit-test count.** Before that run, finish cost verification and inspect remaining historical-country consumers. If cloud execution is blocked, record the blocker and continue independent local ingestion/portal checks without representing those checks as retrieval gains.

## Evidence and local locations

- Checkout: `C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy`
- Work ledger: `docs/audits/2026-09-06/AWAY_WORK_LEDGER.md`
- Frozen failed comparison and both answers: `docs/audits/2026-09-06/FOLLOWUP_SEGMENTS_RESULTS.md`
- Writer adapter: `scripts/segments_chat_adapter.py`
- Context candidate and adapter: `scripts/followup_context_candidate.py`, `scripts/followup_chat_adapter.py`
- Isolated comparison runner: `scripts/run_matched_chat_comparison.py`
- Runtime follow-up logic: `app/orchestrator/chat_orchestrator.py`
- Ingestion: `services/knowledge_ingestion.py`
- Upload form: `admin-portal/src/components/KnowledgeUploader.tsx`

Status is based on saved test evidence and the inspected local checkout, not a new production audit or billing query.

## 9. Deployment versus implementation: the exact distinction

There are three different baselines. They must not be presented as one version:

1. **Observed live widget:** tested on September 5. Its deployed commit, flags and cache provenance were not verified in that UI test.
2. **Local committed baseline:** `7d29dad`. Git history includes the admin experimental-behavior toggle and the subsequent narrowing-loop/email-address regex fix. A merged commit is not proof of deployment.
3. **Local working tree:** baseline plus substantial uncommitted changes and experimental scripts. This is what the recent local tests exercised.

| Change or capability | What can be established | Deployment status |
| --- | --- | --- |
| Live widget answers, sources and safety responses | Observed in the September 5 UI smoke test | Live behavior observed then; current deployment identity unverified |
| April office directory retirement | September 6 registry snapshot reports it removed from active publications; sponsoring is the sole active global publication | Historical live source-state change verified at that snapshot, not a new change in this window |
| Post-retirement section inventory | Snapshot reports UK English 728 sections, US English 435, sponsoring 113 | Historical index snapshot, not current live revalidation or passed questions |
| Admin candidate toggle and narrowing-loop/regex fix | Present in local merged Git history | Deployment not newly verified |
| Stage A/B/C fixes described below | Documented local implementation and tests | No deployment established by these records |
| New uploader defaults, sponsoring-only parser fallback removal, latest-question preservation | Local source edits, with recorded tests | Not deployed in this work window |
| Structural selector, bound review, scoped writer, segments writer and structured follow-up adapter | Evaluation components or harness-only integrations | Experimental; not approved for live activation |
| Authority-aware ranking, complete parent-child retrieval and signal-calibrated confidence | Larger roadmap work, not completed by the narrow fixes | Not approved for deployment |

The earlier retirement did not delete the S3 source file. The newer parser change prevents future ingestion through the retired fallback; it is not a claim that this safeguard was present during the historical retirement.

Before declaring exactly what is deployed, collect the running backend revision/image, widget and portal artifact versions, effective model/prompt/feature flags, active document generations and cache namespace. Compare them to the tested manifest. This report deliberately does not invent those values.

## 10. Additional work already built before the latest checkpoints

The September 5 implementation ledger records the following local changes. These expand the scope of the handoff beyond the most recent fixes in section 3. They are not all newly re-audited line by line for this report.

| Area | Recorded implementation | Important unfinished scope |
| --- | --- | --- |
| Administrative authorization | Publication permission checks, global-publication restrictions, review-by-default uploads, opt-in before flattening heterogeneous market permissions | Browser permission-editing checks and full approval lifecycle |
| Evidence eligibility | Per-document locale filtering, validity/lifecycle checks, generation checks on cached evidence, nested metadata preservation | Existing-index backfill and comprehensive lifecycle parity |
| Global versus local evidence | Reapprove global evidence alone on foreign-market requests; scoped confidence cannot borrow strong local evidence | General mixed local/global compound requests can still lose an answerable half |
| Country recognition | Configured aliases and CLDR-derived localized country names across 155 two-letter regions and 38 configured languages | Recognition is not policy permission; arbitrary inflections, suffixes and typos are not solved |
| Parsing | OCR/extracted pages forwarded to specialized parsers, unrecognized policy bodies rejected, expiry propagated, short non-PDF notice exception | Real-file page/table coverage, partial OCR, legacy lifecycle metadata |
| Numeric/contact output | Source-matched complete phone values treated atomically; checks for altered digits, fragments and wrong numeric subjects | Source role/market correctness and real end-to-end phone delivery |
| Policy versus unsafe claims | Strict legitimate policy-prohibition questions can enter retrieval; appended unsafe instructions do not gain that exemption | General multilingual classification and final-answer verification |
| Compound requests | Narrow two-clause English question plus unsafe writing command decomposition; safe pipeline preserved; cached safe reply not mutated | Ambiguous, implicit, quoted, dependent, multilingual and more-than-two-clause cases |
| Session history | Actual delivered request/reply persisted once, including refusals/cache hits; newline role spoofing prevented | Typed context resolution and broader terminal-path verification |
| Prompt | Shorter source-grounded instructions; qualifications, local/global boundaries, warmer style; history/source data separated from system instructions | Model compliance, complete answers and tone consistency |
| Citations | Exact known citation-ID cleanup before numeric validation, explicit approved references preserved, malformed contract fields rejected | Semantic support and complete claim coverage |
| Portal | Live flow avoids demo traces for successful empty results; Overview panels load independently with request versioning; safer permission editing | Full page/browser review, Insights races, accessibility and load behavior |
| Widget | Expected-answer feedback uses the correct API field; source-link restrictions | Browser end-to-end checks |
| Parent identity | Cross-document parent-identity collision corrected | This is NOT implementation of parent-child retrieval expansion |

Historical full-suite checkpoints ranged from 810 to 841 tests for earlier remediation, and increased through later experiments. Do not add those counts or assume a historical build validates the newest tree. The last full run is the 1,255-test checkpoint already listed.

## 11. Actual strategy for the existing application

**Improve the existing pipeline in place. Do not replace it with an entirely new RAG architecture or add model calls simply because they seem more sophisticated.** Keep the current session admission, source eligibility, market restrictions and output safeguards. Replace only the failed behavior at each boundary, behind isolated evaluation until verified.

Proposed target flow:

```text
User question + selected policy market + response language
  -> current-intent classification and bounded context resolution
  -> authorized document scope (local policy OR approved global sponsoring)
  -> candidate retrieval
  -> governing-rule selection with stable source identity
  -> evidence support / completeness approval
  -> one set of source-linked answer segments
  -> mechanical displayed-answer assembly
  -> numeric/contact, safety and citation checks
  -> delivered answer + correctly scoped cache and session history
```

This is the target design, not a statement that every step is currently integrated and proven.

### A. Resolve the question before retrieval

Current gap: short-reference heuristics and older anchors can drop new intent, inherit old unsafe intent, or target an earlier country.

Implement: maintain the latest requested action separately from topic entities and target country. Retain the exact current question. Update country targets only from explicit user context; comparisons retain multiple targets. Reset irrelevant history on an independent new topic. Do not treat historical assistant text as evidence. Ask a clarification when the necessary entity is unavailable instead of making one up.

Already built: narrow latest-question preservation and an isolated structured-context adapter. Still needed: safe entity inheritance after unsafe requests, field-only references, multilingual dependence classification, selected-market changes and checking every downstream consumer.

Expected benefit: retrieve evidence for the question actually asked, with fewer stale-topic refusals and wrong-country searches. Proof required: multi-turn delivered-answer comparisons, not only matching the target-country field.

### B. Keep source scope independent of conversation context

Implement: selected market controls company-policy eligibility. Global sponsoring uses the requested record country but only the approved sponsoring source. Repeat eligibility checks after selection and on cache replay. A country name in a prompt must never change access authorization.

Already built: local scope/generation safeguards and experimental latest-target directory routing. Still needed: all-consumer integration tests, mixed requests, stale cache/source lifecycle and unsupported-market cases.

Expected benefit: useful cross-country sponsoring answers without leaking foreign company policies.

### C. Select the governing rule, not just a related paragraph

Implement: separate the entity mentioned from the property requested. For example, mentioning rank does not automatically make the question about rank retention; it may ask whether monthly activity must be requalified. Select the applicable rule and necessary definitions/conditions. Bind quotes to stable document-generation-section identities, not just a candidate's list position.

Already built: governing/source-binding components and several selector experiments. Some experiments improved evidence selection but did not meet final approval requirements. Three initial selector proposals were rejected.

Still needed: independent labels, varied phrasing and wrong-rule controls; an evidence-set approval contract compatible with the selected evidence. Do not manufacture an approved flag or copy a differently defined confidence score into the current gate.

Expected benefit: fewer apparently relevant but legally incomplete or incorrect answers. If the passage is missing from the index, fix extraction/chunking in a separate experiment rather than asking selection to recover absent text.

### D. Generate each displayed statement once

Implement: model returns ordered text segments with their own supporting source references and quotes. Validate the structure and evidence, then join those exact segments to form the displayed answer. Do not independently regenerate an answer and its claim list: that caused wording mismatch.

Already built: single-text binding and experimental schema-constrained writer. Component results are promising structurally, but the full-chat integration failed before the schema repair and has not been rerun afterward.

Still needed: semantic support, required-condition completeness, refusal behavior, exact contact formatting and scope discipline. Quote membership alone does not prove that a statement follows from its source.

Expected benefit: remove duplicated wording drift, prevent correct quotes being attached to different displayed claims, and reduce unnecessary planning/repair work. No full-chat latency improvement is yet proven.

### E. Protect ingestion before increasing recall

Implement: stage uploads, validate metadata and extraction, show uncertain pages/fields for review, and activate only a verified approved generation. Preserve page/section provenance and table/contact relationships. Never silently accept uncertain country/language authority because the uploader left fields blank.

Already built: explicit portal choices, several parser/lifecycle safeguards and sponsoring-only parser acceptance. Still needed: actual PDF coverage measurement, contradictory metadata, OCR/table cases, retry/duplicate/partial activation and isolated upload-to-answer tests.

Expected benefit: the index contains the correct, complete, authorized material; retrieval cannot compensate for an omitted governing clause or mislabeled country.

### F. Optimize ranking and confidence only after these boundaries are measurable

Authority tags, parent-child expansion, embedding/ranking alternatives and calibrated evidence signals remain separately evaluated later tracks. Prefer a measured, isolated gain over stacking all of them. Confidence tuning is last and requires safety/unsupported-evidence evaluation, not recall alone.

Caching remains an optimization, not a source of truth. First compare cache-free retrieval. Then verify cache isolation by market, language, source generation and relevant versions, plus follow-up-specific keys and revoked-source rejection.

## 12. Tests performed and what they actually taught us

These are distinct experiments with different inputs, schemas and snapshots. Their scores must not be pooled into one success percentage.

| Recorded test | Result | What it taught us / what it does NOT prove |
| --- | --- | --- |
| September 5 production UI smoke | FBO expansion answered but over-detailed; Belgium phone omitted despite source excerpt containing it; legitimate medical-policy question refused; unsafe claims refused; mixed safe half lost | Visible output problems confirmed. Exact deployed root cause and cache-free retrieval rate not established |
| Three selector experiments | 108 model calls; selected-set candidate 6/18 vs control 12/18, quote-first 12/18 vs 12/18, polarity 13/18 vs 12/18 | All rejected. Wrong governing-rule interpretation, instability and wrong quote/source association; differing contracts make scores non-equivalent quality percentages |
| Remaining Canada refusal probes | 20 calls for target-property wording, 20 for explicit decision protocol; candidate checks 9/10 and 6/10 respectively | Wording alone did not solve refusal; plausible prose cannot override an invalid support decision |
| Structural full-chat integration | 10 questions × two arms, 20 responses; five answerable policy requests reached relevant bound evidence but were stopped at approval | Better selection alone did not recover answers. Refusal layers differ and need distinct fixes |
| Scoped writer comparisons | Two separate 20-response runs; improvements on reused activity/qualification cases; Canada paraphrase still added unasked bonuses | Useful case-level progress, not a held-out overall gain. Final citation-display patch happened after the cloud runs |
| Extra answer-plan experiment | 36 calls; binding valid 1/12 direct vs 5/12 planned; component median 2.76s vs 4.43s including plan | Extra planning still failed often and added measured component latency. Do not integrate it as the solution |
| Single-text component | 24 calls; candidate 12/12 structurally valid vs dual-text 0/12; component medians 2.62s vs 2.80s | Supports one-text assembly. Does not establish general correctness, safety, retrieval improvement or full-chat speed |
| Full-chat segments/follow-up comparison | 42 scheduled turns, 38 responses, two validation errors, two dependent skips; writer 0/4 accepted | Integration failed even after successful component tests. The latest schema repair needs a fresh run |
| Latest local runtime/candidate tests | Last full suite 1,255 passed; subsequent 17 targeted tests passed | Specific code paths verified locally. No new actual-model comparison under the current US$25 budget |

The locally tested source-binding and phone fixes are not proof that every generated statement is grounded or every phone number is correctly labeled. The proper test is the final displayed answer against the correct source record, not merely the presence of a matching number somewhere in retrieved text.

## 13. Gap-to-action map and acceptance evidence

| Gap | Fixed or built now | Remaining implementation / evidence |
| --- | --- | --- |
| Basic answerable questions abstain | Several failure mechanisms isolated | Trace each miss and measure actual recovered correct answers without new unsafe answers |
| Latest follow-up discarded | Narrow local fix | Fresh paraphrases and full turn sequences, including references without existing English markers |
| Country switches forgotten | Experimental adapter | Verify every retrieval/approval/writer path and selected-market transitions |
| Old unsafe intent contaminates safe product question | Standalone reset tested only | Resolve dependent safe entities without inheriting unsafe action; keep new unsafe requests refused |
| Wrong governing passage | Source-binding/selection candidates built | Independent rule labels, governing-first validation, compatible evidence approval |
| Answer/claim wording drift | Single-text candidate built | Full-chat schema repair retest; semantic completeness and output guardrails |
| Unasked details / missing conditions | Prompt and scoped writer work | Fresh cases for both over-inclusion and over-exclusion |
| Phone missing/broken output | Local phone/citation validation fixes | Delivered role-labeled numbers, no neighboring-record substitutions or blank labels |
| Language tied to market | Identified, not resolved | Explicit supported language policy and same-market source proof |
| Misleading metadata defaults | Portal fix | Server-side contradictions and publication review; browser proof |
| Retired office parser accepted | Local fallback removed | Deployment review; lifecycle tests and no accidental republishing |
| Missing text/OCR/table fidelity | Partial parser changes | Source-to-chunk page/table coverage and reviewable uncertainty |
| Portal reliability and polish | Several partial changes | Every page, race/loading/error/empty state, authorization and accessibility verification |
| Runtime latency | Component timings only | Whole-turn p50/p95, call counts and timeout/failure rates on representative cases |
| Release readiness | Local tests, historical smoke evidence | Fresh full comparison, safety/Legal gates, CI environment, user approval and deployed parity |

## 14. Implementation and release order

1. Preserve the current dirty checkout and export its change inventory; do not overwrite user/Claude work.
2. Complete the cloud-test spending bound and reserve the small first batch from the cumulative US$25 authorization.
3. Retest schema-constrained single-text generation in the full path as one candidate. Keep actual rejected drafts separate from delivered answers.
4. Test structured follow-up context as a separate candidate on the same frozen local baseline. Include fresh independent questions and unsafe-history controls.
5. Resolve remaining evidence-set approval and governing-rule misses without lowering global confidence thresholds.
6. Test approved improvements together only after their individual comparisons are understood; verify interaction regressions.
7. In parallel, finish independent local ingestion/portal safeguards. Any shared-index or live-publication work requires separate approval.
8. Run source-grounded held-out and full safety/Legal/market/language checks, repeated where practical within budget. Report failures, skips and limitations honestly.
9. Run full local/CI checks on the exact proposed release state; inspect the entire dirty diff and split experiments from production changes.
10. Present the review packet for approval. Only then perform separately approved push/merge/deploy actions and verify live parity/rollback readiness.

No date or percentage improvement is promised before these gates are measured. General multilingual coverage, zero information loss and universal conversational understanding are goals requiring evidence, not completed features.

## 15. Evidence index and export boundaries

This Markdown is the consolidated strategy/status/test handoff. It is **not a raw source-code dump**, a fresh AWS inventory, or an export of credentials/customer data. All known open categories are included; unknown deployment state and unverified behaviors remain explicitly marked rather than filled in from memory.

The following repository-relative files contain the detailed history, protocols and captured outputs. Earlier notes are historical and may be superseded by later checkpoints:

- `docs/audits/2026-09-05/IMPLEMENTATION_STATUS.md` — Stage A–D, historical local checks and limitations.
- `docs/audits/2026-09-05/PRODUCTION_UI_BASELINE.md` — exact visible questions/answers and observation limits.
- `docs/audits/2026-09-05/POST_RETIREMENT_BASELINE.md` — historical registry/index/source identity evidence.
- `docs/audits/2026-09-05/SELECTOR_EXPERIMENT_REVIEW.md` — 108-call rejected selector experiments.
- `docs/audits/2026-09-05/GOVERNING_BINDING_INTEGRATION_REVIEW.md` — governing/binding integration history.
- `docs/audits/2026-09-06/REMAINING_REFUSAL_REVIEW.md` — Canada refusal probes.
- `docs/audits/2026-09-06/STRUCTURAL_DECISION_REVIEW.md` and `STRUCTURAL_CHAT_REVIEW.md` — selector decision and full-chat reviews.
- `docs/audits/2026-09-06/BOUND_EVIDENCE_APPROVAL_REVIEW.md` — evidence-review controls and integration history.
- `docs/audits/2026-09-06/SCOPED_WRITER_REVIEW.md` — writer comparisons and later offline citation changes.
- `docs/audits/2026-09-06/FINAL_CLAIM_BINDING_REVIEW.md`, `PER_CLAIM_REVIEW.md`, `STRUCTURED_CLAIM_REVIEW.md`, `FRAGMENT_REVIEW_RESULTS.md`, `RELEVANCE_ONLY_RESULTS.md` — supporting experiment reports; not separate deployment approvals.
- `docs/audits/2026-09-06/ANSWER_PLAN_PROTOCOL.md` and `ANSWER_PLAN_RESULTS.md` — rejected extra-planner direction.
- `docs/audits/2026-09-06/SEGMENTS_PROTOCOL.md` and `SEGMENTS_RESULTS.md` — single-text component experiment and both outputs.
- `docs/audits/2026-09-06/FOLLOWUP_SEGMENTS_RESULTS.md` — latest frozen full-chat questions and both actual outcomes.
- `docs/audits/2026-09-06/AWAY_WORK_LEDGER.md` — latest incremental changes, budget and pending work.

Do not infer that every supporting report was revalidated against the current tree. The detailed claims and counts above come from the specific records identified; additional files are indexed for handoff continuity.

### Decisions/approvals still needed

- Confirm response-language support when source language and selected market differ.
- Supply/confirm current Legal-approved wording and its applicable markets/version before closing Legal completeness.
- Approve any live index publication/backfill, deployment or access/infrastructure change separately.
- Approve spending beyond US$25 only if it becomes necessary; the current authorization has not been consumed by new AWS tests.

**Bottom line:** the strategy is to stop losing the user's intent, select and approve the right authorized rule, generate source-linked wording once, and verify the exact displayed answer. The main unfinished proof is a fresh, bounded, end-to-end comparison of the repaired pipeline.
