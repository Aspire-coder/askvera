# Retrieval Hardening Rollout

## Purpose

This profile improves evidence precision without changing the indexed documents,
chunks, embeddings, country boundaries, or the default production path. It was
introduced after legal QA showed that relevant sections could exist in the
candidate set while a nearby but non-governing section was selected instead.

## Feature flag

`OPENSEARCH_RETRIEVAL_HARDENING_ENABLED` defaults to `false`.

When disabled, AskVera keeps the existing retrieval queries, scoring, evidence
selector prompt, and cache namespace. Deploying the code alone therefore does
not enable the new behavior.

When enabled, the profile:

1. Adds bounded, country-neutral query expansion for rank requirements and
   product-purchase channels.
2. Prefers clauses that directly state how the requested rank is achieved.
3. Prefers sections that explicitly identify a permitted purchase channel.
4. De-emphasizes detached numeric fragments when the question does not ask for
   a number or amount.
5. Requires the evidence selector to distinguish direct evidence from topic-only
   overlap and permits a safe no-evidence result.
6. Rotates exact and semantic cache namespaces automatically, preventing answers
   generated under one profile from being reused by the other.

The rules are intent-based and apply across configured countries. They do not
contain country-specific answers or question-specific answer text.

## Failure behavior

- A malformed selector response preserves the existing ranked candidates.
- A Bedrock selector failure preserves the existing ranked candidates.
- A valid `relevant_evidence=false` decision returns no evidence only while the
  hardening profile is enabled.
- Disabling the flag restores the baseline behavior and cache namespace.

## Verification completed locally

- Full unit suite: 648 passed.
- Lint, source compilation, and whitespace validation passed.
- Read-only checks against the live index confirmed:
  - Manager qualifications lead with the governing Manager clause.
  - United States purchase-channel questions lead with section 17.10.
  - Product returns continue to lead with section 21.03.
  - Unsupported current product-price questions return no evidence instead of
    unrelated policy sections.
- Existing deployment retrieval canary: 7 of 7 passed against the live index.
- Retrieval-hardening legal QA canary: 4 of 4 passed against the live index,
  including the evidence-approval gate and the safe no-evidence case.

The hardening-specific canary is stored at
`tests/fixtures/retrieval_hardening_canary.json` and can be run with:

```powershell
$env:OPENSEARCH_RETRIEVAL_HARDENING_ENABLED = "true"
python scripts/run_retrieval_canary.py --load-ssm `
  --fixture tests/fixtures/retrieval_hardening_canary.json
```

## Promotion gates

Do not enable the flag in production until all of the following are recorded:

1. Locked retrieval benchmark passes with no Recall@5 or Recall@10 regression.
2. Legal QA cases for manager qualifications, purchase channels, returns, and
   unsupported price/history questions pass at the answer level.
3. Country and language isolation tests pass.
4. P95 latency remains within the approved operational limit.
5. A rollback owner confirms that setting the flag to `false` is available.

## Rollback

Set `OPENSEARCH_RETRIEVAL_HARDENING_ENABLED=false` and restart the API service.
The baseline cache namespace becomes active again automatically. No reindexing,
document migration, or cache deletion is required.
