# CX Lane 8: compose_cx_response

`app/response/cx_compose.py`, `tests/unit/test_cx_compose.py`. Reads
`docs/conversation-quality/phase3/CX_LANES.md` (binding) and assembles the
pieces lanes 1-7 already built -- `ConversationOutcome` (Lane 1),
`assess_field_coverage` (Lane 2), `contact_escalation` / `suggest_follow_ups`
/ `detect_personal_account_request` (Lane 3), `cx_render.render` /
`join_list` (Lane 4) -- into one pure function that produces the final
CX-layered `ChatResponse` for a turn.

## API

```python
def compose_cx_response(
    response: ChatResponse,
    outcome: ConversationOutcome,
    *,
    question: str,
    language: str,
    country: str,
    evidence_documents: Sequence[RetrievedDocument],
    topic_supported: Callable[[str, str], bool],
    render: Callable[..., str] = cx_render.render,
) -> tuple[ChatResponse, dict]:
```

Returns the new `ChatResponse` (every existing metadata key preserved except
`metadata["outcome"]`, refreshed when field coverage promotes the outcome to
`partial_answer`, and the new `metadata["cx_applied"]`) plus the same small
`{"cx_applied": [...]}` dict as a second value, for a caller or test that
wants it without re-reading `response.metadata`.

`evidence_documents` must already be this turn's APPROVED evidence (the same
`EvidenceDecision.evidence` value `app/response/partial_answer.py` itself
documents) -- this module does no approval or ranking of its own.

## The call the coordinator should make

At the existing choke point, `_attach_conversation_outcome`
(`app/orchestrator/chat_orchestrator.py`), right after `derive_outcome(...)`
is computed and before (or in place of) the existing
`self._replace_answer(response, response.answer, {"outcome": outcome.to_metadata()})`
call:

```python
response, _cx_meta = compose_cx_response(
    response,
    outcome,
    question=question,
    language=body.language,
    country=body.country,
    evidence_documents=getattr(_TURN_EVIDENCE.get(), "evidence", None) or (),
    topic_supported=<market-evidence-coverage predicate>,
)
```

- `evidence_documents` comes from the same `_TURN_EVIDENCE` contextvar
  `_attach_conversation_outcome` already reads to build `evidence_decision`
  for `derive_outcome` -- its `.evidence` attribute (approved documents), not
  raw retrieval results. `_TURN_EVIDENCE.get()` may be `None` on a
  pre-retrieval fallback turn; the coordinator should pass `()` in that case
  (this module accepts an empty sequence -- `assess_field_coverage` then
  reports every requested field as unsupported, exactly like having no
  evidence at all).
- `topic_supported(topic, country)` needs its own signal (Lane 3's brief,
  `CX_LANE3_CONTACTS_SUGGESTIONS_ACCOUNT.md`, recommends approved
  directory-record field coverage for the market); this lane does not
  provide one, only the injection point.
- `compose_cx_response` already writes `metadata["outcome"]` (including the
  `partial_answer` promotion) and `metadata["cx_applied"]`, so once wired the
  coordinator's own `self._replace_answer(..., {"outcome": ...})` call
  becomes redundant for the outcome key and should be dropped in favour of
  using `response` as returned here directly.

## Fixed order (never re-applied, never reordered)

1. `strip_leading_preamble(answer, language)`.
2. `assess_field_coverage(question, language, answer, evidence_documents)`;
   if any requested field is unsupported, render ONE `partial_answer_gap`
   note. Unlike `app/response/partial_answer.py`'s own `partial_answer_note`
   (which reports raw field ids and deliberately does not localize or join
   them), this lane does the localization itself: each unsupported field id
   is rendered through its own `field_label_<id>` key, then joined with
   `cx_render.join_list`, before filling the note's `{fields}` placeholder.
   When this fires, the outcome carried forward for every later step is
   replaced (kind -> `partial_answer`, `fields_answered`/`fields_unsupported`
   set from the computed coverage).
3. `detect_personal_account_request(question, language)` -> append
   `personal_account_limit` once. Not a refusal -- the answer stays.
4. `contact_escalation(outcome, ...)` -- handles its own eligible-kind set
   and dedup (recommendation-phrase detection, and a plain substring check
   against the session market's reviewed phone/website/email values, so a
   contact the orchestrator's own `_office_contact_addendum` or
   `_apply_support_contact_supplement` already appended is never repeated).
5. `international_directory_note` -- only for the original
   `international_directory` outcome kind (checked before any
   `partial_answer` promotion, since `directory_target` only ever means
   something for that kind), rendered with `{country}` = `directory_target`,
   unless the answer already names that market (an accent-folded substring
   check against each `/`-separated segment of `directory_target`, e.g.
   `"Kenya/East Africa"` matches an answer naming either "Kenya" or "East
   Africa").
6. `suggest_follow_ups(...)` -> each key rendered and placed into
   `ChatResponse.suggestions` as `{"type": "follow_up", "key": <key>,
   "text": <rendered>}` -- see "Suggestions item shape" below. Never
   appended to the answer text.

Steps 1-3 and 5 only run for an answer-shaped outcome kind (`answer`,
`international_directory`, `partial_answer`). Steps 4 and 6 also run for the
fallback kinds (`evidence_missing`, `cross_market_policy`,
`dependency_unavailable`, `personal_account`), whose own reviewed fallback
copy is otherwise left byte-for-byte untouched.
`clarification`/`safety_refusal` get no addition at all, and neither does a
response whose `metadata.get("response_source")` is `"guardrail"` or
`"client_action"`, or whose `metadata.get("failure_layer")` is one of the
governance/PII values (`local_guardrail`, `risk_policy`, `aws_guardrail`,
`sensitive_pii_input`) -- both checks return the original `response` object
unchanged, with `{"cx_applied": []}`.

## Suggestions item shape

No existing caller in this codebase populates `ChatResponse.suggestions`
with a concrete shape (every constructor in the codebase passes `[]`), so
this lane fixes one, following the brief's own example exactly:

```python
{"type": "follow_up", "key": "suggest_topic_delivery_cost", "text": "Delivery cost"}
```

`key` is the raw `suggest_topic_<name>` message key (for a client or a test
to key off of); `text` is that key rendered in `language` via the same
`render` callable everything else in this module uses.

## Invariants enforced here

- Citations are never touched (`ChatResponse.citations` passed through
  unchanged).
- Every existing `response.metadata` key survives; only `"outcome"` and
  `"cx_applied"` are added or changed.
- The answer is never emptied -- only ever appended to, and only when the
  original answer is non-empty is a leading blank line avoided.
- Each addition is joined with `"\n\n"` (its own paragraph).
- A final regex check (`\{[a-zA-Z_][a-zA-Z0-9_]*\}`) runs on the composed
  answer before returning; an unfilled placeholder raises `ValueError`
  rather than ever being delivered (mirrors, and is independent of, the
  orchestrator's own `_UNFILLED_CX_PLACEHOLDER_RE` delivered-response check).
- Deterministic: no randomness, no clock, no I/O.
- Every addition is rendered in `language` via the injected `render`
  callable -- this module never inlines English copy.

## Tests

`tests/unit/test_cx_compose.py`: every outcome kind's addition set, in en
plus es/fr/de/fi for the localized additions (partial-answer note,
personal-account note); the dedup against a contact the answer already
recommends or already quotes (including one shaped like the orchestrator's
own support-contact supplement); a real unsupported directory field over
real `RetrievedDocument` evidence; suggestions excluded for an unsupported
topic and for the question's own topic, and excluded entirely for
`dependency_unavailable`; the `international_directory_note` compound-target
match; and each global invariant (citations/metadata/never-empty/paragraph
separation/determinism/no-unfilled-placeholder/guardrail and governance
suppression/clarification and safety_refusal no-op) as its own test.
