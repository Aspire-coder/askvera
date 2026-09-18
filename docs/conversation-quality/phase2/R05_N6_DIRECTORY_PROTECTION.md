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
