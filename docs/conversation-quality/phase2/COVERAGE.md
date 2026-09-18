# Phase 2, Lane G: coverage report

Author: Lane G (test and measurement integrity). Base commit `583b39a`,
worktree `askvera-p2-g-test-integrity`, branch `p2/g-test-integrity-20260918`.

This report is deliberately strict: a test whose outcome is decided by a
fixture, a scripted fake model, or its own premise check is marked **mocked
only** or **prompt-structure only**, never "real proof", even if it currently
passes. See `docs/conversation-quality/TASK_BOARD.md` for the acceptance
criteria text and `tests/conversation_pack/README.md` for the pack's own
label definitions, which this report reuses.

Categories used below:

- **Real behavioural proof** - drives the actual orchestrator/validator/
  governance code path with a fake retriever/router standing in only for the
  live model and AWS calls (no live model or network anywhere), and the
  assertion is decided by that real code, not by the fixture or the fake's
  scripted return value.
- **Mocked/scripted only** - the fake router's scripted text (not a real
  layer) decides the assertion, or the mechanism only checks that the fake's
  input reached a stub correctly.
- **Prompt-structure only** - proves instruction text exists and stays
  inside budget; proves nothing about what a live model would do with it.
- **Nothing** - no offline mechanism exists; the criterion needs a live run
  and none was made.

## A1-A8 (Lane A: follow-up state)

| ID | Real behavioural proof | Mocked/scripted only | Prompt-structure only | Nothing |
|---|---|---|---|---|
| A1 | `tests/conversation/test_followup_state_e2e.py::test_a1_kenya_field_follow_up_never_reaches_retrieval_with_stale_history_numbers` (query never carries stale digits - real query builder); `test_a1_office_or_order_phone_follow_up_keeps_kenya_and_uses_the_fresh_record` (rewritten Phase 2, Lane G: scripts the fake model to echo the STALE number and runs the real validator/response pipeline (`validator=None`); asserts on `response.metadata["numeric_claim_repair"]`, `removed_numeric_claims` and `directory_contacts_restored`, not just the answer string - the real `numeric_grounding_validator` and directory-contact-restoration mechanism decide the outcome, not the script); `tests/conversation_pack/test_conversation_pack.py::CONTACT-KENYA-001` (field_preservation_chain, real `_secure_and_complete_response`) | - | - | Whether a live model would ever produce the stale number in the first place (rather than this test's deliberately-scripted probe of it) is unverified |
| A2 | `test_a2_office_hours_follow_up_keeps_kenya_context` (real query-layer retrieval targeting); `tests/conversation_pack`'s `CONTACT-KENYA-002` (retrieval_query_inherit, real `_build_retrieval_query`) | The delivered `"09.00 am"` text comes from the fake router's scripted string | - | - |
| A3 | `test_a3_explicit_uganda_follow_up_does_not_inherit_kenya` (real query targeting: Uganda in, Kenya out); `COUNTRY-CHANGE-001` (real query builder) | Delivered phone digits come from the fake router | - | - |
| A4 | `test_a4_fresh_session_id_gets_no_facts_or_state_from_a_prior_session` (real `services.session` memory store, not stubbed); `test_a4_two_sessions_never_share_cache_identity`; `ISOLATION-001`/`ISOLATION-002` (real `AIOrchestrator.handle_chat`, real cache-key builder) | - | - | - |
| A5 | `test_a5_topic_change_drops_the_kenya_directory_context`; `TOPIC-CHANGE-001` | - | - | - |
| A6 | `test_a6_language_switch_keeps_topic_and_switches_deterministic_refusal_text` (real `governance_engine` + real `localized_conversation_response`, not a fake); `test_a6_language_switch_on_a_safe_topic_follows_the_new_language` (real query-layer target check) | - | - | Whether a live model's own prose is produced in French/Spanish is unverified; `LANGUAGE-SELECTOR-SWITCH-001` in the pack is `needs_live: true` for exactly this reason |
| A7 | - | - | - | Strict `xfail` (`test_a7_the_other_one_after_two_named_markets_does_not_silently_answer_for_one`) - confirmed open defect, not proof of anything fixed; Codex request filed |
| A8 | `test_a8_fabricated_prior_policy_claim_is_not_repeated_as_trusted_fact` - uses the REAL `OutputValidator`/`ResponseBuilder` (`validator=None`), asserts real `HISTORY_SOURCED_CLAIM_UNGROUNDED` + `NUMERIC_CLAIM_UNGROUNDED` issue codes fired | - | - | - |

## B1-B6, E1 (Lane B: composition)

| ID | Real behavioural proof | Mocked/scripted only | Prompt-structure only | Nothing |
|---|---|---|---|---|
| B1 | - | - | `test_composition_prompt_structure.py::test_composition_rule_is_present["mandatory qualifications, amounts, periods"]`, `["routes concretely, even when simplifying"]` | Whether a live model actually states concrete qualifications is unverified |
| B2 | `test_composition_numeric_role_binding.py::test_two_roles_each_keep_their_own_supported_figure` (real `numeric_grounding_validator`, both FBO and Preferred Customer figures survive); `tests/unit/test_supported_figure_role_binding.py` (real validator, role-binding edge cases) | - | `test_composition_rule_is_present["tier, role, section, product or country"]` | Live prose distinguishing the two roles is unverified |
| B3 | `MULTIPART-001` (`tests/conversation_pack`, field_preservation_chain against real `_secure_and_complete_response`); `tests/conversation/test_order_size_field_keeping.py` (real `remove_unrequested_directory_fields`, not owned by Lane G) | - | `test_composition_rule_is_present["naming any the evidence does not establish"]` | Whether a live model composes both parts of a two-part question in the first place is unverified. Multilingual field detection (`_requested_directory_field_set`) is English-only per HANDOFF.md - a French two-part question is not covered by any test |
| B4 | - | - | - | No deterministic reproduction found (TASK_BOARD.md); dropped for budget. Nothing offline or live exists |
| B5 | `test_composition_numeric_role_binding.py::test_sentence_initial_word_before_plural_role_acronym_does_not_orphan_figure`, `test_bare_role_acronym_still_binds_as_before` (real validator, repro-before/fixed-after); `tests/unit/test_supported_figure_role_binding.py`, `test_supported_figure_preservation_c.py` (real validator) | - | `test_composition_rule_is_present["tier, role, section, product or country"]` | - |
| B6 | Decimal-time remnant fix only, covered by `tests/unit/test_numeric_grounding_repair_corrections.py`/`test_numeric_grounding_repair_defects.py` (not Lane G's; referenced, not verified here) | - | - | No general audit of post-validator remnants was done (TASK_BOARD.md); most remnant classes are unchecked |
| E1 | - | - | `test_composition_rule_is_present["Lead with the direct answer"]`, `["no stock openers, generic disclaimers or sign-off questions"]`; `test_prompt_stays_inside_the_existing_budget`; `test_prompt_version_moved_with_the_prompt` | Whether a live answer is actually direct/concise is unverified |

## C1-C5, D1, F1 (Lane C: intent, contacts, recovery)

| ID | Real behavioural proof | Mocked/scripted only | Prompt-structure only | Nothing |
|---|---|---|---|---|
| C1 | `test_intent_company_identity_and_purchasing.py::test_income_intent_verification_downgrades_false_positive_without_a_model_call` (real `_verified_conversation_intent`, a double that raises if the model is ever called - proves the bypass fires without needing a live model); `test_governance_allows_these_questions_outright` (real `governance_engine`); `US-POLICY-001/002` in the pack (real `approve_evidence`) | - | - | Whether the model itself withholds the unrelated income disclaimer in its own prose is unverified; both cases are `needs_live: true` for exactly this |
| C2 | `test_real_income_guarantee_about_products_still_refuses`, `test_real_medical_claim_about_a_returned_product_still_flagged` (negative controls, real policy/governance code); `GUARDRAIL-MISFIRE-001/002/003` (real `governance_engine.evaluate`) | - | - | Live generation-side misfire (the model volunteering a disclaimer anyway) is unverified; all three pack cases are `needs_live: true` |
| C3 | - | - | - | Diagnosis only (`laneC-c3-c4-diagnosis.md`); no clear workbook case; nothing offline or live done here |
| C4 | - | - | - | Diagnosis only; points to retrieval/evidence approval (Codex-owned); several cited cases were already fixed before this project |
| C5 | `test_intent_dependency_failures_are_distinct.py` (a-f, real `AIOrchestrator.handle_chat`, real failure-layer wiring for Bedrock timeout, embedding-service `AwsServiceError`, missing-evidence, low-confidence, policy-country restriction, off-topic - all distinct wording, asserted against the real response, not a script); `test_configuration_error_is_not_disguised_as_a_transient_hiccup` (negative control) | - | - | A real OpenSearch outage is still swallowed by the provider and reported as missing evidence - open, Codex request filed. Nothing here (or anywhere in this project) proves that half |
| D1 | `test_contacts_type_and_country_fidelity.py` - all 6 tests (real `build_support_contact_supplement`, `contact_for_country`, `remove_or_replace_contact_placeholders`, with negative controls for order/office mix-up and cross-country number borrowing); `CONTACT-KENYA-001`/`CONTACT-KENYA-002` in the pack | - | - | - |
| F1 | Dependency-failure half: same tests as C5. Unnamed-"they" handoff: `test_composition_rule_is_present["Name who to contact."]` (prompt-structure only) | - | `test_composition_rule_is_present["Name who to contact."]` | Empty-answer and central-claim-rejection routing "already routed to fallback (not re-audited)" per TASK_BOARD.md - no test found or added for those two paths specifically |

## G1 (Lane G: regression pack) and Phase 2 Lane G goals

| Sub-area | Status |
|---|---|
| 27 cases, all 14 required categories | Real: `tests/conversation_pack/test_conversation_pack.py::test_every_required_category_is_covered`, `test_every_case_has_required_manifest_fields` (structural, but genuinely checks the manifest, not a fixture) |
| Evidence-gate / query-inherit / field-preservation / governance / isolation mechanisms | Real behavioural proof - each drives the real function (`approve_evidence`, `_build_retrieval_query`, `_secure_and_complete_response`, `governance_engine.evaluate`, `AIOrchestrator.handle_chat`) |
| `absent_fact_check` / `role_bound_fact_absent` (`UNKNOWN-001/002`) | Premise-only: proves the fixture omits the fact, always passes regardless of what AskVera would answer. Reported as `pytest.skip`, not a pass, since the Fable review (see `tests/conversation_pack/README.md`) - confirmed still correct in this Phase 2 pass |
| `needs_live_only` (`TYPO-001/002`) | Nothing offline; explicitly skipped, not faked |

## Phase 2 lane acceptance criteria (A-G, from TASK_BOARD.md's Phase 2 table)

Only Lane G's own goals are gradeable here; the other six lanes are `active`
in a different worktree and outside this report's visibility.

| Lane | Goal | This report's finding |
|---|---|---|
| G-1: collection | `pytest.ini`/`Makefile` now include `tests/unit tests/governance tests/conversation tests/conversation_pack` by default; `tests/integration` stays opt-in (self-gates on `INTEGRATION_TEST=true`) | Done. `tests/unit/test_collection_integrity.py` (new) runs a real `pytest --collect-only` subprocess and fails if any of the four directories drops out of the default surface, and fails if `tests/integration` is pulled in. Collection counts before/after in the handoff below |
| G-2: vacuous tests | Reviewed every test in the six Lane-G-writable Phase 1 files plus `tests/conversation_pack/**` | The two previously-known vacuous mechanisms (`absent_fact_check`, `role_bound_fact_absent`) were already converted to premise-checked skips before this phase (Fable review, 2026-09-18) and remain so - re-verified, not re-fixed. The one remaining known-vacuous assertion, `test_a1_office_or_order_phone_follow_up_keeps_kenya_and_uses_the_fresh_record` (`test_followup_state_e2e.py`), was rewritten: empirically probed (not assumed) by scripting the fake model to echo the STALE number and running the real `OutputValidator`/`ResponseBuilder` pipeline (`validator=None` instead of the file's usual no-op stub). Confirmed a real mechanism does the work - `numeric_grounding_validator` strips the unsupported stale figure and a directory-contact-restoration step supplies the correct, freshly-retrieved one - and the test now asserts on `response.metadata["numeric_claim_repair"]`, `removed_numeric_claims` and `directory_contacts_restored`, which only the real pipeline can produce, not on answer text a script could have supplied either way |
| G-3: labels | Every module under `tests/conversation` and `tests/conversation_pack` states one of the five required labels | Done for all Lane-G-writable files (added the missing label to `test_contacts_type_and_country_fidelity.py`). New `tests/conversation_pack/test_module_docstring_labels.py` enforces this dynamically (globs current files, not a hardcoded list) for both directories; one file outside Lane G's write scope (`tests/conversation/test_intent_multipart_order_size_payment.py`, Lane B's Phase 2 target) still lacks a label and is listed by name in that test's `_KNOWN_GAPS` with a reason, so it is skipped rather than silently ignored, and the check will start failing again the moment that file gains a label unless the entry is removed |
| G-4: this report | `docs/conversation-quality/phase2/COVERAGE.md` | This file |

## Limitations of this report

- It covers only Lane A/B/C/G's Phase 1 output as it exists in this
  worktree at base commit `583b39a`. Phase 2 work by Lanes A-F is in
  separate worktrees and not visible here.
- "Real behavioural proof" still means offline: a fake retriever/router
  stands in for the live model and AWS everywhere. No claim here is a claim
  about production behaviour.
- The known-gap file (`test_intent_multipart_order_size_payment.py`) is
  Lane B's to label; this report only records the gap, not a fix.
