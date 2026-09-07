# Captured-evidence component test

## Outcome

178 focused local regression tests passed (one pytest cache-directory permission
warning). Three completed, saved live Bedrock answers contained the requested
phone; the current numeric validator found zero unsupported numeric claims in each.
This is not a full answer-quality pass, retrieval benchmark, or promotion result.

| Case | Earlier production answer | Live candidate generation | Elapsed seconds |
| --- | --- | --- | --- |
| Belgium English | Email/website only; no requested phone | +31 88 646 0200, explicitly labeled Netherlands reception | 4.58 |
| Belgium French | Email/website only; no requested phone | +31 88 646 0200, labeled reception in French | 5.39 |
| US typo question | Generic contact advice; no phone | 1-888-440-ALOE (2563) | 3.98 |

Full exact questions, old answers, source excerpts, candidate raw answers and token
usage are in [captured-phone-component-results.json](captured-phone-component-results.json).
The test runner is scripts/run_captured_phone_component_probe.py.

## Method and limits

- Used local PromptBuilder with version 2026-09-05-context-boundaries-v2.
- Invoked us.anthropic.claude-sonnet-4-5-20250929-v1:0 through AWS CLI Converse,
  configured guardrail idy33rbs9v1i version 1, maxTokens 512, no prompt cache points.
- Only the previously transcribed source excerpts were supplied. No active index,
  database, document-publication lookup, application startup or shared cache access.
- No source URI/version was invented. Fixture confidence 0.9 is not measured recall
  or confidence; the generation request did not run the retriever/evidence selector.
- Language selection remained English; French was requested explicitly in the
  question, matching the earlier UI setup. Conversation history was empty here,
  unlike the earlier sequential production conversation.
- Ran generation and unsupported_numeric_claims, not the entire orchestrator,
  PII pipeline, output contract or production citation rendering. Unit tests cover
  additional paths with mocks, and must not be confused with these live calls.
- Three usable responses were captured. An additional French invocation completed
  far enough to produce non-ASCII output, but the initial Windows reader failed
  before saving it. The runner's output encoding was corrected and the French case
  repeated. Its lost response/usage are not included in the saved three results.
- Recorded times cover CLI invocation plus response parsing/checking, not chatbot
  end-to-end latency. Original production timing/model/cache provenance is unknown.

## Remaining findings

- Both Belgium replies added the unrequested order number and unnecessary closing
  text. French also described the reception as centralized, an inference not stated
  explicitly in the short excerpt. Numeric acceptance does not validate this wording.
- US reply extends the excerpt's clarification language to products; semantic scope
  should be checked rather than assuming that zero numeric errors means correctness.
- Medical-policy routing and mixed-intent fixes passed the focused mocked regression
  suite, but no new live factual answer is claimed for them. No relevant medical-policy
  passage was captured in the baseline. The FBO baseline captured the bot's answer
  and source title, not a verbatim definition passage to reuse as verified evidence.
- No percentage improvement, multilingual generalization or release readiness is
  established. Matched retrieval and complete response-pipeline evaluation remain open.

No production settings, deployment, source documents or shared cache were changed.
Model calls may incur ordinary inference charges and existing AWS invocation logging.
