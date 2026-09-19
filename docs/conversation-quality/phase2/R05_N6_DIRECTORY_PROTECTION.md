# R05/N6: directory protection requires genuine compatible runtime intent

Worker: Claude Sonnet 5. Base: `e21a86e` (R11, conversation-quality +
Evidence-First V2 combined). Commit: `1dfcb78d8e254f0b9a7b73f3f3e3b262bc46cb78`
on `r05/directory-protection-needs-intent-20260918`.

## Defect and mechanism (file:line)

`docs/conversation-quality/phase2/R06_DIAGNOSIS.md`'s Norway section and the
raw capture `output/evidence-first-v2/retrieval-capture-20260918-r3.json`
(case `ho-slp-16-norway-former-fbo-reapplication-and-downline-no`) show
current production ranking the global directory record
`GLOBAL|en|International-Sponsoring-Directory.pdf|sponsoring-081-norway`
first with score `10.097727`, ahead of the correct policy clause
`NO:17.08-c`/its neighbours (`18.02-i` at `1.403168`, an ~8x gap), for a
question that only names the country ("Forever Norge") while asking about a
former FBO's reapplication and downline retention - an ordinary
company-policy question.

Root cause: `_directory_record_country_score`
(`app/retrieval/opensearch_sections.py:670`, pre-fix) unconditionally awarded
a `>= 6.0` target-country-match bonus to any global directory record once a
country was named in `target_country_names`, regardless of what the question
was actually asking for. That score feeds:

- `_merge_hits` (`app/retrieval/opensearch_sections.py:2160`, the raw
  merge/rank computation, two call sites at what are now lines ~2166 and
  ~2185), and, through the merged score,
- `_dominant_directory_row`/`_restore_dominant_directory_record`
  (`app/retrieval/opensearch_sections.py:809`/`839`, the post-selector
  dominance guard), which recomputes the same bonus to decide whether a raw
  candidate "decisively dominates" and should be restored to rank 1 even
  after the selector demoted it.

A country mention alone was therefore sufficient to bury every competing
policy clause, with no genuine directory/sponsoring signal at all.

## Failing-before reproduction (offline, before the fix)

`tests/unit/test_r05_directory_protection_intent.py::test_directory_record_country_score_ignores_intent_when_none_is_supplied`
and `test_norway_merge_order_directory_dominates_without_a_runtime_intent`
reproduce the exact shape offline: a directory hit with country-only lexical
relevance (base score ~0) plus the `+8.0` bonus outranks a policy hit with
ordinary topical relevance (base score ~1.29), matching the raw capture's
qualitative shape (a decisive, one-sided rout, not a close contest) even
though the exact numeric magnitudes differ because this is a synthetic
fixture, not real OpenSearch/Titan embeddings scores. The full merge/dominance
call chain (`_merge_hits` -> `_restore_dominant_directory_record`) is
exercised with `runtime_scope_intent=None` (the legacy shape every existing
caller in this repository uses) to show this is exactly the code path in
production before this fix.

## The fix

The `>= 6.0` branches of `_directory_record_country_score` now also require a
directory-compatible runtime scope intent - the deterministic, already-
computed decision `_runtime_scope_intent` produces in
`app/retrieval/providers.py:176` for every real request (V2 already relies on
this same function for `_authorized_policy_market`) - whenever one is
supplied:

- **Directory-compatible intents (bonus kept): `directory`,
  `international_sponsoring`, `unknown`.** `unknown` is the deliberately
  permissive fallback used when the Bedrock query planner is disabled or
  unavailable (`_planned_retrieval_plan`'s `planner_disabled`/
  `planner_unavailable` branches), which already documented that it
  "preserve[s] directory availability" - this fix does not change that.
- **Suppressed intents (bonus collapses to `0.0`): `policy`, `ambiguous`.**
  These are exactly the two intents that mean a country mention is not a
  genuine directory/sponsoring signal for this request.
- **`runtime_scope_intent=None` (no intent computed): bonus kept
  (unconditional, prior behaviour).** This is an *additive* gate, not a
  replacement classifier - every existing caller that constructs a
  `RetrievalQueryPlan`/calls the scoring functions directly without a
  runtime intent (every pre-existing test in `test_opensearch_sections.py`,
  and the entire Kenya/Uganda directory gate suite, which builds its own
  fixed plan via `monkeypatch.setattr(provider, "_build_search_plan", ...)`)
  is untouched.
- The `-4.0` wrong-country penalty and the weak generic fallback scores
  (`<= 2.4`, used when no country was targeted at all) are **not** gated -
  they are not boosts and never caused this class of bug.

This never touches retrieval inclusion: a directory record can still be
searched for and returned as a candidate (the OpenSearch query itself still
filters/boosts by `target_country_names` independently); only its
score-driven ranking and post-selector protection change.

`_dominant_directory_row`/`_restore_dominant_directory_record`
(`app/retrieval/opensearch_sections.py:809`/`839`) gained one new optional
parameter, `runtime_scope_intent`, threaded straight into the same
`_directory_record_country_score` call they already made to compute
`country_bonus` - no separate/duplicate gate was needed, because the
existing `country_bonus < _DIRECTORY_DOMINANCE_MIN_COUNTRY_BONUS` (6.0)
threshold check already fails once the bonus collapses to 0.0.

### The one new classifier input: `directory_topic_route`

`_runtime_scope_intent` (`app/retrieval/providers.py:176`) gained one new
deterministic input, `directory_topic_route`, computed in
`_planned_retrieval_plan` (`app/retrieval/providers.py:~665-690`) as
`bool(_directory_guard_topic_match(message))` - **the exact same regex gate
the dominance guard already used** (`_directory_guard_topic_match`,
`app/retrieval/opensearch_sections.py:800`), imported, not reinvented. It is
OR'd into the existing `deterministic_directory_route` input alongside
`operational_directory_route` and `own_market_directory_route`.

This was necessary because a cross-market sponsoring/bonus question can use
no operational-field keyword (delivery/order/payment/business-hours) and no
literal "sponsor" root word at all - e.g. the V2-09 Ghana regression control,
"I'm an FBO living outside Ghana. How much do I need to earn before Forever
Ghana pays my bonus, and who covers the bank transfer charges?" - and would
otherwise fall through to `ambiguous` and lose protection right alongside the
genuine Norway regression. `_directory_guard_topic_match` already recognizes
"bonus" wording (and already excludes anything matching
`DIRECTORY_POLICY_WORDING_RE`, so it never fires on a genuine "policy"
question), so reusing it verbatim closes this gap with no new country- or
case-specific code.

No case IDs, no expected section IDs, and no country names appear anywhere
in the runtime logic. No weight was retuned; the existing `8.0`/`6.0`/`-4.0`/
`_DIRECTORY_DOMINANCE_MIN_*` constants are unchanged.

## Which intent values count as directory intent

`directory`, `international_sponsoring`, and `unknown` (the planner-off/
planner-unavailable permissive fallback). `policy` and `ambiguous` do not.
A caller supplying no intent at all (`None`) is treated as compatible for
backward compatibility.

## Control results

All results below are from `tests/unit/test_r05_directory_protection_intent.py`
(24 tests) unless noted. Full command output and exit codes are in the
"Test run counts" section.

| Case | Intent computed | Bonus | Outcome |
|---|---|---|---|
| Norway former-FBO/downline (English) | `ambiguous` | suppressed (`0.0`) | policy clause outranks directory record in `_merge_hits`; dominance guard does not restore the directory record; full `retrieve()` pipeline returns the policy clause first |
| Norway former-FBO/downline (Norwegian, `Jeg sa opp forhandlerskapet...`) | `ambiguous` | suppressed | same as English - no English-only regex accidentally matches Norwegian text |
| French policy question naming "Forever Norge" | `ambiguous` | suppressed | `_directory_target_country_names` still resolves "Norge" as an alias, but the classifier still lands on `ambiguous` |
| Finnish policy question naming "Forever Norjan" (Norway's Finnish inflection) | `policy` (`not include_global_documents`, since "Norjan" is not a recognized market alias) | suppressed | same practical outcome as the other two - protection withheld either way |
| Hong Kong delivery-fee question, US session | `directory` (`operational_directory_route`/`directory_topic_route`, both fire on "delivery fee") | kept (`8.0`) | full `retrieve()` pipeline keeps the global record at rank 1 |
| Ghana cross-market bonus question, GB session (exact V2-09 fixture wording) | `directory` (`directory_topic_route` only - no operational keyword, no "sponsor" root word) | kept | full `retrieve()` pipeline keeps the global record at rank 1 despite a competing local policy row |
| Mexico international-sponsoring question, US session | `international_sponsoring` (`SPONSORING_QUESTION_RE`) | kept | full `retrieve()` pipeline keeps the global record at rank 1 |
| Kenya business-hours question, US session | `directory` (`operational_directory_route`) | kept | unchanged; `test_demo_kenya_directory_gate.py`'s 14 tests pass unmodified (they never construct a runtime intent, so this gate is a no-op for them by design) |
| Kyrgyzstan bonus question (real 2026-09-14 production-failure shape, `international_sponsoring` intent) | `international_sponsoring` | kept | dominance guard still restores the record - direct control mirroring `test_dominance_guard_restores_kyrgyzstan_shaped_directory_record` in `test_opensearch_sections.py` |

## Test run counts and exit codes

All commands run in the foreground with `--basetemp` under the assigned
scratchpad and `-o addopts=""`, `-p no:cacheprovider`.

1. Targeted list (`test_r05_directory_protection_intent.py`,
   `test_opensearch_sections.py`, `test_retrieval_service.py`,
   `test_retrieval_rank_list_capture.py`, `test_demo_kenya_directory_gate.py`,
   `test_demo_directory_routing.py`, `test_demo_own_market_directory.py`,
   `test_evidence_routing.py`, `test_chat_orchestrator.py`,
   `tests/evidence_first_v2`, `tests/conversation`):
   **926 passed, 2 failed, `EXIT=1`.**
   The 2 failures are `tests/evidence_first_v2/test_v2_audit.py::AuditTests::test_closed_26_path_manifest_and_aggregates`
   and `::test_manifest_drift_duplicate_and_public_alias_do_not_authorize` - a
   content-hash manifest audit over 26 approved experimental-audit-module
   paths, none of which this task touched. Confirmed pre-existing: running
   the identical file against the unmodified base (`git stash`, same
   command) reproduces the identical 2 failures with the identical assertion
   text, so nothing in this change caused or affects them.
2. Full `tests/unit` (foreground, 600000ms timeout): **8935 passed, 13
   xfailed, `EXIT=0`**, 350.73s wall time.
3. `flake8` on the three changed/added files
   (`app/retrieval/opensearch_sections.py`, `app/retrieval/providers.py`,
   `tests/unit/test_r05_directory_protection_intent.py`): **no output,
   `FLAKE8_EXIT=0`.**
4. `git diff --check HEAD~1 HEAD`: **no output, `DIFFCHECK_EXIT=0`.**

## Follow-up (2026-09-18): multilingual directory-intent RECOGNITION

An independent review of the fix above (offline, stubbed-planner
reproduction, no network) confirmed the "Limitations" section below as a
real, exploitable gap, not a theoretical one: every RECOGNITION regex this
classifier reads (`SPONSORING_QUESTION_RE`, `DIRECTORY_OPERATIONAL_QUESTION_RE`,
`_DIRECTORY_GUARD_TOPIC_RE`) matches English vocabulary only, so a genuine
directory question phrased in another language - or in English using a
contact verb or payment-instrument name rather than a literal field name -
fell through to `ambiguous` and lost the country-match bonus entirely
(8.0 -> 0.0). Reproduced exactly as reported, US session, a Ghana
`international_sponsoring_directory` row, `targets={'Ghana'}`:

| Question | Language | Before | After |
|---|---|---|---|
| "¿Cuál es el número de teléfono de Forever Ghana?" | es | `ambiguous` (0.0) | `directory` (8.0) |
| "Quel est le numéro de téléphone de Forever Ghana ?" | fr | `ambiguous` (0.0) | `directory` (8.0) |
| "Wie lautet die Adresse von Forever Ghana?" | de | `ambiguous` (0.0) | `directory` (8.0) |
| "How do I reach Forever Ghana?" | en | `ambiguous` (0.0) | `directory` (8.0) |
| "Where is Forever Ghana located?" | en | `ambiguous` (0.0) | `directory` (8.0) |
| "Does Forever Ghana accept credit cards?" | en | `ambiguous` (0.0) | `directory` (8.0) |
| "What is the Ghana office address?" (control) | en | `directory` (8.0) | `directory` (8.0), unchanged |
| "Who is the country manager for Forever Ghana?" | en | `ambiguous` (0.0) | `ambiguous` (0.0), unchanged - names no directory field |
| Norway former-FBO/downline (en/no) | en/no | `ambiguous` | `ambiguous`, unchanged |

### The fix: reuse the reviewed field vocabulary, don't invent a new one

`_runtime_scope_intent` (`app/retrieval/providers.py:176`) gained one new,
optional parameter, `language` (default `"en"`), and one new disjunct in its
branch that decides the `directory` intent: alongside the existing
`deterministic_directory_route`, it now also asks
`utils.directory_fields.directory_field_intent_present(text, language=language)`.
That function (new, `utils/directory_fields.py`) is a thin, read-only
wrapper:

1. It first calls the *already-reviewed* `_requested_directory_field_set`
   (the same function that drives field removal/restoration) with the
   request's own language. This is why Spanish "teléfono", French
   "téléphone", and German "Adresse" needed **zero new vocabulary** -
   `config/directory_field_vocabulary.py`'s `LANGUAGE_FIELD_TERMS` already
   carried reviewed stems for phone/email/website/address/business_hours/
   payment_methods/delivery_cost/delivery_time/fax in 12 non-English
   languages (13 with English), and English's own
   `_FIELD_REQUEST_PATTERNS["address"]` already matched "located"/"location"
   - it was simply never consulted from `providers.py` before this change.
2. Only for the two reviewer-identified shapes that name no field at all -
   "reach"/"contact" (a bare contact verb) and "credit card(s)"/"debit
   card(s)" (a payment instrument, not the phrase "payment methods") - a
   new, small, closed, **English-only** dictionary,
   `DIRECTORY_INTENT_SYNONYM_TERMS` (`config/directory_field_vocabulary.py`),
   is checked as a second disjunct. Its own docstring records the exact
   scope and confidence (English only, reviewer-identified 2026-09-18, not
   yet extended to the other 12 languages).

Critically, `directory_field_intent_present` is a **new, separate**
function - it is not folded into `_requested_directory_field_set` itself,
and `DIRECTORY_INTENT_SYNONYM_TERMS` is never read by
`remove_unrequested_directory_fields`, `restore_missing_requested_directory_fields`,
or `directory_field_conflicts`. Those three functions - which decide what to
strip or restore in an *already-generated answer* and must stay
conservative about compound/ambiguous requests - keep reading only
`LANGUAGE_FIELD_TERMS`/`ORDER_WORD_TERMS`, byte-for-byte unchanged. This
fix only ever affects retrieval scoring/protection classification, never
answer post-processing.

An unrecognized `language` (no table in either vocabulary) makes
`directory_field_intent_present` return `False`, falling back to exactly
the English-only recognition this classifier already had before this
change - measured directly: the Ghana Spanish phone question, re-run under
a bogus `language="xx"`, stays `ambiguous`, identical to the pre-N6
(`5b1d33f`) shape for the same underlying reason (the unconditional country
bonus never depended on language either). No worse than before.

### NOTE 6: "bonus" alone must not imply directory intent

The reviewer separately flagged that `directory_topic_route` reuses
`_directory_guard_topic_match` verbatim, whose `_DIRECTORY_GUARD_TOPIC_RE`
includes a bare `\bbonus(?:es)?\b` alternative (added for the Ghana/
Kyrgyzstan cross-market bonus controls). Taken naively, a Norway-shaped,
own-market policy question that also happens to mention "bonus" - e.g. "I
cancelled my Forever Norge distributorship... and do I keep my old downline
**and their bonus**?" - would be wrongly promoted to `directory` on that
word alone, which is exactly the class of bug R05/N6 exists to close.

**Decision: separable with an existing signal, no new vocabulary needed.**
The distinguishing signal between the genuine Ghana/Kyrgyzstan controls and
the Norway-shaped risk is already available at the call site in
`_planned_retrieval_plan`: `named_markets` (from `find_market_mentions`,
which already returns market **codes**) versus the request's own `country`
code. The Ghana and Kyrgyzstan controls are genuinely cross-market (a GB/US
session naming a foreign market); the Norway risk names only the session's
own market. So `directory_topic_route`'s "bonus"-only match (i.e. neither
`_DIRECTORY_DETAIL_RE` nor `DIRECTORY_OPERATIONAL_QUESTION_RE` also matched)
is now trusted only when `SPONSORING_QUESTION_RE` matches OR
`named_markets - {own_market_code}` is non-empty - a genuinely
cross-market or literal-"sponsor" question. A "bonus" mention alongside
other independent directory/operational wording (e.g. "business hours ...
bonus") is untouched, since that other wording is its own, non-"bonus"
signal and was never gated.

This change lives entirely inside `_planned_retrieval_plan`'s own
`directory_topic_route` computation (`app/retrieval/providers.py`) and does
**not** touch `_directory_guard_topic_match`/`_DIRECTORY_GUARD_TOPIC_RE`
themselves - those are also used, unmodified, by the post-selector
dominance guard's own topical gate in `app/retrieval/opensearch_sections.py`
(`_dominant_directory_row`), which is a separate precondition from
`runtime_scope_intent` compatibility and out of this follow-up's scope.
Verified: Norway-with-"bonus" stays `ambiguous`; the pre-existing Ghana
cross-market bonus control and the Kyrgyzstan real-production-failure-shape
control both still resolve to `directory`; a "bonus" mention alongside
independent directory wording ("business hours") stays `directory` for an
own-market question too.

### Follow-up test run counts and exit codes

All commands run in the foreground with `--basetemp` under the assigned
scratchpad and `-o addopts=""`, `-p no:cacheprovider`.

1. `test_r05_directory_protection_intent.py` alone (24 pre-existing + 16 new
   tests added by this follow-up): **40 passed, `EXIT=0`.**
2. Targeted list (`test_r05_directory_protection_intent.py`,
   `test_opensearch_sections.py`, `test_retrieval_service.py`,
   `test_retrieval_rank_list_capture.py`, `test_demo_kenya_directory_gate.py`,
   `test_demo_directory_routing.py`, `test_demo_own_market_directory.py`,
   `test_evidence_routing.py`, `test_directory_fields.py`,
   `tests/conversation`, `tests/evidence_first_v2`): **920 passed, 1 failed,
   `EXIT=1`.** The 1 failure is
   `tests/evidence_first_v2/test_offline_isolation.py::OfflineIsolationTests::test_package_imports_use_a_narrow_allowlist`,
   an unrelated import-allowlist check on
   `app/experimental/evidence_first_v2/scope_aware_fusion.py` (a file this
   follow-up never touched). Confirmed pre-existing: `git stash` back to the
   unmodified worktree and re-running the identical file reproduces the
   identical failure with the identical assertion text.
3. Full `tests/unit` (foreground, 600000ms timeout): **8961 passed, 13
   xfailed, `EXIT=0`**, 347.98s wall time. (8961 = the prior fix's 8935 plus
   this follow-up's 16 new tests, minus the 24 pre-existing
   `test_r05_directory_protection_intent.py` tests already counted in that
   8935; net +26 tests in the file, 16 of which are new to this follow-up.)
4. `flake8` on the four changed/added files
   (`app/retrieval/providers.py`, `config/directory_field_vocabulary.py`,
   `utils/directory_fields.py`, `tests/unit/test_r05_directory_protection_intent.py`):
   **no output, `FLAKE8_EXIT=0`.**
5. `git diff --check`: **no output, `DIFFCHECK_EXIT=0`.**

## Limitations

- **Multilingual directory-field RECOGNITION now covers 13 languages
  (English plus the 12 `config/directory_field_vocabulary.py`
  `LANGUAGE_FIELD_TERMS` carries: fr, de, nl, es, it, pt, sv, da, no, fi, ru,
  sr) for questions that literally name a canonical field** (phone, email,
  website, address, business hours, payment methods, delivery cost/time,
  fax). This is a real improvement over the 39-market configuration's much
  broader language surface - the remaining ~26+ configured languages this
  repository otherwise supports (per the task's own count) still recognize
  directory intent in English only, an explicit, documented gap, not a
  claimed complete solution.
- **The two synonym-only shapes ("reach"/"contact", "credit/debit
  card(s)") are English-only, and deliberately so** -
  `DIRECTORY_INTENT_SYNONYM_TERMS` carries no non-English entries yet. A
  native-language addition should follow this module's own
  "compound stem, not a bare generic word" discipline before being trusted.
- **A question naming no canonical field at all** ("Who is the country
  manager for Forever Ghana?") stays `ambiguous` in every language,
  unchanged - this fix recognizes named *fields*, not arbitrary
  directory-adjacent topics, by design (recognizing more would risk
  reopening the original Norway-shaped bug from the other direction).
- **NOTE 6's cross-market gate uses market *codes*, not names or session
  locale**, and only narrows the "bonus"-only match specifically - it does
  not add any new suppression path, and a "bonus" mention with independent
  directory/operational wording is unaffected.
- **This fix does not address retrieval recall.** The raw capture shows the
  literal required section `NO:17.08-c` is entirely absent from the
  60-candidate merged list even in the per-channel data (only `17.08` and
  `17.08-a` appear), while a different vector-query variant independently
  ranks it first in its own channel. That is a channel-union/recall gap
  upstream of scoring, not a ranking/protection defect, and is out of this
  task's scope; the offline reproduction here instead uses `18.02-i`-shaped
  fixtures (the actual second-ranked real candidate) to isolate and prove
  the scoring/protection mechanism this task was asked to fix.
- **No live/AWS-backed verification was performed** (per the task's "no
  network, AWS, or model calls" constraint) - all reproduction and control
  tests are offline with mocked Bedrock/OpenSearch clients, per the pattern
  already established by `test_demo_kenya_directory_gate.py` and
  `test_demo_directory_routing.py`.
- **The two pre-existing `test_v2_audit.py` manifest failures are
  unrelated and were not investigated further** - they are outside this
  task's file scope (an experimental audit-module content-hash check over a
  fixed 26-path manifest) and reproduce identically on the unmodified base
  commit.

## Second follow-up (2026-09-18): Fable re-review findings F1/F2

An independent Fable re-review approved the multilingual-RECOGNITION follow-up
above "with limitations" and flagged two should-fix findings against the
stubbed-planner (`document_scopes=[]`) Norway/Ghana repro set.

### F1: the policy-wording suppression stayed English-only

`_runtime_scope_intent`'s policy branch
(`is_policy_safety_question`/`DIRECTORY_POLICY_WORDING_RE` = `policy|rules`)
was still English-only, while the `directory_field_intent_present` disjunct
added by the first follow-up is 13-language. A non-English POLICY question
that also names a directory field in the same language therefore skipped the
(English-only) policy branch and matched the (multilingual) field branch
instead - reopening the N6 class of bug for exactly the languages the first
follow-up had just added recognition for.

**Fix:** `config/directory_field_vocabulary.py` gains a new, small, closed,
documented `POLICY_WORDING_TERMS` table (policy/rules/regulations/terms and
their equivalents) for every language `LANGUAGE_FIELD_TERMS` already covers
except English (es, fr, de, nl, it, pt, fi, no, da, sv, ru, sr).
`utils/directory_fields.py` compiles it into
`localized_policy_wording_present(question, language=...)`, checked in
`_runtime_scope_intent` alongside the existing English-only checks, before
the directory disjunct - so a genuine non-English policy-wording match keeps
the question `policy`, exactly like its English equivalent, regardless of
what any deterministic directory route separately computed.

| Question (language) | Before this fix | After this fix |
| --- | --- | --- |
| "¿Cual es la politica de Forever Norway sobre los metodos de pago?" (es) | `directory` (8.0) | `policy` (0.0) |
| "Quelles sont les regles de Forever Norge sur l'adresse de livraison ?" (fr) | `directory` (8.0) | `policy` (0.0) |
| "Welche Regeln gelten bei Forever Norge fur die Ruckgabe per E-Mail?" (de) | `directory` (8.0) | `policy` (0.0) |
| "Quelle est la politique de Forever Ghana sur les frais de livraison ?" (fr, GB session) | `directory` (8.0) | `policy` (0.0) |
| "What is the policy of Forever Norway on payment methods?" (en, control) | `policy` (0.0) | `policy` (0.0), unchanged |
| "¿Cual es el numero de telefono de Forever Ghana?" (es, earlier directory repro) | `directory` (8.0) | `directory` (8.0), unchanged |
| "Quel est le numero de telephone de Forever Ghana ?" (fr, earlier directory repro) | `directory` (8.0) | `directory` (8.0), unchanged |
| "Wie lautet die Adresse von Forever Ghana?" (de, earlier directory repro) | `directory` (8.0) | `directory` (8.0), unchanged |

### F2: the "reach" synonym matched its own inflections

`DIRECTORY_INTENT_SYNONYM_TERMS["en"][PHONE]` (`("reach", "contact")`) was
compiled with a leading word-start boundary (`(?<!\w)`) only, the same style
used for `LANGUAGE_FIELD_TERMS`'s compound stems - correct there (deliberately
open-ended, so one spelling catches inflected forms of a compound), but wrong
for a bare, complete verb like "reach": it also matched "reach**es**", so
"What happens to my downline in Ghana when it **reaches** Manager level?"
(a downline-rank question, not a contact request) was wrongly promoted to
`directory`.

**Fix:**
`utils/directory_fields._DIRECTORY_INTENT_SYNONYM_PATTERNS` now compiles every
synonym term with both a leading and a trailing boundary
(`(?<!\w)(?:...)(?!\w)`), so only the complete word matches. Separately,
"contact" was removed from the synonym set as redundant: it is already
present, with the same full-word matching, in
`app/retrieval/opensearch_sections.py`'s `_DIRECTORY_DETAIL_RE`, which feeds
`_directory_guard_topic_match` -> `directory_topic_route` ->
`deterministic_directory_route` independently of this synonym set - proven by
a dedicated control test rather than assumed.

| Question | Before this fix | After this fix |
| --- | --- | --- |
| "What happens to my downline in Ghana when it reaches Manager level?" | `directory` (8.0) | `ambiguous` (0.0) |
| "How do I reach Forever Ghana?" (control, bare word) | `directory` (8.0) | `directory` (8.0), unchanged |
| "How do I contact Forever Ghana?" (control, synonym removed) | `directory` (8.0) | `directory` (8.0), unchanged (via `_DIRECTORY_DETAIL_RE`, not the removed synonym) |

### Second follow-up test run counts and exit codes

All commands run in the foreground with `--basetemp` under the assigned
scratchpad and `-o addopts=""`, `-p no:cacheprovider`.

1. Both new F1/F2 repro tests, on the unmodified worktree (`git stash` the
   three source changes, keep the new tests): **5 failed, `EXIT=1`**,
   confirming genuine fail-before reproductions
   (`test_f1_reviewer_repro_non_english_policy_question_naming_a_field_stays_policy`
   x4 and
   `test_f2_reviewer_repro_reaches_inflection_does_not_trigger_directory_synonym`).
   `git stash pop` restored the fix afterward.
2. Targeted list (`test_r05_directory_protection_intent.py`,
   `test_opensearch_sections.py`, `test_retrieval_service.py`,
   `test_retrieval_rank_list_capture.py`, `test_demo_kenya_directory_gate.py`,
   `test_demo_directory_routing.py`, `test_directory_fields.py`,
   `tests/conversation`): **650 passed, `EXIT=0`.**
3. Full `tests/unit` (foreground, 600000ms timeout): **8974 passed, 13
   xfailed, `EXIT=0`**, 341.42s wall time.
4. `flake8` on the four changed files (`app/retrieval/providers.py`,
   `config/directory_field_vocabulary.py`, `utils/directory_fields.py`,
   `tests/unit/test_r05_directory_protection_intent.py`): **no output,
   `FLAKE8_EXIT=0`.**
5. `git diff --check`: **no output, `DIFFCHECK_EXIT=0`.**

### Second follow-up limitations

- **F1's policy-wording set is closed and per-language**, same discipline as
  the field vocabulary it sits beside: es/fr/de/nl/it/sv are ordinary,
  unambiguous dictionary words (high confidence, reused stems' sibling
  quality); pt/fi/no/da/ru/sr are this module's own first pass (medium
  confidence - a native reviewer should check these before they gate
  anything destructive in production), exactly mirroring the confidence
  split `LANGUAGE_FIELD_TERMS` already documents for the same language set.
- **F1 does not touch `_directory_guard_topic_match`'s own (English-only)
  `DIRECTORY_POLICY_WORDING_RE` check** in
  `app/retrieval/opensearch_sections.py` - it does not need to: the new
  `localized_policy_wording_present` check runs first in
  `_runtime_scope_intent`'s if/elif chain, ahead of `deterministic_directory_route`,
  so it overrides that route's result regardless of how it was computed.
- **F2's trailing-boundary fix is scoped to `DIRECTORY_INTENT_SYNONYM_TERMS`
  only**, not `LANGUAGE_FIELD_TERMS`'s compound stems, which still
  intentionally omit a trailing boundary for the documented inflection
  reasons in `config/directory_field_vocabulary.py`'s own docstring.

## Third follow-up (2026-09-18): coordinator review of 88da3cc - accent folding

A coordinator review of the F1 fix (commit `88da3cc`) found a symmetric gap:
`POLICY_WORDING_TERMS` only spelled its accented forms ("política"), so a
question that omits accents entirely - which users routinely do - did not
match it, while `LANGUAGE_FIELD_TERMS`'s own field patterns already tolerate
missing accents (e.g. Spanish `m[eé]todos?\s+de\s+pago` matches "metodos de
pago" via an explicit character class). Probe:
`localized_policy_wording_present("Cual es la politica de Forever Norway
sobre los metodos de pago?", language="es")` returned `False` while
`directory_field_intent_present` returned `True` for the same text, so the
question still resolved to `directory`/8.0 - reopening F1's own bug for
accentless input.

**Fix:** rather than hand-maintaining a second accentless literal or
character class per `POLICY_WORDING_TERMS` term (which the field vocabulary
does, pattern-by-pattern, and which does not generalize), both the
vocabulary's terms (at compile time) and the question text (at match time)
are folded through the same NFKD-decompose/strip-combining-marks/casefold
recipe `app/retrieval/providers.py`'s own `_fold_search_text` already uses
for its local query-expansion heuristics. That exact function could not be
imported into `utils/directory_fields.py` (`providers.py` already imports
*from* that module, so importing back would be circular), so a private
`_fold_diacritics` duplicate was added there instead, documented as
intentionally mirroring `_fold_search_text` rather than reinventing it. This
folding also transparently handles NFD-decomposed input (a base letter plus
a separate combining-mark codepoint, one of two valid Unicode encodings of
the same accented text) without any special-casing, since NFKD decomposition
subsumes NFD. Cyrillic letters (ru, sr) have no compatibility decomposition,
so folding is a no-op for those entries and they are unaffected.

| Question (language) | Before this fix | After this fix |
| --- | --- | --- |
| "Cual es la politica de Forever Norway sobre los metodos de pago?" (es, accentless) | `directory` (8.0) | `policy` (0.0) |
| "Quelles sont les regles de Forever Norge sur l'adresse de livraison ?" (fr, accentless) | `directory` (8.0) | `policy` (0.0) |
| "Qual e a politica de Forever Ghana sobre as formas de pagamento?" (pt, accentless) | `directory` (8.0) | `policy` (0.0) |
| NFD-decomposed form of the accented Spanish F1 repro | `ambiguous` (0.0)* | `policy` (0.0) |
| "¿Cuál es la política ...?" (es, accented, precomposed - F1 control) | `policy` (0.0), unchanged | `policy` (0.0), unchanged |
| "Welche Regeln ...?" (de, control - already accentless) | `policy` (0.0), unchanged | `policy` (0.0), unchanged |

\* Before this fix, NFD-decomposed accented Spanish text also broke the
(unfolded) field-intent match - `directory_field_intent_present`'s own
character-class patterns expect a single precomposed accented character, not
a base letter plus a separate combining mark - so that specific probe landed
on `ambiguous`, not `directory`. This is a separate, narrower, pre-existing
gap in the field disjunct for NFD input specifically; it is not addressed
here (out of scope for this coordinator review), but the policy-wording fix
resolves the question correctly regardless, because it is checked first.

### Third follow-up test run counts and exit codes

All commands run in the foreground with `--basetemp` under the assigned
scratchpad and `-o addopts=""`, `-p no:cacheprovider`.

1. The 8 new accent-folding tests, on `utils/directory_fields.py` reverted
   via `git stash` (tests kept): **6 failed, 2 passed, `EXIT=1`** - the 2
   pre-existing passes are the German control (no accent to begin with) and
   the accented-Portuguese control (already matched via the literal,
   unfolded term added in the second follow-up); the 6 failures are the
   genuine accentless/NFD-decomposed reproductions. `git stash pop` restored
   the fix afterward.
2. Targeted list (`test_r05_directory_protection_intent.py`,
   `test_opensearch_sections.py`, `test_retrieval_service.py`,
   `test_retrieval_rank_list_capture.py`, `test_demo_kenya_directory_gate.py`,
   `test_demo_directory_routing.py`, `test_directory_fields.py`,
   `tests/conversation`): **658 passed, `EXIT=0`.**
3. Full `tests/unit` (foreground, 600000ms timeout): **8982 passed, 13
   xfailed, `EXIT=0`**, 387.63s wall time.
4. `flake8` on the four changed files (`app/retrieval/providers.py`,
   `config/directory_field_vocabulary.py`, `utils/directory_fields.py`,
   `tests/unit/test_r05_directory_protection_intent.py`): **no output,
   `FLAKE8_EXIT=0`** (one `E302` blank-line finding was caught and fixed
   during this follow-up before the final run).
5. `git diff --check`: **no output, `DIFFCHECK_EXIT=0`.**

### Third follow-up limitations

- **The NFD-input gap in `directory_field_intent_present` itself (see the
  table footnote above) is not fixed here** - it is masked for policy
  questions because the policy check runs first, but a genuinely
  directory-intentioned question typed with NFD-decomposed accents (an
  uncommon but valid input encoding) would still not be recognized by the
  field disjunct. Flagged as a candidate for a future, narrower follow-up if
  NFD input is confirmed to occur in practice; not in this review's scope.
- **`_fold_diacritics` is a small, private duplicate of
  `app/retrieval/providers.py._fold_search_text`**, not a shared import,
  specifically to avoid a circular import between that module and
  `utils/directory_fields.py`. If a third caller needs the same fold in the
  future, it should move to a shared, dependency-free location rather than
  being duplicated a third time.

## Fourth follow-up (2026-09-18): coordinator review finding S1

A Fable review of candidate `11d9657` (containing `88da3cc` and `0b1f0e3`)
approved the fix "with limitations" - F1 and F2 were closed - but flagged
one should-fix (S1) against `POLICY_WORDING_TERMS`: its own docstring
claimed "policy/rules/regulations/terms" coverage, but only "policy"/
"rules" (nominative/plural forms) actually existed in the table, and
English's `DIRECTORY_POLICY_WORDING_RE` was still `policy|rules` only.
Every repro below (stubbed planner, `document_scopes=[]`, a Norway
directory row) resolved to `directory`/8.0 before this fix and must resolve
to `policy`/0.0.

**Fix, in two parts:**

1. `POLICY_WORDING_TERMS` (`config/directory_field_vocabulary.py`) gains a
   regulation/guideline/condition family of synonyms for every language it
   already covers: es reglamento(s)/condicion(es)/directriz(ces); fr
   condition(s)/directive(s) (règlement(s) already present); de
   Vorschrift(en)/Bestimmung(en)/Bedingung(en); nl voorwaarde(n)/
   richtlijn(en)/reglement; it regolamento/condizione(i)/"linea guida"/
   "linee guida"; pt regulamento/condicao(oes)/diretriz(es); fi
   ehto/ehdot/maarays(maaraykset)/ohje(ohjeet) (medium confidence); no/da/sv
   definite plural forms (reglene/retningslinjene, reglerne/
   retningslinjerne, reglerna/riktlinjerna) plus the invariant vilkar/
   villkor; ru oblique cases of politika/pravila (politike/politiku/
   politikoj, pravilam/pravilami/pravilah) and uslovie/uslovija/uslovijah;
   sr the equivalent oblique forms, Latin and Cyrillic. The docstring above
   the table was rewritten to state exactly what is covered (broken out by
   sense: policy/regulation/guideline/condition, plus the oblique/definite
   grammatical forms), the confidence split (unchanged from the earlier
   follow-up: fr/de/nl/es/it/sv high, pt/fi/no/da/ru/sr medium, with
   Finnish's ehto/ehdot pair flagged medium-to-low for its own consonant
   gradation), and the accepted idiom trade-off (see point 3 below).
2. English's `DIRECTORY_POLICY_WORDING_RE` (`app/retrieval/providers.py`)
   widens from `policy|rules` to also match `regulation(s)`,
   `guideline(s)`, `condition(s)`, and the phrase `terms and conditions` /
   `terms of`. A bare `\bterms\b` was deliberately NOT added, because it is
   dominated by the unrelated "in terms of X" idiom and would suppress
   genuine directory questions on that idiom alone.
3. **Accepted idiom trade-off (reviewer note N1):** "regel"/"regler" (no/da)
   and the riktlinje/regel family also fire inside the idiom "som regel"
   ("as a rule", not a policy-document reference), so a genuinely
   directory-intentioned Scandinavian question using that idiom would be
   wrongly suppressed. This is accepted, not fixed, symmetric with
   English's own `terms of` firing inside "in terms of X" - narrowing
   either pattern to dodge its own idiom risks missing the genuine
   policy-document sense that dominates real usage, and the cost of
   over-suppression is only the country-match *bonus*, never retrieval
   inclusion.

| Question (language) | Before this fix | After this fix |
| --- | --- | --- |
| "¿Cuál es el reglamento de Forever Norway sobre la dirección de entrega?" (es) | `directory` (8.0) | `policy` (0.0) |
| "¿Cuáles son las condiciones de Forever Norway sobre la dirección de entrega?" (es) | `directory` (8.0) | `policy` (0.0) |
| "Quelles sont les conditions de Forever Norge sur l'adresse de livraison ?" (fr) | `directory` (8.0) | `policy` (0.0) |
| "Quali sono le condizioni di Forever Norway sull'indirizzo di consegna?" (it) | `directory` (8.0) | `policy` (0.0) |
| "Согласно политике Forever Norway, какой адрес доставки?" (ru, dative) | `directory` (8.0) | `policy` (0.0) |
| "What are the regulations of Forever Norway on the delivery address?" (en) | `directory` (8.0) | `policy` (0.0) |
| "What are the terms and conditions of Forever Norway on the delivery address?" (en) | `directory` (8.0) | `policy` (0.0) |
| "What are the guidelines of Forever Norway on the delivery address?" (en) | `directory` (8.0) | `policy` (0.0) |
| "How do I reach/contact Forever Ghana?" (en, control) | `directory` (8.0) | `directory` (8.0), unchanged |
| es/fr/de phone and address repros (control) | `directory` (8.0) | `directory` (8.0), unchanged |
| "What payment methods does Forever Norway accept?" (en, control) | `directory` (8.0) | `directory` (8.0), unchanged |

### Fixture/conversation-pack grep for false-suppression risk

Per the coordinator's instruction, `tests/fixtures` and `tests/conversation_pack`
were grepped for every S1 word (English `regulation`/`guideline`/`condition`
and every non-English addition: `reglamento`, `regolamento`, `condicion`,
`condizion`, `voorwaarde`, `vorschrift`, `bestimmung`, `bedingung`,
`richtlijn`, `directive`, `directriz`, `"linea guida"`, `ehto`/`ehdot`,
`maarays`, `ohje`, `vilkar`/`villkor`, `reglene`/`reglerne`/`reglerna`,
`retningslinjene`/`retningslinjerne`/`riktlinjerna`, `uslov`). Every hit was
inspected by hand:

- `ho-slp-02-ghana-prospect-fbo-first-order-conditions-en`'s "conditions" is
  only in the case-ID slug; the actual `"question"` field ("How much would
  my first order have to be?") contains none of these words.
- Every other `held_out_source_linked_pack.json` hit is inside an audit/
  annotation field (`quote`, `source_evidence`, `not_copied_from`,
  `forbidden_claims`), never the `"question"` text sent to the classifier.
- The one genuine hit in a `"message"`/`"text"` field is
  `tests/conversation_pack/cases.json`'s `"What are the return conditions?"`
  - a genuine return-*policy* question (not a directory/country-bonus
    question), whose test only asserts `expected_outcome: "answer"` and a
    guardrail-misfire control; it carries no directory-routing assertion,
    so this fix does not disturb it, and routing it to "policy" is the
    behaviourally correct outcome regardless.

**Conclusion: no false-suppression risk found in either fixture set.**

### Fourth follow-up test run counts and exit codes

All commands run in the foreground with `--basetemp` under the assigned
scratchpad and `-o addopts=""`, `-p no:cacheprovider`.

1. The 8 new reviewer-repro tests (5 non-English + 3 English), on
   `config/directory_field_vocabulary.py` and `app/retrieval/providers.py`
   reverted via `git stash` (tests kept): **8 failed, `EXIT=1`**, confirming
   genuine fail-before reproductions. `git stash pop` restored the fix
   afterward.
2. Targeted list (`test_r05_directory_protection_intent.py`,
   `test_opensearch_sections.py`, `test_retrieval_service.py`,
   `test_retrieval_rank_list_capture.py`, `test_demo_kenya_directory_gate.py`,
   `test_demo_directory_routing.py`, `test_directory_fields.py`,
   `tests/conversation`): **674 passed, `EXIT=0`.**
3. Full `tests/unit` (foreground, 600000ms timeout): **8998 passed, 13
   xfailed, `EXIT=0`**, 416.43s wall time.
4. `flake8` on the four changed files (`app/retrieval/providers.py`,
   `config/directory_field_vocabulary.py`, `utils/directory_fields.py`,
   `tests/unit/test_r05_directory_protection_intent.py`): **no output,
   `FLAKE8_EXIT=0`.**
5. `git diff --check`: **no output, `DIFFCHECK_EXIT=0`.**

### Fourth follow-up limitations

- **Coverage is still a closed, hand-picked synonym list, not exhaustive
  grammatical coverage.** Every other inflected case a language's grammar
  can produce beyond the forms explicitly listed (e.g. Finnish's remaining
  oblique cases of `kaytanto`/`saanto`/`ehto`/`maarays`/`ohje`) is not
  covered; an unlisted spelling falls back to "ambiguous", the same
  behaviour as before this task existed - it can only cost directory
  protection for that spelling, never wrongly grant it.
- **The "som regel"/"in terms of X" idiom trade-off (point 3 above) was
  originally accepted for both English and Scandinavian - the fifth
  follow-up below fixes the English "in terms of X" half with a targeted
  lookbehind (a coordinator review found the "accepted" framing was
  actually a false-suppression bug, not a tolerable trade-off) and leaves
  the Scandinavian "som regel" half accepted, since "regel"/"regler" have
  no equivalent narrow exclusion available without losing the genuine
  "policy" sense they exist to catch.**
- **The Finnish "ehto"/"ehdot" pair is flagged medium-to-low confidence**
  specifically: Finnish consonant gradation (t/d) is handled for this one
  pair by listing both forms explicitly, but no further oblique case of it
  is covered.

## Fifth follow-up (2026-09-18): coordinator review of d77c13f

A coordinator review of the fourth follow-up found two English
false-suppression leaks in its own widening of
`DIRECTORY_POLICY_WORDING_RE`:

- **S2a:** the new `terms\s+of` branch matched *inside* the unrelated "in
  terms of X" idiom too broadly - not just the intended "terms of
  service"/"terms of payment" phrasing the addition was meant for. Probe:
  "What are the office hours in terms of weekends?" resolved to
  `policy`/0.0 instead of `directory`/8.0.
- **S2b:** the new singular `condition` matched a genuine physical-condition
  question with no policy-document sense at all. Probe: "Is the office in
  good condition?" resolved to `policy`/0.0 instead of `directory`/8.0.

**Fix:**

1. `terms\s+of` is now guarded by a fixed-width negative lookbehind,
   `(?<!\bin\s)\bterms\s+of\b` (Python requires fixed-width lookbehinds;
   `\bin\s` is exactly 3 characters wide since `\b` itself consumes none).
   This excludes only "in terms of X" (where "terms" is immediately
   preceded by the standalone word "in") while still matching "terms of
   service"/"terms of payment"/any other "terms of X" phrasing. The
   lookbehind's own `\b` means a word merely *ending* in "...in "
   (e.g. "certain terms of service") is not excluded, since "in" there is
   not its own word. This was chosen over an explicit "terms of
   (sale|service|use|payment|business|membership)" phrase list as the
   simpler, still-auditable fix: one general pattern that excludes exactly
   the one problem idiom, rather than an open-ended list needing its own
   upkeep as new "terms of ..." phrasings appear. `terms and conditions`
   is unaffected (no lookbehind needed - it does not appear inside the "in
   terms of X" idiom).
2. `conditions?` narrows to plural-only `conditions` (English). Genuine
   English "terms and conditions" usage is itself always plural, so the
   singular added no real recall and only false-suppressed physical-
   condition questions like "Is the office in good condition?".
3. The same singular/plural asymmetry is applied to the four Romance
   languages that share the identical ambiguity from Latin: es
   ("condición" dropped, "condiciones" kept), fr ("condition" dropped,
   "conditions" kept), it ("condizione" dropped, "condizioni" kept), pt
   ("condição" dropped, "condições" kept) - in each, the singular noun is
   also the ordinary word for a physical/product condition ("el telefono
   esta en buena condicion"), while the plural is not idiomatic that way.
   German (Bedingung/Bedingungen), Dutch (voorwaarde/voorwaarden), Finnish
   (ehto/ehdot), Russian (uslovie/uslovija), and Serbian (uslov/uslovi)
   keep their singular forms unchanged: none of those languages uses that
   noun for a physical condition (they use a separate word - Zustand/staat/
   kunto/sostoyanie/stanje respectively), so there is no equivalent risk.
   The Scandinavian vilkar/villkor entries are grammatically invariant
   (identical singular and plural), so the distinction does not apply.

| Question (language) | Before this fix | After this fix |
| --- | --- | --- |
| "What are the office hours of Forever Norway in terms of weekends?" (en) | `policy` (0.0) | `directory` (8.0) |
| "What is the phone number of Forever Norway? Is the office in good condition?" (en) | `policy` (0.0) | `directory` (8.0) |
| "What are the terms of payment at Forever Norway?" (en, control) | `policy` (0.0), unchanged | `policy` (0.0), unchanged |
| "¿Está el teléfono en buena condición?" (es, singular) | `policy` (0.0) | `directory`-eligible (0.0 suppression removed)* |
| "¿Cuáles son las condiciones de venta?" (es, plural, control) | `policy` (0.0), unchanged | `policy` (0.0), unchanged |
| Equivalent fr/it/pt singular-physical / plural-policy pairs | same pattern | same pattern |
| German/Dutch/Finnish/Russian/Serbian singular condition-family forms | `policy` (0.0), unchanged | `policy` (0.0), unchanged (no risk in these languages) |

\* The table's Spanish/French/Italian/Portuguese rows are unit-level
`localized_policy_wording_present` results (True -> False), not full
`_runtime_scope_intent` results - no existing test fixture pairs a
Romance-language singular-condition question with a directory field in a
way that would flip a full pipeline result, so the fix is proven at the
function level, matching the coordinator's own repro shape.

### Fixture/conversation-pack note

The coordinator's earlier fixture grep (fourth follow-up section, above)
already covered `condition`/`conditions` and every non-English word this
follow-up touches; no new grep was needed since this follow-up only
*removes* recognition (singular condition forms, the "in terms of" idiom)
rather than adding any new word.

### Fifth follow-up test run counts and exit codes

All commands run in the foreground with `--basetemp` under the assigned
scratchpad and `-o addopts=""`, `-p no:cacheprovider`.

1. The 17 new S2 tests, on `config/directory_field_vocabulary.py` and
   `app/retrieval/providers.py` reverted via `git stash` (tests kept):
   **7 failed, 10 passed, `EXIT=1`** - the 7 failures are the genuine S2a/
   S2b leaks and their four Romance-language siblings; the 10 pre-existing
   passes are controls unaffected by this specific bug (the non-Romance
   singular-kept controls, the "terms of payment" policy control, etc.).
   `git stash pop` restored the fix afterward.
2. Targeted list (`test_r05_directory_protection_intent.py`,
   `test_opensearch_sections.py`, `test_retrieval_service.py`,
   `test_retrieval_rank_list_capture.py`, `test_demo_kenya_directory_gate.py`,
   `test_demo_directory_routing.py`, `test_directory_fields.py`,
   `tests/conversation`): **691 passed, `EXIT=0`.**
3. Full `tests/unit` (foreground, 600000ms timeout): **9015 passed, 13
   xfailed, `EXIT=0`**, 404.10s wall time.
4. `flake8` on the four changed files (`app/retrieval/providers.py`,
   `config/directory_field_vocabulary.py`, `utils/directory_fields.py`,
   `tests/unit/test_r05_directory_protection_intent.py`): **no output,
   `FLAKE8_EXIT=0`.**
5. `git diff --check`: **no output, `DIFFCHECK_EXIT=0`.**

### Fifth follow-up limitations

- **The negative lookbehind excludes only the literal, standalone word
  "in" immediately before "terms of".** A different preposition-like idiom
  this task's reviewers have not yet identified (if one exists) would not
  be caught by this specific exclusion and would need its own review.
- **The Romance-language singular/plural fix is a coarse binary per
  language**, not a semantic disambiguator - a genuinely policy-document
  singular use in Spanish/French/Italian/Portuguese ("la condicion
  principal del contrato es...") is now also not recognized, exactly
  mirroring English's own choice to drop the singular entirely rather than
  attempt to disambiguate sense from a bare word. This trades a small
  amount of recall for eliminating the physical-condition false positive,
  the same trade-off English's fix makes.

## Sixth follow-up (2026-09-18): coordinator review of 99ec438 (MEDIUM finding)

A Fable review of candidate `99ec438` (the fourth and fifth follow-ups)
approved the fix "with limitations", with one MEDIUM finding: the
widening amplifies false suppression. The review ran 35 idiom/
subordinate-clause probes against the vocabulary and found **27 newly,
wrongly suppressed from `directory`/8.0 to `policy`/0.0**. The fifth
follow-up's own reasoning - that the Romance-language plural
("condiciones"/"conditions"/"condizioni"/"condições") was not idiomatic
the way the singular was - was itself factually wrong: the plural IS the
standard idiom for the same physical/circumstantial sense ("La oficina
esta en buenas condiciones?" = "Is the office in good condition?").

### Confirmed false positives (reviewer's probe set)

- es "¿Cuál es la dirección de Forever Ghana? ¿La oficina está en buenas
  condiciones?", it "in buone condizioni", pt "em boas condições" - the
  plural physical-condition idiom in all three Romance languages.
- en "road conditions near Forever Ghana's office address", "weather
  conditions" - the same idiom in English (the fifth follow-up's
  plural-only fix did not go far enough).
- ru "в условиях пандемии" ("under pandemic conditions" - a
  circumstance/setting, not a policy document).
- no/da/sv "uansett vilkår"/"under alla villkor" ("regardless of
  terms"/"under all conditions" as a general expression).
- nl "onder voorwaarde dat" ("on condition that", a conjunction).
- de "unter der Bedingung" (the same conjunction sense), "die Bestimmung
  meiner Sendung" ("Bestimmung" here means "destination", a genuine
  directory/logistics question, not "provision/regulation").
- fr "dans ces conditions" ("under these circumstances"), "directives de
  mon médecin" (a doctor's instructions, not a Forever policy document).
- it "linee guida del mio medico" (a doctor's guidelines).
- es "directrices" (bare, same guideline-instruction ambiguity).

### Coordinator decision (implemented exactly): keep only words whose dominant sense is a policy document

**KEEP**, per language, exactly three categories:

1. The original, second-follow-up F1 set (already reviewed then),
   including German "Richtlinie"/"Richtlinien" - kept specifically because
   it was part of that original reviewed set, not a new addition (see the
   justification comment directly above `POLICY_WORDING_TERMS` in
   `config/directory_field_vocabulary.py`).
2. A distinct "regulation(s)" synonym where the language has one:
   `regulation(s)` (en), `reglamento(s)` (es), `règlement(s)` (fr, already
   in the F1 set), `Vorschrift(en)` (de), `reglement` (nl), `regolamento`/
   `regolamenti` (it), `regulamento`/`regulamentos` (pt), `määräykset`
   (fi, medium confidence, **plural only** - the coordinator's exact
   wording; the singular `määräys` is dropped along with everything else
   not explicitly named).
3. The COMPOUND "terms and conditions" phrase, matched as a whole
   multi-word phrase (so it cannot fire on a bare word inside it appearing
   alone elsewhere): en "terms and conditions"/"terms of" (already
   present, with the fifth follow-up's lookbehind); es "términos y
   condiciones"; fr "conditions générales"; de "Geschäftsbedingungen"/
   "AGB"/"Nutzungsbedingungen"; nl "algemene voorwaarden"; it "termini e
   condizioni"; pt "termos e condições"; no/da "vilkår og betingelser"/
   "salgsbetingelser"; sv "allmänna villkor"; fi "käyttöehdot"/
   "toimitusehdot"; ru "условия использования"/"условия продажи". The ru
   oblique cases of политика/правила (политике/политику/политикой,
   правилам/правилами/правилах) are also explicitly kept (named by the
   coordinator as an exception).

**DROP** everything else the fourth/fifth follow-ups added:

- Every BARE condition-family form, in every language: es condiciones, fr
  conditions, de Bedingung(en), nl voorwaarde(n), it condizioni, pt
  condições, fi ehto/ehdot, no/da/sv vilkår/villkor, ru
  условие/условия/условиях, sr uslov/uslovi/uslova/uslovima (Latin and
  Cyrillic).
- Every BARE guideline-family form: es directriz/directrices, fr
  directive(s), it "linea guida"/"linee guida", pt diretriz/diretrizes,
  fi ohje/ohjeet, nl richtlijn(en), no/da retningslinje/retningslinjer/
  retningslinjene, sv riktlinje/riktlinjer/riktlinjerna. (German
  "Richtlinie" is the sole survivor of this family - see KEEP #1 above.)
- de Bestimmung(en) specifically (the "destination" sense dominates).
- Serbian's oblique-case additions (politici/politiku/politikom,
  pravilima, and Cyrillic equivalents), and the Scandinavian definite
  plural rule forms (reglene/reglerne/reglerna): neither was explicitly
  named in the coordinator's KEEP list (only "the ru oblique cases" were),
  so both revert to their pre-fourth-follow-up state as the conservative,
  literal implementation of the decision - not a claim that they are
  themselves unsafe, but a deliberate choice to keep only what was
  explicitly authorized.
- English: `conditions?` and `guidelines?` removed from
  `DIRECTORY_POLICY_WORDING_RE`; `regulation(s)`, `terms and conditions`,
  and `terms of` (with the fifth follow-up's lookbehind) are kept.

### Also fixed: whitespace collapse and stale comments

- **(a) Whitespace collapse:** `_runtime_scope_intent` now computes
  `text = " ".join((message or "").split())` before any matching (it
  previously read `text = message or ""`). Without this, "in  terms  of"
  (double-spaced) would not match the fifth follow-up's
  `(?<!\bin\s)` lookbehind (which recognizes exactly one space), letting
  the "in terms of X" idiom leak through as if it were the accepted
  "terms of X" phrasing.
- **(b) Stale comments fixed:** the fourth follow-up's claim that nl
  "richtlijn"/no/da "retningslinje(r)"/sv "riktlinje(r)" were "already
  present" (imprecise, and now moot since those forms are dropped); the
  fifth follow-up's N1 paragraph, which still described "terms of" as
  firing inside "in terms of" as an accepted trade-off (that trade-off was
  actually fixed by the fifth follow-up's own lookbehind - the paragraph
  was updated to say so); `_runtime_scope_intent`'s docstring lines
  describing `DIRECTORY_POLICY_WORDING_RE` as "policy|rules" (stale since
  the fourth follow-up; now points to that regex's own comment for current
  coverage); the fifth follow-up's now-incorrect claim that the Romance
  plural "isn't idiomatic" for the physical-condition sense (removed,
  replaced with the corrected finding above).

### Before/after table

| Question (language) | Before this fix | After this fix |
| --- | --- | --- |
| es "¿Cuál es la dirección de Forever Ghana? ¿La oficina está en buenas condiciones?" | `policy` (0.0) | `directory` (8.0) |
| it "...L'ufficio è in buone condizioni?" | `policy` (0.0) | `directory` (8.0) |
| pt "...O escritório está em boas condições?" | `policy` (0.0) | `directory` (8.0) |
| en "What are the road conditions near Forever Ghana's office address?" | `policy` (0.0) | `directory` (8.0) |
| en "...What are the weather conditions?" | `policy` (0.0) | `directory` (8.0) |
| ru "...В условиях пандемии офис работает как обычно?" | `policy` (0.0) | `directory` (8.0) |
| no/da/sv "...Uansett vilkår/Under alle vilkår/Under alla villkor..." | `policy` (0.0) | `directory` (8.0) |
| nl "...Onder voorwaarde dat, is het kantoor open?" | `policy` (0.0) | `directory` (8.0) |
| de "...Nur unter der Bedingung, dass das Büro geöffnet ist?" | `policy` (0.0) | `directory` (8.0) |
| de "...Was ist die Bestimmung meiner Sendung?" | `policy` (0.0) | `directory` (8.0) |
| fr "...Dans ces conditions, le bureau est-il ouvert ?" | `policy` (0.0) | `directory` (8.0) |
| fr "...Je suis les directives de mon médecin." | `policy` (0.0) | `directory` (8.0) |
| it "...Seguo le linee guida del mio medico." | `policy` (0.0) | `directory` (8.0) |
| es "...Sigo las directrices de mi médico." | `policy` (0.0) | `directory` (8.0) |
| "What are the office hours...in  terms  of weekends?" (double-space) | `policy` (0.0) | `directory` (8.0) |
| es "reglamento"/ru dative "политике" (control, regulation/oblique kept) | `policy` (0.0), unchanged | `policy` (0.0), unchanged |
| en "regulations"/"terms and conditions" (control) | `policy` (0.0), unchanged | `policy` (0.0), unchanged |
| de "Richtlinie" + directory field (control) | `policy` (0.0), unchanged | `policy` (0.0), unchanged |
| es "términos y condiciones"/de "AGB" (new compound, control) | n/a (new) | `policy` (0.0) |

### Test assertions CHANGED (not deleted), per the coordinator's instruction

- `test_s1_reviewer_repro_regulation_condition_guideline_wording_stays_policy`:
  split into two tests. The `spanish-condiciones`/`french-conditions`/
  `italian-condizioni` cases moved to a new
  `test_s1_bare_condition_repros_now_resolve_directory_after_sixth_follow_up`,
  asserting `directory` instead of `policy`. `spanish-reglamento`/
  `russian-dative-politike` are unchanged (kept vocabulary).
- `test_s1_reviewer_repro_english_regulation_condition_guideline_wording_stays_policy`:
  the `english-guidelines` case moved to a new
  `test_s1_bare_guidelines_repro_now_resolves_directory_after_sixth_follow_up`,
  asserting `directory` instead of `policy`. `english-regulations`/
  `english-terms-and-conditions` are unchanged.
- `test_s1_localized_policy_wording_present_unit_new_terms`: 28 of its 40
  assertions changed from `True` to `False` (every bare condition/
  guideline-family form and the Serbian/Scandinavian unlisted additions);
  11 remain `True` unchanged (the regulation(s) equivalents and the ru
  oblique cases), and 1 remains `False` unchanged (the pre-existing
  "Cual es el telefono?" not-a-false-positive control). Each changed line
  carries an inline `# CHANGED: ...` comment naming the reason.
- `test_s2_romance_language_singular_condition_dropped_plural_kept`
  renamed to `test_s2_romance_language_bare_condition_forms_dropped_entirely`;
  all four `-plural-policy` cases changed from `True` to `False` (the
  bare plural is itself the idiom now recognized as a false positive);
  all four singular cases are unchanged (already `False`).
- `test_s2_non_romance_singular_condition_forms_unchanged` renamed to
  `test_s2_non_romance_bare_condition_forms_also_dropped_after_sixth_follow_up`;
  all five cases (de/nl/fi/ru/sr) changed from `True` to `False`.

### Sixth follow-up test run counts and exit codes

All commands run in the foreground with `--basetemp` under the assigned
scratchpad and `-o addopts=""`, `-p no:cacheprovider`.

1. The 20 new sixth-follow-up tests
   (`test_s6_compound_terms_and_conditions_phrases_present_across_languages`,
   `test_s6_richtlinie_kept_with_justification`,
   `test_s6_reviewer_idiom_repros_stay_directory` x16,
   `test_s6_whitespace_collapse_prevents_in_terms_of_leak`,
   `test_s6_whitespace_collapse_unit_control`), on
   `config/directory_field_vocabulary.py` and `app/retrieval/providers.py`
   reverted via `git stash` (tests kept): **19 failed, 1 passed,
   `EXIT=1`** - the 1 pre-existing pass is
   `test_s6_richtlinie_kept_with_justification` (Richtlinie was already
   present before this follow-up). `git stash pop` restored the fix
   afterward.
2. Full `test_r05_directory_protection_intent.py` plus targeted list
   (`test_opensearch_sections.py`, `test_retrieval_service.py`,
   `test_retrieval_rank_list_capture.py`, `test_demo_kenya_directory_gate.py`,
   `test_demo_directory_routing.py`, `test_directory_fields.py`,
   `tests/conversation`): **711 passed, `EXIT=0`.**
3. Full `tests/unit` (foreground, 600000ms timeout): **9035 passed, 13
   xfailed, `EXIT=0`**, 338.92s wall time.
4. `flake8` on the four changed files (`app/retrieval/providers.py`,
   `config/directory_field_vocabulary.py`, `utils/directory_fields.py`,
   `tests/unit/test_r05_directory_protection_intent.py`): one `W605`
   invalid-escape-sequence finding (a docstring, not a regex) was caught
   and fixed; final run: **no output, `FLAKE8_EXIT=0`.**
5. `git diff --check`: **no output, `DIFFCHECK_EXIT=0`.**

### Sixth follow-up limitations (reopened, stated honestly)

- **A genuine policy question using bare "conditions" once again resolves
  to `directory`/8.0 instead of `policy`/0.0** - exactly the shape this
  whole task exists to prevent, reopened deliberately: "What are the
  conditions of Forever Norway on the delivery address?" (English) or the
  identical shape in any covered language no longer suppresses the
  country bonus. Only the specific compound "terms and conditions" phrase
  is recognized now. This is the coordinator's explicit, accepted
  trade-off: false suppression (blocking a genuine directory question) was
  judged worse than this reopened gap (a genuine policy question
  occasionally keeping its directory bonus), given the review's 27/35
  false-positive rate on the wider vocabulary.
- **The same reopened gap applies to the guideline family**: "What are
  the guidelines of Forever Norway on the delivery address?" also
  resolves to `directory`/8.0 again, in every language except German
  ("Richtlinie", the sole kept guideline-family word).
- **Serbian's oblique political/pravila forms and the Scandinavian
  definite-plural rule forms (reglene/reglerne/reglerna) were reverted
  conservatively**, not because they were shown to be unsafe, but because
  the coordinator's KEEP list did not name them explicitly. A future
  review could reinstate them with an explicit decision either way.
- **The compound "terms and conditions" phrases are closed, literal,
  multi-word strings** - a paraphrase or reordering of the standard phrase
  in any language (e.g. a non-standard German phrasing that isn't
  "Geschäftsbedingungen"/"AGB"/"Nutzungsbedingungen") is not recognized,
  by design (recognizing partial or reordered phrases risks reopening the
  same bare-word ambiguity this follow-up just closed).

## Seventh follow-up (2026-09-18): coordinator review of 52cee7b (small fix)

A coordinator review of the sixth follow-up found one over-correction:
"reglene"/"reglerne"/"reglerna" (the definite PLURAL of no/da/sv "regel" =
"rule") were dropped alongside the (correctly dropped)
retningslinjene/riktlinjerna guideline-family definite forms, because
neither was "explicitly named" in the sixth follow-up's KEEP list. But
"reglene" etc. are rules-family, not guideline/condition-family - squarely
inside the KEEP list's own "policy/RULES family", and the ordinary way to
write "the rules of Forever Norge for..." in these three languages.

**Fix:** restored, narrowly, in `POLICY_WORDING_TERMS`
(`config/directory_field_vocabulary.py`): `no` "reglene", `da` "reglerne",
`sv` "reglerna" (the definite plural of "regel" only -
`retningslinjene`/`riktlinjerna` stay dropped), and `sr`
`pravilima`/`правилима` (the dative/instrumental plural of "pravila" =
rules; Serbian's other, unrestored oblique forms - `politici`, `politiku`,
`politikom`, and the entire `uslov`/`услов` condition-family - stay
dropped exactly as the sixth follow-up left them).

| Question (language) | Before this fix | After this fix |
| --- | --- | --- |
| no "Hva er reglene til Forever Norge for leveringsadressen?" | `ambiguous` (0.0) | `policy` (0.0) |
| da "Hvad er reglerne for Forever Norge for leveringsadressen?" | `ambiguous` (0.0) | `policy` (0.0) |
| sv "Vad är reglerna för Forever Norge för leveransadressen?" | `ambiguous` (0.0) | `policy` (0.0) |
| sr "Koja su pravilima Forever Norge za adresu isporuke?" | `directory` (8.0) | `policy` (0.0) |
| no/sv "retningslinjene"/"riktlinjerna" + directory field (control) | `directory` (8.0), unchanged | `directory` (8.0), unchanged |
| sr "politici"/"uslovi" (control, still dropped) | `directory` (8.0), unchanged | `directory` (8.0), unchanged |
| no "som regel" idiom + directory field (N1 control, unchanged) | `policy` (0.0), unchanged | `policy` (0.0), unchanged |

Test assertions updated in `test_s1_localized_policy_wording_present_unit_new_terms`
(four lines, `False` -> `True`, marked "CHANGED AGAIN (seventh follow-up)"
in an inline comment): no "Hva er reglene?", da "Hvad er reglerne?", sv
"Vad är reglerna?", sr "pravilima".

### Seventh follow-up test run counts and exit codes

All commands run in the foreground with `--basetemp` under the assigned
scratchpad and `-o addopts=""`, `-p no:cacheprovider`.

1. The 8 new `test_s7_*` tests, on `config/directory_field_vocabulary.py`
   reverted via `git stash` (tests kept): **5 failed, 3 passed,
   `EXIT=1`** - the 3 pre-existing passes are the regression-guard
   controls (retningslinjene/riktlinjerna, politici/uslovi, and the "som
   regel" idiom control), unaffected by this restoration either way.
   `git stash pop` restored the fix afterward.
2. Targeted list (`test_r05_directory_protection_intent.py`,
   `test_opensearch_sections.py`, `test_retrieval_service.py`,
   `test_retrieval_rank_list_capture.py`, `test_demo_kenya_directory_gate.py`,
   `test_demo_directory_routing.py`, `test_directory_fields.py`,
   `tests/conversation`): **719 passed, `EXIT=0`.**
3. Full `tests/unit` (foreground, 600000ms timeout): **9043 passed, 13
   xfailed, `EXIT=0`**, 415.11s wall time.
4. `flake8` on the four changed files: **no output, `FLAKE8_EXIT=0`.**
5. `git diff --check`: **no output, `DIFFCHECK_EXIT=0`.**
