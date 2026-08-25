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
copy of the Current documents, logical IDs, metadata and embeddings for
ranking-only experiments. OpenSearch Serverless regenerates its private `_id`;
ranking uses the preserved logical `id` field. The source mapping is copied so
nested metadata fields are parsed exactly as they are in Current. The utility
refuses to:

- use the source as the destination;
- overwrite an existing destination; or
- report success when source and destination counts or full-content SHA-256
  digests differ.

An explicitly requested recovery mode can resume an existing destination only
when its searchable document count is zero.

The utility was run against a new isolated index. The verified experiment copy
is `askvera-policy-sections-rank-20260825-92b2020-v3`:

- source count: 17,896;
- clone count: 17,896; and
- deterministic full-source SHA-256:
  `78ae706f8ce76bd2ac247c306a63cb5b7bd9c5c416d63294ff1f7c0450dc0c83`.

The digest covers each logical ID and its complete `_source`, including text,
metadata and embeddings. OpenSearch Serverless alone regenerated private
document `_id` values.

Two failed setup indexes require an administrator with delete permission to
remove them. `askvera-policy-sections-rank-20260825-92b2020` is empty and
`askvera-policy-sections-rank-20260825-92b2020-v2` is partial. Neither is used
by an application or experiment. The experiment IAM identity received HTTP
403 for index deletion, so cleanup was not broadened into a permission change.

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

## Exact-clone ranking ablations

The first clone baseline deliberately disabled all candidate controls. It
scored 10/15 because Current already uses evidence selection. That run is kept
under `exports/retrieval-ablation/exact-clone-baseline` as evidence of the
configuration error; it is not a valid ranking-factor comparison.

The benchmark now supports a `parity` mode that mirrors Current first and then
adds exactly one requested factor. Parity reproduced Current at 15/15 with the
same case identities. The active parity state was evidence selector on, with
RRF, parent diversity, retrieval hardening and Bedrock reranking off.

| Isolated profile | Score | Exact regression | Decision |
|---|---:|---|---|
| Current-parity clone | 15/15 | None | Valid baseline |
| Parity + RRF | 14/15 | Unopened-product return window | Reject |
| Parity + parent diversity | 14/15 | Mexico sponsoring with typos | Reject |
| Parity + retrieval hardening | 12/15 | Kyrgyzstan bonus, Mexico sponsoring, return window | Reject |
| Parity + Bedrock reranker | 14/15 | Unopened-product return window | Reject |

None of the added factors improved a frozen case. Evidence selection was not
tested as an addition because it is already enabled in Current and is required
for clone parity. The exact case-level CSV and JSON artifacts are stored under
`exports/retrieval-ablation`.

## Required next experiment

1. Keep all four rejected ranking factors off.
2. Run the parity profile and any future candidate on the held-out multilingual
   and multi-turn suites, not only the frozen 15-case canary.
3. Add latency and Bedrock reranker cost measurements before any promotion.
4. Test semantic-v2 parsing and embeddings separately in another isolated
   index so parsing changes cannot be confused with ranking changes.
5. Expand the held-out corpus before retesting a revised factor.

No candidate may be promoted unless it beats or preserves all locked recall,
locale, safety, citation, latency and cost gates on both frozen and held-out
questions.

## Verification

- Focused clone and comparison tests: 13 passed
- Complete unit suite: 678 passed
- Python lint: passed
- Python source compilation: passed
- Security regression checks: passed
- Minimum configuration contract: passed with CI-safe placeholders
- Frozen canary fixture validation: 15 cases, valid
- Fixture SHA-256:
  `6a4f9c2c2f412c3c8640b48314509d792f105952a219c94068d84f4a50c2e4b0`

## Promotion decision

Current remains the only customer-serving retrieval profile. Exact-clone
parity is proven, but every newly tested ranking factor regressed at least one
locked case and improved none. RRF, parent diversity, retrieval hardening and
Bedrock reranking must remain off. Nothing from this experiment is approved
for production promotion.
