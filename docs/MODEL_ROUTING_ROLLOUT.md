# AskVera generation model routing

## Purpose

AskVera can evaluate whether a grounded answer is structurally low risk enough
for Claude Haiku 4.5 or should remain on Claude Sonnet 5. Retrieval, country
scope, approved evidence, prompts, validation, citations, guardrails, and cache
semantics remain unchanged.

## Modes

| Mode | Production answer model | Routing telemetry | Answer-cache impact |
|---|---|---|---|
| `off` | Existing `BEDROCK_MODEL_ARN` | Disabled | None |
| `shadow` | Existing `BEDROCK_MODEL_ARN` | Records the proposed route | None |
| `live` | Haiku or Sonnet according to the policy | Records proposed and actual model | Cache version rotates |

Production must begin with `MODEL_ROUTING_MODE=shadow`. Do not use `live` until
Haiku passes the same reviewed answer benchmark and evidence-contract checks as
the current production model.

## Routing policy

Haiku is proposed only when all of these conditions are satisfied:

- no conversation history is required to interpret the question;
- retrieval confidence meets the configured minimum;
- the question is within the configured length limit;
- the question is not multi-part;
- the question does not request an explicit number, percentage, or currency;
- evidence comes from no more than the configured number of documents;
- evidence does not cross market boundaries;
- evidence is not marked as a table, calculation, or conflicting version.

Every other request routes to Sonnet. The checks use structure and Unicode
character properties rather than country names or English business terms, so
the policy applies consistently across supported countries and languages.

## Runtime configuration

```text
MODEL_ROUTING_MODE=shadow
BEDROCK_FAST_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0
BEDROCK_COMPLEX_MODEL_ID=us.anthropic.claude-sonnet-5
MODEL_ROUTING_FAST_MIN_CONFIDENCE=0.75
MODEL_ROUTING_FAST_MAX_DISTINCT_SOURCES=1
MODEL_ROUTING_FAST_MAX_QUESTION_CHARS=220
```

Startup validation rejects unknown modes, missing or identical model IDs,
invalid thresholds, and live routing without evidence-gated output.

## Failure handling

- In shadow mode, model selection cannot change the answer because the existing
  production model is always invoked.
- In live mode, a transient Haiku service failure retries the unchanged prompt
  and approved evidence with Sonnet.
- Permission and configuration errors are surfaced instead of being hidden.
- Retrieval failures and low-confidence blocks still occur before generation.

## Promotion gates

Before changing from `shadow` to `live`:

1. Review the proportion and categories proposed for Haiku.
2. Replay a representative, human-reviewed benchmark through both models.
3. Require no country, language, follow-up, numeric, citation, or grounding
   regression.
4. Compare answer quality, abstention rate, latency, token use, and estimated
   cost at the case level.
5. Keep rollback to `MODEL_ROUTING_MODE=shadow` documented and tested.

The shadow release is an observation phase, not a quality claim or permission
to enable live routing.
