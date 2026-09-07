# AskVera — Session Resume Document

**Purpose:** Everything needed to pick this project back up in a fresh Claude Code session (e.g. on another account), with no prior conversation memory. Written 2026-09-05.

---

## 1. What this project is

**AskVera** is an enterprise RAG (retrieval-augmented generation) chatbot for **Forever Living Products (FLP)**, serving distributors ("FBOs" — Forever Business Owners) and customers with answers grounded in two document sets:
- The **company policy** documents (US-EN-Company-Policy.pdf and per-market equivalents)
- The **International Sponsoring Directory** (global office contact/sponsoring records, ~112 countries)

Phase 1 scope is deliberately narrow: **only** these two document types are indexed. No product-catalog, no wellness-article content, no general knowledge — this is a legal/compliance-conscious design choice, not a gap to casually fill.

### Repository
- **Local path:** `C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy`
- **GitHub:** `https://github.com/Aspire-coder/askvera` (git user: `Aspire-coder`)
- **Main branch:** `main`
- **Workflow convention established this session:** feature/fix branch → push → open PR via the URL git prints on push (no `gh` CLI installed on this machine) → user merges via GitHub web UI → deploy.

### Live infrastructure
- **Backend API:** `https://api.vera-api.xyz` — FastAPI app, runs as systemd service `askvera` on an EC2 box at `/opt/askvera`, app user `askvera`.
- **Admin/Operations portal:** `https://operations.vera-api.xyz` — React/Vite app, deployed to S3 + CloudFront via CloudFormation stack `askvera-operations` (AWS account `615592621509`, region `us-east-1`).
- **Widget:** embeddable chat widget (`widget-wrapper/`), deployed to its own CDN.
- **This is described throughout the session as "the test environment"** — not yet carrying real production distributor/customer traffic. That fact was explicitly used to justify a live (not just admin-preview) experimental-behavior toggle (see §5).
- **Database:** Postgres (RDS), accessed via `services/db.py`'s `get_engine()`, credentials pulled from AWS Secrets Manager using the EC2 instance role.
- **Cache:** Redis/Valkey via ElastiCache (`services/cache.py`).
- **Retrieval:** OpenSearch Serverless, index `askvera-policy-sections`, pipeline version referenced in canary output as `2026-08-23-selector-calibration-v4`.
- **Model:** AWS Bedrock, Claude models (Haiku for fast path, Sonnet available but only used in "shadow" routing mode — see §7).
- **Config:** SSM Parameter Store, default path `/askverachat/prod/` (`config/settings.py`'s `SSM_PARAMETER_PATH`, overridable via env var).

### Critical access constraints (learned the hard way this session)
- **I (Claude Code) have NO direct SSM send-command / EC2 execution access** — every attempt is blocked by "the Claude Code auto mode classifier." All backend-side work (migrations, restarts, `deploy.sh`, reading production logs, setting SSM parameters) must be handed to the user as a **read-only script** in a `sudo tee /opt/askvera/scratch_*.py > /dev/null << 'PYEOF' ... PYEOF` block, which the user pastes into their own already-open EC2 `sh-5.2$` shell.
- **I DO have direct AWS CLI credentials on my own machine** (`aws sts get-caller-identity` → `arn:aws:iam::615592621509:user/pavan410`), confirmed usable for:
  - Read-only queries (S3, CloudWatch, CloudFormation describe, SSM `get-parameter`) — always safe to just run.
  - **Write access to the admin-portal's S3 bucket + CloudFront + CloudFormation stack** — I successfully ran `admin-portal/scripts/deploy-portal.ps1` myself this session (user explicitly approved this once; treat as approved-per-instance, re-confirm before doing it again in a new session unless told otherwise).
  - **`npm run deploy-widget`** in `widget-wrapper/` — established earlier in the (pre-compaction) session as something I can run directly.
  - **`ssm:PutParameter` is explicitly blocked** for me by the classifier (confirmed by direct attempt — got the generic "blocked by classifier" refusal, not an AWS permission error). The user must set SSM parameters themselves, and their own EC2 shell's `aws` CLI is *also* insufficient (it runs as the `ChatbotAppRole` instance role, which only has `ssm:GetParameter*`, not `PutParameter` — confirmed via a live `AccessDeniedException`). SSM parameter writes must be done via the **AWS Console** (`https://console.aws.amazon.com/systems-manager/parameters?region=us-east-1`) or a CLI configured with the user's own personal IAM credentials — never from the EC2 box.
- **The backend deploy is user-run only:** `cd /opt/askvera && sudo ./deployment/deploy.sh` — pulls latest `main`, installs deps, runs the full unit suite + a **blocking retrieval-quality canary**, restarts the `askvera` service, health-checks, and **auto-rolls-back to the previous commit if the canary fails**.
  - **Known flaky-canary issue:** Bedrock `ServiceUnavailableException` (transient capacity throttling) intermittently fails several canary cases with no real regression. Fixed partially in PR #54 (`54af583`, gave the canary its own retry budget distinct from production's zero-retry client), but it can still recur. **The fix when it happens: just retry `deploy.sh`.** Confirmed working again as recently as this session's own candidate-mode-fix deploy (failed once on throttling, passed 15/15 on immediate retry).

---

## 2. Architecture map (key files)

### Request flow (`app/orchestrator/chat_orchestrator.py` — `AIOrchestrator.handle_chat`)
1. Session/consent validation (`services/session_service.py`, `services/consent_service.py`)
2. PII scrub (`services/pii.py`)
3. **Early conversation response** (`_early_conversation_response`) — exact-phrase/typo-tolerant greeting/thanks/capability routing via `app/evidence.py`'s `classify_intent`; also catches probable country-name typos (`services/market_config.py`'s `find_probable_market_typo`) before they hit a generic refusal.
4. Conversation history fetch (`services/session.py`'s `get_session_history`)
5. **Input governance** (`app/governance/`) — Bedrock Guardrails + deterministic risk policies (`app/risk/policies/*.py`, phrase lists in `config/guardrail_topics.py`'s `DENIED_TOPICS`). `IncomeClaimPolicy` = REFUSE (hard block); `MedicalClaimPolicy` = **WARN only** (logs but never blocks) — **this asymmetry is a known, still-unfixed gap**, see §6.
6. Exact-cache check (`services/cache.py`)
7. Retrieval (`app/retrieval/` — `RetrievalService` → `OpenSearchSectionProvider`, hybrid lexical+vector search, an LLM query planner, an optional LLM evidence selector)
8. **Evidence routing / approval gate** (`_route_or_approve_evidence` → `_conversation_route_response` for semantic routes (assistant_meta/medical_claim/income_claim/off_topic) and `app/evidence.py`'s `approve_evidence` for the document-grounded evidence gate)
9. Semantic-cache check (`services/semantic_cache.py`)
10. Prompt build (`app/prompts/`) → model generation (`app/models/router.py` → `bedrock_provider.py`)
11. Evidence-contract check (`app/evidence_contract.py`) → response build/validate (`app/response/`, `app/validation/`)
12. Output governance (same engine, re-run on the generated answer)

### Conversation routing philosophy (deliberate, documented)
`app/evidence.py`'s `classify_intent()` is **exact-phrase-match only** by design ("fail closed... Business vocabulary does not belong in this router" — direct quote from the docstring), with a narrow, bounded typo-tolerance helper (`_safe_short_phrase_variant`, originally capped at ≤3 words/32 chars, categories `{greeting, thanks, farewell}` only). The query planner has its **own** semantic classification (`conversation_intent`/`conversation_subtype`/`intent_confidence`) but it is explicitly **vetoed** for `assistant_meta` unless the exact-phrase list also agrees — *except* for "thanks", which is trusted on its own once it clears every guard in `is_planner_trusted_low_risk_subtype` (added this session, PR #52/`a691504`). This veto exists specifically so a broad semantic classifier can never impersonate the trusted assistant-identity route.

### Claim/guardrail wording
- `services/claim_safety.py`'s `classify_claim_scope()`/`localized_claim_response()` only returns a canned answer for the narrow `product_disease_claim` subtype (needs BOTH a product term AND a disease-claim term, per-locale lists in `config/claim_safety.json`). The broader `medical_claim` intent falls through to a *different* string in `config/conversation_routes.json`. **This wording fork was flagged by Legal's review as inconsistent and was never actually fixed this session** — see §6, this is real pending work.
- `app/risk/policies/income_claim_policy.py` = the proven-working pattern (REFUSE action, phrase list + a regex guarantee+earnings combo check). `medical_claim_policy.py` should mirror it but currently doesn't (WARN only).

### Model routing
`app/models/model_routing.py`'s `decide_model_route()` computes fast(Haiku)/complex(Sonnet) routing but only ever runs in **shadow mode** — the override never actually applies (gated in `app/models/router.py`). Real production log data pulled this session showed **60/76 (79%) of a 24-hour traffic sample classified "complex"** — flipping to live routing would be a major cost/latency shift, not a minor tweak, and the "complex" trigger is very broad (any digit/currency symbol in the question qualifies). **This was discussed but deliberately left alone — decision pending, not resolved.**

---

## 3. This session's complete work log (chronological)

Earlier portions of this session (before a mid-session compaction) covered, and merged to `main`:
- **PR #49** (`3ea3460`) — retrieval audit batch 3: removed dead vNext code, marked legacy Bedrock KB provider, widened English glossary.
- **PR #50** (`e336bb0`) — reject near-empty document extractions; fully retire superseded document rows on republish.
- **PR #51** (`527f6d9`) — fixed basic conversational routing (added natural "thanks"/"how can you help" phrase variants across all 12 locales) and widened market-mention recognition (`config/global_directory_markets.json`, new file — 27 supplementary markets including Japan, China, India, and 7 alias corrections like Tanzania→TZ).
- **PR #52** (`4d56f49`) — the **planner-trust mechanism**: `is_planner_trusted_low_risk_subtype()` in `app/evidence.py`, letting the query planner's own "thanks" classification be trusted without an exact phrase match (narrowly scoped, see §2).
- **PR #53** (`f9c303f`) — fixed a `[AGE]`-style bracket-placeholder generation bug (root cause: Haiku used despite router recommending Sonnet, since routing is shadow-only), a UK widget header CSS truncation bug (`text-overflow:ellipsis` doesn't work on `display:inline-flex`, needed `inline-block`), and a mislabeled office-hours answer (root cause: `directly_answers_top_rank:false` was computed by the evidence selector but discarded before reaching generation — now surfaced as a prompt-level warning note).
- **PR #54** (`789ad8b`) — gave the deploy canary its own AWS retry budget, separate from production's deliberately zero-retry "fail fast" client, fixing repeated false-failure rollbacks from transient Bedrock throttling.

Also covered pre-compaction, **not yet resolved**:
- A **Legal review document** ("AI Chatbot Q&A's") was analyzed in depth. Most flagged issues were retested live and found either already fixed (by earlier work) or non-reproducible/flaky (Bedrock-load-dependent). **One clear, confirmed, unfixed gap: medical-claim response wording is inconsistent** (see §2 and §6) — the user agreed to consolidate it, asked me to propose wording via `AskUserQuestion`, and **selected "I'll provide the exact wording Legal wants" — but never actually sent it.** The conversation moved on to a Taia competitive comparison instead. **This is the single most concrete piece of unfinished business from before this document.**
- Live production **model-routing data pull** (confirmed 79% "complex" classification) — decision on going live deliberately deferred, not resolved.

### Taia (Thorne's chatbot) competitive comparison
Used the in-app Browser tool to run Taia through 9 test questions (greeting, product Q&A, medical-claim decline, prompt-injection, competitor comparison, typo tolerance, unsafe-dosage, off-topic, medical-emergency). Findings that shaped the next feature:
1. Taia never hard-refuses — on a retrieval/knowledge miss it asks a **narrowing clarifying question** instead of a flat "I don't have that."
2. Guardrail declines are phrased **in the model's own words**, one natural paragraph, not a canned template.
3. Typo tolerance is much looser (not scoped to a short reviewed-phrase list).
4. UI affordances: quick-reply chips, inline product cards, thumbs up/down.

Follow-up discussion concluded: AskVera's narrower behavior is **partly deliberate** (Phase 1 scope is genuinely smaller than Taia's full catalog+articles corpus) but partly a **fixable behavior gap** independent of content breadth — leading directly to the candidate-mode feature below.

### The candidate-mode admin toggle feature (this session's main deliverable)
**Goal:** let an admin flip a live switch on the **test-environment** widget (not just an internal preview — the user explicitly accepted this risk since it's test-only) to compare "current AskVera" vs. three Taia-inspired "candidate" behaviors, with the ability to strip it out cleanly if it's not good.

**Architecture** (mirrors a purpose-built-but-dormant existing pattern, `retrieval_runtime_control`/`docs/RETRIEVAL_PROFILE_CONTROL.md`, built for an earlier removed feature):
- New table `chat_candidate_control` (singleton row, `control_id='primary'`), migration `migrations/20260903_01_chat_candidate_control.sql`.
- New service `services/candidate_control.py`: `CandidateFlags` (3 booleans), `get_candidate_flags()`/`set_candidate_flags()`.
- **Master switch:** `settings.CANDIDATE_MODE_LOOKUP_ENABLED` (off by default) — until explicitly turned on in an environment's SSM config, `get_candidate_flags()` never touches the database at all. This was specifically added so the **existing large unit-test suite never had to be touched** to accommodate the new DB-backed read (candidate flags are threaded as an explicit parameter from `handle_chat` down to every hook point — never read ad hoc inside a lower-level function — keeping `app/evidence.py` a pure, I/O-free module).
- New admin endpoints `GET`/`PUT /api/admin/experiments/candidate-mode` (`api/admin_routes.py`) — Super-Admin-only, exact confirmation phrase `UPDATE CANDIDATE MODE` required, audit-logged. Modeled directly on the existing `operational_cache_reset` endpoint's safety pattern.
- New admin-portal panel `admin-portal/src/components/CandidateModeControl.tsx`, rendered inside the existing "Live flow" view.

**The three behaviors:**
1. **Narrowing fallback** — on a retrieval miss (`LowConfidenceError`/evidence-gate-rejected), makes one small constrained Bedrock call (`_candidate_narrowing_response` in `chat_orchestrator.py`) asking a clarifying question instead of the flat refusal. Generalizes the existing `_directory_clarification_response` pattern.
2. **In-voice guardrail phrasing** — phrases medical/income/off-topic declines in the model's own words via `_candidate_guardrail_phrasing`. **The decision to decline stays fully deterministic (governance/risk-policy layer unchanged) — only the phrasing is generated.** Explicitly marked in code and UI copy as an **unreviewed placeholder pending Legal sign-off** — must never reach anywhere real users could see it.
3. **Wider typo tolerance** — extends `_safe_short_phrase_variant` to also cover the `capability` category with a wider word/char cap (6 words/60 chars vs. 3/32), same edit-distance-1 strictness.

**Deploy sequence actually executed** (PRs #55 `3caa0ea` feature + #56 `7d29dad` bugfix, both merged and **live on the test environment as of this writing**):
1. Migration applied via a hand-run script (`chat_candidate_control` table created).
2. SSM `CANDIDATE_MODE_LOOKUP_ENABLED=true` set at `/askverachat/prod/CANDIDATE_MODE_LOOKUP_ENABLED` (had to be done via AWS Console, not the EC2 shell — see §1 access constraints).
3. Backend `deploy.sh` run (failed once on canary throttling flake, passed on retry).
4. Admin portal deployed by me directly via `admin-portal/scripts/deploy-portal.ps1`.

**Live testing found two real bugs, both fixed and deployed** (PR #56, commit `8a054b8`):
- **Narrowing-fallback loop:** the clarifying-question call only ever saw the current turn's raw message, no conversation memory — a product-price thread looped "which product?" → "which detail?" → "which product?" forever. **Fixed** by threading `history` (the same session-history string used elsewhere) into the prompt, with an explicit instruction to admit "I don't have that detail" once it recognizes it already asked.
- **Pre-existing "email address" directory-clarification bug** (unrelated to candidate-mode, surfaced by testing it): `DIRECTORY_FIELD_TERMS["directory-address"]`'s regex matched the word "address" inside "email address," so that phrase always matched two fields and was never treated as already-specified — an unresolvable loop confirmed live (clicking the "Email address" quick-reply card re-triggered the same ambiguous clarification indefinitely). **Fixed** with a negative lookbehind: `r"(?<!email\s)\baddress\b"`.

**Live-testing verdict after both fixes deployed:** All three candidate behaviors confirmed working via a live diagnostic script run through the full `handle_chat` path (bypassing session/consent checks with monkeypatches, since synthetic session IDs were never created through the real init flow). In-voice guardrail phrasing works consistently and cleanly. Wider typo tolerance works for genuinely short (≤6-word) typo'd phrases. Narrowing fallback works for single-turn cases; **the multi-turn fix (history-awareness) was deployed but not yet independently re-verified live after the fix** — that's an open action item (see §8).

---

## 4. The external "Codex" audit (2026-09-05)

A separate AI tool ("Codex," per the user) ran an independent end-to-end code audit against commit `7d29dad` (the exact commit this session had just deployed). Report: **`docs/audits/2026-09-05/ASKVERA_END_TO_END_RAG_AUDIT.md`** (not committed to git — local file only). Reproduction probes: `docs/audits/2026-09-05/test_review_probes.py`.

**My assessment of it (given verbatim to the user, worth preserving):** unusually well-calibrated for an AI-generated audit — it labels every claim's evidence strength (Reproduced / Code-confirmed / Risk-gap), is explicit about what it didn't verify (no live AWS, no production commit check, only 2 Taia turns before hitting a consent wall), and refuses to let "774 tests + 13 probes passed" be read as a release badge. Its core recommendation — fix correctness before touching ranking/confidence thresholds — is sound. It is a single-pass code review with mocked/isolated probes, **not** a confirmed production incident report.

### Top findings (24 total, F01–F24; full detail in the report)
Highest priority (P1), in the report's own order:
- **F01** — a `knowledge/stage`-only permission can reach the *publish* endpoint (missing global-content restriction on publish, mirrored from upload).
- **F02** — the numeric-grounding validator dedupes by numeric text, not by subject/claim — a repeated number can mask a false second claim.
- **F03** — exact cache hits bypass retrieval with no check that the cached answer's source document generation is still current.
- **F04** — cached foreign-office-phone answers can have their number silently overwritten with the *session* country's number during PII-placeholder repair. (Flagged by me as the single scariest one — confidently wrong contact info, not a visible failure.)
- **F05** — local guardrail phrase matching has no word boundaries: "How do I **secure**ly register?" trips the "**cure**" substring. Also over-blocks legitimate policy-explanation questions about prohibited claims.
- **F06** — cross-market evidence isolation isn't a complete per-evidence invariant (only checks the raw current message; evidence-set approval is all-or-nothing).
- **F07** — global-country aliases (the `config/global_directory_markets.json` work from PR #51) are recognized by the market resolver but a *separate* "directory-target helper" resolves against only the base config — Japan can be recognized as mentioned but still produce no target filter; Tanzania resolves to a long canonical name that can miss the actual record. **I flagged this as directly worth re-verifying against my own PR #51 work before either accepting or dismissing it — not yet done.**
- **F08/F09** — a parser can "succeed" (pass the chunk-count gate) while only extracting front matter/outline and losing the actual policy body; OCR bypasses the specialized policy/directory extractors entirely.
- **F10** — the evidence contract checks structure (non-empty claims, valid IDs) not truth — a completely wrong claim can pass if it cites real evidence IDs.
- **F11** — translated numeric facts can be wrongly rejected (the validator requires English word overlap).
- **F13** — document effective/expiry dates aren't an enforced retrieval eligibility filter.
- **F16** — the admin portal's Live Flow view substitutes demo trace data for a genuinely empty live response and labels it "live" — an operator can't tell demo from real.
- **F20** — **directly about this session's own candidate-mode feature**: the "test environment only" / "unreviewed wording" protection is convention (docstrings, UI copy) and a master switch, not a hard server-side environment check. *(Note: as of the file-change notices received mid-conversation, this looks like it may already be partially addressed — `services/candidate_control.py` on disk now checks `settings.APP_ENV` against an allowed-environment set before permitting either read or write. This was NOT done by me in this conversation — see §5, uncommitted working-tree state.)*

Full remaining list (F12, F14, F15, F17–F19, F21–F24) covers: parent-diversification key collisions, source-download locale-check bypass, fragile conversation-state reconstruction, admin-portal loading/permission coupling, per-market permission flattening on user edit, expected-answer feedback field mismatch, no shared request-deadline budget, incomplete latency/cost metrics, untrusted history/evidence placed in the system prompt without guardrail content-marking, and the CI canary running in `--validate-only` mode (fixture validation, not a live quality gate).

### Recommended fix sequence (from the report, endorsed)
- **Stage A:** F01–F07, F10–F11, F14, F18, F20 — correctness/safety, narrow reviewed changes, thresholds unchanged.
- **Stage B:** F08–F09, F13 — extraction coverage/OCR/validity, needs real production-source fixtures.
- **Stage C:** F15, F17, F19, F21–F22 — conversation state, feedback, latency, tracing.
- **Stage D:** ranking/parent-child/confidence-calibration experiments, evaluated independently, off by default.

---

## 5. ⚠️ Current uncommitted working-tree state (as of this document)

**This is the most important section to check first when resuming.** Partway through this session (after the audit was reviewed), files started changing on disk that I did not make — almost certainly **Stage A remediation work being done in parallel**, possibly by the same "Codex" tool operating directly on this checkout. This document is being written specifically to capture the current state accurately rather than just what I built.

Confirmed via `git status --porcelain` and `git diff --stat` against the last commit (`7d29dad`):

**Modified, uncommitted:**
```
api/admin_routes.py
api/routes.py
app/evidence.py
app/orchestrator/chat_orchestrator.py
app/retrieval/experiments.py
app/retrieval/opensearch_sections.py
app/risk/policies/income_claim_policy.py
app/validation/validators/numeric_grounding_validator.py
services/candidate_control.py
services/guardrails.py
services/knowledge_generations.py
tests/unit/test_chat_orchestrator.py
tests/unit/test_opensearch_sections.py
tests/unit/test_retrieval_experiments.py
tests/unit/test_source_links.py
```

**New, untracked:**
```
app/retrieval/cache_evidence.py       (new module — restore_evidence/serialize_evidence)
docs/audits/                          (the audit report + probes + status ledger)
tests/unit/test_audit_stage_a.py      (new regression tests, 81 lines)
.claude/                              (pre-existing, unrelated to any of this)
scratch/                              (pre-existing, unrelated)
docs/CLAUDE_CODE_FULL_PROJECT_CONTEXT_2026-09-01.md   (pre-existing, unrelated)
```

**A tracking ledger already exists at `docs/audits/2026-09-05/IMPLEMENTATION_STATUS.md`**, stating (verbatim):
> Baseline: 7d29dad. No deployment or runtime flag changes authorized by this work.
> **Stage A - in progress**: Implemented with local unit-suite verification: publication permission checks, global publication restriction, review-by-default uploads, per-document locale filtering, current-generation evidence on cache replay, numeric occurrence checks, substring guardrails, full-catalog global aliases, source-link widget restriction, and test-only experiment controls. Parent identity collision addressed separately.
> Still to verify/finish: end-to-end compound intent and inherited markets, semantic claim completeness, translated numeric grounding, cache contact round-trip, heterogeneous admin scope editing, and source validity windows.
> **Stage B/C/D**: pending, as described in §4 above.
> **Release status**: Not release-ready. Local unit tests alone do not establish production quality.

**Verified this session:** `py -3 -m pytest tests/unit/ -q` passes clean against this exact uncommitted working tree (all green, no failures) — so whatever's in progress is at least internally consistent and tested, just **not committed, not reviewed by me, and not deployed**.

**Specifically confirmed by direct inspection:** `services/candidate_control.py` now guards *both* `get_candidate_flags()` and `set_candidate_flags()` behind `settings.APP_ENV in {"development", "test", "testing", "staging", "uat"}` — `set_candidate_flags` now raises `ValueError` outside that set. This looks like exactly the F20 fix. **I have not reviewed the rest of this diff in detail, have not verified it against the live test environment, and have not deployed it.** A new `APP_ENV` setting is implied but its default value / where it's set (SSM? env var? does the live test box currently have it set to something in the allowed list, or would this uncommitted change silently break the candidate-mode admin panel if deployed as-is?) has **not been checked**.

### What a resuming session must do first
1. `git status` / `git diff` to see the *actual current* state (this file is a snapshot, already possibly stale).
2. Read `docs/audits/2026-09-05/IMPLEMENTATION_STATUS.md` for the latest word on what's done.
3. Decide with the user whether to review/commit/deploy this in-progress Stage A work, or whether it needs more scrutiny first — **do not assume it's safe to deploy without an independent review**, since it touches governance/guardrail/cache logic across many files at once.
4. Specifically verify: does `settings.APP_ENV` exist and have a sensible value in the live test environment's SSM config? If this uncommitted diff were deployed today, would the candidate-mode admin panel (built this session, currently live and working) still function, or would it now refuse because `APP_ENV` isn't set/isn't in the allowed list?

---

## 6. Known, confirmed, still-unfixed gaps (independent of the Codex audit)

1. **Medical-claim response wording is inconsistent** (Legal's own finding, confirmed by direct testing this session). Two-part fix agreed but never implemented:
   - Remove the scope fork in `services/claim_safety.py`'s `localized_claim_response()` (the `if scope != "product_disease_claim": return None, scope` early-return) so every `medical_claim` case gets one unified answer.
   - Upgrade `app/risk/policies/medical_claim_policy.py`'s `action` from `WARN` to `REFUSE`, and expand `config/guardrail_topics.py`'s `DENIED_TOPICS["medical_claim"]` list with ailment/symptom terms it currently lacks (sunburn, headache, rash, acne, pain, etc.), mirroring the already-working `income_claim_policy.py` pattern.
   - **Blocker:** the user was going to supply Legal's exact approved wording and never did. **This is the clearest, most concrete next task if the user wants to resume where the pre-Taia thread left off.**
2. **Model routing** stays shadow-only by deliberate non-decision (cost/latency impact quantified at 79% "complex" classification on live traffic; not resolved either way).
3. Everything in the Codex audit not yet addressed by the in-progress Stage A work (§4/§5).
4. Narrowing-fallback's history-awareness fix (§3) was deployed but not yet independently re-verified live post-deploy.

---

## 7. Established working conventions this session (important for consistency)

- **Git:** feature/fix branches off `main`, named `fix/...` or `feat/...`; push; hand the printed "Create a pull request" URL to the user; user merges via GitHub web UI (no `gh` CLI on this machine).
- **Commit/PR attribution** (current instruction, supersedes any earlier guidance in this doc's history):
  - Commits end with: `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`
  - PR descriptions end with: `🤖 Generated with [Claude Code](https://claude.com/claude-code)`
- **Backend deploy is always user-run** (`sudo ./deployment/deploy.sh` from `/opt/askvera`), because of the SSM/EC2-execution block on me.
- **All production/EC2 diagnostics are read-only Python scripts**, handed to the user as a `sudo tee /opt/askvera/scratch_<name>.py > /dev/null << 'PYEOF' ... PYEOF` block, run via `sudo -u askvera .venv/bin/python scratch_<name>.py`, then deleted (`sudo rm -f`). Always add `os.environ.setdefault(...)` or `settings.load_ssm_config()` calls at the top matching the pattern in existing scripts.
- **When testing `handle_chat()` directly in a diagnostic script**, session/consent validation will reject a synthetic session ID unless you monkeypatch `validate_and_touch_session`, `has_valid_consent`, `get_session_history`, and `append_session_turn` on the `chat_orchestrator` module — a real session ID only exists if created through the actual widget init/consent flow.
- **Widget deploy:** bump `widget-wrapper/package.json`'s version first (immutable S3 version path), then `npm run deploy-widget` — I can run this myself.
- **Admin-portal deploy:** `admin-portal/scripts/deploy-portal.ps1 -CognitoDomainPrefix "askvera-operations-615592621509"` (all other params already default to the live stack's current values) — I can run this myself, confirmed by explicit user approval this session; treat future runs as needing a fresh confirmation unless told otherwise.
- **Never treat "unit tests pass" or "N diagnostic probes reproduced" as a release/quality badge** — this was explicitly called out by both the Legal review methodology and the Codex audit, and matches this session's own established discipline (never claim a fix without a traceable code change; distinguish "doesn't reproduce" from "confirmed fixed"; Bedrock capacity flakiness vs. genuine LLM-classification non-determinism vs. real regressions were repeatedly and carefully distinguished throughout).
- **User's typing style:** frequent typos, very informal — read intent generously, don't get hung up on literal wording.
- **User pattern:** says "lets deploy" / "merged" / "done" as terse go-ahead signals for the next step in an established sequence — treat these as sufficient authorization to proceed with the *next conventional step*, not as blanket pre-authorization for anything else.

---

## 8. Suggested next steps (priority order)

1. **Re-establish ground truth on the uncommitted Stage A work** (§5) — read the actual current diff, decide with the user whether to review/finish/commit it or set it aside, and specifically resolve the `APP_ENV` question before anything touching `services/candidate_control.py` goes near a deploy.
2. **Independently verify F04 (cache+PII-restore wrong-country phone) and F05 (guardrail substring matching)** — these were flagged as the two most concerning, concrete, and cheaply-verifiable findings; worth confirming for real before trusting the audit's characterization.
3. **Verify F06/F07 (market alias resolution)** specifically against this session's own PR #51 work (`config/global_directory_markets.json`) — there may be a second, unwired code path.
4. **Get Legal's exact medical-claim wording from the user** and implement the two-part fix described in §6 — this has been sitting half-done since before the Taia detour and is probably the single cleanest, most self-contained piece of remaining work.
5. **Re-verify the narrowing-fallback history-awareness fix live**, post the PR #56 deploy, to confirm the Aloe-Vera-Gel-style loop is actually resolved in practice (not just in the unit-test prompt-construction check).
6. Decide on model-routing (shadow → live) — needs real cost-delta modeling and/or tightening the "complex" trigger first.
7. Work through the Codex audit's remaining Stage A/B/C items in the sequence it recommends, always independently verifying before deploying (per this session's established discipline).

---

## 9. Quick reference

| Thing | Value |
|---|---|
| Repo | `github.com/Aspire-coder/askvera` |
| Local path | `C:\Users\KRISH\Downloads\Chatbot\Archives\enterprise-chatbot\askvera-deploy` |
| Backend API | `https://api.vera-api.xyz` |
| Admin portal | `https://operations.vera-api.xyz` |
| AWS account | `615592621509`, region `us-east-1` |
| Admin-portal CFN stack | `askvera-operations` |
| SSM config path | `/askverachat/prod/` |
| EC2 app dir | `/opt/askvera`, service `askvera`, app user `askvera` |
| Backend deploy | `sudo ./deployment/deploy.sh` (user-run only) |
| Admin-portal deploy | `admin-portal/scripts/deploy-portal.ps1 -CognitoDomainPrefix "askvera-operations-615592621509"` |
| Widget deploy | `npm run deploy-widget` in `widget-wrapper/` (bump version first) |
| OpenSearch index | `askvera-policy-sections` |
| Last deployed commit (confirmed live, canary-passed) | `7d29dad09540527a9302b95436f36e93f7fa5a2a` |
| Latest audit | `docs/audits/2026-09-05/ASKVERA_END_TO_END_RAG_AUDIT.md` |
| Audit remediation ledger | `docs/audits/2026-09-05/IMPLEMENTATION_STATUS.md` |

---

*End of resume document. If anything here conflicts with what you observe directly in the repo or via the user, trust direct observation — this is a best-effort snapshot, not a guarantee, especially regarding §5's in-progress uncommitted work.*
