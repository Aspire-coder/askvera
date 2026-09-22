# Terra handoff - R03 correction 8 (earned trust redesign)

Date: 2026-09-18
Scope: R03 Finnish anaphoric follow-up decision only, local and offline.
Next owner: fresh Sol review, then Astra. R04 remains paused.

## Why this is a redesign, not correction 8 of the same idea

The Finnish `Entä jos hän...` place resolution went through seven
corrections, and an independent review (Fable) of correction 7 again found
the same class of defect: the code examined tokens one at a time and
**trusted by default**, so every place signal it failed to collect silently
left a trusted resolution standing. Coordinator direction (Claude Opus) was
to stop patching that shape and build one earned-trust decision instead.

## Design

One function, `AIOrchestrator._resolve_finnish_anaphoric`, is now the single
source of truth. It is read by both query construction and provenance
through a thin wrapper, `_finnish_anaphoric_trust_decision`, which no
consumer bypasses:

- `_needs_history_context` uses only the `decision`.
- `_contains_topic_shift_marker` uses only the `decision`.
- `_has_ambiguous_finnish_lowercase_complement` (provenance) checks for
  `decision == "unresolved"`.
- `_canonicalize_finnish_anaphoric_market` (the retrieval query) uses
  `code`/`place` only when `decision == "resolved"`.

`_resolve_finnish_anaphoric` collects evidence over the **whole message**,
exhaustively, before deciding anything:

1. Exact configured inessive forms, matched on whole normalized tokens.
   `_finnish_inessive_market_codes` now normalizes its keys with the same
   accent-stripping the tokens go through, instead of only casefolding them,
   which was why part of the map (Fable's ~2,373-key estimate; 667 measured
   in this worktree's actual market/alias config) could never match.
2. Direct market mentions and shared-office record countries, matched with
   `find_market_mentions(message)` / `find_shared_office_record_countries
   (message)` over the **entire message** - the same matcher the rest of the
   system uses, which already understands multi-word names. The prior code
   called this per token, so "United States", "South Africa" and "United
   Kingdom" were invisible.
3. Place-shaped residue: any token carrying a Finnish inner-locative or
   directional case ending (inessive `-ssa`/`-ssä`, elative `-sta`/`-stä`,
   adessive `-lla`/`-llä`, ablative `-lta`/`-lta`, allative `-lle`, or a short
   illative approximated as a doubled vowel plus "n", e.g. "Ugandaan") that
   is not accounted for by a code collected above, or any capitalized token
   with that ending. This is a closed grammatical shape test
   (`_FINNISH_LOCATIVE_CASE_ENDING`), not a place list, documented in one
   place in `chat_orchestrator.py`.

A closed set of known Finnish function/connector words used inside this
configured form (`_FINNISH_ANAPHORIC_FUNCTION_WORDS`) is excluded from
residue scoring, because a few of them coincidentally end in a
locative-shaped suffix ("edelleen", "siellä", the inessive-possessive
"tiimissään"). The doubled-vowel illative pattern additionally excludes an
immediately preceding "ss", so "tiimissään" (inessive + possessive, not
illative) is never mistaken for a place.

TRUSTED `resolved` (with a market to substitute) only when: exactly one
market code was collected in total; it came from the supported configured
inessive form (a bare direct-name mention with no inessive/residence support
behind it keeps context but is `unresolved`, since a name mention alone is
not a residence claim); every place-shaped token is accounted for by that
same market; and no negation from the closed set `{"ei", "eikä", "enää"}`
scopes the residence verb (`asuu`/its negated stem `asu`). A follow-up with
**no** place evidence at all is also trusted, with `code = None` (a plain
dependent question, e.g. a role follow-up) - this is unchanged from
correction 7's behavior and is required by the existing role-follow-up
control.

Everything else is not trusted:

- A capitalized unknown place, more than one competing code, or an unknown
  place directly asserted as the residence (`asuu <unknown>`) fails closed
  as `standalone` - never guess a market.
- A negated residence claim over an otherwise single, accounted-for code
  also fails closed as `standalone` (trusting it would assert the opposite
  of what was said).
- Any other unaccounted-for place-shaped residue (an unsupported case form
  of a configured market, or an ambiguous lowercase noun after `on`/
  `työskentelee`) keeps the prior anchor for retrieval but is recorded as
  `unresolved` - never a trusted resolved follow-up, never a
  `prior_user_turn_id`.

A second, smaller fix: the exact accented span substituted back into the
retrieval query (`_canonicalize_finnish_anaphoric_market`) now comes from a
new `_follow_up_raw_tokens` helper that preserves the original accented
surface text, instead of the accent-stripped token that correction 7 (and
every prior correction) used for the substitution. Without this, fixing the
dead-key normalization (item 1 above) would make the map *lookup* succeed
for an accented input but the display substitution would silently no-op,
because it searched the original message for the unaccented spelling.

## Removed special cases

- `_finnish_location_phrase_cue` - dead code (defined, never called anywhere
  in the codebase). Removed rather than carried forward.
- The `allow_state_cue` parameter on `_is_finnish_location_phrase` - the
  distinction it encoded (whether "on"/"työskentelee" count as a strong
  residence cue for an unknown place) is now handled uniformly by the
  evidence/decision split: an unaccounted lowercase residue token is always
  `unresolved` unless it is specifically the bounded `asuu`/`asu` terminal
  phrase, which is always `standalone`. No separate code path needed it.
- The old `_finnish_anaphoric_place_resolution` returned an overloaded
  3-tuple `(code, place, unresolved_bool)` that conflated "no market found"
  with "actively untrusted" (both surfaced as an empty code). It is replaced
  by the explicit 3-way `_FinnishAnaphoricResolution.decision`, so a caller
  can no longer accidentally read "no code" as "safe to treat as resolved".
- Per-token `find_market_mentions(place)` calls inside the token loop are
  gone; direct/shared-office mentions are now collected once, over the whole
  message, before the loop runs.

Net effect in `app/orchestrator/chat_orchestrator.py`: 213 lines added, 86
removed (net +127), most of which is documentation of the closed grammatical
sets this design explicitly asked to keep "in one documented place" rather
than scattered as inline comments the way the case/negation logic was spread
across three prior methods. No behavior-bearing special case survived to be
duplicated.

## Reproductions - before and after

All reproduced against the frozen Tanzania history: "How does Forever
Tanzania pay bonuses to FBOs who live outside the country?"

| Finding | Input | Before (correction 7) | After (correction 8) |
| --- | --- | --- | --- |
| Fable BLOCKER 1a | `Entä jos hän on United States mutta asuu ugandassa?` | Resolved Uganda, trusted, `prior_user_turn_id` set | `standalone` (`not_dependent`); neither Tanzania nor Uganda in query |
| Fable BLOCKER 1b | `...asuu ugandassa mutta työskentelee South Africa?` | Resolved Uganda, trusted | `standalone` |
| Fable BLOCKER 1c | `...asuu ugandassa mutta työskentelee United Kingdom?` | Resolved Uganda, trusted | `standalone` |
| Fable SHOULD-FIX 2a (illative) | `Entä jos hän muuttaa ugandaan?` | Kept Tanzania, trusted `resolved_dependent_follow_up` | Keeps Tanzania anchor, `unresolved` (untrusted) |
| Fable SHOULD-FIX 2b (elative) | `Entä jos hän on kotoisin ugandasta?` | Kept Tanzania, trusted | Keeps Tanzania anchor, `unresolved` |
| Fable NOTE 3 (negation) | `Entä jos hän ei asu ugandassa?` | Resolved Uganda, trusted | `standalone`; neither market in query |
| Fable NOTE 4 (dead accented key) | `Entä jos hän on Argentínassa?` (probe; "Argentína" is a real single-word alias in this worktree's config) | Never matched (dead key); fell through as an unaccounted capitalized place | Resolves to Argentina, trusted, and the accented span is replaced in the query text |

Controls that already worked and must keep working:

| Control | Input | Outcome |
| --- | --- | --- |
| Single-word direct conflict (unchanged) | `Entä jos hän on Yhdysvallat mutta asuu ugandassa?` | `standalone` |
| Single-word direct conflict (unchanged) | `Entä jos hän on Kenya mutta asuu ugandassa?` | `standalone` |
| Already-fixed forms (correction 6/7) | `...asuu edelleen ugandassa?`, `...asuu nyt pysyvästi ugandassa?`, `...asuu ugandassa ja työskentelee siellä?` | All still resolve to Uganda, trusted |
| Pseudo-substring guard | `Entä jos hän asuu pseudougandassa?` | `standalone`, no accidental Uganda match |
| Capitalized unknown | `Entä jos hän on Atlantisissa?` / `...Berliinissä?` | `standalone` |
| Role follow-up, no place at all | `Entä jos hän on johtaja?` | Resolved, trusted, `code=None` |
| Configured-language follow-up with possessive-inessive noise | `...ja hänen tiimissään on ensimmäisen sukupolven Recognized Managereita?` | Resolved, trusted (false-positive residue avoided) |
| No history / cross-session | (see test file) | Unchanged - standalone without history, opaque per-session `prior_user_turn_id` |

## New probe: bare direct-name mention alone

`Entä jos hän on Kenya?` (no inessive/residence support) now records
`unresolved` rather than a trusted resolved follow-up, even though the
separate, pre-existing `_replace_directory_target` step still swaps the
anchor's named market (that mechanism is unrelated to this Finnish decision
and untouched by this correction). This was not explicitly a Fable finding,
but follows directly from "trusted only when the code came from the
supported configured inessive form."

## Finland probe (acceptance criterion)

`Entä jos hän asuu Suomessa?` - "Suomessa" is not a configured single-word
inessive alias for Finland in this worktree (the configured market name is
"Finland"), so it is an unrecognised **capitalized** place candidate. Per the
earned-trust rule this fails closed exactly like any other capitalized
unknown place: **standalone**, dropping the Tanzania anchor rather than
guessing at a market.

## Test commands and results

Focused suite (adds 11 new tests to the R03 file: 43 -> 54 passed there):

```
<PYTHON> -m pytest tests/evidence_first_v2/test_r03_context_capture.py tests/unit/test_demo_multilingual_followups.py tests/unit/test_demo_followup_resolution.py tests/unit/test_retrieval_canary_delivered_answer.py tests/unit/test_retrieval_rank_list_capture.py -p no:cacheprovider --basetemp <TEMP>\pytest-r03c8
```

Result: **472 passed, exit 0**.

Compatibility suite:

```
<PYTHON> -m pytest tests/unit/test_chat_orchestrator.py tests/unit/test_evidence_routing.py tests/unit/test_opensearch_sections.py tests/unit/test_retrieval_service.py tests/unit/test_retrieval_rank_list_capture.py tests/evidence_first_v2 -p no:cacheprovider --basetemp <TEMP>\pytest-r03c8
```

Result: **511 passed, 1 failed, exit 1**. The sole failure is the
pre-existing, separately queued `test_offline_isolation.py::
test_package_imports_use_a_narrow_allowlist` (the `capture_provenance`
relative-import isolation allowlist mismatch in `scope_aware_fusion.py`).
Unchanged and untouched by this correction, as instructed.

Scoped lint (the project's established baseline ignores):

```
<PYTHON> -m flake8 --ignore=E203,E402,E501,C901 app/orchestrator/chat_orchestrator.py scripts/evidence_first_v2/capture_read_only_retrieval.py scripts/evidence_first_v2/finalize_read_only_capture.py tests/evidence_first_v2/test_r03_context_capture.py
```

Result: **exit 0**.

Plain `flake8` (disclosure only, same files):

```
<PYTHON> -m flake8 app/orchestrator/chat_orchestrator.py scripts/evidence_first_v2/capture_read_only_retrieval.py scripts/evidence_first_v2/finalize_read_only_capture.py tests/evidence_first_v2/test_r03_context_capture.py
```

Result: **exit 1**, but the only findings are pre-existing baseline items in
files this correction did not touch: `scripts/evidence_first_v2/
capture_read_only_retrieval.py:234` (`C901 '_capture' is too complex (18)`)
and `scripts/evidence_first_v2/finalize_read_only_capture.py:17` (`E402
module level import not at top of file`). Neither
`app/orchestrator/chat_orchestrator.py` nor the test file is flagged even
under the unscoped run.

`git diff --check`: **exit 0**.

## Snapshot identity

Base HEAD: `5b1d33fe37167e2a1384e47ac0fa1fe08ea3aee7` (this worktree's branch
point is the byte-identical correction-7 snapshot, commit `e3b399a`).

Selected-file snapshot SHA-256 (same four files, same canonical format as
prior corrections - UTF-8 `path` line, LF, lowercase SHA-256 of that file's
exact bytes, LF, one final LF; manifest was 463 bytes):

`47ccc1db3b257331c6ca9cec29988b203acb40bed8e9bf1498a13ef93b86ebd0`

## Limitations

- **Approximate morphology, not a full analyzer.** The case-ending set is a
  closed, documented shape test on accent-stripped text; ä/ö are not
  distinguished from a/o once stripped, and the illative approximation
  (doubled vowel + "n", or "h" + vowel + "n") does not cover every Finnish
  illative allomorph (e.g. a stem already ending in a long vowel/diphthong
  that takes "-hVn" without a preceding "h" in the base form is not modeled
  beyond the one `h[aeiouy]n$` branch added for "maahan"-style forms).
- **All-caps input.** `ENTÄ JOS HÄN ASUU UGANDASSA?` still works (existing
  control, casefolded before matching), but the capitalized-vs-lowercase
  residue distinction for an *unknown* place is meaningless once a message
  is fully upper-cased - an all-caps unknown place is scored as lowercase
  residue (ambiguous/unresolved), not as the stronger capitalized-unknown
  signal. This is unchanged from every prior correction and is a genuine gap
  for shouted input.
- **Multiword inflected forms.** Only single-word configured market names
  get an inessive form in `_finnish_inessive_market_codes` (by design - a
  multi-word inessive form such as "Etelä-Afrikassa" is not modeled). A
  multi-word market can only be recognized in its direct/nominative spelling
  via `find_market_mentions`, never in an inflected form.
- **Negation scope is a bounded window, not full-sentence.**
  `_FINNISH_RESIDENCE_NEGATION_TOKENS` fires when the negation word is
  followed, within `_FINNISH_NEGATION_WINDOW` (2) tokens, by a residence or
  location verb stem. **Correction 9 update:** this note originally (and
  incorrectly) said "ei enää asu" was unhandled - it was already covered
  even under correction 8's narrower adjacency check, since "enää" is
  itself one of the negation tokens and the residence-verb token followed
  it one position later. What correction 8 actually missed was the perfect
  tense's auxiliary ("ei ole asunut", the verb two tokens after "ei") - see
  the correction 9 section below. A negation separated by more than the
  2-token window (an intervening adverb between "ei"/"ole" and the verb) is
  still not recognized and would be scored as a plain, non-negated claim.
- **Function-word list is closed and hand-picked.** It was grown only from
  forms that actually appear in this configured follow-up's existing tests
  and reproductions, not a general Finnish stop-word list. A new connector
  or adverb that happens to end in a locative-shaped suffix could still be
  mis-scored as residue until added to the list.
- No AWS, network, OpenSearch, live model, reindex, install, push, merge, or
  deployment occurred. Local tests prove decision correctness for the
  reproduced and probed inputs, not live ranking, answer quality, or release
  readiness.

See `docs/evidence_first_v2/R03-CORRECTION-9-TOKENIZATION-AND-RESIDUE.md` for
the correction that followed this one (a tokenization blocker and a
redefinition of place residue), which supersedes several details above -
most importantly the tokenization approach and the residue definition. This
file is kept as the historical record of correction 8's own design and is
not hand-edited further; read correction 9's handoff for the current state.

Send this exact snapshot to a fresh Sol review, then Astra final review.
Stop after review; R04 remains paused.
