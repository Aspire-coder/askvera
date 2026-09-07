# Segments-only comparison - frozen before calls

Same six questions, captured sources and semantic expectations as
ANSWER_PLAN_PROTOCOL.md. Two fresh repeats, two arms, 24 calls maximum.
Control uses the previous dual-text output; candidate generates segments only.
Neither uses a planning/reviewer call. Both use the same model, token cap,
full source passages and scope instructions; only output representation changes.
Order reverses on repeat two. No retries or post-hoc repairs.

Primary measure: structurally valid response with all text tied to its own source
quote. Separate inspection: required quantities/conditions retained, no unasked
topics, correct interpretation and passage. No release score from structural counts.
Record every question, both drafts, generated support, errors, usage and latency.

The 7 follow-up sequences / 21 turns are still a separate full-chat gate. They
must run through real routing, authorization, history and validation, not be
misrepresented by passing this standalone captured-evidence writer test.
