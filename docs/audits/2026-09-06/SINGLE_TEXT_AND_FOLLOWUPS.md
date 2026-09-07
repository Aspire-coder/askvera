# Single-text contract and follow-up coverage

## Local implementation complete; model integration pending

`assemble_bound_segments` accepts only ordered source-bound segments. It derives
the displayed text from those exact segments and preserves each source reference.
There is no separately generated answer to drift. Legacy answer/claims payloads
are not silently converted or repaired. Existing quote validation and total-size
limits remain. The function is opt-in and has no production caller.

This fixes representation consistency only. A well-formed segment can still be
irrelevant, incomplete, unsafe, or unsupported in meaning despite an authentic
quote. Refusal/clarification outputs remain on existing controlled paths; this
factual segment contract is not a replacement for those paths.

## Follow-up tracking retained explicitly

`scripts/conversation_comparison.py` records separate Current and Candidate
histories with the exact request, selected country/language, actual delivered
answer, citations/trace fields returned by the adapter, and per-turn expectations.
Expected behavior is never sent to the chatbot. Each version receives only its
own prior answers. Explicit selection changes are passed through unchanged.
New sequences start empty. Rejected drafts are not accepted as delivered turns.
Execution errors stop the comparison and preserve partial records on the raised
exception rather than invent a reply or continue with contaminated context.

This recorder does not itself resolve pronouns, retrieve documents, persist to
production sessions, run safety checks or decide correctness. Isolated chat
adapters must perform those actions and return the real delivered answer.

`tests/fixtures/followup_conversations.json` defines **7 sequences / 21 turns**:

1. Monthly activity -> previous-month credits -> now-requested bonuses.
2. Belgian sponsoring -> Germany -> telephone-only follow-up.
3. Restricted Belgian company policy -> dependent follow-up -> explicit US switch.
4. Missing sponsoring details -> country/phone typos supplied -> explanation follow-up.
5. German policy -> English translation -> explicit Canadian market change.
6. Supported qualification plus unsafe caption -> product cost -> renewed unsafe request.
7. Fresh-session ambiguity -> Belgian sponsoring -> unrelated weather.

These are behavioral expectations, not source-verified factual gold answers.
Active-document evidence must be checked before grading factual values. No model
has yet run these sequences; they are not 21 passing chatbot cases.

## Verification

- 20 new unit tests; full local suite **1,219 passed**, two existing dependency warnings.
- Tests cover exact segment assembly, wrong/stale quotes, limits, immutability,
  arm isolation, selected-locale changes, hidden gold labels, fresh histories,
  rejected drafts and preservation of completed turns on failure.
- Graph refresh attempted; graphify unavailable and no graph present.
- No AWS/model calls, production deployment, cache/index changes, commit or push.

## Next required work

Wire the segments-only schema into the isolated writer experiment without the
extra planner, compare against the frozen dual-text contract, and inspect both
outputs. Connect fully validated chat adapters to the conversation recorder,
persist each run's results, and run all 21 turns for both versions with fresh
sessions/repeats. Check actual resolution of references, country/global scope,
clarification loops, safety, factual completeness and latency. Only then consider
runtime activation. Current local tests do not establish general answer-quality
or follow-up improvement.
