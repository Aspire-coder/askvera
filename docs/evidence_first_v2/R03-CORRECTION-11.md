# R03 correction 11 - invert the trust default for the Finnish anaphoric follow-up

Date: 2026-09-18
Scope: R03 Finnish anaphoric follow-up decision only (`_resolve_finnish_
anaphoric` and its helpers in `app/orchestrator/chat_orchestrator.py`), local
and offline. Continues the same worktree/branch as corrections 8-10.

## Review findings (final independent review of correction 10)

The reviewer found a fourth class of hole in the residue-detection design
corrections 8-10 built up, all the same root cause: **residue detection over
open-ended Finnish morphology keeps missing new forms**. Reproduced before
any fix, against commit `51a9c69`:

1. **Negated olla.** `"Entä jos hän ei ole ugandassa?"` and `"...ei ole
   ollut ugandassa?"` resolved **TRUSTED** to Uganda, query rewritten to
   `"...ei ole Uganda?"`. `"...ei ole koskaan asunut ugandassa?"` also
   resolved trusted - the adverb `"koskaan"` pushed the verb to offset 3,
   outside the negation window (2) correction 9 tuned for `"ei ole
   asunut"`.
2. **Clitics on unconfigured places, verb-after-place order, long gaps.**
   `"Entä jos hän asuu narniassakin?"`, `"...asuu suomessakin?"`, `"...asuu
   suomestakin?"`, `"Entä jos hän narniassa asuu?"`, `"...asuu nyt jo monta
   vuotta narniassa?"` all resolved `resolved, code=None,
   no_place_evidence` - i.e. fully **TRUSTED**, keeping the prior Tanzania
   anchor - because none of these forms tripped the old case-ending residue
   test (the clitic doesn't end in a case ending; word order and adverb gap
   both defeated the old backward-looking verb window).
3. **Compound names.** `"Entä jos hän asuu Pohjois-Koreassa?"` (North
   Korea) resolved to **KR** (South Korea), query rewritten to `"...asuu
   Pohjois-Korea?"` - a **wrong market with trusted provenance**. The old
   tokenizer split the hyphenated compound into `"pohjois"` and
   `"koreassa"`, and `"koreassa"` alone is South Korea's configured
   inessive form.

Every one of these is the same failure mode: the residue detector never
imagined the shape, so it silently fell through to "no place evidence
found" and trusted the fallback ordering. Adding a seventh special case
cannot converge, because Finnish morphology is open-ended - there will
always be another clitic, another word order, another adverb, another
compound.

## Design decision: invert the default

Correction 11 stops chasing morphology and inverts the default. Trusted
resolution and market substitution now happen **only** when the whole
message matches one of two narrow, documented shapes. Everything else that
would previously have been trusted becomes `unresolved` (context retained
for retrieval, no `prior_user_turn_id`, no substitution) or `standalone`
where correction 7's existing standalone rules still apply.

**Cost asymmetry**: a false `unresolved` only means V2's trusted fallback
ordering does not fire for that turn. A false `resolved` can retrieve the
wrong market outright (finding 3) or silently invert a negated claim
(finding 1). The asymmetry justifies erring toward `unresolved`.

### T1 - market swap (`AIOrchestrator._finnish_market_swap_shape`)

`"Entä jos hän"` (or `"hänen"`)
+ an optional run of the closed temporal/aspectual adverb set
  `_FINNISH_TEMPORAL_ASPECTUAL_ADVERBS` = `{nyt, edelleen, yhä, vielä,
  pysyvästi, nykyään, jo, taas}` (accent-stripped) - a small, documented set,
  **not** a place list
+ a non-negated residence/location verb from the existing vocabulary (the
  strong `asu-` stem, the weak stems, the `kotoisin` idiom, or any olla form
  - olla's correction-10 complement-shape restriction does not apply here,
  because T1 always supplies an exact locative complement) - **any**
  negation token (`ei`/`eikä`/`enää`) **anywhere in the message**
  disqualifies T1 outright; there is no window to outrun any more
+ an optional run of the same adverbs
+ **exactly one** configured-market inessive token, matched as a **whole**
  token via a hyphen-preserving tokenizer (`_finnish_shape_words`) - a
  hyphenated compound counts as one token, so `"Pohjois-Koreassa"` can never
  match the bare stem `"koreassa"`
+ an optional trailing clause built only from the closed
  `_FINNISH_ANAPHORIC_FUNCTION_WORDS` vocabulary (e.g. `"ja työskentelee
  siellä"`)
+ end punctuation.

### T2 - non-place follow-up (`AIOrchestrator._finnish_non_place_shape`)

`"Entä jos hän"` + content with:
- **no** locative-case-bearing token at all, checked on the bare token AND
  on the token with a clitic (`-kin`/`-ko`) stripped, so `"narniassakin"` is
  still caught even though the clitic suffix itself does not end in a case
  ending;
- **no** capitalised non-initial token;
- **no** configured-market name stem.

Context is kept and trusted, but nothing is substituted (a role or ordinary
topic follow-up, e.g. `"Entä jos hän on johtaja?"`).

**Known limitation, accepted rather than chased**: the same case-ending test
also flags an ordinary time illative (`"...24 kuukauteen"`) and a handful of
unrelated words that happen to end in a doubled vowel plus `"n"` (`"mukaan"`,
`"jälkeen"`). These fall to `unresolved` rather than being special-cased,
per the cost asymmetry above.

### Everything else

A message fitting neither T1 nor T2 is untrusted: `unresolved` by default,
or `standalone` where a correction-7 standalone rule already applies
(competing/conflicting market signals, an unrecognised capitalised place, a
strong `asuu` verb governing an unknown place, or a negated residence claim
the old windowed check still catches). None of correction 7's standalone
triggers needed to change - the reviewer's four repro classes were never
misclassified as `standalone`, only as `resolved`.

## Implementation

`_resolve_finnish_anaphoric` keeps its pre-existing residue scan
(`_finnish_collect_residue_signals`, extracted unchanged, purely to keep the
method body readable) to decide `standalone` and `unresolved` exactly as
before. The **only** change is at the two places that scan used to return
`resolved`:

- `resolved, code=None` (no place evidence collected) is now re-gated
  through `_finnish_non_place_shape` (T2). If T2 does not match, the
  outcome downgrades to `unresolved, reason=t2_shape_not_matched`.
- `resolved, code=<market>` (exactly one configured inessive code
  collected) is now re-gated through `_finnish_market_swap_shape` (T1),
  which independently re-tokenizes with the hyphen-preserving tokenizer and
  must find the **same** code. If it does not (either because the shape
  does not match at all, or - the compound-name bug - because the correct,
  hyphen-aware tokenization finds no configured place where the old
  tokenizer's split halves found the wrong one), the outcome downgrades to
  `unresolved, reason=t1_shape_not_matched`.

No other branch of `_resolve_finnish_anaphoric` changed. `_FINNISH_NEGATION_
WINDOW` and `_FINNISH_RESIDENCE_VERB_WINDOW`-based verb-tier lookup
(`_finnish_residence_verb_tier`, `_finnish_negation_scopes_residence`) are
kept exactly as they were for `standalone`/`unresolved` classification, but
T1 no longer uses any window arithmetic at all for granting trust - it
walks the message once, left to right, and either the exact sequence is
there or it is not.

This nets out to **less new logic than correction 10**, not more: two small,
self-contained shape-matchers (roughly 60 lines combined) replace what would
otherwise have been a fifth and sixth special case bolted onto the residue
scan.

## Reviewer repros - fixed

All nine reproduced forms now resolve `unresolved` (context kept, no
substitution, no wrong market) instead of the previous wrongly-trusted
outcome:

| Message | Correction 10 (`51a9c69`) | Correction 11 |
| --- | --- | --- |
| `"...ei ole ugandassa?"` | resolved UG (wrong: negation ignored) | unresolved |
| `"...ei ole ollut ugandassa?"` | resolved UG | unresolved |
| `"...ei ole koskaan asunut ugandassa?"` | resolved UG | unresolved |
| `"...asuu narniassakin?"` | resolved, code=None (trusted, Tanzania kept) | unresolved |
| `"...asuu suomessakin?"` | resolved, code=None | unresolved |
| `"...asuu suomestakin?"` | resolved, code=None | unresolved |
| `"...hän narniassa asuu?"` | resolved, code=None | unresolved |
| `"...asuu nyt jo monta vuotta narniassa?"` | resolved, code=None | unresolved |
| `"...asuu Pohjois-Koreassa?"` | resolved **KR** (wrong market) | unresolved |

Covered by new tests in `tests/evidence_first_v2/test_r03_context_capture.py`:
`test_negated_olla_forms_are_never_trusted_regardless_of_gap`,
`test_clitic_on_an_unconfigured_place_is_never_trusted`,
`test_verb_after_place_word_order_is_never_trusted`,
`test_adverb_gap_wider_than_the_old_fixed_window_is_never_trusted`,
`test_hyphenated_compound_name_never_matches_the_wrong_markets_stem`.

## Reference forms kept trusted

As required, all four reference forms remain `resolved`:

- `"Entä jos hän asuu nyt pysyvästi ugandassa?"` - T1 (two adverbs after the verb).
- `"Entä jos hän asuu edelleen ugandassa?"` - T1 (one adverb after the verb).
- `"Entä jos hän asuu ugandassa ja työskentelee siellä?"` - T1 (trailing
  function-word-only clause).
- `"Entä jos hän on johtaja?"` - T2 (no place, no capitalised token, no
  market stem).

Every other existing correction-8/9/10 single-occurrence market-swap test
(`"Entä jos hän on Ugandassa?"`, the accented-key tests, the `on`/`asuu`/
`työskentelee` verb variants, the uppercase-message variant, etc.) still fits
T1 exactly as before and is unaffected.

## Trust changes: what moved from `resolved` to `unresolved`

Every one of these is a **documented, deliberate** narrowing - trusted to
unresolved, never the reverse - required by the stricter T1/T2 shapes. No
`standalone` outcome changed.

| Test | Before (`resolved`) | After (`unresolved`) | Why |
| --- | --- | --- | --- |
| `test_configured_language_follow_up_uses_only_its_own_stored_turn` (correction 7 baseline) | trusted | unresolved | T2's "no capitalised non-initial token" rule reads "Sponsored Recognized Manager" / "Recognized Managereita" as capitalised tokens, same as it would an unrecognised proper-noun place. |
| `test_finnish_possessive_inessive_token_is_not_mistaken_for_illative_residue` (correction 8) | trusted | unresolved | Same capitalised-role-title reason; `"tiimissään"` itself is still correctly read as non-place. |
| `test_nfkd_expanding_character_does_not_crash_or_misalign` (correction 9 BLOCKER) | trusted, substituted Uganda | unresolved, no substitution | `"vuotta"` ("years") sits between the verb and the place and is not one of T1's closed adverbs, so the shape no longer matches. The no-crash/no-misalignment guarantee this test exists for is unaffected and still asserted. |
| `test_ordinary_case_marked_nouns_outside_residence_context_are_trusted` -> renamed `..._are_unresolved` (correction 9 SHOULD-FIX, all 7 parametrized cases) | trusted | unresolved | T2 withholds trust from ANY locative-case-shaped token with no verb-adjacency gate at all; several of these ordinary words (`"kuukauteen"`, `"mukaan"`, `"tilille"`, `"tasolle"`, `"jälkeen"`, `"toimistossa"`, `"netissä"`) happen to end in a real or illative-approximated case ending. This is exactly the accepted cost-asymmetry trade-off, applied in bulk to a test that was itself created to chase the opposite failure mode. |
| `test_repeated_resolved_market_is_substituted_at_every_occurrence` -> renamed `test_repeated_market_mention_outside_the_t1_shape_stays_unresolved` (correction 9 NOTE 5) | trusted, both occurrences substituted | unresolved, no substitution | T1 requires exactly one configured-market token, with everything after it drawn from the closed function-word vocabulary; a second literal `"ugandassa"` in the trailing clause is not a function word, so the message no longer fits T1. |

No correction-7/8/9/10 assertion was removed or loosened toward more trust;
every change above narrows trust, and the rationale is recorded both here
and in the test's own updated docstring.

## Removed-line audit

`git diff e3b399a -- tests/evidence_first_v2/test_r03_context_capture.py`
after this correction: **1 line removed** (the single `assert
provenance["status"] == "resolved_dependent_follow_up"` in
`test_configured_language_follow_up_uses_only_its_own_stored_turn`,
replaced by the stricter `assert provenance == {"provenance": "runtime",
"status": "unresolved"}` documented above). Before this correction (against
`51a9c69`), that same diff had **zero** removed lines (`e3b399a`..`51a9c69`
was pure insertion). No other correction-7 assertion changed.

`git diff 51a9c69 -- tests/evidence_first_v2/test_r03_context_capture.py`
after this correction: the removed lines are exactly the five assertions/
docstrings listed in the table above, each replaced by a stricter assertion
in the same test function - no test function and no assertion was deleted
outright.

## Runs

Focused suite:

```
<PYTHON> -m pytest tests/evidence_first_v2/test_r03_context_capture.py tests/unit/test_demo_multilingual_followups.py tests/unit/test_demo_followup_resolution.py tests/unit/test_retrieval_canary_delivered_answer.py tests/unit/test_retrieval_rank_list_capture.py -p no:cacheprovider --basetemp <TEMP>\pytest-r03c11
```

Result: **all passed, exit 0**.

Compatibility suite:

```
<PYTHON> -m pytest tests/unit/test_chat_orchestrator.py tests/unit/test_evidence_routing.py tests/unit/test_opensearch_sections.py tests/unit/test_retrieval_service.py tests/unit/test_retrieval_rank_list_capture.py tests/evidence_first_v2 -p no:cacheprovider --basetemp <TEMP>\pytest-r03c11
```

Result: **546 passed, 1 failed, exit 1**. The sole failure is the same
pre-existing, unrelated `test_offline_isolation.py::test_package_imports_
use_a_narrow_allowlist` (`capture_provenance` relative-import allowlist
mismatch in `scope_aware_fusion.py`) every prior R03 correction has
reported, unchanged by this correction.

Lint:

```
<PYTHON> -m flake8 --ignore=E203,E402,E501,C901 app/orchestrator/chat_orchestrator.py scripts/evidence_first_v2/capture_read_only_retrieval.py scripts/evidence_first_v2/finalize_read_only_capture.py tests/evidence_first_v2/test_r03_context_capture.py
```

Scoped lint: **exit 0**. Plain `flake8` (disclosure only, same files):
**exit 1**, with the same two pre-existing baseline findings in untouched
scripts as every prior correction (`capture_read_only_retrieval.py` C901,
`finalize_read_only_capture.py` E402); `chat_orchestrator.py` is NOT flagged
(the residue-collection loop was extracted into
`_finnish_collect_residue_signals` specifically to keep the new gated
`_resolve_finnish_anaphoric` under the C901 threshold), and the test file is
not flagged.

`git diff --check`: **exit 0**.

## Limitations carried forward

- T2's blanket locative-case exclusion is a known false-negative source for
  ordinary Finnish words that are not places at all (time illatives,
  `"mukaan"`, `"jälkeen"`, etc.) - accepted per the cost asymmetry rather
  than special-cased.
- T1/T2 both operate on accent-stripped text, so ä/ö are not distinguished
  from a/o - unchanged from earlier corrections.
- The clitic-stripping set (`-kin`, `-ko`) is closed and grown only from
  forms actually seen in the reviewer's repros, not a general Finnish
  clitic stripper; a clitic outside this set on an unconfigured place would
  still fall through only because its case ending is independently visible
  without stripping in most real forms, but this is not guaranteed for
  every possible clitic combination.
- The temporal/aspectual adverb set is closed and documented; a genuine
  Finnish adverb outside this set between the verb and the place (as with
  `"vuotta"` in the correction-9 NFKD test, not itself an adverb but
  illustrative of the same effect) will correctly fail T1 and fall to
  `unresolved` rather than being trusted - this is intentional, not a gap.
