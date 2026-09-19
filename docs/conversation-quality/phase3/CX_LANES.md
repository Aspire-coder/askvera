# CX lane contract (authoritative for lanes 2-7)

Coordinator: Claude Opus. Branch `cx/conversation-experience-20260918`, based on
the independently reviewed candidate `a53dcae`. The design is
`CX_DESIGN.md` (conv-quality worktree); this file fixes the shared names and
the rules every lane follows.

## Shared rules (every lane)

- **Consume decisions, never make them.** No lane changes retrieval, ranking,
  scope-aware fusion, evidence approval, country authorization or the prompt.
  The prompt budget test is never raised.
- **One outcome object.** `app/response/outcome.py` (Lane 1) is the only
  outcome type. Lanes read `ConversationOutcome`/`OutcomeKind`; they do not add
  a parallel status field.
- **No duplicated vocabularies.** Reuse `utils/directory_fields`,
  `config/directory_field_vocabulary.py`, `config/reference_vocabulary.py`,
  `app/retrieval/typo_safety.py` (read-only, Codex-owned) and
  `services/market_config`. A new closed vocabulary is allowed only where none
  exists, lives in `config/`, and is documented with its confidence per language.
- **No hardcoded case ids**, no market-specific conditions written around one
  example, and every behaviour is tested in at least one non-English language.
- **Never weaken tests.** Don't delete or loosen an existing assertion. V2
  (`app/experimental/**`, `tests/evidence_first_v2/**`) is off limits.
- **`chat_orchestrator.py` is single-writer (the coordinator).** Lanes expose
  pure functions plus a documented hook signature; the coordinator wires them.
- **Copy is data.** Any user-visible sentence is a message key in
  `config/conversation_routes.json` (Lane 4 is the only writer). Other lanes
  refer to keys by the names below and pass placeholder values; they never
  inline an English sentence in code.
- Offline only: no network, AWS, Bedrock or secrets. Tests run with the project
  venv, `-p no:cacheprovider -o addopts=""`, in the foreground.

## Message keys (Lane 4 writes; the others reference)

| Key | Placeholders | Used by |
|---|---|---|
| `evidence_missing_detail` | `{topic}` | outcome evidence_missing |
| `dependency_unavailable` | none | outcome dependency_unavailable (`bedrock_error` stays as an alias) |
| `cross_market_policy_scope` | `{country}` | outcome cross_market_policy |
| `international_directory_note` | `{country}` | outcome international_directory |
| `personal_account_limit` | none | Lane 3 |
| `partial_answer_gap` | `{fields}` | Lane 2 |
| `clarify_field` | `{options}` | Lane 5 (typo, one question) |
| `clarify_country` | `{options}` | Lane 5 |
| `clarify_role` | `{options}` | Lane 5 |
| `repair_ack` | none | Lane 5 |
| `contact_offer` | `{contact}` | Lane 3 |
| `suggest_intro` | none | Lane 3 |
| `suggest_topic_<name>` | none | Lane 3: a small closed set, e.g. `suggest_topic_delivery_cost`, `suggest_topic_payment_methods`, `suggest_topic_contact`, `suggest_topic_returns` |

Placeholders are filled after localization. A translation that loses or
changes a placeholder is rejected, and the English copy is used instead.
`{options}` and `{fields}` are joined by `app/response/cx_render.py` (Lane 4)
with the locale's list separator.

## Lane write scopes

| Lane | Writes (only) |
|---|---|
| 2 Partial answers | `app/response/partial_answer.py`, `tests/unit/test_cx_partial_answer.py` |
| 3 Contacts, suggestions, personal account | `app/response/contact_completion.py` (extend), `app/response/suggestions.py`, `app/response/personal_account.py`, `config/personal_account_vocabulary.py`, `tests/unit/test_cx_contacts_suggestions.py`, `tests/unit/test_cx_personal_account.py` |
| 4 Localization and rendering | `config/conversation_routes.json`, `app/response/cx_render.py`, `tests/unit/test_cx_render.py`, and any pin or test that must be re-pinned because routes changed (with a dated comment) |
| 5 Repair and typo clarification | `app/orchestrator/conversation_repair.py`, `config/repair_vocabulary.py`, `tests/unit/test_cx_repair.py` |
| 6 Evaluation | `tests/conversation_pack/cx/**` (new cases only; frozen held-out content is never edited) |
| 7 Answer language | `app/orchestrator/answer_language.py`, `tests/unit/test_cx_answer_language.py` |
| Coordinator | `app/orchestrator/chat_orchestrator.py` wiring, `app/response/outcome.py` fixes after Lane 1, docs |

Each lane also writes one doc: `docs/conversation-quality/phase3/CX_LANE<n>_*.md`.

## Coordinator wiring checklist

- [ ] Extract the orchestrator-private `_support_contact_segments` / `_directory_record_matches_a_target` into a shared utility and make both `chat_orchestrator.py` and `app/response/outcome.py` import it (Lane 1's `f51d974` re-implemented the same shape locally to avoid importing the orchestrator).
- [ ] Attach `derive_outcome(...).to_metadata()` to `ChatResponse.metadata["outcome"]` once per turn, on every return path (answers and every fallback builder).
- [ ] Fold in the R05 LOW fixes (a single policy-wording helper at all four sites; comment corrections).
