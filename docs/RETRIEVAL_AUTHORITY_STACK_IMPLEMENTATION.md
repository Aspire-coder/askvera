# Retrieval Authority Stack Implementation

## Status

Implemented on `feat/retrieval-authority-stack`. All customer-facing flags remain off by default. No production deployment or index mutation is authorized until every promotion gate passes.

## Isolated commits

1. `8136590` - deterministic entity, question-type, and section-authority classification.
2. `6cd0c98` - bounded authority-aware ranking.
3. `c2257ec` - bounded parent-child policy expansion.
4. `276a333` - signal-based confidence scoring.

Keeping the changes separate makes attribution and rollback possible.

## P1-1 classification

New ingestion metadata:

- `entity_tags`
- `question_type_tags`
- `section_authority`

Question types include definition, qualification, timing, eligibility, restriction, process, benefit, pricing, exception, contact, and general.

Authority values include governing, supporting, definition, exception, directory, and summary.

The classifier is deterministic and does not call an LLM. Existing indexed sections without tags are classified at runtime, so a reindex is not required merely to run a candidate comparison.

## P0-3 authority-aware ranking

Flag: `RETRIEVAL_AUTHORITY_RANKING_ENABLED=false`

Candidate flag: `RETRIEVAL_VNEXT_AUTHORITY_RANKING_ENABLED=false`

Behavior when enabled:

- Governing requirements receive a bounded boost for qualification, eligibility, restriction, process, pricing, timing, and exception questions.
- Definitions remain preferred for definition questions.
- Directory records remain preferred for contact questions.
- A governing label cannot rescue a candidate with no entity or question-type alignment.
- Locale, access-scope, status, and active-generation filters are unchanged.

## Parent-child retrieval

Flag: `RETRIEVAL_PARENT_CHILD_ENABLED=false`

Candidate flag: `RETRIEVAL_VNEXT_PARENT_CHILD_ENABLED=false`

The provider may add up to `RETRIEVAL_PARENT_CHILD_LIMIT=2` exact parents. A parent must match the child source file, country, language, access scope, and active generation. Global directory records are excluded. Failure to fetch a parent returns the original result unchanged.

## Signal-based confidence

Flag: `RETRIEVAL_SIGNAL_CONFIDENCE_ENABLED=false`

Candidate flag: `RETRIEVAL_VNEXT_SIGNAL_CONFIDENCE_ENABLED=false`

Confidence uses bounded evidence signals:

- retrieval score;
- entity alignment;
- question-type alignment;
- governing/definition/directory authority alignment;
- country, language, and access-scope alignment;
- selector choice and independent corroboration;
- explicit penalties for wrong-market, wrong-language, unrelated, and summary-only evidence.

The established evidence approval threshold is not lowered.

## Required isolated evaluations

Run each factor against an exact isolated clone of Current, with caches bypassed:

```powershell
python scripts/compare_retrieval_profiles.py --load-ssm --vnext-index <exact-clone-index> --vnext-factor authority --output-dir exports/retrieval-authority/authority-only
python scripts/compare_retrieval_profiles.py --load-ssm --vnext-index <exact-clone-index> --vnext-factor parent-child --output-dir exports/retrieval-authority/parent-child-only
python scripts/compare_retrieval_profiles.py --load-ssm --vnext-index <exact-clone-index> --vnext-factor signal-confidence --output-dir exports/retrieval-authority/signal-confidence-only
python scripts/compare_retrieval_profiles.py --load-ssm --vnext-index <exact-clone-index> --vnext-factor authority-stack --output-dir exports/retrieval-authority/combined
```

The combined profile enables only authority ranking, parent-child retrieval, and signal confidence. It does not enable hardening, RRF, parent diversity, evidence selection, or Bedrock reranking.

## Promotion gates

Deployment is prohibited unless all of these pass on the same commit and frozen manifest:

1. Exact-clone Current parity passes before testing any factor.
2. No held-out case regression for an isolated factor or the combined profile.
3. Recall@1 improves; Recall@5, Recall@10, and Recall@20 do not regress.
4. Safety and must-abstain fixtures pass without lowering the confidence threshold.
5. Country, language, global-directory, and access-scope isolation tests pass.
6. Response quality rejects empty labels, heading-only answers, unsupported numbers, and wrong-country facts.
7. Follow-up, typo, split-intent, and scope-discipline regressions pass.
8. Full unit, lint, compile, and security checks pass.
9. Latency and model cost stay within the locked release limits.
10. Production parity is checked after deployment against the frozen candidate artifacts.

## Current hold

Code implementation is complete locally. Live AWS comparisons, the complete test suite, and deployment remain pending. The branch must not be merged or deployed based only on compile checks or unit-level examples.
