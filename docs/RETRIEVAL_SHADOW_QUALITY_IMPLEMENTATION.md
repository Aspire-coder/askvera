# Retrieval Shadow Quality Implementation

Date: 2026-08-25

## Outcome

The retrieval and parsing improvements are implemented on the isolated
`feat/retrieval-shadow-quality` branch. They are not enabled for customer
answers and have not been promoted to production.

The deployed Current profile was rechecked against the frozen retrieval
canary and remains at 15/15. The candidate profiles did not meet the promotion
gate, so the runtime continues to serve Current.

## Production protection

- The Current provider still uses its established weighted lexical/vector
  merge and production index.
- Candidate-only controls default to disabled.
- Starting Shadow evaluation cannot change the customer-facing provider.
- Candidate parsing and embeddings require a separate index.
- The candidate semantic embedding profile is rejected if it targets the
  Current index or a Current chunk package.
- No OpenSearch index was created, replaced, or deleted by this implementation.

## Implemented changes

### Candidate diagnostics

The candidate now reports content-free diagnostics for each ranking stage:

- fusion strategy;
- fused candidate count;
- reranked candidate count;
- diversified candidate count;
- selector output count;
- above-threshold and below-threshold counts;
- selector rejection state; and
- exact candidate feature flags.

The comparison tool records exact improved and regressed case IDs instead of
relying only on aggregate totals.

### Isolated ranking factors

The vNext provider can independently evaluate:

- Reciprocal Rank Fusion between lexical and vector result lists;
- Bedrock reranking;
- parent-section diversity;
- evidence selection; and
- retrieval hardening.

Every factor defaults to off. This supports one-factor-at-a-time ablations and
prevents a bundled candidate from hiding which change caused an improvement or
regression.

### Candidate parsing and embeddings

The existing vNext parser keeps structure-aware sections, atomic definitions,
lists and numeric facts, parent IDs, table structure, versions, dates and
locale metadata.

The new `semantic-v2` embedding profile embeds only the section title and
content. Country, language, source, version and access metadata remain
available for lexical search and filtering but no longer dilute the candidate
vector. Current packages retain their existing metadata-rich embedding text.

### Exact-clone experiment support

`scripts/ingestion/clone_opensearch_index.py` creates a new, non-destructive
copy of the Current documents, IDs, metadata and embeddings for ranking-only
experiments. It refuses to:

- use the source as the destination;
- overwrite an existing destination; or
- report success when source and destination counts differ.

Creating that cloud index remains a separate, explicit operation. It has not
been run as part of this code change.

## Live read-only evaluation

### Current profile

- Index: `askvera-policy-sections`
- Deployed commit: `e71bd8e`
- Frozen canary: 15/15
- Result: unchanged and retained

### Existing bundled vNext profile

- Index: `askvera-policy-sections-vnext-2fadf50`
- Frozen canary: 7/15
- Improvements over Current: none
- Regressions: 8
- Result: do not promote

The regressed cases were:

1. Belgium minimum-order typo
2. Kyrgyzstan foreign-FBO bonus
3. Mexico sponsoring typos
4. Recognized Manager British-English typo
5. Supervisor case credits
6. Thailand minimum order
7. Unopened-return window
8. Uruguay telephone number

### RRF on the existing vNext index

- Frozen canary: 3/15
- Result: inconclusive as an RRF ablation and not promotable

This run changed ranking while also using different vNext chunks and index
content. It is therefore confounded and must not be used to conclude that RRF
alone caused the regressions.

## Required next experiment

1. Create a new exact clone of the Current index with a versioned name.
2. Point the isolated vNext provider at that clone.
3. Confirm all candidate factors are off and prove 15/15 parity.
4. Enable exactly one ranking factor.
5. Run the frozen canary and held-out suites.
6. Record exact improved, unchanged and regressed case IDs, latency and cost.
7. Reset the factor before testing the next one.
8. Test semantic-v2 parsing and embeddings separately in another isolated
   index.

No candidate may be promoted unless it beats or preserves all locked recall,
locale, safety, citation, latency and cost gates on both frozen and held-out
questions.

## Verification

- Focused retrieval, ingestion, comparison and isolation tests: 93 passed
- Complete unit suite: 670 passed
- Python lint: passed
- Security regression checks: passed
- Minimum configuration contract: passed with CI-safe placeholders
- Frozen canary fixture validation: 15 cases, valid
- Fixture SHA-256:
  `6a4f9c2c2f412c3c8640b48314509d792f105952a219c94068d84f4a50c2e4b0`

## Promotion decision

Current remains the only customer-serving retrieval profile. The candidate is
implemented for controlled evaluation but is not ready to deploy or promote.
