# Audit remediation working ledger

Baseline: 7d29dad. No deployment or runtime flag changes authorized by this work.

## Stage A - in progress

Implemented with local unit-suite verification: publication permission checks,
global publication restriction, review-by-default uploads, per-document locale
filtering, current-generation evidence on cache replay, numeric occurrence checks,
substring guardrails, full-catalog global aliases, source-link widget restriction,
and test-only experiment controls. Parent identity collision addressed separately.

Also implemented: source validity checks on evidence/cache replay, preserving
nested lifecycle metadata, production experiment controls, and explicit opt-in
before flattening an administrator's heterogeneous market permissions.

Follow-up implementation: mixed local/global candidates now reapprove global
evidence alone when a foreign market is requested. Local-policy evidence is not
used to answer for that market. Scoped confidence cannot increase or borrow a
strong-local-match override. Dependent follow-ups inherit a market only when no
new explicit market is named. The cached global phone response now has a test
through real PII allowlisting, cleanup and output validators (external Comprehend
and generation-registry reads are mocked).

Localized country names are generated from Node's Unicode CLDR data for 155
two-letter catalog regions across 38 configured languages. This recognizes names,
not policy eligibility. Custom business regions retain configured names. Matching
remains whole-name based; inflection, attached suffixes and every possible typo
are not universally solved. Tests cover several scripts and overlapping names.

Still to verify/finish: general compound-intent decomposition, semantic claim
completeness, translated numeric grounding, broader inherited-market scenarios,
and browser testing of permission editing. Mixed requests can still lose their
local-policy half because evidence narrowing is conservative; this is not a
complete compound-intent solution.

## Stage B - partial implementation

Implemented: normalized OCR/extracted pages feed specialized directory and policy
parsers; directories no longer intentionally fall through to generic chunks;
unrecognized policy bodies fail closed; single-page non-PDF policy notices have a
minimum-count exception; expiry metadata flows into newly indexed sections.
Live Flow no longer substitutes demo traces for an empty successful response.
Overview loads authorized panels independently and suppresses unavailable/demo
panels in production. Request versioning prevents old Overview responses winning.

Remaining: verified real-PDF extraction coverage, per-page OCR and table-layout
preservation, existing-index lifecycle backfill, Insights loading/races, and
browser verification. No index or source lifecycle migration has been executed.

## Stage C - partial implementation

Implemented: shorter source-grounded prompt, explicit local/global and compound
request rules, mandatory qualifications, warmer concise style, and history/source
content moved out of system instructions into JSON context in the user message.
Default prompt version is 2026-09-05-context-boundaries-v2; deployment overrides
still need inspection. Embedded newlines cannot create synthetic history role
lines. Widget expected-answer feedback now uses the expected_answer API field.

Insufficient-evidence fallback turns are now persisted for subsequent follow-ups.
Remaining: typed follow-up state, audit of other terminal-turn paths, latency budgets,
bounded fan-out, and complete durable cross-worker tracing. Prompt construction
tests do not prove model compliance or semantic quality. No measured latency
improvement is claimed.

## Stage D - pending

Isolated authority ranking, parent-child retrieval, confidence calibration and
Current/Candidate promotion evaluation. Experiments must remain off by default.

Only the cross-document parent-identity collision is fixed. Actual parent-child
expansion, authority-aware ranking, and calibrated confidence are not implemented
by that correction. Do not promote these experiments before a frozen baseline.

## Verification checkpoint - 2026-09-05 (follow-up)

- Final full local unit suite: 810 passed, two dependency deprecation warnings.
- Final Python lint and git diff --check: passed.
- Runtime used: isolated Python 3.11.15 with requirements.txt dependencies.
- Admin portal TypeScript check: passed.
- Widget TypeScript check: passed.
- Python lint: passed with pinned flake8 7.1.1. Upload authorization was simplified
  without weakening its required permission; ingestion indentation was corrected.
- Python compilation and repository security-regression check: passed.
- Admin and widget production builds and build validators: passed (local Node 24.15.0;
  CI uses Node 22, so the complete Linux CI environment is not reproduced).
- Retrieval canary --validate-only: 15-case fixture schema valid, NOT live answers.
- Live model tests, load tests, deployed parity and full dependency vulnerability
  audits: not run. CloudFormation infrastructure was not changed or revalidated.
- Graphify update unavailable: executable not installed and no local graph present.
- Changes remain local and uncommitted. No push, deployment, cloud mutation,
  production flag change, or threshold reduction was performed.

The new tests prove specific corrected behavior, including per-document market
filtering, cache revocation/lifecycle checks, global contact evidence round-trip,
repeated-number subject binding, strict safety-policy question handling, source
metadata preservation, prompt data separation, history role boundaries, directory
country/page retention, and rejection of unrecognized policy bodies.

## Evaluation inputs needed before promotion

Identify the approved non-production Current and Candidate evaluation targets,
their frozen index/source/model/configuration manifests, and a permitted live-run
budget. Supply or confirm verified source-grounded expected outcomes and current
Legal-approved wording. Preserve exact questions and both full answers for each
repeat; report retrieval, final correctness, safety, Legal and latency separately.
This requirement does not mean the remaining local implementation is complete.

## Release status

### Mixed-intent follow-up - bounded local implementation

- Two explicit independent English clauses (one question and one writing command)
  can now be separated, with both evaluated by the existing governance engine.
  Splitting proceeds only when the question is allowed and the command has an
  explicit medical/income/off-topic refusal. Provider errors, both-allowed and
  both-denied cases retain the original whole-message path.
- Only the unchanged supported question enters the existing retrieval, evidence,
  country-scope, generation and output-safety pipeline. The declined command is
  answered with existing controlled refusal copy, not a newly generated claim.
- Cache keys and values remain those of the safe question. The combined response
  is assembled afterward without mutating the cached object. A real cache replay
  test proves a subsequent safe-only question receives no leftover refusal.
- Turn persistence is centralized at handle_chat: original scrubbed request plus
  actual delivered reply are saved once, including cache hits and terminal refusals.
  Private routing/cache helpers no longer save partial turns. Tests use isolated
  memory history rather than falling through to the database.
- Deliberate scope limit: ambiguous/implicit, quoted, dependent, multilingual and
  more-than-two-clause decomposition is not implemented. This is not a general
  compound-intent solution or a claim of multilingual safety coverage.
- Verification: 841 local unit tests passed; source lint and git diff --check
  passed. Three warnings remain (two dependency deprecations and pytest cache
  permission). Graphify refresh is unavailable because its executable is absent.
- Live comparison remains NOT RUN. No listener was reported on the checked local
  ports 8000, 8001, 8080 or 5174. Available evaluation scripts are retrieval-only;
  they cannot establish final-answer improvement. No AWS connector was available.
  An isolated Candidate runtime with verified cloud configuration and the same
  source/index versions is still needed before a matched live comparison.
- No deployment, production configuration change, cache clear, commit or push.

### Production-baseline follow-up - local fixes

- Reproduced phone loss in the numeric validator using constructed full answers
  grounded in the source excerpts observed in production. The original raw model
  responses and production traces remain unavailable, so this establishes a local
  failure mechanism, not definitive deployed root-cause attribution.
- Numeric checking now treats complete phone/vanity-phone values atomically and
  preserves source-matched labeled contacts despite answer wording changes. Both
  sentence repair and validation use the same contact grounding path. No confidence
  threshold or PII setting changed. Existing public-evidence PII checks remain active.
- Added English, French and US vanity-phone tests through real local PII cleanup
  and output validation, plus altered digit, fragmented-source and wrong numeric
  subject checks. All three previously failing numeric positive tests now pass.
- Strict policy-safety questions now enter policy retrieval through the shared
  planner instead of being eligible for a model-classified claim refusal. This
  reuses the existing full-message English matcher, not a broad keyword exemption.
  Appended unsafe instructions do not receive that exception. A generated answer
  still requires approved source evidence and output safety checks.
- Final full local suite: 822 passed, three warnings (two dependency deprecations
  and pytest cache-write permission). Python source lint and git diff --check passed.
  Graphify refresh attempted but the command is unavailable.
- Still pending: general mixed-intent decomposition, fresh-session repetitions,
  UK active-source verification, full raw answer/trace attribution and matched live
  Current/Candidate comparison. Policy factual answer delivery is not yet verified
  against the live model. Phone matching is not proof of role/market correctness.
- No production changes, deploy, shared-cache clear, push or commit performed.

Not release-ready. Local unit tests alone do not establish production quality.
Live index/model/corpus tests, full CI environment verification, Legal wording
approval and production parity are separate gates. Existing audit probes assert
the old defects; new correctness tests are under tests/unit/test_audit_stage_a.py.
