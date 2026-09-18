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

## Limitations

- **Language coverage of the classifier is English-only for the
  *recognition* side.** `SPONSORING_QUESTION_RE`,
  `DIRECTORY_OPERATIONAL_QUESTION_RE`, `DIRECTORY_POLICY_WORDING_RE`, and
  `_directory_guard_topic_match`'s component regexes all match English
  vocabulary only. A genuinely directory-intentioned question phrased
  entirely in another language (no English loanword, no recognized market
  alias) will not be classified as `directory`/`international_sponsoring`
  and will lose the country-match bonus even though it should keep it - this
  fix does not add multilingual keyword coverage.
- **The *suppression* side is not language-limited**, because it is the
  default outcome whenever nothing matches (`ambiguous`, or `policy` when
  `include_global_documents` is also false): a policy question naming a
  market in French or Finnish is correctly suppressed for the same reason
  the English case is, without needing any French/Finnish vocabulary in the
  classifier at all. Verified directly for French and Finnish in the new
  test file.
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
