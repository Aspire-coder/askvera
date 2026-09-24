# AskVera CX copy review pack

AskVera's fallback, clarification and CX (conversation-experience) copy
is translated into 12 route languages but had never been checked by a
native speaker of each language. This pack is one CSV per non-English
language, sized so a reviewer can work through the whole language in
about an hour.

## Sources

- `config/conversation_routes.json` -> `locales.<lang>.responses` --
  the message-key table `app/response/cx_render.py::render()` reads at
  runtime. Only `responses` is reviewed here; `patterns` and
  `scope_terms` are inbound-message matching phrases, not text shown
  to a customer.
- `config/claim_safety.json` -> `responses` -- the regulated
  "a Forever Living product treats/cures a disease" refusal, read by
  `services/claim_safety.py`. It has no key of its own in that file,
  so this pack labels its row `product_disease_claim_refusal`.
- `config/public_contacts.json` is contact data (phone numbers,
  addresses, hours), included in the task brief as reference only --
  it is not language copy and is not part of this review pack.

## How to fill in a row

Each row is one piece of copy in one language. Compare `english` and
`translation` and fill in the three reviewer columns:

- **reviewer_verdict**: `OK` (translation is correct and natural),
  `FIX` (translation is wrong, unnatural, or has a problem you can
  describe), or `UNSURE` (you are not confident either way -- leave a
  comment explaining why).
- **reviewer_suggested_text**: your corrected text, only when the
  verdict is `FIX`. Leave blank for `OK` or `UNSURE`.
- **reviewer_comment**: free text -- why you flagged it, or any other
  note. Optional for `OK`.

**A row with an empty `translation` is a missing key, not a blank
one to skip.** Its `runtime_when_missing` column says what a customer
gets today instead (see "Missing strings: what customers see today"
below for the full picture). These rows still need your work: read
`english`, write a proper translation into
`reviewer_suggested_text`, and leave `reviewer_verdict` as `FIX` --
there is no existing translation to mark `OK`, and `UNSURE` should
only be used if you cannot produce a translation yourself (e.g. a
term you are not confident about) and need to say why in
`reviewer_comment`.

Guidance while reviewing:

- **Keep every `{placeholder}` exactly as written**, including the
  braces and the name inside them (e.g. `{topic}`, `{country}`,
  `{fields}`, `{options}`, `{contact}`). These are filled in by code
  after translation -- renaming, dropping, or translating the name
  inside the braces breaks the message at render time. The
  `placeholders_english` / `placeholders_translation` /
  `placeholder_mismatch` columns are this script's own mechanical
  check of that; a `yes` there is always worth a look even before you
  read the sentence.
- **Register and tone**: plain, friendly, second person -- match the
  English original's register, not a more formal or more casual one.
- **Legal and compliance strings** (the medical and income claim
  refusals, the FDA disclaimer, `product_disease_claim_refusal`, and
  similar) **must keep their exact meaning**. Do not mark a faithful
  but blunt or awkward-sounding legal translation as `FIX` just to
  make it read more smoothly -- if the meaning is intact, that's
  `OK`. Flag it instead if the translation softens, drops, or adds a
  claim the English does not make (e.g. implying a product does
  treat something, or dropping the referral to a healthcare
  professional).

## How to regenerate this pack

Run from the repository root:

```
py -3 scripts/build_copy_review_pack.py
```

The script reads `config/conversation_routes.json` and
`config/claim_safety.json` (never writes to either) and rewrites every
file in this directory. It is deterministic: given the same inputs, two
runs produce byte-identical output. Any in-progress reviewer columns
(`reviewer_verdict`, `reviewer_suggested_text`, `reviewer_comment`) are
**not preserved** across a regenerate -- copy them out first if a
review is partway done and the underlying copy has changed.

## String counts

| Language | Code | Strings reviewable | Missing keys |
| --- | --- | --- | --- |
| English (source) | `en` | 45 | - |
| French | `fr` | 39 | 6 |
| Spanish | `es` | 39 | 6 |
| German | `de` | 39 | 6 |
| Dutch | `nl` | 39 | 6 |
| Italian | `it` | 37 | 8 |
| Danish | `da` | 36 | 9 |
| Finnish | `fi` | 37 | 8 |
| Norwegian | `no` | 37 | 8 |
| Serbian | `sr` | 36 | 9 |
| Swedish | `sv` | 37 | 8 |
| Russian | `ru` | 36 | 9 |

## Runtime path per key

Every one of the 45 keys, classified by which runtime function(s)
actually render it in production (see this script's module
docstring for the full trace and the missing-key behaviour each
path implies). A blank note means the classification alone is not
misleading about which code renders it.

| Key | Path | Note |
| --- | --- | --- |
| `catalogue_scope` | `conversation_route` |  |
| `wellbeing` | `both` | assistant_meta_response() (early exact-phrase route) and localized_conversation_response() (later planner-routed route) are both real call sites. |
| `greeting` | `both` | assistant_meta_response() (early exact-phrase route) and localized_conversation_response() (later planner-routed route) are both real call sites. |
| `thanks` | `both` | assistant_meta_response() (early exact-phrase route) and localized_conversation_response() (later planner-routed route) are both real call sites. |
| `farewell` | `cx_render` | app/evidence.py::assistant_meta_response() only -- never reachable via localized_conversation_response(). |
| `capability` | `both` | assistant_meta_response() (early exact-phrase route) and localized_conversation_response() (later planner-routed route) are both real call sites. |
| `casual` | `both` | assistant_meta_response() (early exact-phrase route) and localized_conversation_response() (later planner-routed route) are both real call sites. |
| `period_not_covered` | `conversation_route` |  |
| `country_typo_confirmation` | `conversation_route` |  |
| `insufficient_evidence` | `both` | cx_compose.py's render("insufficient_evidence", ...) and chat_orchestrator.py's localized_conversation_response("insufficient_evidence", ...) are both real call sites. |
| `office_contact_lead_in` | `conversation_route` |  |
| `off_topic` | `conversation_route` |  |
| `medical_claim` | `conversation_route` |  |
| `income_claim` | `conversation_route` |  |
| `bedrock_error` | `conversation_route` |  |
| `sensitive_pii` | `conversation_route` |  |
| `guardrail_blocked` | `conversation_route` |  |
| `reference_clarification` | `conversation_route` |  |
| `dependency_unavailable` | `unreferenced` | Never passed as a key anywhere; a dependency_unavailable failure is actually rendered with the bedrock_error copy instead. |
| `evidence_missing_detail` | `cx_render` |  |
| `cross_market_policy_scope` | `cx_render` |  |
| `international_directory_note` | `cx_render` |  |
| `personal_account_limit` | `cx_render` |  |
| `partial_answer_gap` | `cx_render` |  |
| `clarify_field` | `cx_render` |  |
| `clarify_country` | `unreferenced` | conversation_repair.py documents this key but never constructs a Clarification with it. |
| `clarify_role` | `unreferenced` | conversation_repair.py documents this key but never constructs a Clarification with it. |
| `repair_ack` | `unreferenced` | conversation_repair.py documents this key but never constructs a Clarification with it. |
| `contact_offer` | `cx_render` |  |
| `suggest_intro` | `unreferenced` | Present in conversation_routes.json but never passed to render() -- suggestions are delivered as structured items, not this intro sentence. |
| `suggest_topic_delivery_cost` | `cx_render` |  |
| `suggest_topic_payment_methods` | `cx_render` |  |
| `suggest_topic_contact` | `cx_render` |  |
| `suggest_topic_returns` | `cx_render` |  |
| `field_label_phone` | `cx_render` |  |
| `field_label_order_phone` | `cx_render` |  |
| `field_label_email` | `cx_render` |  |
| `field_label_website` | `cx_render` |  |
| `field_label_address` | `cx_render` |  |
| `field_label_business_hours` | `cx_render` |  |
| `field_label_payment_methods` | `cx_render` |  |
| `field_label_delivery_cost` | `cx_render` |  |
| `field_label_delivery_time` | `cx_render` |  |
| `field_label_fax` | `cx_render` |  |
| `product_disease_claim_refusal` | `cx_render` | services/claim_safety.py::localized_claim_response(), not render() or localized_conversation_response() -- same English-floor shape as render(), and all 12 locales are populated today so this key has no missing-key rows. |

## Missing strings: what customers see today

For every key that is missing in at least one language, this is what
a customer in that language is actually shown right now -- traced from
the runtime code, not a guess (see this script's module docstring,
"RUNTIME BEHAVIOUR WHEN A KEY IS MISSING", for the full trace).

**`guardrail_blocked` and `sensitive_pii` are safety messages** -- a
missing translation for either one means a customer who triggered a
safety guardrail, or whose message contained something that looked
like sensitive personal information, is currently shown an
unreviewed, machine-translated safety notice (both are classified `conversation_route` -> `machine_translated_at_request_time` below),
rather than reviewed copy.

| Key | Path | What the customer gets | Languages missing it |
| --- | --- | --- | --- |
| `catalogue_scope` | `conversation_route` | An UNREVIEWED machine translation of the English text is generated by a live Bedrock call at request time, once per turn, and shown immediately -- no human ever reviews it. `app/evidence.py::localized_conversation_response()` -> `services/controlled_copy.py::localize_reviewed_copy()`. | `fr`, `es`, `de`, `nl`, `it`, `da`, `fi`, `no`, `sr`, `sv`, `ru` |
| `farewell` | `cx_render` | The reviewed ENGLISH template is shown as-is (no translation call). `app/response/cx_render.py::render()` (or, for `farewell` and `product_disease_claim_refusal`, an equivalent English-floor function -- see this script's module docstring). | `fr`, `es`, `de`, `nl`, `it`, `da`, `fi`, `no`, `sr`, `sv`, `ru` |
| `casual` | `both` | Depends which code path handles the turn: the reviewed ENGLISH template (`assistant_meta_response()`, the early exact-phrase route) on some turns, or an UNREVIEWED machine translation generated at request time (`localized_conversation_response()`, the later planner-routed route) on others. | `fr`, `es`, `de`, `nl`, `it`, `da`, `fi`, `no`, `sr`, `sv`, `ru` |
| `period_not_covered` | `conversation_route` | An UNREVIEWED machine translation of the English text is generated by a live Bedrock call at request time, once per turn, and shown immediately -- no human ever reviews it. `app/evidence.py::localized_conversation_response()` -> `services/controlled_copy.py::localize_reviewed_copy()`. | `fr`, `es`, `de`, `nl`, `it`, `da`, `fi`, `no`, `sr`, `sv`, `ru` |
| `country_typo_confirmation` | `conversation_route` | An UNREVIEWED machine translation of the English text is generated by a live Bedrock call at request time, once per turn, and shown immediately -- no human ever reviews it. `app/evidence.py::localized_conversation_response()` -> `services/controlled_copy.py::localize_reviewed_copy()`. | `fr`, `es`, `de`, `nl`, `it`, `da`, `fi`, `no`, `sr`, `sv`, `ru` |
| `office_contact_lead_in` | `conversation_route` | An UNREVIEWED machine translation of the English text is generated by a live Bedrock call at request time, once per turn, and shown immediately -- no human ever reviews it. `app/evidence.py::localized_conversation_response()` -> `services/controlled_copy.py::localize_reviewed_copy()`. | `fr`, `es`, `de`, `nl`, `it`, `da`, `fi`, `no`, `sr`, `sv`, `ru` |
| **`sensitive_pii`** (safety) | `conversation_route` | An UNREVIEWED machine translation of the English text is generated by a live Bedrock call at request time, once per turn, and shown immediately -- no human ever reviews it. `app/evidence.py::localized_conversation_response()` -> `services/controlled_copy.py::localize_reviewed_copy()`. | `it`, `da`, `fi`, `no`, `sr`, `sv`, `ru` |
| **`guardrail_blocked`** (safety) | `conversation_route` | An UNREVIEWED machine translation of the English text is generated by a live Bedrock call at request time, once per turn, and shown immediately -- no human ever reviews it. `app/evidence.py::localized_conversation_response()` -> `services/controlled_copy.py::localize_reviewed_copy()`. | `it`, `da`, `fi`, `no`, `sr`, `sv`, `ru` |
| `reference_clarification` | `conversation_route` | An UNREVIEWED machine translation of the English text is generated by a live Bedrock call at request time, once per turn, and shown immediately -- no human ever reviews it. `app/evidence.py::localized_conversation_response()` -> `services/controlled_copy.py::localize_reviewed_copy()`. | `da`, `sr`, `ru` |

## Mechanical findings

The script itself checks the things below without judging the
language -- these are not translation-quality judgements, only
structural facts about the current copy. A reviewer should treat every
listed key as a `FIX` (or at least an `UNSURE`) candidate for that
language's CSV row, since the row's translation is unreliable in one
of these mechanical ways (or, for a missing key, not reviewable at all).

### French (`fr`)

- Missing keys (present in English, absent here) (6): `catalogue_scope`, `farewell`, `casual`, `period_not_covered`, `country_typo_confirmation`, `office_contact_lead_in`
- Placeholder mismatches: none
- Identical to English (possibly untranslated) (1): `field_label_fax`
- Empty strings: none
- Length ratio outside 0.5-2.0x (2): `greeting`, `thanks`

### Spanish (`es`)

- Missing keys (present in English, absent here) (6): `catalogue_scope`, `farewell`, `casual`, `period_not_covered`, `country_typo_confirmation`, `office_contact_lead_in`
- Placeholder mismatches: none
- Identical to English (possibly untranslated) (1): `field_label_fax`
- Empty strings: none
- Length ratio outside 0.5-2.0x (3): `greeting`, `thanks`, `field_label_email`

### German (`de`)

- Missing keys (present in English, absent here) (6): `catalogue_scope`, `farewell`, `casual`, `period_not_covered`, `country_typo_confirmation`, `office_contact_lead_in`
- Placeholder mismatches: none
- Identical to English (possibly untranslated) (2): `field_label_website`, `field_label_fax`
- Empty strings: none
- Length ratio outside 0.5-2.0x (2): `greeting`, `thanks`

### Dutch (`nl`)

- Missing keys (present in English, absent here) (6): `catalogue_scope`, `farewell`, `casual`, `period_not_covered`, `country_typo_confirmation`, `office_contact_lead_in`
- Placeholder mismatches: none
- Identical to English (possibly untranslated) (2): `field_label_website`, `field_label_fax`
- Empty strings: none
- Length ratio outside 0.5-2.0x (2): `greeting`, `thanks`

### Italian (`it`)

- Missing keys (present in English, absent here) (8): `catalogue_scope`, `farewell`, `casual`, `period_not_covered`, `country_typo_confirmation`, `office_contact_lead_in`, `sensitive_pii`, `guardrail_blocked`
- Placeholder mismatches: none
- Identical to English (possibly untranslated) (1): `field_label_fax`
- Empty strings: none
- Length ratio outside 0.5-2.0x (2): `greeting`, `thanks`

### Danish (`da`)

- Missing keys (present in English, absent here) (9): `catalogue_scope`, `farewell`, `casual`, `period_not_covered`, `country_typo_confirmation`, `office_contact_lead_in`, `sensitive_pii`, `guardrail_blocked`, `reference_clarification`
- Placeholder mismatches: none
- Identical to English (possibly untranslated) (1): `field_label_fax`
- Empty strings: none
- Length ratio outside 0.5-2.0x (2): `greeting`, `thanks`

### Finnish (`fi`)

- Missing keys (present in English, absent here) (8): `catalogue_scope`, `farewell`, `casual`, `period_not_covered`, `country_typo_confirmation`, `office_contact_lead_in`, `sensitive_pii`, `guardrail_blocked`
- Placeholder mismatches: none
- Identical to English (possibly untranslated): none
- Empty strings: none
- Length ratio outside 0.5-2.0x (2): `greeting`, `thanks`

### Norwegian (`no`)

- Missing keys (present in English, absent here) (8): `catalogue_scope`, `farewell`, `casual`, `period_not_covered`, `country_typo_confirmation`, `office_contact_lead_in`, `sensitive_pii`, `guardrail_blocked`
- Placeholder mismatches: none
- Identical to English (possibly untranslated): none
- Empty strings: none
- Length ratio outside 0.5-2.0x (2): `greeting`, `thanks`

### Serbian (`sr`)

- Missing keys (present in English, absent here) (9): `catalogue_scope`, `farewell`, `casual`, `period_not_covered`, `country_typo_confirmation`, `office_contact_lead_in`, `sensitive_pii`, `guardrail_blocked`, `reference_clarification`
- Placeholder mismatches: none
- Identical to English (possibly untranslated): none
- Empty strings: none
- Length ratio outside 0.5-2.0x (2): `greeting`, `thanks`

### Swedish (`sv`)

- Missing keys (present in English, absent here) (8): `catalogue_scope`, `farewell`, `casual`, `period_not_covered`, `country_typo_confirmation`, `office_contact_lead_in`, `sensitive_pii`, `guardrail_blocked`
- Placeholder mismatches: none
- Identical to English (possibly untranslated) (1): `field_label_fax`
- Empty strings: none
- Length ratio outside 0.5-2.0x (2): `greeting`, `thanks`

### Russian (`ru`)

- Missing keys (present in English, absent here) (9): `catalogue_scope`, `farewell`, `casual`, `period_not_covered`, `country_typo_confirmation`, `office_contact_lead_in`, `sensitive_pii`, `guardrail_blocked`, `reference_clarification`
- Placeholder mismatches: none
- Identical to English (possibly untranslated): none
- Empty strings: none
- Length ratio outside 0.5-2.0x (3): `greeting`, `thanks`, `field_label_email`
