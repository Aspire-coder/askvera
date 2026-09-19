# Phase 3, Lane 2: partial answers and final-answer quality checks

Status: implemented. See `docs/conversation-quality/phase3/CX_DESIGN.md` for
the full lane breakdown and `docs/conversation-quality/phase3/CX_LANES.md`
for the shared rules and message-key table this note assumes. Covers only
Lane 2's write scope: `app/response/partial_answer.py` (new), `app/response/quality.py`
(extended -- existing functions untouched), `tests/unit/test_cx_partial_answer.py`,
`tests/unit/test_cx_answer_quality.py`.

Every function below is pure (no I/O, no model call, no import of
`app.orchestrator.chat_orchestrator`). Nothing in this lane changes
retrieval, ranking, evidence approval or country authorization; nothing
writes `chat_orchestrator.py` -- the coordinator wires these in.

## 1. Partial answers (`app/response/partial_answer.py`)

### `FieldCoverage`

```python
@dataclass(frozen=True)
class FieldCoverage:
    requested: frozenset[str]
    answered: frozenset[str]
    unsupported: frozenset[str]
    omitted: frozenset[str]
```

Four disjoint states per requested canonical directory field (the same field
keys `utils.directory_fields._label_canonical_field` already recognises:
`phone`, `order_phone`, `email`, `website`, `address`, `business_hours`,
`payment_methods`, `delivery_cost`, `delivery_time`):

- **requested** -- the question confidently named this field
  (`utils.directory_fields._requested_directory_field_set`).
- **answered** -- an approved evidence document carries a value for it, and
  that value is already in the final answer text.
- **unsupported** -- no approved evidence document carries a value for it at
  all. This is the state a partial-answer note is about.
- **omitted** -- an approved evidence document DOES carry a value, but it
  never made it into the answer text. Deliberately reported, not filled: per
  the lane assignment, the existing contact-completion/supplement path
  (`app/response/contact_completion.py`, Lane 3) owns actually restoring an
  omitted field; this module only classifies.

### `assess_field_coverage`

```python
def assess_field_coverage(
    *, question: str, language: str, answer_text: str,
    evidence_documents: list[RetrievedDocument],
) -> FieldCoverage
```

`evidence_documents` must already be the turn's APPROVED evidence (e.g.
`EvidenceDecision.evidence`, or `RetrievalResult.documents` after evidence
approval) -- this function does no approval or ranking of its own.

Reuse, not a second vocabulary (per `CX_LANES.md`'s "No duplicated
vocabularies"):
- "which fields did the question ask for" --
  `utils.directory_fields._requested_directory_field_set(question,
  language=language)` (13-language table), unchanged.
- "does an approved document carry a value for a field" -- the exact
  shape `app/orchestrator/chat_orchestrator.py`'s own
  `_support_contact_approved_fields` already reads
  (`document.metadata["directory_fields"]` dict, else
  `utils.directory_fields.parse_directory_fields(document.content)`), then
  `utils.directory_fields._label_canonical_field(label)` to map each parsed
  label to its canonical key.
- "is the value already in the answer" --
  `utils.directory_fields._value_is_present` (the same fuzzy/digit-aware
  comparison `restore_missing_directory_contacts` uses).

When the question does not confidently name a field
(`_requested_directory_field_set` returns `None`/empty -- a plain policy
question, or a compound/ambiguous request that function itself declines to
guess at), every set in the returned `FieldCoverage` is empty.

### `partial_answer_note`

```python
def partial_answer_note(
    coverage: FieldCoverage, language: str, *,
    render: RenderCopy, outcome_kind: OutcomeKind | None = None,
) -> str | None
```

`RenderCopy` is a `Protocol`: `render(key: str, language: str, **placeholders)
-> str`. `app/response/cx_render.py` (Lane 4) does not exist yet in this
worktree; tests pass a fake renderer (see both test files' `_fake_render`).

Returns `None` when `coverage.unsupported` is empty, or when `outcome_kind`
is given and is not `OutcomeKind.ANSWER` / `OutcomeKind.PARTIAL_ANSWER`
(reused from `app/response/outcome.py`, Lane 1 -- no parallel status field).
Otherwise calls `render("partial_answer_gap", language, fields=sorted(coverage.unsupported))`
-- `fields` is the RAW sorted list of field ids (e.g. `["email", "phone"]"`),
**not** pre-localized or pre-joined. Per `CX_LANES.md`'s message-key table,
joining `{fields}` with the locale's list separator is `cx_render.py`'s job.

A partial answer never deletes supported content: this function only ever
returns text to append once; it edits nothing.

**Field labels Lane 4 must provide:** no existing table covers all nine
field ids in a form suitable for interpolating into a sentence like
"...but we don't have their {fields}". The closest existing table,
`utils.directory_fields._SUPPORT_CONTACT_LABEL_TRANSLATIONS`, only covers 7
languages (nl, fr, de, es, it, pt, sv) and 6 of the 9 fields (no
`payment_methods`, `delivery_cost`, `delivery_time`) and is shaped for a
"Label: value" contact line, not sentence-embeddable prose -- reusing it for
this purpose was judged unsafe rather than a genuine fit. Per the lane
assignment's fallback instruction, this module passes raw field ids and
Lane 4 must add, per the 12 route locales, a `field_label_<field>` key for
each of:

```
field_label_phone, field_label_order_phone, field_label_email,
field_label_website, field_label_address, field_label_business_hours,
field_label_payment_methods, field_label_delivery_cost, field_label_delivery_time
```

## 2. Final-answer quality checks (`app/response/quality.py` additions)

### `leading_preamble_span` / `strip_leading_preamble`

```python
def leading_preamble_span(answer: str, language: str) -> tuple[int, int] | None
def strip_leading_preamble(answer: str, language: str) -> str
```

Detects a first sentence (`utils.sentence_spans.iter_sentences` -- span-aware,
so a decimal/abbreviation/initial/email/URL is never mis-split) that is pure
pleasantry ("Great question!", "Certainly!", ...), against a new **closed**,
per-language table in `quality.py` (`_PREAMBLE_OPENERS`), matched only at the
sentence's start after accent-folding
(`utils.directory_fields._fold_diacritics`). Confidence per language is
documented directly above the table:

- **High** (checked against this codebase's own reviewed tone/examples): en,
  es, fr, de, it, nl.
- **Medium** (built the same way, not yet checked against a real generated
  corpus): da, no, sv, fi.
- **Lower** (no native-speaker review yet, kept deliberately narrow): ru, sr.

A sentence is **never** treated as preamble, regardless of the table, when it
contains: a digit; a citation marker in the shape
`utils.inline_citations.separate_verified_citations` already recognises
(`[1]`, `[Source 1]`); a directory `Label: value` line
(`utils.directory_fields._INLINE_FIELD_RE`, the same pattern
`parse_directory_fields` itself uses); or policy wording (English:
`app.retrieval.providers.DIRECTORY_POLICY_WORDING_RE`; other languages:
`utils.directory_fields.localized_policy_wording_present`, backed by the
existing reviewed `config.directory_field_vocabulary.POLICY_WORDING_TERMS`).

`strip_leading_preamble` removes only that one sentence span and never
empties the answer (if nothing but whitespace would remain, the original
answer is returned unchanged).

### `overclaim_findings`

```python
def overclaim_findings(answer: str, coverage: FieldCoverage) -> list[str]
```

Report-only (never edits `answer` -- the numeric/contact validators already
own repair). Flags sentences whose text matches a value SHAPE for a field in
`coverage.unsupported`. Deliberately narrow: only `phone`, `order_phone`,
`email` and `website` have an unambiguous, low-false-positive shape (a
phone-number-like digit run, an email address, a URL); `address`,
`business_hours`, `payment_methods`, `delivery_cost` and `delivery_time` are
free-form prose with no safe shape and are not checked -- a documented
limitation, not an oversight.

### `confidence_framing_key`

```python
def confidence_framing_key(outcome_kind: OutcomeKind, coverage: FieldCoverage) -> str | None
```

Returns `"partial_answer_gap"` only for `OutcomeKind.PARTIAL_ANSWER` with a
non-empty `coverage.unsupported`; `None` otherwise (including a full
`OutcomeKind.ANSWER`, which never gets hedging framing it does not need). No
numeric confidence is computed or shown; no new hedging phrase is invented --
this returns only the one existing message key.

## Recommended hook call sites (coordinator, `chat_orchestrator.py`)

Both hooks live inside `_secure_and_complete_response`
(`app/orchestrator/chat_orchestrator.py`), the method that already runs every
other post-generation directory/PII edit in sequence, so a Lane 2 edit
composes with the rest exactly like every existing step there.

1. **`strip_leading_preamble`** -- at the very top of
   `_secure_and_complete_response`, before its first edit
   (`citation_cleaned = separate_verified_citations(...)` at line 1638),
   e.g.:
   ```python
   preamble_stripped = strip_leading_preamble(chat_response.answer, language)
   if preamble_stripped != chat_response.answer:
       chat_response = self._replace_answer(
           chat_response, preamble_stripped, {"leading_preamble_stripped": True},
       )
   ```
   Running first means every later directory-field/PII edit in this method
   operates on the already-preamble-free text, and the removed opener can
   never re-absorb a fact a later step adds.

2. **`assess_field_coverage`, `partial_answer_note`, `overclaim_findings`** --
   immediately after the `_apply_support_contact_supplement` call
   (line 1757-1764, the last step that can still add a previously-omitted
   contact field to the answer) and before the PII scrub at line 1766, so the
   coverage reflects the truly final field set:
   ```python
   coverage = assess_field_coverage(
       question=user_question, language=language,
       answer_text=chat_response.answer,
       evidence_documents=retrieval_result.documents,
   )
   overclaims = overclaim_findings(chat_response.answer, coverage)
   if overclaims:
       LOGGER.warning("cx_overclaim_detected", correlation_id=correlation_id, sentences=overclaims)
   note = partial_answer_note(
       coverage, language, render=render_copy, outcome_kind=outcome_kind,
   )
   if note:
       chat_response = self._replace_answer(
           chat_response, f"{chat_response.answer}\n\n{note}",
           {"partial_answer_gap_fields": sorted(coverage.unsupported)},
       )
   ```
   `outcome_kind` here requires `app.response.outcome.derive_outcome`
   (Lane 1) to already be wired at this point in the method -- it is not yet
   wired in this worktree (see `CX_LANE1_OUTCOME.md`); until it is, call with
   `outcome_kind=None` and let the caller pre-gate on "this turn will end up
   `answer`-shaped" (no `failure_layer` set on `chat_response.metadata` yet)
   instead.

3. **`confidence_framing_key`** -- wherever the coordinator finally computes
   `ConversationOutcome` per turn (not yet wired; see Lane 1's doc), pass the
   same `coverage` computed in (2) and the derived `outcome.kind`.

## Test run

```
pytest tests/unit/test_cx_partial_answer.py tests/unit/test_cx_answer_quality.py
       tests/unit/test_response_quality.py tests/unit/test_response_builder.py
       tests/conversation -q
                                                          -> 442 passed
flake8 app/response/partial_answer.py app/response/quality.py
       tests/unit/test_cx_partial_answer.py tests/unit/test_cx_answer_quality.py
                                                          -> exit 0 (clean)
git diff --check                                          -> exit 0 (clean)
```

## Fix (coordinator review of 568a422)

`leading_preamble_span`/`strip_leading_preamble` did not strip a sentence's
leading opening punctuation (Spanish inverted marks `¡`/`¿`,
guillemets, straight/curly quotes) before comparing it against
`_PREAMBLE_OPENERS`, so `"¡Buena pregunta! ..."` was left unchanged.
Fixed by stripping a leading/trailing run of wrapper punctuation
(`_LEADING_WRAPPER_PUNCTUATION_RE` / `_TRAILING_WRAPPER_PUNCTUATION_RE`) from
the accent-folded sentence before the opener comparison, for every language
-- the openers table itself stays plain, unquoted text. Also added a bare
`"claro"` entry to the Spanish table (`"claro que si"` alone did not cover a
standalone `"¡Claro!"`). New tests cover `"¡Buena pregunta!"`,
`"¡Claro!"`, `"¡Por supuesto!"`, and a control where the
punctuation-wrapped opener sentence itself states a number (still never
preamble).

## Fix 2 (coordinator review of cadd4f1): negation/yes-no answers were being deleted

`strip_leading_preamble` matched an opener as a PREFIX of the first
sentence, so "Of course not. Returns are not accepted." matched the "of
course" opener and deleted "Of course not." -- the actual "no" to the
reader's question, not a pleasantry. Same defect for "Certainly not.",
"Claro que no.", "Claro que si.", "Naturlich nicht.", "Bien sur que non.".

Two changes:

1. **Whole-sentence match only.** `leading_preamble_span` now requires the
   folded, wrapper-punctuation-stripped first sentence to EQUAL an opener
   entry -- or equal an opener plus a short entry from the new closed
   `_PREAMBLE_FILLER_TAILS` table (e.g. English "of course, i'd be happy to
   help with that") -- never a prefix match. A prefix match is what let
   "of course" silently swallow "of course not" in the first place.

2. **Negation/yes-no token guard.** A new closed, per-language
   `_NEGATION_OR_YES_NO_TOKENS` table (en not/no/yes; es no/si; fr
   non/oui/pas; de nicht/nein/ja/kein(e)(n); it no/si/non; pt nao/sim; nl
   niet/nee/ja; sv inte/ja/nej; no ikke/ja/nei; da ikke/ja/nej; fi ei/kylla;
   ru не/нет/да; sr ne/da), matched whole-word on the accent-folded
   sentence via `_sentence_has_negation_or_yes_no_token`, wired into
   `_sentence_is_never_preamble`. Any sentence carrying one of these tokens
   is never preamble, regardless of whether it also opens with a table
   phrase -- this is what actually blocks "Claro que si." (contains the
   Spanish "si"/yes token) even though "claro que si" itself is still a
   listed Spanish opener for the plain "¡Claro!" case.

   Documented, deliberate over-blocking trade-off: Spanish "si" is also the
   word for "if", so this table leaves some genuinely-preamble Spanish
   sentences containing "si" unstripped. Always the safe direction -- it can
   only ever keep a sentence whole, never delete real content.

New tests cover every example in the coordinator's report (English,
Spanish, German, French) keeping its first sentence, plus two positive
controls ("Of course! Returns are accepted..." and "¡Claro! Puedes...")
confirming genuine pleasantries still strip after the fix.

## Fix 3 (coordinator BLOCKER, 2026-09-19, on `cx/lane2b-20260918`): bulleted facts read as `unsupported`

Wiring `assess_field_coverage` against the real Kenya directory record
surfaced a defect that would have shown customers "I couldn't find payment
methods" under an otherwise correct, complete answer.

**Cause:** the record states payment methods, delivery cost, delivery time
and minimum order as bulleted "• Label: value" lines. `_document_field_values`
only ever read `utils.directory_fields.parse_directory_fields` (or the
`metadata["directory_fields"]` map `app/retrieval/opensearch_sections.py:2424`
builds with that same parser), and that parser -- see `_INLINE_FIELD_RE` --
only recognises the contact-style fields (phone/email/website/address/
business hours). It never saw a bullet, so every bulleted field came back
with no value, and the old code treated "no value" as `unsupported`
unconditionally.

**Fix, in `app/response/partial_answer.py` only** (`parse_directory_fields`
itself is shared and untouched):

1. `_label_line_field_values` reads bulleted fact lines directly, reusing
   `utils.directory_fields._FIELD_ALLOWED_LINE_FRAGMENTS` -- the same label
   vocabulary `remove_unrequested_directory_fields` already matches against,
   imported rather than copied -- tolerant of a leading bullet/dash/asterisk
   marker, with the value read after the line's `:`/`#`/`-` separator plus
   any non-labeled continuation lines. Its results are merged with
   `_document_field_values`'s.
2. **Safety rule:** `assess_field_coverage` now only ever places a field in
   `unsupported` when BOTH (a) every approved document is directory-shaped
   (`_all_evidence_is_directory_shaped`, reusing `app.response.outcome`'s
   own `_is_directory_shaped` predicate -- imported, not re-derived) AND
   (b) the field's label does not appear anywhere in any document's content
   at all (`_field_mentioned_anywhere`, a raw fragment search independent of
   whether a clean value could be parsed). Every other case -- no evidence,
   any non-directory/prose evidence present, or a label mentioned in some
   unparsed shape -- falls back to `omitted` instead: "no value collected",
   never the stronger, wrong claim "this fact does not exist". This is the
   safe direction: it can only ever under-report a real gap, never fabricate
   one for a fact the evidence actually states.

New tests (`tests/unit/test_cx_partial_answer.py`) cover: the real Kenya
record shape (bulleted minimum order, delivery cost, payment methods, then
a contact block) -- payment_methods/delivery_cost answered when the answer
uses the value, omitted (never unsupported) when it does not; a field the
same record genuinely lacks (delivery_time) -- still correctly
`unsupported`; policy-prose-only evidence -- never `unsupported`; mixed
directory + policy evidence -- never `unsupported`; no evidence at all --
never `unsupported`; es/fr/de questions against the bulleted fields.

**Test run:**
```
pytest tests/unit/test_cx_partial_answer.py tests/unit/test_cx_answer_quality.py
       tests/conversation -q
                                                          -> 419 passed
pytest tests/unit/test_cx_compose.py -q                  -> 51 passed
pytest tests/unit/test_cx_outcome_wiring.py -q           -> 13 passed (no
       failures found -- `fields_answered`/`fields_unsupported` are not yet
       wired into `derive_outcome`'s call sites in this worktree, so nothing
       in that file currently exercises this module's output; nothing to
       report back to the coordinator)
flake8 app/response/partial_answer.py tests/unit/test_cx_partial_answer.py
                                                          -> exit 0 (clean)
git diff --check                                          -> exit 0 (clean)
```
