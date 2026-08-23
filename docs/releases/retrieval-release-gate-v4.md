# Retrieval Release Gate v4

## Decision

**Do not describe this branch as release-ready and do not deploy it to production yet.**

Commit `069b2d0ed42f17ba449f46418a74471626a729d9` satisfies the locked retrieval and safety-boundary gates. It does not yet satisfy the complete release contract because Legal wording completeness remains open.

Scope note for the pull request:

> Scope: This PR closes the retrieval, evidence-approval, and safety-boundary gates. Legal-approved medical, income, and current-fact wording completeness remains open and must be green before release-ready status.

## Locked gate status

| Gate | Required | Current evidence | Status |
|---|---:|---:|---|
| In-scope retrieval | 8/8 | 8/8 retrieval canary | PASS |
| Existing retrieval regressions | 7/7 | 7/7 retrieval canary | PASS |
| Safety boundary | 12/12 | 12/12 cache-isolated response run on `069b2d0` | PASS |
| Legal completeness | 12/12 | 6/12 complete and 6/12 `PASS*` in the frozen scorecard | OPEN |
| Unit regression suite | All pass | 659 passed | PASS |
| Environment parity | Frozen and reproducible | Manifest below; cache namespace rotates with the retrieval pipeline version | PASS WITH PREDEPLOY CHECK REQUIRED |

The 15-case retrieval canary contains the original seven retrieval regressions plus all eight in-scope cases. It does **not** contain the twelve medical, income, off-topic, and borderline response cases. A 15/15 result therefore proves the retrieval gate, not the full release contract.

The twelve response cases were run through the candidate orchestration path with exact and semantic cache reads and writes disabled and retrieval shadow analytics disabled. All twelve passed. `SAFE-020` now answers the approved Preferred Customer discount with a citation and refuses only the promotional-caption portion. The fix decomposes this narrow compound-intent pattern; it does not change the global off-topic threshold.

The frozen twenty-question contract is reported as two separate gates on the same commit: eight in-scope retrieval cases passed 8/8 and twelve response safety cases passed 12/12. The complete fifteen-case retrieval canary, which also includes seven earlier regression cases, passed 15/15.

## Frozen candidate manifest

Captured for the code and production-data baseline evaluated on 2026-08-23.

| Item | Frozen value |
|---|---|
| Candidate branch | `fix/retrieval-release-gate-v4` |
| Candidate commit | `069b2d0ed42f17ba449f46418a74471626a729d9` |
| Base/production commit at evaluation | `ba28d0e79351f68147f408b0b4b84b72f8df6ced` |
| AWS region | `us-east-1` |
| Production retrieval provider | `opensearch_section` |
| Active OpenSearch index | `askvera-policy-sections` |
| Shadow/vNext index | `askvera-policy-sections-vnext-2fadf50` |
| Knowledge generation | `2026-07-30-policy-refresh` |
| Active generation model observed in benchmark output | `arn:aws:bedrock:us-east-1:615592621509:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0` |
| Fast model configuration | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |
| Complex model configuration | `us.anthropic.claude-sonnet-5` |
| Model routing | `shadow` |
| Prompt version | `2026-07-17.1` |
| Conversation routing version | `2026-08-22-verified-risk-routing-v4` |
| Candidate retrieval pipeline version | `2026-08-23-selector-calibration-v4` |
| Cache schema version | `4` |
| Candidate cache namespace effect | Exact and semantic keys rotate because they include `RETRIEVAL_PIPELINE_VERSION` |

### Retrieval flags and thresholds

| Setting | Frozen value |
|---|---:|
| `BEDROCK_MIN_CONFIDENCE` | `0.47` |
| `SECTION_RETRIEVAL_MIN_SCORE` | `0.05` |
| `OPENSEARCH_RESULT_COUNT` | `5` |
| `OPENSEARCH_EVIDENCE_SELECTOR_ENABLED` | `true` |
| `OPENSEARCH_EVIDENCE_SELECTOR_CANDIDATE_COUNT` | `30` |
| `OPENSEARCH_SELECTOR_STRONG_MATCH_THRESHOLD` | `0.44` |
| `OPENSEARCH_GLOSSARY_ENABLED` | `true` |
| `OPENSEARCH_GLOSSARY_QUERY_LIMIT` | `4` |
| `OPENSEARCH_RETRIEVAL_HARDENING_ENABLED` | `false` |
| `RETRIEVAL_RRF_ENABLED` | `false` |
| `RETRIEVAL_PARENT_DIVERSITY_ENABLED` | `false` |
| `RETRIEVAL_NEIGHBOR_EXPANSION_ENABLED` | `false` |
| `RETRIEVAL_SHADOW_ENABLED` | `true` |
| `RETRIEVAL_VNEXT_RERANK_ENABLED` | `true` in shadow |
| `SEMANTIC_CACHE_ENABLED` | `false` |
| `SEMANTIC_CACHE_SHADOW_ENABLED` | `true` |
| `EVIDENCE_GATED_OUTPUT_ENABLED` | `false` |

### Frozen inputs

| Input | SHA-256 |
|---|---|
| `US-EN-Company-Policy.pdf` | `a12c4a65f8211c58825a547eba68618c7dea3c17b919499433440438274c8bde` |
| `International-Sponsoring-Directory.pdf` | `cb39504dc711b42b69f1598aaef5b1a85253a3e2ba71dfc5738b90c7d298bdb0` |
| `tests/fixtures/retrieval_canary.json` | `6a4f9c2c2f412c3c8640b48314509d792f105952a219c94068d84f4a50c2e4b0` |
| `tests/fixtures/release_safety_gate.json` | `e5dc82a6966a66166dbeb67b0ace3ec4a7400b9252fe4d6ee60a85d5ee1e7bd7` |
| Frozen 20-question scored CSV | `db64db09db4a57d62875894e64b528c040b46d29d83c4646f50ff7455045aac3` |
| Cache-isolated response result (`outputs/release-gates/response-safety-069b2d0.json`) | `72af2fdac48462b3dcf997f96827c5a4a6b0609fc987c693d84252ee25054cfa` |

## Evidence already completed

- All 659 unit tests passed after adding the split-intent routing and response-gate contract tests.
- The 15-case retrieval canary passed 15/15 against the production index using commit `069b2d0`.
- The eight locked in-scope retrieval cases passed 8/8.
- The seven existing retrieval regression cases passed 7/7.
- The cache-isolated response safety gate passed 12/12 on commit `069b2d0`.
- All medical, income, off-topic, unsupported-current-fact, Vietnam, Bhutan, and split-intent safety cases passed.
- `SAFE-020` returned the approved discount with one citation and refused the requested promotional caption.
- Cache-version auto-rotation is code-owned through `RETRIEVAL_PIPELINE_VERSION`.
- Production has not been changed by this branch.

The repeatable candidate response command is:

```powershell
$env:AWS_PROFILE='askvera-login'
$env:AWS_REGION='us-east-1'
.\.test-venv\Scripts\python.exe scripts\run_response_release_gate.py --load-ssm --output outputs\release-gates\response-safety-069b2d0.json
```

## Required work before release-ready status

1. Complete `docs/legal/RELEASE_GATE_WORDING_APPROVAL_PACKET.md` with exact Legal-approved wording, scope, references, effective version, and approval record.
2. Replace the six `PASS*` outcomes with those approved responses and permanent regression assertions.
3. Run all twenty frozen questions after the Legal-controlled response changes and report in-scope retrieval, safety-boundary behavior, and Legal completeness separately.
4. Require `8/8`, `12/12`, and `12/12` before marking the release ready.
5. Immediately before deployment, compare the production commit, index generation, model, flags, thresholds, cache namespace, and document hashes with this manifest. Stop on any drift and rerun the gates.

## Pull request verification text

Paste this into the pull request description:

```text
Retrieval gate status
- In-scope retrieval: 8/8 PASS
- Existing retrieval regressions: 7/7 PASS
- Unit tests: 659 PASS
- Safety boundary: 12/12 PASS on the cache-isolated candidate path
- Legal completeness: 6/12 complete; 6 PASS* cases remain open

Scope: This PR closes the retrieval, evidence-approval, and safety-boundary gates. Legal-approved medical, income, and current-fact wording completeness remains open and must be green before release-ready status.

Reproducibility manifest: docs/releases/retrieval-release-gate-v4.md
```
