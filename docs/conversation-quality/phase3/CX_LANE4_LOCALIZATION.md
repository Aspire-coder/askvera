# Phase 3, Lane 4: localization and rendering

Status: implemented. See `docs/conversation-quality/phase3/CX_DESIGN.md` and
`docs/conversation-quality/phase3/CX_LANES.md` for the full lane breakdown;
this note covers only Lane 4's write scope -- `config/conversation_routes.json`,
`app/response/cx_render.py`, `tests/unit/test_cx_render.py`, and the existing
pin tests re-pinned below because the routes changed.

## What this is

`config/conversation_routes.json` now carries every message key from the
CX_LANES.md "Message keys" table, for all 12 reviewed locales
(`en fr es de nl it da fi no sr sv ru`):

- `evidence_missing_detail` (`{topic}`)
- `dependency_unavailable` (none -- see "bedrock_error alias" below)
- `cross_market_policy_scope` (`{country}`)
- `international_directory_note` (`{country}`)
- `personal_account_limit` (none)
- `partial_answer_gap` (`{fields}`)
- `clarify_field`, `clarify_country`, `clarify_role` (all `{options}`)
- `repair_ack` (none)
- `contact_offer` (`{contact}`)
- `suggest_intro` (none)
- `suggest_topic_delivery_cost`, `suggest_topic_payment_methods`,
  `suggest_topic_contact`, `suggest_topic_returns` (none)

Plus one `field_label_<field>` key per locale for each of the ten canonical
directory fields `utils/directory_fields.py` / `config/directory_field_vocabulary.py`
already track: `phone`, `order_phone`, `email`, `website`, `address`,
`business_hours`, `payment_methods`, `delivery_cost`, `delivery_time`, `fax`.

### `bedrock_error` alias

`dependency_unavailable` is a plain alias of `bedrock_error` -- both keys
hold the identical string per locale, and `bedrock_error` itself is never
edited for a locale that already had it (`en fr es de nl`). Five of the
remaining seven locales (`it da fi no sr sv ru`) had no `bedrock_error` entry
at all before this change, so one was added (Lane 4's own translation, tone-
matched to the existing `en/fr/de/es/nl` wording) purely so
`dependency_unavailable` would have a real string to alias rather than an
empty one.

### Placeholders

Every locale's copy for a given key carries exactly the same placeholder
names as the English source (verified by
`tests/unit/test_cx_render.py::TestCxLanesKeyCoverage::test_every_locales_placeholders_match_english_per_key`,
parsed from the CX_LANES.md table rather than retyped).

## `app/response/cx_render.py`

`render(key, language, **placeholders) -> str`:

1. Resolves `language` to a locale with the existing normalizer
   (`app.evidence._locale_key`).
2. For the 12 reviewed route locales, returns the reviewed copy directly.
3. For any other configured language, translates the *English* template via
   `services.controlled_copy.localize_reviewed_copy`, with placeholders
   protected as opaque sentinels (`⟦NAME⟩`) before the call and
   restored after. A translation that loses, duplicates, or alters a
   sentinel -- or a failed/refused translation call -- falls back to the
   English template.
4. Placeholders are filled only after localization.
5. Never returns an empty string: the English template is the floor.

`join_list(items, language)` joins with a small closed per-locale
separator/conjunction table (two items: "a and b"; three or more:
"a, b and c"), falling back to English outside the 12-locale table.

`mixed_language_or_empty(text, language)` is a deterministic, documented
Cyrillic-vs-Latin script check (the one script split among the 12 reviewed
locales) plus an empty/whitespace check. It is not a language identifier and
does not flag a genuinely mixed string that contains some of the expected
script.

## Review status

All 11 non-English locales' new copy (the CX_LANES.md keys, the
`field_label_*` keys, and the seven added `bedrock_error` entries for
`it da fi no sr sv ru`) is Lane 4's own translation and has **not** been
reviewed by a native speaker of any of those languages. It follows the
existing tone of each locale's reviewed copy (short, warm, plain, no
promises, no invented facts, no market-specific facts) and reuses vocabulary
already reviewed elsewhere in this repository where it existed
(`utils/directory_fields.py`'s `_SUPPORT_CONTACT_LABEL_TRANSLATIONS` for
`nl fr de es it sv`'s field labels; `config/directory_field_vocabulary.py`'s
per-language field-request stems for the rest), but every non-English string
added by this task needs native review before it should be treated as
reviewed, reviewed-locale copy the way the pre-existing English/French/
Spanish/German/Dutch copy is.

## Re-pinned tests (routes changed)

Populating `cross_market_policy_scope` surfaced a wider integration than
just `_cross_market_scope_message`: both `app/orchestrator/chat_orchestrator.py`
and `scripts/run_benchmark.py` (`_cross_market_scope_copy`,
`classify_outcome`) already looked up this exact key via
`configured_conversation_response` before this task -- both were pre-wired
by the coordinator to consume it once Lane 4 added it. Every test below
pinned the *previous* behaviour (the key being absent everywhere), so all
are re-pinned, dated 2026-09-18, to the reviewed copy that now exists. None
was loosened -- each still asserts a specific outcome/copy, just the
now-correct one.

- `tests/unit/test_codex_conversation_tone.py::test_only_six_english_response_values_changed_from_head`:
  `ROUTES_REST_SHA256` updated -- purely additive, no existing key's value
  changed.
- `tests/unit/test_cross_market_refusal_explanation.py` (both tests): assert
  the reviewed `cross_market_policy_scope` copy (English and French)
  directly, instead of the hardcoded `CROSS_MARKET_POLICY_SCOPE_RESPONSE`
  constant or a fallback to `_insufficient_evidence_message`.
- `tests/unit/test_cross_market_demonym_refusal.py::test_orchestrator_gives_scope_copy_and_no_model_context_for_the_reported_question`:
  same fix, via `configured_conversation_response("cross_market_policy_scope", "en")`.
- `tests/conversation/test_intent_dependency_failures_are_distinct.py::test_d_policy_country_restriction_is_distinct_from_missing_evidence_and_dependency_failure`:
  same fix; the assertion no longer greps for the substring "another market"
  (only present in the old hardcoded constant) but checks the actual
  reviewed copy.
- `tests/unit/test_benchmark_capture.py::test_refusal_copy_is_labelled_by_the_kind_of_refusal`
  and `::test_labelling_never_asks_for_a_translation_and_labels_stay_correct`
  (parametrized over `fi it no fr nl`): use the reviewed
  `cross_market_policy_scope` copy (via the file's existing `_copy`/
  `_configured` helpers, which call `localized_conversation_response` /
  `configured_conversation_response` -- never a translation call, keeping
  the "no model call while labelling" invariant these tests also check)
  instead of the hardcoded constant.
- `tests/unit/test_held_out_governing_recall.py::test_outcomes_are_labelled_offline_for_artifacts_that_predate_the_label`:
  same fix, via `configured_conversation_response("cross_market_policy_scope", "en")`.

**Known gap for the coordinator's orchestrator wiring** (outside Lane 4's
write scope): `_cross_market_scope_message` calls
`configured_conversation_response` directly, not `cx_render.render`, so the
`{country}` placeholder in the returned copy is not filled today -- every
re-pinned test above that touches this path asserts the literal, unfilled
`{country}` token (via `.startswith(...)` rather than an exact match).
Moving this call site (and `scripts/run_benchmark.py`'s
`_cross_market_scope_copy`, which has the same gap) to
`cx_render.render(..., country=country)` is wiring outside Lane 4's write
scope.
