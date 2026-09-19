# CX Lane 7: answer language (X1, approval 6, option B)

Status: implemented as pure functions in `app/orchestrator/answer_language.py`.
Not wired into `chat_orchestrator.py` - that is the coordinator's job
(`chat_orchestrator.py` is single-writer per `CX_LANES.md`).

## Decision this implements

`docs/conversation-quality/phase2/X1_LANGUAGE_SWITCH_DECISION.md`, option B,
approved 2026-09-18: when a user writes in a language other than the widget's
selected `body.language`, the ANSWER follows the message language
(answer-only). Retrieval and source eligibility keep using the selected
`body.language`, unchanged - that split is authorization (retrieval) vs.
presentation (answer language) and must never blur.

## Public API

```python
detect_message_language(message, *, candidates=ROUTE_COPY_LANGUAGES) -> Detection(language, score, runner_up, reason)
resolve_answer_language(message, selected_language) -> AnswerLanguage(answer_language, switched, reason)
retrieval_language(selected_language, answer_language) -> str  # always returns selected_language
```

`ROUTE_COPY_LANGUAGES = ("da", "de", "en", "es", "fi", "fr", "it", "nl", "no", "ru", "sr", "sv")`
- the 12 `config/conversation_routes.json` locale keys; `resolve_answer_language`
never switches into a language outside this set.

## Detection method

Deterministic, model-free marker-word counting - no network, no per-run
state. For each candidate language, count how many of the message's tokens
(NFKD-decomposed, accent-stripped, casefolded, letters only - a numeric/code
token never counts) are members of that language's closed-class marker-word
set (`MARKER_WORDS`): articles, prepositions, conjunctions, WH-question
words, pronouns, copula/auxiliary verbs.

**Script signal.** Cyrillic and Latin letters are detected separately. A
message containing both is `mixed_script` and returns no language
(ambiguous, per the X1 decision). A Cyrillic-only message restricts scoring
to `{ru, sr}` (Serbian is written in either script); a Latin-only message
scores every candidate except `ru`.

**Marker-word provenance (no duplicated vocabularies).**
`config.reference_vocabulary.LOCALIZED_NON_CONTENT_TOKENS` already reviews
this exact closed grammatical class for 9 of the 12 route-copy languages
(en, fr, de, nl, it, es, fi, sv, no) and is reused verbatim. The remaining
three (da, ru, sr) are not present there as a per-language dict - the only
place they exist is `chat_orchestrator.py`'s
`LOCALIZED_FOLLOW_UP_STOP_WORDS` / `LOCALIZED_FOLLOW_UP_FUNCTION_WORDS`, but
both are built as one flat merged set for a different purpose (blanket
function-word stripping), not keyed by language, and importing
`chat_orchestrator.py` here would create an import cycle once the
coordinator wires this module into it. `answer_language.py` therefore
carries a small, literal supplement for da/ru/sr only, copied token-for-token
from those two tables' per-language lines (order confirmed against
`LOCALIZED_TOPIC_SHIFT_OPENERS`, which keys the same per-language groups
explicitly) - see the module docstring for the full citation.

## Switch threshold (documented, conservative)

A switch happens only when ALL of the following hold:

- at least `MIN_TOKENS = 4` word tokens in the message (blocks single-word
  and very short messages, and numbers/codes-only messages, which tokenize
  to zero words);
- the detected language has at least `MIN_MARKER_HITS = 3` marker hits;
- its margin over the runner-up candidate is at least `MIN_MARGIN = 2`;
- extra margin required for closely related pairs: `no`/`da`/`sv` need
  `MIN_MARGIN + 2` between each other (their function words overlap
  heavily - "og"/"og"/"och", "for", "til"/"till"); Serbian (`sr`, either
  script) needs `MIN_MARGIN + 2` against any other candidate, because its
  Latin form shares short function words with unrelated Latin-script
  languages by coincidence.
- the detected language must differ from the selected language and be a
  member of `ROUTE_COPY_LANGUAGES`.

Any message that does not clear every gate keeps `selected_language`
unswitched; `resolve_answer_language` always returns a language (the
selection, never `None`) and a `reason` documenting the branch taken
(`too_short`, `matches_selected`, `mixed_script`, `no_letters`,
`no_marker_hits`, `below_threshold`, or `strong_signal` on a switch).

## Retrieval-eligibility invariant

`retrieval_language(selected_language, answer_language)` is an explicit,
greppable no-op: it always returns `selected_language`, regardless of
`answer_language`. It exists so the invariant the X1 decision requires -
retrieval and source eligibility stay on the selected language even when the
answer switches - is directly testable and greppable at every call site,
rather than an implicit assumption.

## Prompt question (no prompt edit made)

`app/prompts/templates.py`'s `SYSTEM_PROMPT` has exactly one language
placeholder, `User language: {{user_language}}` (line 54), and one earlier
instruction that reads ambiguously in isolation: "Keep the complete response
in that language, including headings and support guidance" (line 8). Read
together with the `User language:` line below it, "that language" already
resolves to whatever value is substituted for `{{user_language}}` - there is
no second, independent language reference for the two lines to disagree
about.

`app/prompts/builder.py` (`PromptBuilder.build`, line 58) substitutes its
`language` parameter directly into `{{user_language}}`:
`persona.replace("{{user_language}}", language)`. Today the coordinator
passes `body.language` as `language`; the X1 conflict the design doc
describes ("User language: en" plus an instruction to answer in the user's
own language) is a conflict only because two different values were meant -
the selector value and the message's actual language - and only one
placeholder exists to carry either.

**Preferred fix confirmed, no prompt text change needed:** the coordinator
passes `resolve_answer_language(...).answer_language` as `PromptBuilder.build`'s
`language` argument instead of `body.language`. Once `{{user_language}}` is
filled with the resolved answer language, "User language: {answer_language}"
and "Keep the complete response in that language" agree by construction -
the same substitution already used for the deterministic copy and
post-processing vocabularies. This requires zero characters of prompt text
change and therefore no `PROMPT_VERSION` bump; the 4383/4392-character prompt
budget is unaffected.

(A wording-only fallback - e.g. rephrasing line 8 to explicitly cross-
reference the `User language:` line - was considered but not measured in
detail, because it is unnecessary: the prompt's remaining headroom is only
4392 - 4383 = 9 characters, so any added words risk the budget for no
benefit when the zero-text-change substitution above already resolves the
ambiguity. The no-text-change fix is therefore the recommendation, not a
fallback.)

## Hook sites for the coordinator (not wired here; lane write scope excludes `chat_orchestrator.py`)

Per `CX_DESIGN.md`'s "Answer language" section, `answer_language` should
drive three things, once per turn, after `resolve_answer_language` runs:

1. **Prompt** - `PromptBuilder.build(..., language=answer_language, ...)`
   instead of `body.language` (see above; no prompt text change).
2. **Deterministic/localized copy** - wherever `chat_orchestrator.py` or
   `app/response/cx_render.py` (Lane 4) selects `conversation_routes.json`
   locale copy, select on `answer_language` instead of `body.language`.
3. **Post-processing vocabularies** - the Phase 2 A/B/C/F language-aware
   post-processing steps (e.g. `utils/directory_fields`,
   `config/directory_field_vocabulary.py`-driven field interpretation of the
   generated answer) key off `answer_language`.

**Never** item 4, retrieval: `app/retrieval/*` and the document-language /
same-country English fallback (`OPENSEARCH_GLOBAL_DOCUMENT_LANGUAGE`) keep
`body.language` untouched, enforced by always calling
`retrieval_language(selected_language, answer_language)` (which is always
`selected_language`) at that call site rather than `answer_language` directly.

## Tests

`tests/unit/test_cx_answer_language.py` - 25 tests: switched (French text,
English widget), unswitched (English text, English widget), a short message
("Merci") not switching, a mixed French/English message not switching,
Norwegian/Swedish and Danish/Swedish near-pair guards, Cyrillic Russian vs.
Cyrillic Serbian disambiguation, a numbers-only message not switching, the
`retrieval_language` invariant (including that it never depends on
`answer_language`'s value), and determinism. No case ids; every scenario is a
constructed, generic sentence in its language.

## Verification run (2026-09-18, worktree `askvera-cx-lane7`, branch `cx/lane7-20260918`)

- `pytest tests/unit/test_cx_answer_language.py` - 25 passed.
- `pytest tests/conversation` - 350 passed (unchanged; confirms no regression
  from this lane, which touches no shared code path yet).
- No `tests/unit/test_prompt*.py` files exist in this worktree to re-run.
- `flake8 app/orchestrator/answer_language.py tests/unit/test_cx_answer_language.py` - clean.
- `git diff --check` - clean.
