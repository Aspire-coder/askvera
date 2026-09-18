# Terra handoff - R03 correction 9 (tokenization blocker + residue redefinition)

Date: 2026-09-18
Scope: R03 Finnish anaphoric follow-up decision only, local and offline.
Next owner: fresh Sol review, then Astra. R04 remains paused.

## Review findings (Fable, on correction 8, commit `07b6677`)

Fable accepted correction 8's earned-trust design: all four of its own prior
findings closed, the three reference forms still resolve, and `unresolved`
never activates trusted fusion. It returned **NEEDS CORRECTION** for six new
findings, reproduced below before any fix, and closed in this correction.

## 1 BLOCKER - tokenization

`_follow_up_raw_tokens` (unfolded) and `_follow_up_tokens` (folded) were
tokenized independently and assumed to stay aligned index-for-index. They
didn't:

- NFD input: a combining accent is not a `\w` character, so `unicodedata.
  normalize("NFD", "Entä jos hän asuu ugandassa?")` split "hän" into "ha"
  and "n" in the raw array (6 tokens) while the folded array still saw one
  token "han" (5 tokens). Reproduced: the retrieval query gained a stray
  "Uganda" token instead of replacing "ugandassa", with **trusted**
  `resolved_dependent_follow_up` provenance.
- A character with an NFKD compatibility expansion: "½" decomposes to three
  characters ("1", a fraction slash, "2"), two of which are word characters,
  so the folded array grew by one token relative to the raw array.
  Reproduced: `IndexError: tuple index out of range` raised out of
  `_resolve_finnish_anaphoric`, reachable from `handle_chat` with nothing on
  that path to catch it.

### Fix

Tokenization is now done exactly once, with spans, over text NFC-normalized
a single time (`_follow_up_words`, `chat_orchestrator.py`). Each
`_FollowUpWord` carries `raw`, `folded`, `start`, `end` - all derived from
the SAME `re.finditer` match, so a token's comparison form and its exact
surface span can never drift apart. `_follow_up_raw_tokens` (the
correction-8 helper that caused this) is removed entirely; nothing
tokenizes the Finnish anaphoric message more than once now.

Substitution (`_canonicalize_finnish_anaphoric_market`) no longer re-derives
a literal/regex search for the resolved token's text - it slices the
NFC-normalized original message directly at each resolved span's `(start,
end)` position. This is both simpler and strictly more robust than the
correction-8 approach (which searched for the accent-stripped token's text
inside a possibly-accented original message and had its own latent
"Argentína" substitution gap, now moot).

## 2 SHOULD-FIX and 3 SHOULD-FIX (fail-safe) - the definition of place residue

Both findings trace to the same root cause: correction 8 scored a token as
place-shaped residue purely from its case ENDING. That both missed
unsupported forms of a KNOWN configured market and over-fired on ordinary
nouns with no place meaning:

- **Missed** (finding 2): a clitic ("ugandassaKIN", "ugandassaKO"), the
  inessive-possessive ("ugandassaAN" - not excluded by the `-ssaan` carve-out
  the way "tiimissään" was, since that carve-out is about the ENDING shape,
  not about which stem it is attached to), partitive ("edustaa ugandaA"),
  or essive ("asuu ugandaNA") form of Uganda all reproduced as `resolved,
  code=None, reason=no_place_evidence` - i.e. fully trusted, keeping
  Tanzania - because none of these endings matched the closed case-ending
  set.
- **Over-fired** (finding 3): "Entä jos hän ei ole ostanut mitään 24
  kuukauteen?", "...on sääntöjen mukaan johtaja?", and tokens like
  "tilille", "tasolle", "jälkeen", "toimistossa", "netissä" outside any
  residence context all reproduced as `unresolved` - correction 8's own
  design flaw made the trusted path unreachable for realistic follow-ups
  that happen to contain an ordinary case-marked noun.

### Fix

Residue is redefined as a place CANDIDATE, one of three kinds, all checked
in `_resolve_finnish_anaphoric`:

1. **Configured-market stem prefix** (`_finnish_market_stem_prefix`,
   `_finnish_market_name_stems`): a token whose comparison form STARTS WITH
   a configured market's name/alias stem (derived from configuration, never
   a market literal in code, with a minimum stem length of 4 to avoid a
   short accidental prefix) but is not exactly the one supported inessive
   form. This single, general mechanism catches the clitic, partitive,
   essive, illative, and elative forms in finding 2 without listing any
   grammatical case - it just recognizes "this word is clearly built on a
   configured market's name, in some form we don't substitute." Such a
   token always keeps ordinary (untrusted) context (`unresolved`), never
   `standalone` - it names a real, known market, so dropping the anchor
   entirely would be needlessly destructive; only conflicting with another
   code, or being negated, can still push it to `standalone`.
2. **Residence/location-verb complement** (`_finnish_residence_verb_tier`):
   a token with a locative-case ending AND sitting within
   `_FINNISH_RESIDENCE_VERB_WINDOW` (3) tokens of a residence or location
   verb stem. The closed verb-stem set is split into two tiers:
   - **strong**: `asu-` ("asuu" lives, "asu" negated stem, "asunut"
     perfect participle, matched as a prefix) - the one verb confident
     enough that an UNKNOWN place as its complement fails closed as
     `standalone`.
   - **weak**: `tyoskentel-`, `muutta-`, `sijaits-`/`sijait-`, `oleskel-`,
     plus the idiom token `kotoisin` ("on kotoisin X") - real location
     semantics, but not residence itself, so an UNKNOWN place as their
     complement only keeps ordinary, untrusted context (`unresolved`).

   An ordinary case-marked noun with NO configured-market stem and NO
   residence/location verb nearby is **not a place candidate at all** any
   more - this is the over-fire fix. "on" (the plain copula) is
   deliberately NOT in either verb tier, so "on sääntöjen mukaan johtaja",
   "on 24 kuukauteen", "on tiimissä" (with no residence verb) etc. are all
   now trusted.
3. **Capitalized unknown place** (unchanged from correction 8): a
   capitalized, non-initial token, not a known function word, that also
   carries a locative-case ending.

## Reproductions - before and after

All reproduced against the frozen Tanzania history: "How does Forever
Tanzania pay bonuses to FBOs who live outside the country?"

| Finding | Input | Before (correction 8, `07b6677`) | After (correction 9) |
| --- | --- | --- | --- |
| BLOCKER (NFD) | `unicodedata.normalize("NFD", "Entä jos hän asuu ugandassa?")` | Trusted, query corrupted with a stray "Uganda" token instead of a clean substitution | Trusted, "Uganda" correctly substituted for "ugandassa" |
| BLOCKER ("½") | `Entä jos hän on ½ vuotta ugandassa?` | `IndexError` raised out of `_resolve_finnish_anaphoric` | Trusted, resolves to Uganda, no exception |
| SHOULD-FIX 2 (clitic) | `Entä jos hän asuu ugandassakin?` / `...ugandassako?` | `resolved, code=None`, trusted, kept Tanzania | `unresolved`, untrusted, keeps Tanzania in the query text but not as a trusted target |
| SHOULD-FIX 2 (possessive) | `Entä jos hän asuu ugandassaan?` | `resolved, code=None`, trusted | `unresolved`, untrusted |
| SHOULD-FIX 2 (partitive) | `Entä jos hän edustaa ugandaa?` | `resolved, code=None`, trusted | `unresolved`, untrusted |
| SHOULD-FIX 2 (essive) | `Entä jos hän asuu ugandana?` | `resolved, code=None`, trusted | `unresolved`, untrusted |
| SHOULD-FIX 3 (over-fire) | `Entä jos hän ei ole ostanut mitään 24 kuukauteen?` | `unresolved` | `resolved_dependent_follow_up`, trusted |
| SHOULD-FIX 3 (over-fire) | `Entä jos hän on sääntöjen mukaan johtaja?` | `unresolved` | `resolved_dependent_follow_up`, trusted |
| SHOULD-FIX 3 (over-fire) | `...maksaa tilille?` / `...nousee tasolle?` / `...ostaa sen jälkeen?` / `...vierailee toimistossa?` / `...asioi netissä?` | `unresolved` | `resolved_dependent_follow_up`, trusted |
| NOTE 4 (negation window) | `Entä jos hän ei ole asunut ugandassa?` | `resolved`, trusted, Uganda substituted | `standalone` (`not_dependent`); neither Tanzania nor Uganda in the query |
| NOTE 5 (repeated span) | `Entä jos hän asuu ugandassa ja työskentelee myös ugandassa?` | Only the first "ugandassa" substituted | Both occurrences substituted to "Uganda" |
| NOTE 6 (topic-shift re-run) | `Entä jos hän asuu ugandassa?` | Worked by coincidence (the canonicalized text still parsed as the same Finnish shape) but re-derived the decision from post-substitution text | `_contains_topic_shift_marker` reads the SAME precomputed decision; no re-derivation |

B2 acceptance check (must stay `unresolved`, not `standalone`, not trusted -
it is a WEAK residence-verb complement): `Entä jos hän työskentelee nyt
pysyvästi atlantisissa?` -> `unresolved`, no `prior_user_turn_id`. Unchanged
in both correction 8 and 9 (this was never one of the six findings; it is a
regression control).

Finland acceptance check: `Entä jos hän asuu Suomessa?` -> `standalone`
(`not_dependent`) - "Suomessa" is capitalized and not a configured
single-word inessive alias, so it is an unrecognised capitalized place
candidate. Unchanged from correction 8.

## Other compatibility characters and fuzzing

Also probed and added as tests, per the review's request: a ligature ("ﬁ"
NFKD-decomposes to "f"+"i"), full-width Latin letters (a CJK input-method
compatibility form, NFKD-decomposes to ASCII), and a Roman numeral ("Ⅷ"
NFKD-decomposes to several ASCII letters) - none raise. A 200-iteration fuzz
loop inserts 0-4 random compatibility characters (½, ¼, Ⅷ, ﬁ, ﬂ, fullwidth
e/A, circled 1, a bare combining acute accent, a bare fraction slash, a
zero-width no-break space) into a representative Finnish follow-up, in both
NFC and NFD form (400 variants total) - zero exceptions.

## 4 NOTE - negation window

"Entä jos hän ei ole asunut ugandassa?" ("what if he has NOT lived in
Uganda") reproduced as trusted, resolving Uganda, because correction 8's
negation check only looked at the token immediately after "ei" and missed
the perfect tense's "ole" auxiliary sitting between "ei" and "asunut".
`_FINNISH_NEGATION_WINDOW` is now 2 (checks up to 2 tokens after the
negation word), which reaches past "ole" to the residence-verb stem.

Correction 8's own handoff separately claimed "ei enää asu" was an
unhandled limitation - that was already wrong even under correction 8's
narrower check, since "enää" is itself one of the negation tokens and the
verb followed one token later (i.e. adjacency, not a 2-token skip). That
stale claim is corrected in `R03-CORRECTION-8-EARNED-TRUST.md`.

## 5 NOTE - repeated market substitution

Fixed as a natural consequence of the BLOCKER fix: `_resolve_finnish_
anaphoric` now collects every matching span for the resolved market (not
only the first), and `_canonicalize_finnish_anaphoric_market` replaces each
one by its own `(start, end)` position.

## 6 NOTE - `_contains_topic_shift_marker` re-running the decision

`_build_retrieval_query_with_provenance` now computes the Finnish decision
exactly once, on the original (pre-canonicalization) message, and threads
it through an explicit `finnish_topic_shift` keyword argument to
`_contains_topic_shift_marker` at its one call site inside that method. The
OTHER call site (the anchor walk over PRIOR historical messages,
`_replace_directory_target`'s caller) has no precomputed decision to reuse
and is unaffected - it still recomputes for each historical message it
scans, which is correct there since there is no single "the decision" for a
whole list of past turns.

## Removed / changed from correction 8

- `_follow_up_raw_tokens` - removed; superseded by `_follow_up_words`.
- `_is_finnish_location_phrase` - removed; superseded by
  `_finnish_residence_verb_tier` (which adds the weak/strong split and the
  wider verb-stem vocabulary) and `_finnish_negation_scopes_residence`.
- `_FINNISH_RESIDENCE_VERB_TOKENS` (`{"asuu", "asu"}`, exact-token) -
  removed; superseded by `_FINNISH_STRONG_RESIDENCE_STEMS` (prefix-matched,
  so "asunut" etc. are covered too).
- `_FinnishAnaphoricResolution.place: str` -> `.spans: tuple[tuple[int,
  int], ...]` - carries every matched span for the resolved market, not one
  surface string.

## Test commands and results

Focused suite (adds 15 new tests to the R03 file; corrects 4 existing tests
whose expectations were themselves the over-fire bug: `test_unsupported_
finnish_place_shape_keeps_context_but_is_unresolved`, `test_ambiguous_
lowercase_finnish_complement_keeps_context`, `test_bounded_finnish_
location_phrase_does_not_scan_ordinary_nouns`, and the now-removed
`test_lowercase_finnish_noun_after_on_keeps_context`, merged into the third):

```
<PYTHON> -m pytest tests/evidence_first_v2/test_r03_context_capture.py tests/unit/test_demo_multilingual_followups.py tests/unit/test_demo_followup_resolution.py tests/unit/test_retrieval_canary_delivered_answer.py tests/unit/test_retrieval_rank_list_capture.py -p no:cacheprovider --basetemp <TEMP>\pytest-r03c9
```

Result: **496 passed, exit 0** (54 -> 78 in the R03 file alone).

Compatibility suite:

```
<PYTHON> -m pytest tests/unit/test_chat_orchestrator.py tests/unit/test_evidence_routing.py tests/unit/test_opensearch_sections.py tests/unit/test_retrieval_service.py tests/unit/test_retrieval_rank_list_capture.py tests/evidence_first_v2 -p no:cacheprovider --basetemp <TEMP>\pytest-r03c9
```

Result: **535 passed, 1 failed, exit 1**. The sole failure is the
pre-existing, unrelated `test_offline_isolation.py::
test_package_imports_use_a_narrow_allowlist` (`capture_provenance` relative
import allowlist mismatch in `scope_aware_fusion.py`), unchanged.

Scoped lint:

```
<PYTHON> -m flake8 --ignore=E203,E402,E501,C901 app/orchestrator/chat_orchestrator.py scripts/evidence_first_v2/capture_read_only_retrieval.py scripts/evidence_first_v2/finalize_read_only_capture.py tests/evidence_first_v2/test_r03_context_capture.py
```

Result: **exit 0**.

Plain `flake8` (disclosure only, same files): **exit 1**, but the only
findings are the same two pre-existing baseline items in files this
correction did not touch (`capture_read_only_retrieval.py:234` C901,
`finalize_read_only_capture.py:17` E402) - neither `chat_orchestrator.py`
nor the test file is flagged.

`git diff --check`: **exit 0**.

## Limitations (carried forward and updated)

- **Approximate morphology, not a full analyzer.** Unchanged from
  correction 8: the case-ending set and the market-stem-prefix check are
  both shape/text tests on accent-stripped text, not a morphological
  parser.
- **All-caps input.** Unchanged: an all-caps unknown place loses the
  capitalized-vs-lowercase distinction.
- **Multiword inflected forms.** Unchanged: only single-word configured
  market names get a stem/inessive form; a multi-word market is only
  recognized in its direct/nominative spelling.
- **Negation window is bounded (2 tokens), not full-clause.** Covers direct
  negation and the perfect tense's single auxiliary; a negation separated
  by more than 2 tokens from the verb is not recognized.
- **Residence-verb window is bounded (3 preceding tokens).** Covers the
  modifier gaps seen in existing tests ("asuu nyt pysyvästi X"); a verb
  separated from its complement by more than 2 intervening tokens is not
  recognized as governing it.
- **Minimum market-stem length (4) is a heuristic,** not derived from any
  linguistic property - chosen because the shortest real configured market
  names observed are 4 letters unaccented (Chad, Cuba, Mali, Togo...). A
  configured market shorter than 4 letters (none currently exist) would not
  get stem-prefix coverage.
- **Function-word list is closed and hand-picked**, grown only from forms
  seen in this configured follow-up's tests and reproductions.
- No AWS, network, OpenSearch, live model, reindex, install, push, merge, or
  deployment occurred. Local tests and the adversarial probes/fuzz loop
  prove decision correctness and crash-safety for the inputs exercised, not
  live ranking, answer quality, or release readiness.

Send this exact snapshot to a fresh Sol review, then Astra final review.
Stop after review; R04 remains paused.
