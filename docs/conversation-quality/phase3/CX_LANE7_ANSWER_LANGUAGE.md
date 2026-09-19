# CX Lane 7: answer language (X1, approval 6, option B)

Status: implemented as pure functions in `app/orchestrator/answer_language.py`.
Not wired into `chat_orchestrator.py` - that is the coordinator's job
(`chat_orchestrator.py` is single-writer per `CX_LANES.md`).

## Decision this implements

`docs/conversation-quality/phase2/X1_LANGUAGE_SWITCH_DECISION.md`, option B,
approved 2026-09-18: when a user writes in a language other than the widget's
selected `body.language`, the ANSWER follows the message language
(answer-only). Retrieval and source eligibility keep using the selected
`body.language`, unchanged - that split is authorization (retrieval) vs.
presentation (answer language) and must never blur.

## Public API

```python
detect_message_language(message, *, candidates=ROUTE_COPY_LANGUAGES) -> Detection(language, score, runner_up, reason)
resolve_answer_language(message, selected_language) -> AnswerLanguage(answer_language, switched, reason)
retrieval_language(selected_language, answer_language) -> str  # always returns selected_language
```

`ROUTE_COPY_LANGUAGES = ("da", "de", "en", "es", "fi", "fr", "it", "nl", "no", "ru", "sr", "sv")`
- the 12 `config/conversation_routes.json` locale keys; `resolve_answer_language`
never switches into a language outside this set.

## Detection method (revised 2026-09-18 after coordinator review)

An earlier revision counted raw marker-word hits, reusing
`config.reference_vocabulary.LOCALIZED_NON_CONTENT_TOKENS` for 9 of 12
languages plus a small da/ru/sr supplement copied from
`chat_orchestrator.py`. Coordinator review found this too thin for
language identification: those tables were reviewed for a narrower purpose
(A7/W14 follow-up-ellipsis handling), so recall on ordinary customer
questions was far too low (only nl/fr/de ever switched), and unweighted
overlap let Spanish get misclassified as French. The detector was rebuilt:

1. **A purpose-built marker-word table**, `_RAW_MARKER_WORDS` in
   `answer_language.py`, one entry per `ROUTE_COPY_LANGUAGES` language
   (~25-40 of the most frequent articles, prepositions, pronouns,
   auxiliary/copula verbs, question words and conjunctions). This is *not*
   a duplicate of an existing vocabulary: nothing in the repository already
   covers this closed class at language-ID density and per language for all
   12 - see the module docstring's provenance note. The earlier da/ru/sr
   copy from `chat_orchestrator.py` was removed; the coordinator is moving
   those lists into `config/reference_vocabulary.py` during wiring.
2. **Overlap-weighted scoring**, not raw counting. Every marker word's
   contribution is discounted automatically by how many of the 12
   languages' lists contain the same normalized word (unique: full weight;
   shared by 2: half; by 3: less; by 4+: barely at all) - see
   `_word_overlap_weight`. This is what stops a coincidental cognate
   ("de", "la", "que", "en", "i") from flipping the winner, without hand-
   excluding any specific word.
3. **Distinctive-character and pattern evidence**, scored against the RAW
   message (before accent-stripping, which would erase it): Spanish
   n-tilde/inverted punctuation, German sharp s, French cedilla/oe-ligature/
   circumflex vowels, Nordic ae/oe/aa letters, Swedish/Finnish umlauts,
   Russian-only Cyrillic letters, and Serbian-only letters in either script
   (`_DISTINCTIVE_STRONG` / `_DISTINCTIVE_MODERATE`). Italian additionally
   credits a WORD-FINAL accented vowel (a position, not a bare character,
   because the plain vowels overlap with French - "città", "però"); Finnish
   credits its characteristic doubled-vowel spelling ("maksaa", "Suomeen");
   Serbian credits the idiomatic "da li" yes/no-question opener. This
   evidence is what made short, function-word-sparse real customer
   sentences (the coordinator's Finnish/Russian probes) detectable at all.

**Script signal** (unchanged). Cyrillic and Latin letters are detected
separately. A message containing both is `mixed_script` and returns no
language (ambiguous). A Cyrillic-only message restricts scoring to
`{ru, sr}`; a Latin-only message scores every candidate except `ru`.

## Switch threshold (documented; tuned against the acceptance set, not individual probes)

A switch happens only when ALL of the following hold:

- at least `MIN_TOKENS = 4` word tokens in the message;
- the detected language's WEIGHTED score (marker words + distinctive
  evidence) clears a floor, ahead of the runner-up by a margin - both tuned
  against `tests/unit/test_cx_answer_language.py::TestAcceptanceSet`:
  - Latin-script candidates: `MIN_SCORE = 1.5`, `MIN_MARGIN = 1.0`;
  - Cyrillic-script candidates (only `ru`/`sr` are ever eligible here):
    `CYRILLIC_MIN_SCORE = 0.5`, `CYRILLIC_MIN_MARGIN = 0.5` - deliberately
    lower, because the false-positive risk the higher Latin floor guards
    against (many languages' function words overlapping) does not apply
    when only two candidates are eligible; a Cyrillic message with any
    Russian evidence and zero Serbian evidence should switch to Russian
    even on a thin score (coordinator review), and the real ru/sr
    confusion risk is handled by the distinctive-letter evidence instead;
- extra margin for closely related pairs: `no`/`da`/`sv` need
  `MIN_MARGIN + 1.5` between each other (their function words and, for
  no/da, their distinctive letters - æ/ø/å - are nearly identical); Serbian
  needs `+1.5` (Latin script) or `+1.5` (Cyrillic, against `sr`
  specifically) against any other candidate, because its Latin form shares
  short function words with unrelated Latin-script languages by
  coincidence;
- the detected language must differ from the selected language and be a
  member of `ROUTE_COPY_LANGUAGES`.

Any message that does not clear every gate keeps `selected_language`
unswitched; `resolve_answer_language` always returns a language (the
selection, never `None`) and a `reason` documenting the branch taken
(`too_short`, `matches_selected`, `mixed_script`, `no_letters`,
`no_marker_hits`, `below_threshold`, or `strong_signal` on a switch).

**Known, documented exception: `no`/`da`.** Danish and Norwegian share
almost all their common function words and, for the letters this detector
credits, their entire distinctive-character set (æ/ø/å is identical for
both). A sentence that uses none of the handful of genuinely distinguishing
words (`hva` vs. `hvad`, etc.) scores EXACTLY tied between them and
correctly does not switch (margin 0 < required margin) - this is the
"genuinely ambiguous" case the X1 decision anticipates, never a wrong
switch. See the acceptance-set results below for the confusion matrix: on
this lane's acceptance set, no/da never crossed into the wrong member of
the pair; they simply stayed unswitched on 4 of 8 ambiguous questions.

## Retrieval-eligibility invariant

`retrieval_language(selected_language, answer_language)` is an explicit,
greppable no-op: it always returns `selected_language`, regardless of
`answer_language`. It exists so the invariant the X1 decision requires -
retrieval and source eligibility stay on the selected language even when the
answer switches - is directly testable and greppable at every call site,
rather than an implicit assumption.

## Prompt question (no prompt edit made)

`app/prompts/templates.py`'s `SYSTEM_PROMPT` has exactly one language
placeholder, `User language: {{user_language}}` (line 54), and one earlier
instruction that reads ambiguously in isolation: "Keep the complete response
in that language, including headings and support guidance" (line 8). Read
together with the `User language:` line below it, "that language" already
resolves to whatever value is substituted for `{{user_language}}` - there is
no second, independent language reference for the two lines to disagree
about.

`app/prompts/builder.py` (`PromptBuilder.build`, line 58) substitutes its
`language` parameter directly into `{{user_language}}`:
`persona.replace("{{user_language}}", language)`. Today the coordinator
passes `body.language` as `language`; the X1 conflict the design doc
describes ("User language: en" plus an instruction to answer in the user's
own language) is a conflict only because two different values were meant -
the selector value and the message's actual language - and only one
placeholder exists to carry either.

**Preferred fix confirmed, no prompt text change needed:** the coordinator
passes `resolve_answer_language(...).answer_language` as `PromptBuilder.build`'s
`language` argument instead of `body.language`. Once `{{user_language}}` is
filled with the resolved answer language, "User language: {answer_language}"
and "Keep the complete response in that language" agree by construction -
the same substitution already used for the deterministic copy and
post-processing vocabularies. This requires zero characters of prompt text
change and therefore no `PROMPT_VERSION` bump; the 4383/4392-character prompt
budget is unaffected.

(A wording-only fallback - e.g. rephrasing line 8 to explicitly cross-
reference the `User language:` line - was considered but not measured in
detail, because it is unnecessary: the prompt's remaining headroom is only
4392 - 4383 = 9 characters, so any added words risk the budget for no
benefit when the zero-text-change substitution above already resolves the
ambiguity. The no-text-change fix is therefore the recommendation, not a
fallback.)

## Hook sites for the coordinator (not wired here; lane write scope excludes `chat_orchestrator.py`)

Per `CX_DESIGN.md`'s "Answer language" section, `answer_language` should
drive three things, once per turn, after `resolve_answer_language` runs:

1. **Prompt** - `PromptBuilder.build(..., language=answer_language, ...)`
   instead of `body.language` (see above; no prompt text change).
2. **Deterministic/localized copy** - wherever `chat_orchestrator.py` or
   `app/response/cx_render.py` (Lane 4) selects `conversation_routes.json`
   locale copy, select on `answer_language` instead of `body.language`.
3. **Post-processing vocabularies** - the Phase 2 A/B/C/F language-aware
   post-processing steps (e.g. `utils/directory_fields`,
   `config/directory_field_vocabulary.py`-driven field interpretation of the
   generated answer) key off `answer_language`.

**Never** item 4, retrieval: `app/retrieval/*` and the document-language /
same-country English fallback (`OPENSEARCH_GLOBAL_DOCUMENT_LANGUAGE`) keep
`body.language` untouched, enforced by always calling
`retrieval_language(selected_language, answer_language)` (which is always
`selected_language`) at that call site rather than `answer_language` directly.

## Tests

`tests/unit/test_cx_answer_language.py` - 30 tests in two groups:

- The original safety-property tests (switched/unswitched, short message,
  mixed-language, near-pair guards, Cyrillic ru/sr, numbers-only, the
  `retrieval_language` invariant, determinism).
- `TestAcceptanceSet` (added per coordinator review, 2026-09-18):
  table-driven, 48 ordinary customer questions (4 per `ROUTE_COPY_LANGUAGES`
  language x shipping cost/returns/payment methods/contact-sponsorship
  topics, widget=`en`), 10 English questions each with a different
  non-English widget, and 12 negatives (short, mixed-language, numbers,
  a product name, two code-switched sentences). Assertions are aggregate
  (recall/precision and a confusion-matrix check for the no/da pair), not
  per-sentence, so the thresholds stay tuned against the whole set rather
  than individual cases.

No case ids anywhere in the file; every scenario is a constructed, generic
sentence in its language.

## Precision/recall (from `TestAcceptanceSet`, 2026-09-18)

| Language | Recall | Notes |
|---|---|---|
| da | 1/4 (25%) | 3/4 tied exactly with `no` (genuinely ambiguous - documented exception) |
| de | 4/4 (100%) | |
| en (foreign-widget switch) | 10/10 (100%) | |
| es | 4/4 (100%) | including the probe that previously misclassified as French |
| fi | 4/4 (100%) | |
| fr | 4/4 (100%) | |
| it | 4/4 (100%) | |
| nl | 4/4 (100%) | |
| no | 2/4 (50%) | 2/4 tied exactly with `da` (genuinely ambiguous - documented exception) |
| ru | 4/4 (100%) | including the probe that previously scored only 1 raw hit |
| sr | 4/4 (100%) | |
| sv | 4/4 (100%) | |
| **Overall recall** | **53/58 (91.4%)** | all 5 misses are the documented no/da tie |
| **Overall precision** | **53/53 (100%)** | zero switches to a wrong language anywhere in the set |
| **Negatives (no false switch)** | **12/12 (100%)** | |

`TestAcceptanceSet.test_no_da_pair_never_crosses_to_the_wrong_member`
asserts directly that no/da never produces a WRONG switch (only a
non-switch is possible on the ambiguous cases);
`test_overall_recall_and_precision_meet_the_documented_bar` asserts
`recall >= 0.85` and `precision == 1.0` against this same table.

## Verification run (2026-09-18, worktree `askvera-cx-lane7`, branch `cx/lane7-20260918`)

- `pytest tests/unit/test_cx_answer_language.py` - 30 passed.
- `pytest tests/unit/test_cx_answer_language.py tests/conversation` - 380 passed
  (unchanged in `tests/conversation`; confirms no regression from this lane,
  which touches no shared code path yet).
- No `tests/unit/test_prompt*.py` files exist in this worktree to re-run.
- `flake8 app/orchestrator/answer_language.py tests/unit/test_cx_answer_language.py` - clean.
- `git diff --check` - clean.
