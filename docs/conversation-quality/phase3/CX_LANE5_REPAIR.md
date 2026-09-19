# CX Lane 5: repair and typo clarification

Status: implemented (2026-09-18), branch `cx/lane5-20260918`. Design:
`docs/conversation-quality/phase3/CX_DESIGN.md`; shared contract:
`docs/conversation-quality/phase3/CX_LANES.md`.

**Fixed post-review (coordinator review of 32443d0):** `typo_clarification`
used to also fire on an exact, correctly spelled collision member
("What is the shipping cost?" wrongly asked to disambiguate). An exact
member is never ambiguous - the reader typed a real word, and this module
must not second-guess a correct spelling any more than `typo_safety` itself
silently rewrites one. `_is_collision_ambiguous_token` (the only place in
this lane that reasons about the collision pair) now returns `False` for an
exact member and only fires for a token that is NOT an exact member but is
typo-shaped and within bounded edit distance of one (`_typo_distance`/
`_typo_shape_matches`, both imported read-only from `typo_safety`). New
negative tests pin exact spellings (bare word, full phrase, case variants,
trailing punctuation) in en/es/fr/de returning `None`, alongside the
existing misspelling-triggers-one-question positives.

## What this lane owns

- `app/orchestrator/conversation_repair.py` (new)
- `config/repair_vocabulary.py` (new)
- `tests/unit/test_cx_repair.py` (new, 51 tests)

Nothing else. This lane never touches retrieval, ranking, evidence approval,
country authorization, `chat_orchestrator.py`, or any other lane's files.

## APIs

```python
def typo_clarification(question: str, language: str) -> Clarification | None
def one_question(candidates: Sequence[Clarification | None]) -> Clarification | None
def detect_repair(message: str, language: str, prior_user_turns: Sequence[str]) -> Repair | None
```

```python
@dataclass(frozen=True)
class Clarification:
    kind: str            # "reference" | "country" | "role" | "field"
    key: str              # message key (Lane 4 owns the copy)
    options: tuple[str, ...]

@dataclass(frozen=True)
class Repair:
    kind: str                        # "market" | "topic"
    replacement: str
    replaced: str | None             # the exact prior-turn span swapped out
    rewritten_question: str | None   # prior question with the swap applied
```

Copy is data: this module never inlines an English sentence. `Clarification`
carries a message key (`clarify_field`, and `clarify_country`/`clarify_role`
by convention for other lanes/the coordinator) plus placeholder values;
`config/conversation_routes.json` and its renderer (`app/response/
cx_render.py`, Lane 4) turn a key + placeholders into localized text. Neither
file exists yet as of this lane's implementation, and this module has no
import of either - it is usable and independently testable before Lane 4
lands. `repair_ack` is not produced by this module at all: per the shared
contract, it is a plain message key the coordinator renders and prefixes to
the rewritten answer whenever `detect_repair` returns a `Repair` with a
non-`None` `rewritten_question`.

## Hook sites (for the coordinator; not wired here)

`chat_orchestrator.py` is single-writer and this lane does not touch it, but
the natural hook points, by analogy with the existing `_resolve_unresolved_reference`
hook (chat_orchestrator.py, called from `_handle_chat` right after PII
scrubbing and before `_mixed_request_response`/retrieval):

1. **`detect_repair`** — call it in the same position as
   `_resolve_unresolved_reference`, using the already-fetched session
   history's prior user turns (the same `_user_turns`-shaped list
   `app/orchestrator/reference_resolution.py` derives from
   `get_session_history`). If `repair.rewritten_question` is not `None`,
   substitute it for the scrubbed input going into retrieval - the same way
   `resolve_reference`'s `rewritten_message` is substituted today - and
   prefix the eventual answer with a rendered `repair_ack`. If a `Repair`
   comes back with `replaced is None` / `rewritten_question is None`, do not
   guess: build a `Clarification` instead (`clarify_country` for
   `kind="market"`, `clarify_field` for `kind="topic"`, using `replacement`
   as one option) and route it through `one_question` below.
2. **`typo_clarification`** — call it wherever a directory-field question is
   about to be answered (after `_resolve_unresolved_reference`, before the
   field-request set is used to shape the answer - i.e. before
   `utils.directory_fields._requested_directory_field_set` is trusted to
   have unambiguously identified the field), on the resolved input from step
   1.
3. **`one_question`** — call once per turn, after every other lane's
   candidate clarification has been computed (this lane's
   `typo_clarification` result, Lane 1/the coordinator's reference
   clarification recast as `kind="reference"`, and any country/role
   clarification another lane or the coordinator produces), and render only
   the single result it returns.

This lane does not itself decide where in `_handle_chat` these calls are
inserted - that wiring is the coordinator's, per the lane contract.

## Design notes and deliberate limits

- **Market resolution never uses an alias list.** Both the corrected market
  name and, for a "meant"-style repair, the span being replaced in the prior
  question are resolved only through `services.market_config.find_market_mentions`
  / `market_display_name` - the same resolvers `reference_resolution.py`
  already trusts. A consequence: when a prior question used a market's
  *localized* name and `market_display_name` returns a different spelling
  (e.g. Spanish "Kenia" vs. the canonical "Kenya"), the literal span is not
  found and `replaced`/`rewritten_question` come back `None` rather than a
  guessed swap. This is the documented, safe direction - a caller who wants
  full coverage there would need Codex or another reviewer to extend
  `market_config`'s own resolvers, not a local alias table in this module.
- **`typo_clarification`'s collision pair stays English-only.**
  `app/retrieval/typo_safety.py`'s `_SEMANTIC_COLLISION_PAIRS` is
  Codex-owned and defines exactly one pair, in English
  (`{"shipping", "shopping"}`, one QWERTY-adjacent letter apart). This
  module detects that collision regardless of the message's declared
  language - a support question in any of the 12 route languages may still
  contain the bare English word - and localizes only the *readable
  question* built around it (the two option labels, and the context words
  that suppress it). A genuinely native-language collision pair (two words
  in, say, French, one edit apart with different meanings) is out of scope;
  extending `typo_safety`'s own pair table is Codex's call, not this
  module's.
- **`market` never widens policy eligibility.** `Repair` has exactly four
  fields (`kind`, `replacement`, `replaced`, `rewritten_question`) - no
  `country` or `policy_country` field exists anywhere in this module's
  types, so there is nothing here a caller could accidentally wire into
  country authorization. The session's own country keeps governing policy,
  unchanged; a `market` repair only ever changes which market's *directory*
  record (phone, address, delivery cost, etc.) the follow-up targets.
  `tests/unit/test_cx_repair.py::test_repair_dataclass_carries_no_policy_country_field`
  pins this.
- **`one_question` precedence** is `reference > country > role > field`,
  matching the order in `docs/conversation-quality/phase3/CX_LANES.md`. An
  unrecognised `kind` sorts last (never raises), so a future lane's new
  `Clarification` kind degrades safely instead of crashing this function.
- **Guard against a bare "No...?" question.** Both `detect_repair` cue
  shapes require one of this module's closed correction phrases
  (`config/repair_vocabulary.MEANT_CUE_PHRASES`, e.g. "i meant") or a full
  "not Y, X" contrast with a comma-separated second clause
  (`NOT_CUE_WORDS`). "No minimum order?" and "No, that's wrong" match
  neither shape and are confirmed negative tests.
- **Topic-word granularity.** `detect_repair`'s topic-kind `replacement`/
  `replaced` are bare single words (`config/repair_vocabulary.SHIPPING_BARE_WORD`
  / `SHOPPING_BARE_WORD`), not the multi-word `SHIPPING_OPTION_LABEL` /
  `SHOPPING_OPTION_LABEL` phrases `typo_clarification` renders. Swapping a
  bare word for a bare word keeps the rest of the prior question's own
  wording ("cost", "fee", ...) intact instead of duplicating a word that was
  already there.

## Tests

`tests/unit/test_cx_repair.py`, 51 tests: `typo_clarification` positives and
negatives for en, es, fr, de, fi, sv (context-word suppression in both
directions, an ordinary unrelated typo staying silent, an unknown language
failing conservative, determinism); `one_question` precedence including an
unrecognised kind; `detect_repair` market and topic repairs in the same six
languages (meant-style and contrast-style), the bare-"No" guard, the
no-prior-turn and ambiguous-prior-turn cases (`replaced`/`rewritten_question`
staying `None`), the no-policy-country-field pin, and determinism. No case
ids are used.

Also run (unchanged, still passing): `tests/unit/test_typo_retrieval.py`
(typo_safety's own suite - this lane only imports it, read-only) and every
test under `tests/conversation/`.

## Verification (2026-09-18)

- `pytest tests/unit/test_cx_repair.py tests/unit/test_typo_retrieval.py tests/conversation` -
  434 passed, exit 0.
- `flake8 app/orchestrator/conversation_repair.py config/repair_vocabulary.py tests/unit/test_cx_repair.py` -
  exit 0.
- `git diff --check` - exit 0.
- No `tests/unit/test_reference_resolution*.py` file exists in this worktree
  to run.
