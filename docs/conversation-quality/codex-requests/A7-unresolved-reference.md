# Codex interface request: flag an unresolvable back-reference (task A7)

From: conversation-quality coordinator. 2026-09-18.
Status: open. Nothing here blocks Codex's current work.

## Reproduction (offline, deterministic)

`tests/conversation/test_followup_state_e2e.py::test_a7_the_other_one_after_two_named_markets_does_not_silently_answer_for_one`
(currently a strict xfail).

```
user: What is the delivery cost in Kenya?
vera: ...
user: What about Uganda?
vera: ...
user: What about the other one?
```

The third turn reaches retrieval targeting Uganda alone
(`_directory_target_country_names(query, "US") == {"Uganda"}`). Uganda is the
market just discussed, which is the one reading "the other one" cannot have.
The user gets an answer about the wrong market with no clarification.

## Why this is not fixed on the conversation side

`AIOrchestrator._contains_topic_shift_marker` recognises "What about ..." and
welds the tail onto the latest anchor. To separate "What about the other one?"
from a legitimate topic follow-up such as "What about returns?", the
orchestrator would need one of these:

1. An anaphor phrase list ("the other one", "that one", "the second"). It
   would be English-only, and the brief forbids growing phrase lists for
   multilingual behaviour. Lane A proposed exactly this and it was rejected.
2. A test that the tail contains no recognised field or topic word. It would
   wrongly clarify every legitimate topic whose word is missing from the
   `LOCALIZED_*` vocabularies. That is a regression on a common path to fix a
   rare one.
3. A semantic judgement. That is what the intent planner already does.

## Requested interface

In the existing planner/classifier output (no new model call), expose one
field, for example:

```
unresolved_reference: bool
```

It should be true when the message refers back to an entity (market, office,
role, document) that the current message does not name, and which the
conversation offers two or more candidates for. It should be false when the
message names its own entity, or when only one candidate exists.

Conversation side, once the field exists: when it is true, and the session's
own user turns name two or more distinct markets, route to the existing
`_directory_clarification_response` path. That produces the brief
clarification A7 requires.

## Acceptance

- The A7 xfail above flips to pass.
- "What about returns?" and "What about delivery?" after the same history
  still resolve normally. Negative controls are to be added with the fix.
- It works in every configured language through the planner rather than
  through vocabulary lists.
