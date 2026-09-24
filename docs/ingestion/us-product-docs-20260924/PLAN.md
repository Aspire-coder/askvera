# US product documents: ingestion plan (dry run, awaiting approval)

Prepared 2026-09-24 on branch `feat/us-product-docs-ingestion-prep-20260924` (from `main` at f23f02e).
**Nothing has been uploaded, indexed, embedded, published or activated.** Nothing on this
branch touches AWS, OpenSearch, Bedrock or the database. The files are:

| File | Contents |
|---|---|
| `PLAN.md` | This plan |
| `manifest.json` | Dry-run manifest: each of the 24 files → exact upload metadata, SHA-256 and extractor dry-run counts |
| `COMPLIANCE_REVIEW.md` | Health, benefit, structure/function and disease-adjacent statements, for compliance review (not decided) |
| `DUPLICATES_DIFF.md` | Training guide vs product sheet comparison for the 8 overlapping products |
| `tests/unit/test_us_product_docs_market_isolation.py` | Offline proof of US-only retrieval |

Line references are to `main` at f23f02e.

## 1. How documents are ingested and scoped today

**Upload.** The admin-portal uploader posts `country`, `language`, `document_type` and
`access_scope` (`admin-portal/src/components/KnowledgeUploader.tsx:121-126`) to
`POST /documents` (`api/admin_routes.py:861`). The API enforces the following:

- `country` must be a configured market and `language` one of its languages (`admin_routes.py:879-882`).
- `document_type` must be in `DOCUMENT_TYPES = {"policy", "office_directory"}` (`services/knowledge_ingestion.py:48-51`, checked at `admin_routes.py:885`). **Product material has no type today.** The form default `"other"` (`admin_routes.py:868`) is itself rejected.
- `access_scope` must be in `{"country", "global"}` (`knowledge_ingestion.py:52`). There is no `"local"` scope; the market-only value is `"country"`, shown in the UI as "Selected market only" (`KnowledgeUploader.tsx:303`).
- Global uploads need a Super Admin (`admin_routes.py:889`). `policy` must be `country` (`:892`), and `office_directory` must be `global` (`:897`).

**Worker.** `process_ingestion_job` (`knowledge_ingestion.py:462`) sends a `policy` PDF through the numbered-section policy extractor (`:486`, `:521-534`). Every other type goes through the generic `build_sections` chunker (`:747-803`, called at `:543`). It fails any document yielding fewer than `ADMIN_INGESTION_LOW_COVERAGE_THRESHOLD` = 2 sections (`:559`, `config/settings.py:204`).

Rows are bulk-written with `status="staging"` (`:896-927`). The row shape comes from `scripts/ingestion/load_policy_sections_to_opensearch.py:135-191`. `country`, `language`, `document_type` and `access_scope` are top-level keyword fields, and `search_text` includes the source filename (`:106-115`).

**Publication.** Publishing upserts `knowledge_active_generations` **keyed on `logical_document_id` alone** (`knowledge_ingestion.py:1034-1053`, unique index `migrations/20260730_02_controlled_knowledge_publication.sql:43`). The slot ID is `access_scope:COUNTRY:language:document_type:id` (`services/knowledge_generations.py:40-60`). Retrieval reads that table through `active_generation_ids` (`knowledge_generations.py:71-94`) with a 15 s cache (`:20`).

**Retrieval filters (`app/retrieval/opensearch_sections.py`).**

- **Locale channel.** `_scope_filter(..., "locale")` (`:156-173`) filters on `country ∈ get_document_country_codes(session)` and on `_language_filter`. It does **not** filter on `access_scope` or `document_type`. `get_document_country_codes` returns `documentCountries` or the market code itself (`services/market_config.py:845-849`). US maps to `{"US"}`, and GB maps to `{"UK"}` (`config/policy_locales.json:20`).
- **Language.** `_language_filter` (`:140-148`) adds `"en"` for every non-English session when `OPENSEARCH_ALLOW_ENGLISH_FALLBACK` is true, which is the default (`config/settings.py:430`).
- **Generation pointer.** `_generation_filters` (`:447-478`) repeats the country and language restriction through the pointer table when the pointer is enabled.
- **Global channel.** The global channel is `access_scope = "global"` plus language, with **no country and no document-type filter** (`:158-166`). It is used by the global vector query (`:1844`). The global text query adds a directory-type filter (`:645`); the vector query does not.
- **Evidence gate.** `_has_current_locale_document` (`app/evidence.py:357-384`) accepts a row whose country and language match, with English fallback (`:360-362`). It also accepts **any** `global` row whose type is not `policy` (`:376-379`). `approve_evidence` drops every row that fails it (`evidence.py:165-167`).
- **Citations.** `is_approved_source` (`:481-542`) applies the same rules.
- **Cache.** The answer cache is keyed by country and language (`services/cache.py:120`). Restored evidence is re-gated (`app/retrieval/cache_evidence.py:21-27`).

## 2. Required metadata (see `manifest.json`)

| Field | Value | Why |
|---|---|---|
| `country` | `US` | The locale filter admits only `US` rows to US sessions |
| `language` | `en` | The documents are English |
| `access_scope` | `country` (**never `global`**) | A global row reaches every market through the global vector channel (no country filter, `opensearch_sections.py:158-166`) and passes the evidence gate for every market because its type is not `policy` (`evidence.py:376-379`). The negative-control test demonstrates this leak. |
| `document_type` | `product_information` (**new type, needs a code change**) | Keeps product material separate from company policy. Uploading as `policy` fails: the policy extractor raises "No policy body sections were recognized" on 6 of the 24 PDFs (the AloeTurm and Freedom guides; the Absorbent-D, AloeTurm, Kids and Bright Toothgel sheets) and yields only 2-5 sections on most sheets. It would also label the chunks "Policy section" in the model context (`app/prompts/builder.py:152-167`). The generic chunker produces 5-6 sections per sheet and 32-54 per guide. No document needs OCR. |
| `logical_document_id` | Unique per document, e.g. `us-product-sheet-forever-b12-plus` | The publish upsert is keyed on it alone. **Do not type the portal's placeholder** (`us-policy` for type policy, `KnowledgeUploader.tsx:87`, `:307`). Reusing an existing slot replaces that document's live generation. |
| `document_version` / `effective_date` | Taken from the MMDDYY in each sheet's filename (to be confirmed) | Guides have no date (decision D1) |
| `review_before_publish` | `true` | Keeps the rows `staging` (invisible) until an explicit publish |
| Upload filename | Clean name, e.g. `US-EN-product-sheet-forever-b12-plus-188.pdf` | `source_file` is indexed into `search_text` and shown in citations. The originals carry " (1)" suffixes and the misspelling "Absorbant". |

The code change needed for `product_information` is proposed, not implemented; it needs its own reviewed PR:

- add the type to `DOCUMENT_TYPES`;
- in `admin_routes.py`, reject it unless `access_scope == "country"`, mirroring `:892`;
- give it a "Product information" label in `builder.py`;
- extend the low-coverage error message.

## 3. Offline proof of US-only retrieval

The test file `tests/unit/test_us_product_docs_market_isolation.py` has 82 cases and passes. It builds the index rows for all 24 manifest entries with the real row builder (`loader._document`). It evaluates the real filter clauses (`_text_query`, `_vector_query` locale and global, `_exact_section_query`, `_directory_text_query`) in memory, with the generation pointer both off and on. It also runs the real `_has_current_locale_document`, `approve_evidence`, `is_approved_source` and `cache_evidence.restore_evidence`. The results:

- **Every other market retrieves none of them.** This covers all 16 configured markets, the legacy `UK` code, the unconfigured `MX`/`PR`/`AU`/`IE`/`ZA` and an empty market, in every configured language plus regional tags. No product row passes any locale or global query, the evidence gate, citation authorization or cache restore.
- **US sessions retrieve all 24** in `en` and `en-US`, and in `es`/`es-US` through the English fallback. With the fallback off, US `es` sessions get none.
- **Confirmed: the English fallback is not limited to Spanish.** A US session in any language (for example `fr`, `de` or `pt`) receives these English documents. The model must then answer in the session language from English source text; the translation risk is the same as for today's English-only content.
- **Country-scoped rows never enter the global channels, even for US.**
- **Negative control.** The same rows marked `global` leak to CA, GB and DE through the global vector channel and pass their evidence gate. This proves the assertions above can fail.

Cross-market path. A CA or GB user who names a US product is still filtered to their own country. A US user asking about "Absorbent-D in Canada" gets US material, because `_names_another_market` only blocks explicit "company policy" requests (`evidence.py:161-163`). The answer could present US label facts as if they applied to Canada. This is minor and noted as decision D6.

Relevance side effect. The locale channel does not filter by `document_type`, so US policy questions will now also compete with product chunks, and the reverse. The existing US retrieval regression set should be re-run after publication.

## 4. Why they would not be answerable yet

The findings below are cited on `main`. The proposals are only proposals: nothing is implemented, and no budget is raised.

1. **The system prompt rule** "Sources hold no product prices, catalogue, stock or order status" (`app/prompts/templates.py:46-47`). The model is told there is no catalogue.
2. **The query planner** (LLM, `app/retrieval/providers.py:785-813`) calls the corpus "a policy knowledge base". Its `medical_claim` label covers "health-benefit claims". Any label other than `knowledge` with confidence ≥ 0.85 **skips retrieval entirely** (`opensearch_sections.py:1876-1891`). "What does ImmuBlend do?", "Can kids take Forever Kids?" and "Is Marine Collagen safe if I'm allergic to fish?" are therefore likely refused before retrieval, and every benefit or disease question is.
3. **The phrase guardrail** (`config/guardrail_topics.py:18-39`) runs on input before retrieval and on output after generation. It blocks "sunburn", "acne", "treatment", "cure" and similar. The input side is not negation-aware. On the output side, an answer quoting a product sheet that uses those words is replaced with refusal copy.
4. **`claim_safety`** (`services/claim_safety.py:42-60`, `config/claim_safety.json:17-44`) only chooses which refusal copy is shown. Its product terms are generic, and eczema, colds and eyesight are not disease terms.
5. **`catalogue_scope`** (`config/conversation_routes.json:91-102`) is **not** a pre-retrieval deflection. It is used only in `_insufficient_evidence_message` (`app/orchestrator/chat_orchestrator.py:3760-3767`), after a pipeline failure. On failure, "price", "cost", "catalogue" or "stock" questions get the catalogue boundary copy. Price questions are correctly unanswerable, because the documents contain no prices.
6. **User-facing capability copy** says "company policies and international sponsoring directory" (`conversation_routes.json`, `config/vera_persona.py:28-31,53-56`, `claim_safety.json:4`).

**Prompt budget.** The system prompt is measured in characters: 4383 for `new_prospect`, up to 4389 for `preferred_customer`. The limits are `< 4400` (`tests/unit/test_bedrock.py:57`) and `<= 4392` (`tests/unit/test_codex_conversation_tone.py:134`, `tests/conversation/test_composition_prompt_structure.py:71`), so the binding headroom is **9 characters**. Other pins: the exact substrings "no product prices" and "never offer to look them up" (`test_bedrock.py:60-61`), a hash of the later template (`test_codex_conversation_tone.py:24`), and a hash of the conversation routes (`:75`).

**Proposed changes (not implemented):**

- **A.** Add the `product_information` type (section 2).
- **B.** Drop `catalogue,` from `templates.py:46`. This saves 11 characters and keeps both pinned substrings; the template hash must be refreshed.
- **C.** Put product-answer rules in the user prompt, emitted only when a product chunk is in evidence (next to `builder.py:74-82`). The rules would be:
  - state ingredients, directions, servings and cautions as written;
  - quote benefit wording verbatim;
  - never say a product treats, cures or prevents disease;
  - carry the FDA disclaimer.

  This costs nothing against the system-prompt budget.
- **D.** Update the planner prompt, which is not budget-pinned:
  - describe the corpus as policy **and US product information**;
  - classify ingredient, usage, serving, allergen, suitability and label-benefit questions as `knowledge`;
  - reserve `medical_claim` for treat/cure/prevent-disease questions and personal medical advice;
  - optionally add a deterministic second check like the income one (`providers.py:398`), so a planner label alone cannot skip retrieval.
- **E.** Add product names and eczema, cold, flu and eyesight to `claim_safety.json`, and update the capability and refusal copy. The routes hash and the tone test's `EXPECTED` values must be refreshed. Avoid adding bare "freedom", which collides with "financial freedom".
- **F.** Review "sunburn", "acne" and "treatment" against the actual label wording. For example, allow output sentences that match the evidence verbatim, on the output side only.
- These are market-agnostic: every rule must key on `document_type`, not on US.

## 5. Compliance risk

See `COMPLIANCE_REVIEW.md`. Key facts for the reviewer:

- **All 9 training guides** carry the banner "AI-ASSISTED CONTENT - INTERNAL GUIDANCE ONLY - LOCAL REVIEW AND APPROVAL REQUIRED … For Country Leadership Training Use". It states the guide is "not a universally approved, market-ready, or authorized consumer-facing communication", and that claims must be approved "before external distribution or use by Forever Business Owners (FBOs)". Ingesting a guide into an FBO- or customer-facing assistant is that kind of distribution.
- 395 statements are flagged in total: 169 in the sheets and 226 in the guides. The guides' "avoid / don't say" examples are listed separately and not counted.
- **FDA disclaimer coverage**, verified by text search.
  - **Product sheets:** the FDA statement appears in 11 of the 15. The 10 supplement and drink sheets carry it. Bright Toothgel also carries it, but that is the dietary-supplement wording on a cosmetic. The 4 cosmetic sheets (Aloe Propolis Creme, Aloe First Spray, Aloe Vera Gelly, Aloe Lips) carry a cosmetic notice instead ("Forever makes no claim that its products cure or prevent any diseases…").
  - **Guides:** 6 of the 9 carry the full FDA statement (Marine Collagen, AloeTurm, B12 Plus, Freedom, ImmuBlend, iVision). The Absorbent-D guide quotes it only inside an instruction to staff. The Aloe First and Aloe Propolis Creme guides use cosmetic wording.
  - **No claim is tied to its disclaimer by an asterisk.** Each disclaimer is a single page footer, which a retrieved chunk will usually not include.
- The highest-risk items include:
  - **iVision guide:** children's screen time, blue light and retinal harm, and "first line of defense".
  - **Forever Kids sheet:** it targets children, gives dosing for ages 1-3, and has no iron warning.
  - **ImmuBlend sheet:** "germs, bacteria and viruses", "cardiovascular function" and "70% to 80% of immune cells".
  - **B12 sheet:** "contributes to heart function".
  - **B12 guide:** metformin interaction and pregnancy answers.
  - **Propolis Creme guide:** its answer on eczema, psoriasis and rosacea.
  - **Fiber Fusion sheet:** "ease occasional bloating".

## 6. Duplicates and versions

See `DUPLICATES_DIFF.md`: 19 contradictions across the 8 overlapping products, plus warnings that appear only in the guides. The most material are:

- **Propolis Creme preservatives.** The sheet (v4, Jan 2026) lists methyl- and propylparaben; the guide says the product is paraben-free.
- **AloeTurm gelatin.** The guide says "bovine gelatin from a non-cattle source", which contradicts itself and matters for halal and vegetarian questions.
- **Marine Collagen.** The guide says "No Added Sugars", but grape juice concentrate is the second ingredient on the sheet.
- **ImmuBlend zinc.** The guide says it contains zinc; the sheet text does not.
- **Marketing wording.** Several sheet claims ("scientifically proven", "heart function", "cardiovascular function") are phrases the guides tell staff not to use.
- **Warnings only in the guides.** Adults-only for Absorbent-D, AloeTurm and Marine Collagen; the B12 pregnancy caution; the Propolis bee allergy.

The guide PDFs are newer files, generated 2026-09-22, but they are derived from the product pages and FAQs. For label facts, the sheet or the physical label is the suggested source of truth.

## 7. Live steps: NOT executed, each needs explicit approval

| # | Step | Effect |
|---|---|---|
| 0 | Merge and deploy the `product_information` code change (A). Optionally also B-F. | Separate PR, review and deploy. Without it, uploads fail with HTTP 400 "Unsupported document type". |
| 1 | In the admin portal, per manifest entry: market **United States (US)**, source language **English**, type **Product information**, availability **Selected market only**, the manifest's version, effective date, stable ID, owner and approval reference, **Review before publish on**. Upload the file under `proposed_upload_filename`. | Creates an `ingestion_jobs` row. Stores the PDF in S3 under `countries/US/` (`knowledge_ingestion.py:323-333`). Enqueues the worker. The worker extracts the text, **calls Bedrock to embed each chunk** (cost), and bulk-writes the rows to OpenSearch as `staging`. Not visible to any user. |
| 2 | Preview each job and run the "Test a question" check in the portal. | Read-only for the index. The test question runs retrieval against the staged job. |
| 3 | Publish each job. | Upserts the `knowledge_active_generations` row for its unique `logical_document_id`, and marks its rows `active`. Within about 15 s, US sessions retrieve it: in English, and in any other language through the English fallback. No other market is affected, per the tests. |
| 4 | Verify live: ask the same product question from US/en, US/es, CA/en, CA/fr and GB/en sessions, and re-run the US retrieval regression set. | Read-only checks. The expected result is that only the US sessions cite the product documents. |
| Rollback | Use Versions → roll back, or delete the job (`knowledge_ingestion.py:1313`, `:1349`). | Deactivates the generation. The cached answers are revalidated against the active generations on restore (`cache_evidence.py:24-27`). |

## 8. Decisions for the user

- **D1. Training guides.** Ingest none of the 9 guides (recommended while they carry the internal-only banner), all of them, or only after written local approval? If they are ingested, what version and effective date should they use?
- **D2. Document type.** Approve adding `product_information` (recommended), or accept `policy`? With `policy`, 6 PDFs fail and the chunks are mislabelled as company policy.
- **D3. Compliance sign-off.** Review each flagged statement in `COMPLIANCE_REVIEW.md`. Should the bot quote benefit claims at all, and must every product answer carry the FDA disclaimer?
- **D4. Authoritative source per product.** Sheet or guide, for each contradiction in `DUPLICATES_DIFF.md`, or confirm against the physical US label first.
- **D5. Spanish and other non-English US sessions.** Allow English product sources through the fallback (current behaviour), or exclude this document type from the fallback?
- **D6. Answerability changes.** Which of A-F to pursue, knowing that a fix must stay within the 9-character prompt headroom and keep the prompt hashes pinned.
- **D7. Metadata values.** Supply the owner and approval reference. Confirm the dates inferred from the filenames. Confirm the Aloe First product number (#040 on the sheet; the guide says 040R1).
- **D8. Execution.** Approve steps 1-4 explicitly, separately from D1-D7.
