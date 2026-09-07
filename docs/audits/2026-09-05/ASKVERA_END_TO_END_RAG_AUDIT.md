# AskVera end-to-end RAG and operations audit
Date: 2026-09-05

## Executive verdict

The code has a useful foundation, but I would not treat the current green unit suite as evidence of reliable answer quality or complete market isolation. I reproduced defects in publication authorization, cache handling, numeric verification, global-country resolution, parsing, and guardrails. Several explain why an ordinary question can fail despite apparently successful retrieval.

**Recommendation: repair the correctness and measurement defects first, then evaluate ranking and parent-child changes independently. Do not lower the confidence threshold globally to compensate.**

There is no foolproof RAG design. The practical target is explicit eligibility rules, traceable evidence, measurable extraction coverage, narrow failure handling, and independently verified release gates.

### Snapshot and scope

- Repository: C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy
- Commit: `7d29dad09540527a9302b95436f36e93f7fa5a2a`
- Subject: Merge pull request #56 from Aspire-coder/fix/candidate-mode-narrowing-loop-and-directory-address-regex
- Commit time: 2026-09-04 09:47:46 -0400.
- This is the local checkout reviewed. I did not fetch remote changes or verify the running production commit.
- No application source was changed, no deployment was made, and no cloud settings were changed.
- Existing untracked `.claude/`, `scratch/`, and the earlier full-context document were preserved.
- Added only this report and isolated audit probes under `docs/audits/2026-09-05/`.

### What was actually verified

| Check | Result | What it establishes |
|---|---|---|
| Existing unit suite | 774 passed, 2 warnings | Existing assertions pass locally |
| Isolated audit probes | 13 passed | The 13 documented behaviors were reproduced; these passes confirm gaps, not fixes |
| Admin portal TypeScript check | Passed | Type consistency, not browser correctness |
| Widget TypeScript check | Passed | Type consistency, not live answer quality |
| Taia interaction | Two question/answer turns observed | Limited conversation-style comparison |
| Live AWS/index/PDF corpus evaluation | Not run | Production extraction coverage and retrieval quality remain unmeasured here |

Python tests used the available **Python 3.14.4** environment. CI specifies **Python 3.11**; rerun fixes in that runtime before promotion. I did not run production builds, load tests, or a full authenticated portal browser suite. No tracked PDF or JSONL corpus was present, so synthetic parser fixtures establish failure paths, not which production PDFs are affected.

Evidence labels below:
- **Reproduced**: an isolated local check demonstrates the behavior.
- **Code-confirmed**: direct implementation evidence; no live exploitation or production incident asserted.
- **Risk/gap**: missing protection or measurement requiring additional validation.
P1 means high priority before a quality promotion; P2 means next hardening increment. No severity implies an active breach.

## 1. Highest-priority findings

### F01 — Staging permission can publish content, including a staged global job
**P1 · Reproduced**

The publication endpoint asks for `knowledge/stage`, not `knowledge/publish`. These are distinct permissions in the access model. The endpoint also does not apply the super-admin global-content restriction used by upload.

A user with only US staging permission reached the publication call for a staged global job tagged US in the isolated reproduction. This tested real endpoint authorization with the publication backend mocked; no document was published.

There is a second entry path: upload accepts `review_before_publish=False` by default with staging permission. The UI's review default is not a server authorization control.

**Fix:** require publish permission for every activation path; enforce global publication authority on the server; staging-only requests must remain staged. Apply the same invariant to upload, publish, queue commands, reprocessing, and rollback. Decide explicitly whether separate preparer/approver identities are required.

Sources: [api/admin_routes.py:814](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/api/admin_routes.py:814), [api/admin_routes.py:872](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/api/admin_routes.py:872), [services/admin_users.py:335](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/services/admin_users.py:335).

### F02 — Repeating a numeric value can hide a false second claim
**P1 · Reproduced**

The numeric validator deduplicates by numeric text, not the claim's subject and context.

Source: “Assistant Supervisor requires 2 CC. Recognized Manager requires 120 CC.”
A standalone “Recognized Manager requires 2 CC” is rejected. Put the correct “Assistant Supervisor requires 2 CC” first, and the wrong second claim is not checked.

**Fix:** validate each factual occurrence or each subject/predicate/value/unit/condition tuple. Deduplicate only truly equivalent propositions. Retain dates, currency, qualifying period, role, and exceptions.

Source: [app/validation/validators/numeric_grounding_validator.py:190](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/validation/validators/numeric_grounding_validator.py:190).

### F03 — Exact cache hits do not verify current document generation
**P1 · Reproduced path; lifecycle risk code-confirmed**

Exact hits bypass retrieval. The cache key includes several static safety/version values, but not the active document generation or source revocation state. Publication invalidates the active-generation lookup, not every answer tied to that generation.

Cached responses are reprocessed with empty retrieval evidence. The ordinary citation/numeric checks consequently cannot verify the source text. The isolated check showed an old answer returned without calling retrieval. This is not a live revocation test.

**Fix:** bind cache entries to active corpus generation, source IDs/content hashes, scope, and response/guardrail versions. Verify eligibility on replay; reject stale/revoked evidence. Publication and rollback must make prior answers ineligible across workers. A short TTL is not a revocation guarantee.

Sources: [services/cache.py:119](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/services/cache.py:119), [app/orchestrator/chat_orchestrator.py:530](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/orchestrator/chat_orchestrator.py:530), [services/knowledge_ingestion.py:972](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/services/knowledge_ingestion.py:972).

### F04 — Cached global telephone answers can be rewritten to the session country's number
**P1 · Reproduced with synthetic contacts**

Cached evidence is not available to the public-contact allowlist. A valid foreign office number can be scrubbed as PII, then the placeholder repair substitutes the session country's configured phone.

The probe requested Belgium from a US session and showed a synthetic Belgian number replaced with a synthetic US number. It does not claim today's production contact configuration contains those numbers.

**Fix:** preserve verified public-field provenance through cache replay. Render a phone only from the approved target-country record. Never fill a missing Belgium phone from a US fallback. If the requested field is missing, say that field is unavailable.

Sources: [app/orchestrator/chat_orchestrator.py:354](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/orchestrator/chat_orchestrator.py:354), [app/orchestrator/chat_orchestrator.py:530](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/orchestrator/chat_orchestrator.py:530), [app/response/quality.py:61](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/response/quality.py:61).

### F05 — Local guardrails reject legitimate questions and substrings
**P1 · Reproduced**

The matcher searches phrases as substrings without intent or word boundaries. These all failed the local governance check:

- “How do I securely register?” because “securely” contains “cure”.
- “Does company policy prohibit guaranteed income claims?”
- “What does the policy say about medical advice?”

A question about prohibited conduct is not the same as a request to perform it. Whole-message refusal also obstructs safe halves of mixed-intent requests.

**Fix:** immediately correct substring boundaries; then distinguish requesting a claim from explaining the policy prohibiting it. Decompose compound intent and answer only supported permitted portions. Preserve refusal tests for actual medical/guaranteed-income requests. Do not solve this by globally lowering a retrieval threshold.

Sources: [services/guardrails.py:13](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/services/guardrails.py:13), [config/guardrail_topics.py](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/config/guardrail_topics.py), [app/risk/policies/income_claim_policy.py:37](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/risk/policies/income_claim_policy.py:37).

### F06 — Country isolation is not a complete per-evidence invariant
**P1 · Reproduced component gaps; production cross-market disclosure not demonstrated**

The cross-market check examines the raw current message. It allows a message mentioning both the session market and a foreign market, and cannot itself resolve a foreign target inherited from a prior turn. It also uses the top document's global status.

Separately, evidence approval accepts the entire set when at least one document is eligible. An injected US+Belgium set was approved as a whole for US. Current retriever filters reduce the likelihood of that set reaching approval, but the final enforcement layer should not depend on the provider always being correct.

**Fix:** resolve intent, session policy market, and global target market separately. Filter and validate **every** evidence item, citation, cache entry, and parent expansion. For mixed questions, answer the eligible part and explicitly decline foreign local policy.

Sources: [app/orchestrator/chat_orchestrator.py:1464](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/orchestrator/chat_orchestrator.py:1464), [app/evidence.py:135](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/evidence.py:135), [app/retrieval/opensearch_sections.py:100](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/retrieval/opensearch_sections.py:100).

### F07 — Global-country aliases are recognized and then lost
**P1 · Reproduced**

The market resolver recognizes Japan from the supplemental global catalog, but the directory-target helper resolves names against only the base market configuration. Japan produces no target filter. Tanzania resolves to a long canonical name rather than the ordinary record alias, which can exclude the intended directory record.

**Fix:** store and filter a stable `record_country_code`. Use one full alias catalog for normalization, including approved language variants. Separate display name from filter identity. Ambiguous country names should trigger one clarification, not a guessed neighbor.

Sources: [services/market_config.py](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/services/market_config.py), [config/global_directory_markets.json](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/config/global_directory_markets.json), [app/retrieval/opensearch_sections.py:406](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/retrieval/opensearch_sections.py:406), [app/retrieval/opensearch_sections.py:439](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/retrieval/opensearch_sections.py:439).

### F08 — A parser can “succeed” while omitting the policy body
**P1 · Reproduced**

The specialized parser builds body chunks from recognized headings, then adds front matter and outlines. The ingestion gate checks a minimum number of chunks.

A synthetic three-page PDF with unrecognized body headings produced two chunks—front matter and contents—while losing the substantive joining and returns text. That meets the two-section count gate. Conversely, a valid one-chunk short policy notice is rejected.

**Fix:** measure body coverage, uncovered page spans, preserved headings/clauses, table continuity, and document-specific expected fields. Do not count outline/front matter as proof of body extraction. Quarantine poor extractions with an intelligible preview; permit genuinely short notices when their actual content is completely represented.

Sources: [scripts/ingestion/extract_policy_sections.py:239](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/scripts/ingestion/extract_policy_sections.py:239), [services/knowledge_ingestion.py:557](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/services/knowledge_ingestion.py:557), [services/document_preflight.py:76](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/services/document_preflight.py:76).

### F09 — OCR can lose exactly the structure global retrieval needs
**P1 · Code-confirmed**

OCR is triggered when at least half the pages are effectively empty, or all are. A few scanned critical pages in a mostly searchable PDF may be missed.

When OCR is used, both specialized policy and directory extractors are bypassed in favor of generic chunks. Directory country/field structure is therefore not reconstructed by that path. Non-PDF directory ingestion likewise lacks the specialized PDF record parser. Country-record filtering can then discard relevant text.

**Fix:** detect OCR needs per page; send OCR text/layout through the same normalized document model. Extract directory records with stable country and typed fields regardless of input format. Preserve table headers, units, row labels, and footnotes. Reject malformed records rather than publishing blank telephone labels.

Sources: [services/document_preflight.py:105](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/services/document_preflight.py:105), [services/knowledge_ingestion.py:502](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/services/knowledge_ingestion.py:502), [services/knowledge_ingestion.py:649](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/services/knowledge_ingestion.py:649).

### F10 — The evidence contract checks structure, not truth or completeness
**P1 · Reproduced**

The contract validates status, allowed evidence IDs, nonempty claims, and self-reported coverage. It does not prove the claims follow from their cited text, or that the answer contains only the claims listed.

A payload claiming “Returns are never allowed” passed the contract while referencing qualification text, with an unrelated claim list.

**Fix:** bind answer propositions to precise evidence spans and validate all material propositions. Use deterministic checks for structured facts; reserve bounded entailment checks for high-risk ambiguous prose. After any repair/removal, rerun completeness and citation binding. A model's `complete:true` is not independent evidence.

Source: [app/evidence_contract.py:24](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/evidence_contract.py:24).

### F11 — A correct translated numeric fact can be refused
**P1 · Reproduced**

English source “The initial discount is 5 percent” did not support the equivalent French sentence “La remise initiale est de 5 pour cent” under the lexical numeric validator.

**Fix:** carry language-independent fact bindings from evidence selection into rendering. Verify the value/unit/subject/condition before and after translation, rather than requiring English word overlap. Do not simply disable numeric grounding for non-English responses.

Source: [app/validation/validators/numeric_grounding_validator.py:235](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/validation/validators/numeric_grounding_validator.py:235).

## 2. Further correctness and operational gaps

### F12 — Parent diversification can suppress a different document
**P2 · Reproduced**

Two documents with parent section “5” collapse into one diversity bucket. The key lacks document identity. This applies when the optional diversity path is used; it does not prove the production flag is on.

**Fix:** key by logical document, generation, and parent section. Implement actual child-to-parent expansion independently; diversification alone is not parent-child retrieval.

Sources: [app/retrieval/experiments.py:9](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/retrieval/experiments.py:9), [app/retrieval/opensearch_sections.py:1114](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/retrieval/opensearch_sections.py:1114).

### F13 — Effective and expiry dates are not an enforced retrieval lifecycle
**P1 · Code-confirmed gap**

Dates are collected and stored, but the reviewed search filters do not enforce a current validity window. Effective date is carried as metadata; expiry is not consistently propagated into indexed chunk eligibility. A manually active but expired/future policy can remain eligible.

**Fix:** make status, generation, effective time, and expiry mandatory eligibility predicates. Define missing-date policy explicitly. Apply it to search, cache replay, source links, and rollback. An explicit question about a year is a separate intent from permission to use that edition.

Sources: [services/knowledge_ingestion.py:1209](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/services/knowledge_ingestion.py:1209), [scripts/ingestion/load_policy_sections_to_opensearch.py:70](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/scripts/ingestion/load_policy_sections_to_opensearch.py:70), [app/retrieval/opensearch_sections.py:100](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/retrieval/opensearch_sections.py:100).

### F14 — Source downloads do not use the chat locale authorization check
**P1 · Code-confirmed endpoint discrepancy**

Source-link issuance checks session identity, consent, and whether a URI is approved for the client-supplied locale. It does not call the widget locale restriction used by chat. A caller can request a different locale for the source check.

**Fix:** apply the same authoritative widget/session eligibility policy to downloads, with the global-document exception explicitly represented. Verify links against the evidence actually available to that session. Production exploitability depends on widget configuration and source knowledge; not tested here.

Sources: [api/routes.py:99](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/api/routes.py:99), [api/routes.py:253](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/api/routes.py:253).

### F15 — Conversation state is fragile and some failure turns disappear
**P1/P2 · Code-confirmed**

Context reconstruction relies on message-length/keyword heuristics and parsing flattened `user:` history lines. Several early fallback/refusal returns do not append the current turn. The next “that country” or “telephone number” may lack the very context the user expects.

**Fix:** keep compact typed state: last safe intent, requested entity, session policy market, global target country, requested field, and clarification status. Store safe terminal turns consistently. Treat prior assistant text as context, never evidence. Bound clarification to one useful question and avoid repeating a field the user already named.

Source: [app/orchestrator/chat_orchestrator.py:766](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/orchestrator/chat_orchestrator.py:766), [app/orchestrator/chat_orchestrator.py:1370](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/orchestrator/chat_orchestrator.py:1370).

### F16 — Live flow can show demo traces as live
**P1 · Code-confirmed**

A successful empty API/SSE response is replaced with `demo.traces`; the SSE handler labels that result “live.” This is not just stale data. It fabricates an operational view when there are no live traces.

**Fix:** empty means empty; unavailable means unavailable. Demo content must be an explicit isolated preview, never an automatic production substitute.

Source: [admin-portal/src/components/FlowVisualizer.tsx:59](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/admin-portal/src/components/FlowVisualizer.tsx:59).

### F17 — Dashboard loading couples independent panels and permissions
**P1/P2 · Code-confirmed**

Overview initializes demo data and uses one `Promise.all` for several services. A denied/failed endpoint prevents successful results from updating. Only the audit request is individually permission-gated. Valid users with limited section access can therefore see repeated errors and demo/stale panels.

Insights also retains old data on errors; filter requests lack a clear stale-response guard.

**Fix:** independent panel loading/error/empty states; permission-aware requests; abort or discard obsolete filter responses; last-success timestamp per panel. Surface failed endpoint and correlation ID without sensitive details. Do not label mixed or stale data as wholly live.

Sources: [admin-portal/src/components/OperationsOverview.tsx:23](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/admin-portal/src/components/OperationsOverview.tsx:23), [admin-portal/src/components/InsightsDashboard.tsx:64](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/admin-portal/src/components/InsightsDashboard.tsx:64), [admin-portal/src/api.ts:63](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/admin-portal/src/api.ts:63).

### F18 — Editing a user can flatten different per-market permissions
**P1 · Code-confirmed**

The edit form converts scopes into one permission per section, then recreates the market × section cross-product. A user with different permissions in different markets cannot be faithfully represented. Saving can broaden or reduce access depending on which scope won the map.

**Fix:** preserve the original market/section/permission tuples; offer explicit bulk editing as a separate action. Show a before/after permission diff and require confirmation for broader access.

Source: [admin-portal/src/components/UsersManager.tsx:67](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/admin-portal/src/components/UsersManager.tsx:67), [admin-portal/src/components/UsersManager.tsx:110](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/admin-portal/src/components/UsersManager.tsx:110).

### F19 — Expected-answer feedback goes into the wrong field
**P2 · Code-confirmed**

The widget sends the expected answer as `comment`; the backend's dedicated expected-answer logic reads `expected_answer`. Consequently the structured correction field used for review does not receive that widget input.

**Fix:** align the API contract and add an end-to-end negative-feedback test.

Sources: [widget-wrapper/src/sdk/WidgetRuntime.tsx:791](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/widget-wrapper/src/sdk/WidgetRuntime.tsx:791), [api/routes.py:392](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/api/routes.py:392).

### F20 — Experimental safety wording is protected by convention, not an environment boundary
**P1 configuration risk · Code-confirmed**

The UI and endpoint docstring say “test environment” and warn that in-voice refusal text lacks Legal review. The setter checks super-admin and confirmation, but not environment. The reader has an off-by-default master switch, which is useful, but enabling it in production can expose stored experimental flags.

**Fix:** enforce permitted deployment environments server-side; reject unapproved wording versions in production even for an administrator. Display actual environment, effective flag state, version, and scope. Do not infer production enablement from this code review.

Sources: [api/admin_routes.py:353](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/api/admin_routes.py:353), [services/candidate_control.py:40](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/services/candidate_control.py:40), [services/candidate_control.py:88](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/services/candidate_control.py:88).

### F21 — Latency has serial fan-out without a shared request deadline
**P1/P2 · Code-confirmed; live timing not measured**

Planner, multiple text/vector searches, embeddings, global translation, selection, generation, validation, and fallback can execute serially. Per-call timeouts/retries do not create an end-to-end budget. Widget cancellation does not cancel a synchronous backend request.

**Fix:** instrument total request time first; cap planning and retrieval expansion; reuse embeddings; parallelize independent bounded searches; give optional stages explicit remaining-time budgets. Return a controlled, retryable terminal response when the budget expires. Do not stream unvalidated factual claims merely to improve apparent speed.

Sources: [app/retrieval/opensearch_sections.py:616](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/retrieval/opensearch_sections.py:616), [app/retrieval/providers.py:501](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/retrieval/providers.py:501), [services/embeddings.py](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/services/embeddings.py), [api/routes.py:267](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/api/routes.py:267).

### F22 — Metrics do not yet represent the complete request
**P2 · Code-confirmed**

Live traces are a per-process window of 100. Repeated stages overwrite prior records with the same name, so summing displayed stages is not reliable wall time. Another worker may not have the requested trace.

Analytics records final-generation usage/latency, not the whole planner/selector/translation/embedding chain. Exception requests can be absent from the question/quality denominator. These figures should not be presented as complete billed cost or total user latency.

**Fix:** persist redacted request outcomes and uniquely identified stage attempts; record wall-clock duration and every model call. Include errors, timeouts, refusals, caches, and delivered answers in separate denominators. Use actual billing reconciliation for dollar totals.

Sources: [app/operations/trace_store.py:59](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/operations/trace_store.py:59), [app/operations/trace_store.py:145](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/operations/trace_store.py:145), [services/analytics.py:128](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/services/analytics.py:128), [api/routes.py:287](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/api/routes.py:287).

### F23 — Untrusted history/evidence enters the system prompt
**P1 security hardening gap**

Prompt assembly places retrieved text and flattened history in the system prompt. The final Converse call attaches a guardrail, but plain system content is not evaluated by default as guardrail input. Local keyword governance is a separate mechanism, despite its provider's name.

**Fix:** separate trusted instructions from user/history/source data; explicitly mark trust boundaries and keep retrieved instructions inert. Configure the appropriate guardrail input blocks and test injection in documents/history. No prompt injection exploit was attempted against production.

AWS documents that Converse system prompts are excluded unless appropriately marked with `guardContent`. `guardrailConfig` attaches a guardrail; `guardContent` selects content/qualifiers; `ApplyGuardrail` is the standalone evaluation route. Denied topics, content filters, word filters, sensitive-information filters, and contextual grounding are distinct controls, not substitutes for market authorization or factual verification. [AWS Converse guardrails](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-use-converse-api.html), [contextual grounding](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-contextual-grounding-check.html).

Sources: [app/prompts/builder.py:24](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/prompts/builder.py:24), [app/prompts/templates.py:58](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/prompts/templates.py:58), [app/models/bedrock_provider.py:235](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/app/models/bedrock_provider.py:235).

### F24 — CI's retrieval gate does not demonstrate live answer quality
**P1 measurement gap**

The reviewed workflow runs unit tests and the canary in `--validate-only` mode. That is useful fixture validation, not an end-to-end evaluation against the active corpus and models.

**Fix:** retain fast offline CI, but add an explicitly separate promotion run against a frozen candidate index/configuration. Preserve questions, both profiles' answers, evidence, and failure layers. No release-quality percentage can honestly be inferred from today's unit count.

Source: [.github/workflows/deploy.yml:49](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/.github/workflows/deploy.yml:49).

## 3. The correct country/global contract

The session's selected policy market and the country mentioned in a global-directory question are different dimensions. Geolocation should suggest a selection, not silently override an explicit choice or act as the authorization mechanism.

| Session market | Request | Eligible evidence | Behavior |
|---|---|---|---|
| US | US return policy | Active US policy | Answer with US citations |
| US | Belgium return policy | No Belgium local policy | Explain the market boundary; do not substitute US as Belgium |
| US | How do I join in Belgium, from global sponsoring? | Approved global Belgium record | Answer supported global instructions |
| US | Belgium office phone | Approved global Belgium phone field | Exact field or explicit missing-field response |
| US | Compare US and Belgium policy | US policy only | Answer US portion if useful; decline Belgium policy portion |
| US | Global Belgium sponsorship plus Belgium compensation rules | Global Belgium record, not local Belgium policy | Answer global half; decline local-policy half |
| US | “And its hours?” after Belgium office question | Same global Belgium record | Preserve country; change requested field |
| US | Global record absent | None | Do not borrow UK/US/neighbor-country values |

Implement one eligibility function used by every retrieval provider, selector result, parent expansion, generator input, validator, cache replay, and source-link endpoint.

Minimum evidence identity should include logical document ID, generation, source hash, scope, policy country, record country code where applicable, language, document type, section/parent ID, page/span, publication status, and validity dates.

A global document is globally accessible evidence; it is **not permission to retrieve the target country's local policy**. Conversely, a session-market restriction must not remove a valid foreign-country global record.

## 4. Parsing and retrieval improvement design

### Ingestion

1. Validate file type/size and existing malware controls; retain original immutable source and hash.
2. Extract page text/layout; OCR only pages that need it.
3. Normalize into a document model preserving headings, lists, tables, footnotes, language, and page spans.
4. Apply policy versus directory structure without re-reading and discarding the normalized OCR result.
5. Validate extraction coverage and required record fields. Preview missing spans and malformed records before approval.
6. Create retrieval children with bounded context and parent identity; preserve complete governing clauses and exceptions.
7. Index a staged generation, test it, then activate via controlled publication.
8. Make cache eligibility change with activation/rollback.

Do not use one fixed chunk count or character size as a quality verdict. The current 8,000-character splitting and structured expansion should be measured against real PDF boundaries. Table rows need their headers, units, conditions, and footnotes, not just nearby text.

### Retrieval and selection

Retain hybrid retrieval as a sensible baseline. Repair filters and labels before changing embeddings or ranking.

- Exact structured field retrieval for directory facts.
- Policy search over eligible local evidence, with question-type/entity/authority metadata where it demonstrably helps.
- Combine lexical/vector rankings on a controlled scale. RRF is a reasonable isolated experiment because it fuses ranks rather than treating incomparable raw scores as calibrated probabilities; it is not guaranteed to improve this corpus. [OpenSearch RRF](https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/rrf/).
- Select governing requirements with relevant definitions/exceptions, rather than blanket-demoting all definitions. A definition can be authoritative for a definition question.
- Implement parent expansion separately, preserving eligibility and a context budget. Hierarchical retrieval can retrieve precise children and supply broader parents, but effective returned-result counts and context composition must be measured. [AWS chunking guidance](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-chunking.html).
- Calibrate confidence last using held-out evidence and safety outcomes. Current heuristic scores/model confidence are not automatically probabilities.

Do not add another large abstraction layer, migrate the entire platform, or re-chunk production merely to address the narrow bugs above.

## 5. Conversation quality and the Taia comparison

I opened Thorne's Taia in the available browser automation and observed two actual answer turns:

1. “I'm new to Thorne and a little overwhelmed. How should I get started?”
   - Taia acknowledged the uncertainty, proposed choosing a foundation goal, and asked about goals/preferences.
2. “Can you make that simpler? I just want general wellness, no big routine.”
   - Taia acknowledged the correction and reduced its suggestion to one main product, with an optional later addition.

This is a style observation, not an endorsement of its health advice. It also asked several questions initially and still offered an optional addition after “simpler”; it is not a perfect gold standard.

A subsequent typo-heavy return-policy question led to a conversation reset on one attempt and then a Terms/data-use consent screen. I did not accept that consent without permission. Therefore **I did not verify Taia's returns accuracy, medical/income boundaries, or a broad multi-turn safety suite**. No CAPTCHA was solved. Reference: [Thorne Taia](https://www.thorne.com/featured/taia?open_chat=true).

For AskVera, borrow the interaction pattern, not product recommendations or external facts:

- One brief acknowledgment when useful.
- Direct answer first.
- Only qualifications needed to avoid misleading the user.
- Citation close to the factual statement.
- At most one relevant follow-up.
- When the user says “simpler,” genuinely shorten.
- When refusing one part, retain the safe supported part.
- Ask for country/field only when actually unresolved.

Illustrative style, with placeholders rather than invented policy facts:

> “Happy to help. For Belgium, the approved global sponsoring guide says [verified instruction]. [Citation]  
> I can explain the global joining steps, but Belgium's local company policy isn't available in your selected US policy context.”

For a missing phone:

> “I found Belgium's approved directory record, but it doesn't list a telephone number. I won't substitute another country's number.”

The existing prompt already attempts warmth. More prompt wording alone will not repair lost evidence, repetitive clarification, wrong cache contacts, or premature guardrail refusal.

## 6. Operations portal review summary

| Area | Assessment and next action |
|---|---|
| Overview | Independent panels, permission-aware loading, no production demo fallback, show freshness |
| Live flow | True empty state, durable cross-worker traces, reconnect handling, distinct stage attempts |
| Insights | Stable filter/request association, inclusive failure denominator, full latency/cost labels |
| Knowledge | Enforce stage/publish server-side, scope-aware preview, coverage reports, validity windows |
| Market readiness | Keep “not verified” until an actual market/language evaluation; configuration alone is not readiness |
| Users | Preserve per-market scopes during edit, show access changes before saving |
| Support routes | Keep server-side validation; validate bulk/fallback routes consistently and test delivery/failure states |
| Widget management | Exact origins and draft/publish controls are useful; test default market/language, revoked sessions, key rotation, and source access |
| Candidate controls | Enforce environment/approved wording at runtime, not only in UI labels |
| Feedback | Preserve dedicated expected answer plus comment and correlation ID |

The reviewed UI includes useful origin validation, confirmation dialogs, draft publication concepts, and explicit candidate wording warnings. These should be retained. Full interaction/accessibility and multi-role browser acceptance testing is still required; this was not a pixel-by-pixel audit of every page.

## 7. What is already good

- Separate ingestion, retrieval, governance, generation, validation, and response layers allow narrow repairs.
- Explicit local/global scope and market filtering exist; the goal is to make them consistent across every path.
- Immutable/generation-based publication and rollback machinery provide a useful base.
- Cache reads include fail-open handling for availability; retain that while adding evidence freshness.
- Consent, widget-session binding, exact-origin validation, and admin permission concepts are present.
- Evidence IDs and response integrity checks are a better starting point than unrestricted free-form generation.
- Existing unit coverage and optional experiment controls support isolated changes.

These are implementation strengths, not certification of deployed configuration.

## 8. Recommended sequence and promotion gates

### Stage A — Correctness and safety foundation
Fix F01–F07, F10–F11, F14, F18, and F20 in narrow reviewed changes. Include the cache/global contact path and legal-policy discussion tests. Keep global thresholds unchanged.

### Stage B — Trustworthy content and portal
Fix F08–F09 and F13 with verified production-source fixtures. Fix demo/live states and panel isolation so evaluation results are trustworthy.

### Stage C — Conversation and latency
Repair typed follow-up state, terminal-turn persistence, feedback, per-request timing, bounded fan-out, and cross-worker trace visibility. Measure uncached and cached requests separately.

### Stage D — Isolated retrieval improvements
Evaluate authority-aware ranking, then parent-child retrieval, then confidence calibration as independently attributable candidates. If independent ingestion experiments run in parallel, give them separate indexes/manifests; do not combine unmeasured variables.

### Required evaluation record

For every case, retain:
- case ID, exact question and full turn sequence;
- session market, language, requested global country, intent, eligible document scope;
- verified gold section(s)/record field(s), source hash/version, and whether answer/partial answer/clarification/abstention is expected;
- Current and Candidate complete answers side by side;
- top retrieval candidates, selected evidence, confidence decision, contract/validation result, cache provenance, and failure layer;
- wall time, per-stage attempts, token usage, model/version and active flags.

Measure separately:
1. Extraction coverage and directory-field completeness.
2. Candidate recall at 1/5/10/20 and MRR.
3. Selector success and evidence coverage.
4. Incorrect abstention versus correct abstention.
5. Grounded final correctness and material-qualification completeness.
6. Country/global isolation and safety-boundary compliance.
7. Legal-template completeness/version.
8. Multi-turn/typo/multilingual success.
9. p50/p95/p99 wall time, errors/timeouts, and per-request cost.

Freeze corpus/index/configuration/cache namespace. Repeat cache-free Current and Candidate runs at least three times to expose run variability; report paired per-case changes, not just an aggregate. Three repeats do not by themselves establish statistical significance. Never call a reused regression fixture “held out”; maintain a separate unseen evaluation set.

Hard gates:
- No unauthorized local-policy evidence, source link, or cache replay in the boundary suite.
- No wrong-country directory values.
- No publication privilege bypass.
- No unsupported material numeric claims in the regression/safety suite.
- No empty/heading-only/dangling-field output.
- Required approved disclaimer templates complete.
- All 20-question or larger agreed end-to-end cases rerun on the same commit; keep scope recall, safety, and Legal scores separate.
- Explicit pre-agreed latency/error limits under realistic load.
- Successful deployment-parity verification before announcing release-ready.

These gates should fail closed for promotion, not silently substitute demo data or skip live evaluation.

## 9. Reproduction ledger

[docs/audits/2026-09-05/test_review_probes.py](C:/Users/KRISH/Downloads/Chatbot/Archives/enterprise-chatbot/askvera-deploy/docs/audits/2026-09-05/test_review_probes.py) contains 13 isolated probes with external boundaries mocked:

1. Stage-only publication of a global job.
2. Repeated numeric value hides another unsupported claim.
3. Structural evidence contract accepts unentailed content.
4. Mixed-country evidence accepted as a set.
5. Comparison/inherited target escapes the local cross-market helper.
6. Exact cache hit skips retrieval/generation verification.
7. Unrecognized PDF body leaves only front matter/outline.
8. Valid one-chunk policy notice fails minimum-count gate.
9. Parent identity collision across documents.
10. Global alias recognized but lost before record filtering.
11. Legitimate policy/security questions blocked by local guardrails.
12. Cached foreign phone replaced by session-country phone.
13. Valid translated numeric fact rejected.

These are diagnostic assertions of current behavior. When fixes are implemented, invert/adapt them into ordinary regression tests asserting the correct behavior; do not use “13 passed” as a release badge.

## 10. What is needed to finish production validation

- Read-only access to the current deployment manifest, active flags/index generations, and redacted request traces.
- Approved source PDFs and their expected market/language/global classifications.
- Current Legal-approved templates and version/market applicability.
- A dedicated non-production evaluation path, with cost limits, for side-by-side uncached runs.
- Permission to accept Taia's Terms/data consent if a broader competitor comparison is still wanted.

Until then, this report supports the code-level findings and repair order, not a claim that every production failure is diagnosed or that no other bugs exist.

