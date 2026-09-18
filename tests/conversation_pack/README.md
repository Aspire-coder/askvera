# Conversation regression pack (Lane G)

A development, multi-turn regression pack for AskVera's conversation quality
project. It is a black-box, offline replay of the real orchestrator through
scripted sessions, plus a manifest recording what each turn is expected to
do and why.

**Passing this pack is not proof that production answers correctly.** Every
mechanism here runs against a fake retriever/router and monkeypatched
session/cache/consent/audit hooks, the same offline harness pattern used by
`tests/unit/test_demo_followup_resolution.py::_run_session` and
`tests/unit/test_demo_journeys_postprocessing.py::_deliver`. No live model
call, no real OpenSearch/embeddings, no AWS call, no network call happens
anywhere in this pack. A case that passes here has only been shown correct
at the layer its mechanism actually exercises (query resolution, the
evidence gate, deterministic post-generation field handling, governance
text evaluation, or cross-session cache/state isolation) — never at the
layer of "did the live model say the right sentence."

## Files

- `cases.json` — the manifest. One entry per case: `id`, `category`,
  `paraphrase_family`, `provenance_class`, `mechanism` (+ `mechanism_params`),
  `turns` (each with `session_country`, `role`, `language`, `message`,
  `expected_outcome`, `required_facts`, `forbidden_facts` — every fact carries
  a `source`), `needs_live` (+ `needs_live_reason` when true), and `notes`.
  A case with an `xfail_reason` key is a confirmed, reproduced defect in the
  current code (see "Findings" below).
- `test_conversation_pack.py` — the pytest runner. Reads `cases.json`,
  dispatches each case to one of a small set of mechanisms, and asserts only
  what that mechanism can honestly check.

## Running it

```
<python> -m pytest tests/conversation_pack/ -v
```

from inside this worktree, where `<python>` is the project's `.codex-py311-venv`
interpreter. No network, no live model, no installs.

## Labels

**`provenance_class`**
- `source-grounded` — the expected fact was copied, with a file/section
  reference, from a reviewed source: `us_policy.txt`, the International
  Sponsoring Directory fixtures already used in
  `tests/unit/test_demo_journeys_postprocessing.py` (Kenya, Netherlands
  Benelux), or `config/public_contacts.json` / `config/markets.json`.
- `synthetic-control` — a deliberately invented negative/adversarial probe
  (a cross-market policy request, an unrelated guardrail trigger, a
  compound safe-question-plus-unsafe-command). There is no source for the
  forbidden fact because it should never be said at all.
- `behavioural` — a routing/state expectation with no factual payload
  (directory-target inheritance, topic-change release, cross-session
  isolation). The source is the orchestrator code path itself, cited in the
  case's `notes`.

**`expected_outcome`** (per turn): `answer`, `clarify`, `refuse-scope`,
`refuse-country-restriction`, `missing-evidence`, `dependency-failure`.

**`needs_live`** — `true` means the offline mechanism cannot honestly judge
the case (it depends on real model composition: does the model actually say
X, in language Y, splitting a two-part question correctly). These are run
and skipped, never faked. Full needs-live list, with reasons in `cases.json`:

| Case | Why it needs a live run |
|---|---|
| `US-POLICY-001`, `US-POLICY-002` | Whether the model states the FLP-identity fact and withholds the unrelated income disclaimer is generation composition (task C1 on TASK_BOARD.md); offline only confirms the evidence gate doesn't block/misroute it. |
| `LANGUAGE-SELECTOR-SWITCH-001` | Offline confirms the topic is kept across a mid-session language-selector change; whether the response text is actually produced in the new language depends on live prompt/model composition (TASK_BOARD.md item A6). |
| `TYPO-001`, `TYPO-002` | Typo tolerance lives in `app/retrieval/typo_safety.py` and the OpenSearch scoring pipeline (Codex-owned, `app/retrieval/**`), which needs a real search backend. A fake retriever keyed by exact fixture selection would fake a pass by construction. |
| `MULTIPART-001` | The offline half (post-processing must not destroy an already-correct two-part answer) is asserted directly — and currently fails; see Findings. Whether the live model actually *composes* both parts of a two-part question in the first place (task B3) needs a real generation run and is flagged separately. |
| `UNKNOWN-001`, `UNKNOWN-002` | Offline confirms the retrieved evidence contains no basis for the forbidden fact (structural grounding check). Whether the live answer actually states the gap honestly instead of inventing something needs a real generation run. |
| `GUARDRAIL-MISFIRE-001/002/003` | Offline confirms the governance layer does not block the question. The actual defect these controls target (the model volunteering an unrelated disclaimer/refusal anyway, task C1/C2) is a generation-composition behavior. |

## Findings (confirmed defects, `xfail(strict=True)`)

One case is pinned as a reproduced, confirmed defect rather than a
needs-live unknowns — the offline mechanism itself demonstrates the bug
deterministically, with no model involved. They will flip to a visible,
unexpected pass (and fail the build via `strict=True`) the moment the
underlying code is fixed.

### `CONTACT-KENYA-001`: expectation corrected, not a defect

Originally pinned here as a finding. The coordinator judged the expectation
itself to be wrong and corrected it.

- **Question**: "Is that the office phone or the order phone?"
- **Original expectation**: keep the office number and drop the order
  number `+254 71 0600206`.
- **Why that was wrong**: the user is asking *which number is which*. An
  answer that removes one of them leaves the user unable to tell the lines
  apart. The brief's requirement A1 is that the follow-up "retains Kenya and
  the referenced numbers".
- **Corrected expectation**: both numbers are kept, each under its own label
  (`Telephone Office`, `Telephone for Orders`). Current code already does
  this, so the case is now an ordinary pass.
- **Consistent with** `test_j14_office_phone_question_does_not_keep_the_order_phone_line`,
  where "Is that the office phone for Kenya?" asks about the office line only
  and correctly drops the order number. `_ORDER_PHONE_REQUEST_RE` treating
  "order" as a request for the order line is the right behaviour for both
  questions.

### `MULTIPART-001`
- **Case**: "What is the minimum order for an FBO in Kenya, and what
  payment methods do they accept?" — with an already-correct, two-part
  scripted model answer (`$100 worth of products when joining ... Mpesa`).
- **Expected**: post-processing preserves both parts of the answer.
- **Actual**: the payment-methods sentence is deleted; only the
  minimum-order sentence survives.
- **Suspected layer**: `utils/directory_fields.py:660-671`. The dedicated
  minimum-order-question branch of `remove_unrequested_directory_fields`
  matches `r"\b(minimum|ordering|order)\b.*\b(order|size)\b|\border\s+size\b"`
  and then unconditionally strips every
  payment-methods/delivery-cost/delivery-time/business-hours sentence "so
  an order-size answer still sheds unrelated payment/delivery/hours prose
  exactly as before" (comment at 660-663) — without checking whether the
  *same* question also explicitly names one of those fields. Any
  two-part question that includes an order-size clause always loses the
  other half's content at this layer, independent of what the model
  generated.
- **Related task**: TASK_BOARD.md B3 ("Two-part question... both parts
  answered, or the unestablished part named"). This finding shows the
  post-processing layer will destroy a correct two-part answer even before
  task B3's generation-composition question is reached.
- **Lane C ownership**; not fixed here per this lane's file boundary.

## Coverage

Every category named in the project brief has at least one case in
`cases.json`, verified by
`test_every_required_category_is_covered`: US policy questions;
international sponsoring asked from a different session country (allowed);
company policy of another country from a US session (not allowed); phone
contact follow-ups (including the exact Kenya "office phone or order phone"
and "office hours" follow-ups from the brief); role changes (FBO vs
Preferred Customer); explicit country changes; topic changes; multilingual
follow-ups; a mid-session language-selector switch; typos; multi-part
questions; unknown facts; the three unrelated-guardrail controls named in
the brief; and cross-conversation isolation. Paraphrase families
(`paraphrase_family`) group related cases; negative/adversarial controls
are marked `provenance_class: synthetic-control`.

## What this pack deliberately does not do

- It does not call any live model, any real retrieval backend, or AWS. A
  case that would require that to be honestly judged is `needs_live` and
  skipped, not simulated.
- It does not touch `app/retrieval/**` behavior (Codex-owned) beyond
  reading it to write accurate findings; typo tolerance and real ranking
  are entirely out of this pack's offline reach.
- It does not modify any held-out/frozen fixture, hash, or evaluation file.
  Every question here is newly written for this pack; facts are copied from
  `us_policy.txt`, `us_testing_cases.md` (used only as a source of reviewed
  facts, never as a source of question text to copy), the Kenya/Netherlands
  Benelux fixtures already public inside
  `tests/unit/test_demo_journeys_postprocessing.py`, and
  `config/public_contacts.json` / `config/markets.json`.
