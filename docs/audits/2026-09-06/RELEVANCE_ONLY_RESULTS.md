# Source-blind relevance experiment - 2026-09-06

## Decision: reject this candidate for runtime use

28 bounded Bedrock calls completed. **20/28 matched the relevance-only labels**.
The check still misses the target unasked-bonus defect and rejects necessary
timing context. No production changes, deployment, confidence tuning, source
changes, cache changes, or answer-path integration were made.

This is not a retrieval success rate, a full-answer score, or a comparison against
the deployed bot. Labels were set before the run. No prompt retuning or repeated
calls to replace unfavorable outcomes were performed.

## What was isolated

The model receives only question, displayed answer, and language. It cannot see
source passages, quotes, binding IDs, claim segmentation, expected labels, or a
previous review. Structured JSON is checked locally, including exact copied spans
and verdict/span consistency. No repair/retry path is provided.

The result is named `relevance_passed`, not approval. Incorrect quantities,
incomplete answers, and invalid source bindings can be on-topic. The medical
control is also on-topic but unsafe: its relevance label is expressly NOT an
endorsement of the claim or permission to deliver it. Existing safety and
grounding checks must never be overridden by relevance.

The Bedrock and Python SDK guidance informed the single reused client, explicit
768-token ceiling, bounded timeouts, one attempt, and structured Converse output.

## Results

| Controls | Matched | Finding |
|---|---:|---|
| Unasked bonus, bundled/separated labels | 0/4 | Bonus eligibility incorrectly treated as necessary context |
| Explicitly requested bonus, bundled/separated labels | 4/4 | Both requested parts retained |
| Necessary current-month timing | 0/2 | Style/jargon concerns confused with relevance; one output flags `during that Month` for removal |
| Direct medical question | 0/2 | Both outputs contradict their own span contract: negative verdict with no unnecessary span; locally rejected as errors |
| Wrong-passage control | 2/2 | On-topic only; binding is deliberately not evaluated here |
| Four DE controls, including wrong number and missing condition | 8/8 | Relevance matches; these labels do not assert correctness |
| Unasked medical addition | 2/2 | Extraneous material identified |
| Unasked weather addition | 2/2 | Extraneous material identified |
| Friendly acknowledgement | 2/2 | Kept on-topic answer |
| **Total** | **20/28** | **Not suitable for promotion** |

All 28 calls returned parseable JSON with `end_turn`. Two failed semantic schema
consistency checks, leaving six additional wrong relevance decisions. No transport
failures occurred.

14 case labels contain only **12 distinct question/answer/language inputs**:
bundled and separated claims collapse to identical input by design. Each has two
scheduled repeats, so each duplicated input was actually invoked four times.
They are not independent semantic cases or evidence of deterministic model behavior.
All paired verdicts agreed in this run. These exploratory English/German controls
do not establish generalization to other questions, markets, or languages.

## Interpretation and next work

Removing source passages and claim segmentation did not solve the primary defect.
Source salience alone cannot explain the earlier failures. This reviewer still
equates related consequences with necessary answer content, and sometimes turns
a style preference into a relevance rejection. Another runtime reviewer would
add latency without reliably protecting the answers.

Next, inspect the writer's actual evidence input and test a constrained answer
plan before generation: requested rule, necessary qualifications, and exact
supporting passage IDs. Keep bonus eligibility separate from monthly activity
unless requested. This is a proposed experiment, not a proven fix or a global
keyword demotion rule. Test both requested and unasked details, completeness,
source binding, country/global authorization, and safety together before any
promotion. Do not strip qualifiers from already-generated answers based on this
failed reviewer's suggested spans.

## Verification and artifacts

- 15 new local unit tests; **1,187 full unit tests passed**, two existing
  Starlette/httpx and anyio deprecation warnings.
- Targeted lint passed.
- Graph refresh attempted; `graphify` is not installed. No graph was available.
- Previous experiments and unrelated local changes preserved.
- `relevance-only-controls-01/manifest.json`: frozen labels, model, prompt,
  schema, code and capture hashes.
- `relevance-only-controls-01/1-*.json` and `2-*.json`: full question, answer,
  raw reviewer response, parsed verdict, errors, timing and token usage.
- Implementation: `scripts/relevance_review.py`, `scripts/run_relevance_controls.py`.
- Local tests: `tests/unit/test_relevance_review.py` (no AWS/artifact dependency).
