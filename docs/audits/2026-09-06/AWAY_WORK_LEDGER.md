# AskVera away-work ledger

Started: 2026-09-06 17:14 UTC. Owner review pending.

## Authority and schedule

User approved local fixes, internal tests, retrieval improvements, ingestion/upload
readiness and operations portal improvements. AWS testing approved up to US$25
TOTAL for this work starting now, not per run. Earlier comparison calls precede
this authorization window. Do not deploy, push, merge, publish/delete documents,
change permissions, infrastructure, shared indexes/caches or run migrations.
Preserve existing user/Claude changes. Skip approval-blocked work and continue
independent local tasks. No credentials or secret values in logs or reports.

Existing heartbeat renewed every 30 minutes through 2026-09-07 17:14 UTC
(13:14 Toronto), or stop earlier on user return/stop/completion. This is a bounded
24-hour continuation window, not a guarantee of unattended execution. App/host
availability and tool approvals can still prevent scheduled work.

## AWS spend ledger - mandatory before every cloud batch

Budget USD: 25. Reserved USD: 0. Spent USD: 0. Unreconciled calls: 0.
No billable cloud tests have been launched under this window yet.
Before calls: verify current service/model pricing, reserve a conservative bound
for input/output tokens, embeddings, guardrails, PII, searches and retries/errors.
Record batch, models, maximum calls/tokens, estimate/reservation, actual usage and
remaining balance. Never count missing usage as zero; retain its reservation.
If cost cannot be bounded or ledger safely updated, do local work only.

## Prioritized work

| ID | Area | Status / acceptance |
| --- | --- | --- |
| R1 | Structured status/segments/coverage output | LOCAL FIX: schema-constrained output restored in isolated adapter; 12 targeted tests pass. Cloud/full-flow retest pending; not promoted |
| R2 | Follow-up query context | Pending: retain latest intent and required prior entities, including multi-turn chains; no case-string hardcodes |
| R3 | Safe follow-up after unsafe request | Pending: products/cost must not inherit income-guarantee intent; current unsafe requests still refused |
| R4 | Response language versus policy market | Pending: avoid foreign policy substitution; allow only deliberately supported response-language behavior |
| R5 | Global sponsoring/typos/clarification | Pending: target changes, field-only turns, source-bound numbers, no retired global office source |
| R6 | Retrieval evaluation | Pending: verified source labels, broader unseen phrasing, separate retrieval/selector/approval/writer metrics; both actual answers and failures |
| I1 | Portal upload metadata | PARTIAL LOCAL FIX: removed BE/nl and first-market/language fallbacks; explicit selections and live config required. Contradictory document metadata/content checks and backend lifecycle audit remain pending |
| I2 | Parse/chunk completeness | Pending: scanned/mixed PDFs, empty pages, tables, headings, contact fields, multilingual text; flag uncertain/failed extraction |
| I3 | Approval/publication lifecycle | Pending: duplicates/retries, partial failure, stale generation, atomic activation, approved-only visibility, no premature ready state |
| I4 | Upload-to-answer test | Pending: isolated test fixtures, confirm provenance and country/global boundaries; no live publishing |
| P1 | All portal pages functional audit | Pending: Overview, Live flow, Knowledge, Market readiness, Insights, Support, Users, Widget |
| P2 | Portal UX/accessibility | Pending: loading/error/empty states, honest non-demo metrics, keyboard/focus, responsive layout, consistent visual polish |
| C1 | Conversation usability | Pending: greetings, thanks, clarifications, appropriate tone; no ungrounded factual additions |
| G1 | Regression/release review | Pending: unit/integration/build/lint/security, safety, fresh multilingual cases, latency; deployment held |

## Baseline and evidence

Last local suite: 1,234 passed. Latest frozen full-chat experiment:
FOLLOWUP_SEGMENTS_RESULTS.md / segments-followups-03. HOLD: 0/4 candidate writer
outputs accepted, context and language problems remain. Do not claim significant
retrieval improvement from unit counts or structural binding alone. Preserve
all earlier experiment artifacts unchanged.

## Checkpoints

- Checkpoint 7 (2026-09-07 03:16 UTC scheduled continuation): local-only. Added
  explicit experimental context limits: 32 prior questions and 16,000 total
  question characters. Oversized dependent chains fail before retrieval instead
  of silently dropping the topic/country anchor. Independent fresh questions do
  not inherit or get blocked by oversized unrelated history. Candidate/adapter
  suite: 17 passed; lint and whitespace checks passed. Full suite not rerun at
  this checkpoint (last full run: 1,255). These limits are NOT an AWS dollar cap:
  evidence prompts, provider retries, token prices and other services remain to
  be bounded and reserved before cloud calls. Budget remains reserved 0/spent 0.
  No model comparison, publishing or deployment performed.

- Checkpoint 6: connected `followup_chat_adapter.py` through the isolated harness
  `--followup-context` option. Both arms use the same local code; only fixed gets
  the context adapter. CLI rejects combining with selector/segments candidates;
  manifests identify local control, the factor and adapter hashes. Process-local
  patches restore after use. Global directory targeting uses the latest explicit
  country-bearing user turn, while locale retrieval still receives the session
  country and cross-market policy refusal remains enabled. Two integration tests
  verify Germany after Belgium/elaboration, foreign-local-evidence detection,
  fresh-request reset, original-question references, and patch restoration.
  Full local suite: 1,255 passed, two dependency warnings; targeted lint and diff
  checks passed. Graphify remains unavailable. No cloud batch launched or spend.
  Next: bounded matched model run with recorded questions/answers and verified
  budget reservation. This is not yet end-to-end answer-quality validation, and
  other retrieval ranking inputs still include historical market names. Check
  all downstream consumers before considering promotion. Production unchanged.

- Checkpoint 5: added isolated `scripts/followup_context_candidate.py`, NOT wired
  into runtime. Separates the exact current question, prior user topic chain,
  and latest explicit target-market set. Preserves intervening country changes
  through elaboration, resets history for independent new topics, and retains
  multiple explicit targets without arbitrarily choosing one. Target markets
  do not authorize foreign policy access. Eleven targeted tests pass, including
  configured localized market names. Full suite: 1,253 passed, two warnings;
  lint/whitespace checks passed. Graphify unavailable. No AWS spend/deployment.
  Next: integrate structured target selection into an isolated comparison arm,
  not by concatenating every country's name into existing directory lookup.
  Preserve selected-policy-market constraints independently and test scope at
  retrieval and evidence approval. Existing dependence classifier limitations,
  explicit first-question references, unsafe dependent-history contamination,
  ambiguous targets, bounded-history behavior and fully multilingual reference
  recognition remain open. This checkpoint does not fix production context or
  demonstrate model answer improvement.

- Checkpoint 4: narrow R2 fix in `_build_retrieval_query`: recognized short
  reference follow-ups now retain their exact latest question alongside the
  anchor instead of replacing it. `_build_request_query` avoids adding that
  same labeled question twice. Existing topic-shift handling is unchanged.
  Added preservation cases for credit timing, expiry, returns, and unsafe income
  intent; adjusted previous tests that expected the question to be discarded.
  Orchestrator tests: 73 passed. Full local suite: 1,242 passed, two existing
  dependency warnings. Targeted lint and diff whitespace checks passed.
  Graph update again unavailable. No AWS calls or deployment.
  R2 remains PARTIAL: anchor selection across multi-turn topic/market changes,
  unrecognized or non-English references, and safe turns after unsafe history
  still need work. Real retrieval/answer quality requires the held-out comparison;
  unit preservation tests do not prove a retrieval-quality gain.

- Checkpoint 3: removed the office/staff parser fallback from
  `services/knowledge_ingestion.py::_extract_directory_sections`. The legacy
  office_directory type now accepts only the sponsoring parser; unrecognized or
  retired formats produce a non-retryable failure before approved-source upload,
  indexing or document recording. Updated ingestion regressions to assert those
  publication steps are not called, while sponsoring country/kind metadata stays
  intact. Targeted ingestion/review suite: 30 passed. Full local suite: 1,238
  passed, two dependency deprecation warnings. Initial sandbox temporary-folder
  access errors resolved by the approved local rerun. No AWS calls, existing
  documents/indexes unchanged, no deployment. This does not certify arbitrary
  mixed-document recognition or extraction completeness; those remain I2 work.
  Graph update attempted but graphify is not installed/available on PATH.

- Checkpoint 2: upload scope audit confirmed `DOCUMENT_TYPES` already contains only
  policy and office_directory. The hypothesized other/FAQ global-upload loophole
  is NOT present; no redundant runtime restriction was added. Added four regression
  cases proving even super admins cannot upload other/FAQ global content, global
  policies, or country-scoped directories, before reading/staging file content.
  `tests/unit/test_admin_rbac.py`: 32 passed. No cloud calls or deployment.
  Important remaining I2 review: `_directory_sections_from_pdf` still accepts the
  retired office/staff extractor as fallback. Inspect downstream publication and
  retrieval protections and replace this ingestion acceptance with an explicit
  unsupported-document result, preserving sponsoring extraction and testing both.
  Do not infer currently exposed answers solely from parser acceptance.

- Schedule renewed and scope/budget recorded. No deployment authorization granted.
- Next agent: start with R1 and I1; update this ledger with concrete files, tests,
  failures and approval-needed items after each independently tested change.
- Checkpoint 1: `scripts/segments_chat_adapter.py` now supplies Bedrock outputConfig
  with exact status/segments/coverage JSON schema. Keeps strict parsing, source
  quote membership, coverage verdict, provider parameters and existing guards.
  `tests/unit/test_segments_chat_adapter.py`: 12 passed; targeted lint passed.
  No billable calls made under the new budget yet. Next: validate current pricing
  and pre-reserve a bounded cloud test; do not run the old unlimited-by-dollar harness.
- Checkpoint 1: `admin-portal/src/components/KnowledgeUploader.tsx` requires an
  explicitly selected document market and source language; no first-entry fallback,
  no live upload using demo/unloaded configuration. Invalid replacement file clears
  stale selection. Cancellation text no longer falsely claims server processing
  never began. Corrected global source description to sponsoring-only. Portal
  TypeScript check passed; browser/behavioral upload testing remains pending.
- `git diff --check` passed. Changes remain uncommitted for user review; pre-existing
  changes preserved. Remaining scope is substantial; do not mark portal or ingestion
  readiness complete based on this first checkpoint.
