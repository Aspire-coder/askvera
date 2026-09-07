# Full-chat segments and follow-up protocol

Date: 2026-09-06. Experimental local code only; production unchanged.

## Comparison

Seven existing behavioral sequences, three ordered turns each, one repeat per arm:
42 chat turns maximum. Both arms use the same local structural selector, evidence
review and scoped writer. Only fixed uses the segment response contract. The arm
named current is an experimental control, NOT deployed Current. Neither has been
approved for promotion. These are reused behavioral cases, not verified held-out
factual gold answers.

Use the existing verified registry/index snapshots and fail on returned evidence
outside their hashes. Retain full source identity and quotes. Do not change indexes,
cloud settings, caches, databases, real consent, or deployments. Each worker allows
at most 300 AWS calls and the existing token bounds; stop on isolation violation.
Synthetic prompts may appear in existing AWS model invocation logs.

## Sessions

Session identity is unique per arm, repeat and sequence, and stable across turns
including language/market changes. Use the application's real in-memory history
functions, not supplied gold context. Capture history before/after each actual
handle_chat call. Never inject expected answers. Save expectations only for later
grading. On execution error save the error and skip remaining turns in that sequence;
do not fabricate a response or conversation history. Refusals remain actual turns.

## Writer and gates

Generate factual text once with exact source quotes, then translate it to the
existing output contract without rewriting. Keep the model's coverage verdict;
never manufacture completeness. Invalid bindings become insufficient evidence.
Provider confidence admission, token/model settings, AWS guardrails, downstream
contract and final validators remain in place. Full source eligibility is checked
against captured active generation IDs before the candidate writer.

Separately inspect retrieval/abstention, semantic correctness, completeness, scope,
exact claim/source support, actual final answer versus assembled segments, follow-up
memory, multilingual/market changes, and safety. Structural success alone is not
semantic approval. Record unanswered cases and errors, not only successful answers.

Local preflight: 1,233 tests passed; targeted lint and whitespace checks passed.
New adapter is not imported by production. Full cloud results still pending.

## Pre-restart amendment

`segments-followups-01` stopped at the old 120-call worker ceiling before the fixed
arm ran. Preserve it as incomplete. Before `segments-followups-02`, raise the
conversation-only ceiling to 300 per arm (600 maximum across both), reflecting
the observed multiple retrieval/model calls per chat turn. Do not combine the
partial run with the new run as matched results. Distinct turn correlation IDs
now prevent trace stages from earlier turns persisting into later traces; session
IDs remain stable. Unstructured non-policy responses stay on the existing writer
path and are explicitly recorded as not applicable to the segment experiment.
The current validator's rejection of English with country DE is not bypassed;
record it as an execution failure and skip dependent turns in that sequence.

## Output-contract preflight correction

`segments-followups-02` was stopped after the first candidate turns showed the
local default EVIDENCE_GATED_OUTPUT_ENABLED=false. The segment hook was not being
exercised. This is a harness configuration failure, not a writer result. Preserve
the partial artifacts; do not include them in the final matched comparison.
For `segments-followups-03`, enable EVIDENCE_GATED_OUTPUT_ENABLED in BOTH isolated
arms and record it in isolation_overrides. No deployed setting is changed. The
experimental control is therefore explicitly output-gated, not production Current.
