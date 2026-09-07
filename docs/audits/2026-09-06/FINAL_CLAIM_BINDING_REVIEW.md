# Final claim binding and semantic audit - September 6, 2026

## Decision: HOLD; semantic reviewer rejected for activation

The deterministic final-answer binding is implemented and locally tested. The separate semantic reviewer detects several factual failures, but does not reliably reject unasked bonus detail. It must not be used as a production approval gate yet. Production and existing runtime behavior are unchanged by this turn: all new functionality is opt-in and has no production caller.

## New local work

- `app/final_answer_binding.py` requires the complete displayed answer to equal its ordered claim text, allowing whitespace wrapping only. Extra unlisted text, changed quantities, incorrect source/quote pairings, and stale source identities are rejected. Every claim retains its individual source references. It reuses the existing versioned source-binding implementation.
- This binding is NOT semantic approval. A faithful quote can still be attached to an incorrect interpretation. The result deliberately has no approval property. Source authorization must be performed upstream.
- `scripts/final_claim_review.py` audits the final text and each claim against specifically named passages, with all selected passages available for material-condition checks. One bounded model call, no automatic rewriting/retries or deployment wiring.
- A complete JSON Markdown fence is now accepted, but incomplete fences, trailing commentary, malformed schemas and truncated responses fail. This formatting correction does not alter semantic decisions.
- `scripts/run_final_claim_controls.py` freezes captured Canadian policy passages and six labeled controls, repeated twice. Expected labels are not sent to the reviewer. Results are evaluation records, not approvals usable by the chatbot.

## Verified results

**1,132 unit tests pass**, with two existing dependency warnings. Targeted lint and diff checks pass. Graph maintenance was attempted; graphify is unavailable and the graph file is absent. Existing unrelated changes were preserved.

`final-claim-controls-01` contains **10 model calls and two deterministic source-binding rejections**. These are controls, not end-to-end chatbot requests. No additional end-to-end requests occurred this turn.

The initial strict JSON parser rejected all ten model responses because the model wrapped them in complete Markdown fences. Those parse failures must not be counted as semantic safety passes. Inspecting the same saved outputs after the bounded fence-normalization correction gives:

| Control | Repeat 1 | Repeat 2 |
| --- | --- | --- |
| Supported monthly activity requirement | Accepted correctly | Accepted correctly |
| Contradiction: no need to qualify again | Rejected correctly | Rejected correctly |
| Missing concrete monthly requirement | Rejected correctly | Rejected correctly |
| Guaranteed income | Rejected correctly | Rejected correctly |
| Unasked bonus addition | Incorrectly accepted | Incorrectly accepted |
| Unknown source identity | Rejected locally, no model call | Rejected locally, no model call |

This is **10/12 control outcomes after offline normalization**, not a new cloud run or complete safety gate. Original raw outputs are retained unchanged. The controls reuse Canadian evidence and contain deliberately adversarial drafts; they are not fresh multilingual customer questions.

## Why this does not close the task

The scope criterion explicitly asks the reviewer to reject unrelated additions. It nevertheless accepts the exact bonus passage alongside an answer about monthly activity in both repeats. Adding this reviewer now would add latency without fixing the remaining scope failure. Structural binding also cannot discover a material fact omitted from both answer and claims.

The original optional evidence contract and latest citation-display fix have not received a new full-chat test in this turn. No end-to-end, multilingual, production-parity or release-readiness claim is warranted. The new schema also intentionally has no free-text greeting exemption; conversational rendering requires separate review before integration.

## Next bounded step

Require an explicit per-claim decision separating (a) supported by its cited passage and (b) necessary for the requested question. Add paired controls where bonus information IS requested, so a fix cannot simply ban bonus language. Keep the failed whole-answer reviewer as a recorded rejected baseline. Only integrate after those controls pass, then run the latest full tree against fresh multilingual questions and the complete safety suite.

Bedrock and AWS SDK guidance informed bounded invocation, strict output handling and separation of deterministic binding from model judgment. Credential-safety guidance was followed; no secrets were exposed or credentials changed. No push, merge, deployment, live-index or shared-cache changes were made.
