# AskVera Retrieval vNext Shadow Rollout (retired 2026-09-01)

**This experiment was retired on 2026-09-01.** `current` (`opensearch_section`)
remains the sole retrieval path going forward. The shadow-comparison
mechanism, the vNext OpenSearch index, the `vnext` chunk-size profile, the
Operations Portal comparison controls, and the Insights shadow-comparison
dashboard have all been removed from the codebase.

Reasoning: after ~3.5 weeks live at a 5% sample rate, only 17 real
comparisons had accumulated (traffic was overwhelmingly concentrated in
US/GB), the headline top-match rate was inflated by trivial zero-result
matches, vNext confidence ran measurably lower than current's on the same
queries, and the vNext index was missing two markets entirely (Kyrgyzstan,
Netherlands-French) - a real coverage gap independent of the ranking
question. None of the promotion gates below were ever satisfied. The standing
OpenSearch Serverless index for the isolated candidate was also a confirmed,
material ongoing cost with no offsetting evidence of benefit.

This document is kept as the historical record of what was built and why. If
a similar experiment is revisited later, the design below (separate index,
sampled shadow evaluation, explicit promotion gates) is a reasonable starting
point, but it should be re-implemented rather than un-deleted, since the code
paths referenced here no longer exist.

## Purpose

This rollout compares a proposed retrieval pipeline with the established UAT
pipeline without allowing the proposed result to reach a user.

The current UAT result remains authoritative. Shadow retrieval:

- runs only when explicitly enabled;
- reads from a separate OpenSearch index;
- runs after the primary result has already been selected;
- records content-free comparison metadata;
- cannot replace, modify, or fail the primary result; and
- is limited to a configured sample of requests.

## Default State

The code defaults are safe and inert:

```text
RETRIEVAL_SHADOW_ENABLED=false
RETRIEVAL_SHADOW_SAMPLE_RATE=0.0
RETRIEVAL_VNEXT_PROVIDER=opensearch_section
RETRIEVAL_VNEXT_PIPELINE_VERSION=disabled
OPENSEARCH_VNEXT_INDEX=
RETRIEVAL_VNEXT_RERANK_ENABLED=false
EMBEDDING_SHARED_CACHE_ENABLED=false
BEDROCK_SHARED_CIRCUIT_BREAKER_ENABLED=false
ADMIN_DOCUMENT_PREFLIGHT_ENABLED=false
ADMIN_INGESTION_CHUNK_PROFILE=current
```

With these values, AskVera executes exactly one retrieval call using the current
`RETRIEVAL_PROVIDER` and `OPENSEARCH_INDEX`.

## Request Flow

```text
User question
  |
  v
Current UAT retrieval -----------------------> Current UAT answer
  |
  | primary result is fixed
  v
Sampling check
  |
  +-- disabled/not sampled --> no additional work
  |
  +-- sampled --> background vNext retrieval
                    |
                    v
             separate vNext index
                    |
                    v
             comparison log only
```

The comparison does not log the question or document content. It records:

- country and language;
- primary and vNext pipeline versions;
- primary and vNext index names;
- result counts and confidence values;
- content-free document identifiers;
- whether the top result matched;
- result-set overlap; and
- shadow duration.

## Required Isolation

Shadow mode is rejected by startup validation unless:

1. `RETRIEVAL_VNEXT_PROVIDER` is `opensearch_section`;
2. `OPENSEARCH_VNEXT_INDEX` is configured;
3. `OPENSEARCH_VNEXT_INDEX` differs from `OPENSEARCH_INDEX`; and
4. `RETRIEVAL_SHADOW_SAMPLE_RATE` is greater than `0` and no greater than `1`.

Never load experimental chunks into the current UAT index. Build and publish
them to a separate index, for example:

```text
Current UAT: askvera-policy-sections
Experimental: askvera-policy-sections-vnext
```

Do not use `--replace-source` against the UAT index while preparing vNext.

## Recommended Activation Sequence

### 1. Record the baseline

Before enabling shadow mode, record:

- deployed Git commit;
- current `RETRIEVAL_PIPELINE_VERSION`;
- current `KB_VERSION`;
- current OpenSearch index;
- document counts by country, language, status, and source;
- current retrieval evaluation report; and
- current latency and error-rate baseline.

### 2. Prepare the separate index

Load the same approved documents into the vNext index using the proposed
chunking or ranking configuration. Verify:

- active document counts;
- no staging records;
- country/language isolation;
- global-document access scope;
- source URIs and pages;
- embedding dimensions; and
- no duplicate active records.

### 3. Validate while shadowing remains disabled

Set only:

```text
OPENSEARCH_VNEXT_INDEX=askvera-policy-sections-vnext
RETRIEVAL_VNEXT_PIPELINE_VERSION=<descriptive-version>
```

Keep:

```text
RETRIEVAL_SHADOW_ENABLED=false
RETRIEVAL_SHADOW_SAMPLE_RATE=0.0
```

Restart and run configuration validation. UAT behavior remains unchanged.

### 4. Start with a small internal sample

Recommended initial settings:

```text
RETRIEVAL_SHADOW_ENABLED=true
RETRIEVAL_SHADOW_SAMPLE_RATE=0.05
```

This evaluates approximately five percent of retrieval requests. Shadow work
uses a bounded two-worker background executor, but it still adds OpenSearch and
query-planner traffic. Monitor AWS usage, API CPU, model throttling, and
OpenSearch latency.

### 5. Compare results

Search CloudWatch logs for:

```text
retrieval_shadow_comparison
retrieval_shadow_failed
retrieval_shadow_skipped_unsafe_configuration
retrieval_shadow_submit_failed
```

Shadow comparison alone does not determine correctness. Join the comparisons
with the reviewed evaluation set to calculate:

- expected-section recall at 5 and 10;
- mean reciprocal rank;
- top-result accuracy;
- answer completeness;
- citation correctness;
- country/language isolation;
- p50 and p95 retrieval latency; and
- additional Bedrock/OpenSearch cost.

## Promotion Gates

Do not promote vNext when any of the following occurs:

- an existing passing retrieval case fails;
- a country or language isolation test fails;
- citation correctness declines;
- required policy conditions or exceptions disappear;
- structured directory fields are malformed;
- p95 latency exceeds the approved budget;
- errors or throttling increase materially; or
- the proposed path cannot be disabled immediately.

Promotion is a separate release decision. Enabling shadow mode does not promote
vNext and does not change user-visible retrieval.

## Immediate Rollback

Set:

```text
RETRIEVAL_SHADOW_ENABLED=false
RETRIEVAL_SHADOW_SAMPLE_RATE=0.0
```

Then restart the API. No UAT index rollback is needed because the primary index
was never changed.

## Feature Development Rule

Parent diversity, RRF, cross-encoder reranking, OCR, table extraction, and
alternative chunk sizing must be implemented only in the vNext build/index
until their evaluation passes the promotion gates. Each behavior should have a
separate version or feature flag so its effect can be measured independently.

## Experiment 1: Smaller Structure-Aware Chunks

The first implemented experiment is an opt-in `vnext` chunk profile:

```text
Generic approved documents
  current: 4,500 characters / 450 overlap
  vnext:   2,000 characters / 200 overlap

Policy documents
  current: preserve sections up to 8,000 characters
  vnext:   split long sections at paragraph, line, or sentence boundaries
           with a 2,000-character maximum and 200-character overlap
```

Both profiles preserve headings, source pages, parent-section IDs, document
versions, effective dates, country/language metadata, and the existing atomic
definition/list/numeric-fact chunks. Every generated record carries a
`chunk_profile` value.

The normal admin ingestion path continues to call the default `current`
profile. It cannot select `vnext` from the admin UI. vNext packages are created
offline with `--chunk-profile vnext`, reviewed, and loaded only into the
separate experimental index.

Use `scripts/ingestion/compare_chunk_packages.py` to compare current and vNext
JSONL packages before embedding. Smaller chunks are not promoted based only on
size. They must improve or preserve the reviewed retrieval suite, citation
quality, answer completeness, locale isolation, and latency.

## Experiment 2: Bedrock Reranking

Reranking is implemented only on the vNext provider and is disabled by
default. The current provider never receives the reranking flag.

```text
RETRIEVAL_VNEXT_RERANK_ENABLED=true
RETRIEVAL_VNEXT_RERANK_MODEL_ARN=arn:aws:bedrock:us-east-1::foundation-model/cohere.rerank-v3-5:0
RETRIEVAL_VNEXT_RERANK_CANDIDATE_COUNT=20
RETRIEVAL_VNEXT_RERANK_RESULT_COUNT=10
```

The EC2 role needs `bedrock:Rerank` and `bedrock:InvokeModel` for the selected
reranker. If Bedrock rejects, throttles, or returns an invalid rerank response,
the provider keeps its original candidate order. A reranker failure cannot
change or fail the current UAT answer.

## Document Preflight

`preflight_document.py` classifies an unfamiliar PDF before ingestion:

- text PDFs continue through the normal extractor;
- table-like pages use layout-preserving extraction only in vNext;
- scanned or image-only PDFs are rejected with a clear OCR-required result.

This release does not automatically run Textract. OCR remains a future,
separately reviewed ingestion branch. The admin path remains on the current
extractor unless both the preflight and vNext admin flags are deliberately
enabled.

## Optional Shared Runtime State

The existing Valkey connection can hold:

- embedding results shared across API processes; and
- Bedrock circuit-breaker state shared across API processes.

Both features are disabled by default and fail open to the established
process-local behavior if Valkey is unavailable. They do not change retrieval
ranking or chat memory.

## Local Validation Results

The release package was validated before cloud deployment:

```text
Published locale packages compared: 25
Current chunks: 16,137
vNext chunks: 22,579
Maximum vNext chunk size: 1,999 characters
Country/language and unique-ID checks: PASS

Reviewed country-policy questions compared: 276
Current top family retained in vNext top 5: 92.75%
Current top family retained in vNext top 10: 96.38%
Mean top-10 family overlap: 73.71%
Mean top chunk size: 3,955 -> 1,065 characters
```

These are stability measurements, not promotion evidence. Because top-one
results changed in some cases, vNext must remain shadow-only until reviewed
online evaluation confirms equal or better correctness.

## One Coordinated Deployment

Deploy the release once, but activate it in protected stages:

1. Push one reviewed commit and deploy the API code.
2. Create and populate only the separate vNext index.
3. Validate counts, locale isolation, global scope, and health.
4. Configure the vNext index while shadow remains disabled.
5. Enable a five-percent shadow sample.
6. Enable reranking only after Bedrock model access and IAM are verified.
7. Leave admin vNext ingestion disabled until its own upload test passes.

This is one release package with independently reversible switches. It avoids
multiple code deployments without turning experimental behavior into live
answers.
