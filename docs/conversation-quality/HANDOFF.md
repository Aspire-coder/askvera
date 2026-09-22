# AskVera conversation-quality candidate: handoff

Date: 2026-09-18. Coordinator: Claude Opus 5. Workers: four Claude Sonnet 5
lanes. Independent reviewer: Claude Fable 5.1, which wrote none of this code.

**Status: a reviewable, locally tested candidate. Not deployment-ready.** No
live chatbot run, model call, merge, push or deploy was made. The combined
system (this candidate plus Codex's retrieval work) has not been validated end
to end.

## 1. What users would notice

These results come from deterministic code paths, tested offline:

- **Two-part questions keep both answers.** "What is the minimum order in
  Kenya, and what payment methods do they accept?" used to lose the payment
  half *after* a correct answer was generated. Post-processing deleted it.
- **Durations are not read as office hours.** "…if I need it within 48 hours"
  no longer drags business hours into an order-size answer.
- **Decimal times are not cut in half.** Removing an unrequested hours line
  used to leave the fragment "00 am - 19.00 pm.".
- **Correct role figures survive.** "For FBOs, the minimum order size is
  50 USD" was deleted as unsupported even when the source said exactly that.
  Wrong-role and invented figures are still removed.
- **A Bedrock outage says so.** It used to surface as an HTTP error envelope
  with no failure layer. It now gives the localized "technical hiccup"
  message, distinct from "the documents don't cover this". The same applies
  to an embedding-service outage.

These are instructions to the model only. They are unverified without a live
run:

- A direct answer first, with no stock openers or sign-off questions.
- Concrete qualifications, amounts and periods instead of "specific
  requirements apply".
- Figures kept under their own role.
- Naming a part of the question that the evidence doesn't establish.
- Naming who to contact.

## 2. Commits and worktrees

| | Commit | Path |
|---|---|---|
| Baseline B0 | `5b1d33f` (`origin/main`) | intended production state; the live deploy was **not verified** this session |
| Baseline B1 | `d7b9747` | B0 plus 4 unmerged branches (see TASK_BOARD.md), merged locally |
| **Candidate** | `feat/conversation-quality-20260918`; code as tested is `dbc6a7a` (later commits are docs only) | `askvera-conv-quality` |
| Lane branches | `conv/{a-followup-state,b-composition,c-intent-contacts-recovery,g-regression-pack}-20260918` | `askvera-conv-*`: source material only; everything accepted is already in the candidate |

Review the candidate as `git diff d7b9747..<candidate>`.

## 3. Changed files, by task

| Task | Files |
|---|---|
| B3 / MULTIPART-001, hours, decimal split | `utils/directory_fields.py` |
| C5 / F1 dependency failures | `app/orchestrator/chat_orchestrator.py` |
| B5 role-bound figures | `app/validation/validators/numeric_grounding_validator.py` |
| B1, B2, B3, E1, handoff (prompt) | `app/prompts/templates.py`, `config/settings.py` (`PROMPT_VERSION` → `2026-09-18-composition-contract-v5`) |
| Approved-test pins moved with the prompt | `tests/unit/test_bedrock.py` (version string), `tests/unit/test_codex_conversation_tone.py` (rule-text SHA only; **no size budget changed**) |
| A1–A8 | `tests/conversation/test_followup_state_e2e.py` |
| C1, C2, D1, C5, B3, B5, composition | `tests/conversation/test_*.py` (7 files) |
| G1 regression pack | `tests/conversation_pack/` |
| Coordination | `docs/conversation-quality/` |

No Codex-owned file was edited (`app/retrieval/**`, `app/experimental/**`,
`scripts/ingestion/**`, glossary and alias configs). The independent reviewer
confirmed this.

## 4. Before and after

| # | Input | Before | After | Evidence |
|---|---|---|---|---|
| 1 | Q "minimum order for an FBO in Kenya, and what payment methods do they accept?" with a correct two-part answer | payment sentence deleted | both kept | tested (deterministic) |
| 2 | Q "minimum order size for an FBO if I need it delivered within 48 hours?" | business-hours sentence kept | removed | tested |
| 3 | Unrequested "Business hours are 09.00 am - 19.00 pm." | "00 am - 19.00 pm." left behind | removed whole | tested |
| 4 | "For FBOs, the minimum order size is 50 USD." with source "Minimum order size FBO: 50 USD." | flagged, sentence deleted | kept; "…is 100 USD" still flagged | tested |
| 5 | `generate()` raises `BedrockTimeoutError` | HTTP 504 envelope, no failure layer, turn not saved | "technical hiccup" answer, `dependency_unavailable`, turn saved | tested, mocked |
| 6 | Embedding service raises `AwsServiceError` | HTTP error envelope | as #5 | tested, mocked |
| 7 | OpenSearch unreachable | "documents do not contain enough information" | **unchanged** (see section 7) | reproduced by reviewer |
| 8 | "Is that the office phone or the order phone?" after a Kenya contact answer | both numbers, labelled | unchanged, and correct | pinned |
| 9 | Manager-qualification question | "specific requirements apply" (reported live) | prompt now asks for concrete qualifications | **illustration only**: no live run |

## 5. Tests

Command, from `askvera-conv-quality`:

```
<venv>\Scripts\python.exe -m pytest tests/unit tests/governance tests/conversation tests/conversation_pack -p no:cacheprovider
```

Result: see "Final verification" at the end of this document.

`pytest.ini` collects only `tests/unit` by default. The new directories must be
passed explicitly, or `testpaths` widened (`chore/measure-real-coverage-20260917` does that).

Labels: every new test states whether it is mocked/local, source-grounded or
prompt-structure only. **Passing them is not evidence that production answers
correctly.**

## 6. Independent review

Fable reviewed `a3d965f` against the diff and ran its own probes. It reported
7 findings: 1 blocker for a claim, 3 should-fix, 3 notes. All seven were
addressed. See the disposition table in `TASK_BOARD.md`. The blocker was a
false claim of mine: I had said a retrieval outage now gets dependency
wording. It doesn't for OpenSearch. That claim is corrected throughout.

Also rejected during integration, with reasons in TASK_BOARD.md:

- Lane A's English-regex A7 patch.
- Lane C's sentence-deleting pronoun editor.
- Lane B's prompt rewrite (+26% size, approved budgets raised to fit, a
  "consolidation" that removed nothing, and no cache-version bump).
- One worker test that asserted a defect as its passing condition (Lane A's
  A7 test), and one pack expectation that contradicted the brief
  (CONTACT-KENYA-001 expected the order number to be dropped).

## 7. Remaining failures and gaps

- **C5, retrieval half.** A real OpenSearch outage is still told to the user
  as missing evidence, and RetrievalHealth records success. Codex-owned; a
  request is filed.
- **A7.** "What about the other one?" after Kenya then Uganda answers for
  Uganda. Strict xfail; a request is filed.
- **B4.** Delivery timing vs approval timing: no deterministic reproduction
  found; Lane B's prompt rule was dropped to hold the budget.
- **B6.** Only the decimal-split remnant was fixed; there has been no general
  audit of post-validator remnants.
- **C3/C4.** Diagnosis only. The refused-but-supported cases point to
  retrieval and evidence approval. Several of the workbook cases cited were
  already fixed before this project, so they need a fresh live capture.
- **Language.** Only a selector change switches the response language. A
  message typed in another language under an unchanged selector isn't
  detected.
- **Multilingual field detection.** `_requested_directory_field_set` is
  English-only, so the MULTIPART fix does not reach a French two-part
  question. Pinned by a test; not widened.
- **Prompt rules.** All unverified until a live run.
- **Post-editor count unchanged.** This candidate added no new
  post-generation editor.

## 8. Requests for Codex

- `codex-requests/C5-retrieval-outage-masked-as-no-evidence.md`: surface a
  transport or timeout failure (a flag or a raise). Option "raise as
  `AwsServiceError`" needs no further change on this side.
- `codex-requests/A7-unresolved-reference.md`: an `unresolved_reference`
  field from the existing planner, with no new model call.
- `codex-requests/laneC-c3-c4-diagnosis.md`: supported facts refused, for
  evidence approval to look at.
- **Design overlap:** Codex's evidence-first-v2 has its own standalone-request,
  composition and validation stages that cover Lanes A–C. The user should
  decide which path owns composition.

## 9. Approval queue

Nothing below has been done.

| # | Action | Why | Cost | Output |
|---|---|---|---|---|
| 1 | Accept the monitoring change: Bedrock and escaping-retrieval outages count toward HighFallbackRate instead of HighErrorRate | C5 turns them into HTTP 200 fallbacks; on a quiet deployment a Bedrock outage may not page | none | a decision; or ask for a dedicated dependency metric and alarm |
| 2 | Live paired run of the conversation pack's needs-live cases and the 178-case US workbook, B0 against the candidate | the only way to measure the prompt rules (B1, B2, E1) and C1/C2 prose | about 200–400 Haiku generations; small | pass/fail per case with transcripts |
| 3 | Merge the four B1 branches, then this candidate | release | none | PRs |
| 4 | Deploy | release | — | only after #2 passes, and after Codex's retrieval changes are combined and re-validated |

## 10. Integrating

Conflict-sensitive files, in likely order of contention:

- `app/orchestrator/chat_orchestrator.py`. The only single-writer file here.
  Edits sit in `_handle_scrubbed_chat` around the `retrieve()` and
  `generate()` calls. Anything Codex wires in for evidence-first-v2 will
  touch the same method.
- `app/prompts/templates.py` plus `tests/unit/test_codex_conversation_tone.py`.
  Any other prompt change must re-pin `TEMPLATE_LATER_SHA256` and bump
  `PROMPT_VERSION` again, because both caches key on it.
- `utils/directory_fields.py`. Directory post-processing is shared with the
  contact-supplement path.
- `app/validation/validators/numeric_grounding_validator.py`.

Suggested order: merge the four B1 branches as their own PRs first, then this
branch. The candidate already contains them as merge commits, so merging them first leaves this branch's diff unchanged.

## Final verification

Run on the post-review working tree immediately before the final commit, with
pytest's own exit code captured (an earlier run's "exit 0" had been `tail`'s):

```
tests/unit tests/governance tests/conversation tests/conversation_pack
8902 passed, 4 skipped, 14 xfailed in 714.22s   PYTEST_EXIT=0
```

- 4 skipped: TYPO-001/002 (needs a real search backend) and UNKNOWN-001/002
  (premise verified, answer needs a live run).
- 14 xfailed: 13 already in the suite before this project, plus A7.
