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
pytest tests/unit/test_cx_partial_answer.py tests/unit/test_cx_answer_quality.py -q
                                                          -> 44 passed
pytest tests/unit/test_response_quality.py tests/unit/test_response_builder.py tests/conversation -q
                                                          -> 385 passed
flake8 app/response/partial_answer.py app/response/quality.py
       tests/unit/test_cx_partial_answer.py tests/unit/test_cx_answer_quality.py
                                                          -> exit 0 (clean)
git diff --check                                          -> exit 0 (clean)
```
