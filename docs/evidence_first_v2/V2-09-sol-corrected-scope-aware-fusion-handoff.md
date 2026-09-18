# V2-09 Sol-corrected scope-aware fusion - local handoff

Date: 2026-09-18

## Decision

**Experimental only. Do not deploy or wire this into production.**

**Superseded for replay authority by V2-10.** This historical report used the
captured request country as a temporary authorized-policy-market fallback. The
V2-10 provenance contract removes that fallback: a replay must now consume an
explicit runtime-captured policy market or fail closed for country-policy rows.

This corrects Sol's review findings in the isolated V2 worktree. It has no
AWS, OpenSearch, Bedrock, model, route, configuration, frozen-pack, or
production-retrieval changes.

## Corrections made

1. `scope_aware_fusion.fuse` now accepts both `scope_intent` and
   `authorized_policy_market`.
   - A global record is protected only when trusted runtime provenance declares
     `directory` or `international_sponsoring` intent.
   - Missing, untrusted, policy, and ambiguous intent never protect a global
     row.
   - At most one matching global row is protected.
   - Every country-policy row must match the authorized policy market.
2. Public IDs now carry strict available identity: source file, document
   version, content hash, section, country, and access scope. Conflicting
   identities for one public ID fail closed.
   - The replay's merged-row index and captured-hit mapping now reject
     ambiguity instead of silently accepting the last value.
3. Current order is filtered for eligibility and stably deduplicated before it
   contributes a continuity signal or a trusted-follow-up fallback.
4. The replay now records both pre-selector and post-selector required ranks,
   plus selector limit, evicted IDs, and quota-added IDs.

## Verification

Using the repository's available absolute Python runtime, a task-owned
temporary test directory, and no pytest cache:

| Check | Result |
| --- | --- |
| Full V2 plus offline-replay tests | **161 passed** |
| Targeted flake8 | clean |
| `git diff --check` | clean |

Adversarial controls cover policy wording that names another country,
missing/ambiguous scope intent, conflicting versions/sections/hashes, duplicate
current order, cross-market policy rejection, and pre/post selector eviction.

## Corrected saved-capture metrics

The saved real capture provides request-country codes, so replay uses each
case's captured `country` as the authorized policy market. It provides **no
trusted runtime scope-intent field** on any case. Therefore global protection is
correctly applied to zero of 24 cases; this is a fail-closed result, not a
claim that Hong Kong or Ghana are policy requests.

| Strategy | Recall at 5 | Recall at 10 | Recall at 30 | Required sections present |
| --- | ---: | ---: | ---: | ---: |
| Current production merge | 11/19 (57.9%) | 13/19 (68.4%) | 17/19 (89.5%) | 17/19 |
| Plain RRF | 14/19 (73.7%) | 14/19 (73.7%) | 18/19 (94.7%) | 18/19 |
| Corrected scope-aware V2 | 14/19 (73.7%) | 16/19 (84.2%) | 18/19 (94.7%) | 18/19 |

The required global rows are no longer falsely pinned by target-country text:

| Required row | Current | Plain RRF | Corrected V2 |
| --- | ---: | ---: | ---: |
| Hong Kong delivery | 1 | 20 | 10 |
| Ghana cross-market sponsoring | 1 | 30 | 13 |
| Finland follow-up | 7 | 17 | 6 |

Selector observability found quota replacements in 5 captured cases: 28
pre-selector IDs were evicted and 28 global IDs were added. The evidence JSON
names every affected ID and preserves both ranks.

Tanzania remains absent under all strategies. Its required source row is not in
the captured candidate union, so a fusion change cannot recover it.

## Evidence and changed paths

- `app/experimental/evidence_first_v2/scope_aware_fusion.py`
- `scripts/offline_retrieval_replay.py`
- `tests/evidence_first_v2/test_scope_aware_fusion.py`
- `docs/evidence_first_v2/V2-09-sol-corrected-scope-aware-replay-20260918.json`
  - SHA-256: `991f89b88bb0685d4fc70cfe11f074f9731cb157f86bff192b1a4cf42aaa4ccf`
- `docs/evidence_first_v2/V2-09-sol-corrected-scope-aware-fusion-handoff.md`

## Remaining gate

Before any promotion, capture a new development run that records a trusted
runtime-produced scope decision and authorized policy market per request. Then
repeat this replay and independently verify that only directory-compatible,
international-sponsoring requests receive global protection. The existing 24
cases remain development/regression evidence, not fresh held-out release proof.
