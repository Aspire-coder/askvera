# V2-08 Scope-Aware Fusion - local handoff

> Superseded by `V2-09-sol-corrected-scope-aware-fusion-handoff.md`.
> V2-08 treated an explicit target-country match as enough to protect a global
> record. The corrected experiment requires trusted runtime scope intent.

Date: 2026-09-18

## Decision

**Experimental only. Do not deploy or wire into production.**

This adds an offline-only fusion candidate over the saved real retrieval
capture. It does not call AWS, OpenSearch, Bedrock, or a model, and it does
not edit the frozen pack, production retrieval code, configuration, or routes.

## What changed

- `app/experimental/evidence_first_v2/scope_aware_fusion.py`
  - New deterministic fusion module.
  - RRF over captured lists, plus a bounded current-order continuity signal
    (weight `4.0`).
  - A global record is protected only when its own
    `metadata.record_country` exactly normalizes to a captured explicit target
    country. The implementation uses no case IDs, expected section IDs,
    answers, or source-review labels.
  - A dependent-follow-up fallback exists only for capture provenance that is
    explicitly `runtime` plus `resolved_follow_up` plus a prior user-turn ID.
    It does not infer history state from wording.
- `scripts/offline_retrieval_replay.py`
  - The existing offline `rrf` command now reports three strategies: current,
    plain RRF, and scope-aware V2. It can write the comparison JSON only to a
    new path and continues to refuse a missing capture.
- `tests/evidence_first_v2/test_scope_aware_fusion.py`
  - Focused controls for global partitioning, Unicode country normalization,
    unmatched globals, continuity, provenance-gated follow-up fallback, and
    malformed-input rejection.
- `docs/evidence_first_v2/V2-08-scope-aware-replay-20260918.json`
  - Reproducible local replay of the saved real capture.
  - SHA-256: `718a8757cc05c3a27e04014c254a5b621c463ac665920920b1b8574844f4f491`.

## Saved-capture result

The capture has 19 positive required sections. Five refusal/uncertainty cases
are outside retrieval-recall denominators.

| Strategy | Recall at 5 | Recall at 10 | Recall at 30 | Required sections present |
| --- | ---: | ---: | ---: | ---: |
| Current production merge | 11/19 (57.9%) | 13/19 (68.4%) | 17/19 (89.5%) | 17/19 |
| Plain RRF | 14/19 (73.7%) | 14/19 (73.7%) | 18/19 (94.7%) | 18/19 |
| Scope-aware V2 | 16/19 (84.2%) | 17/19 (89.5%) | 18/19 (94.7%) | 18/19 |

Acceptance checks from the saved capture:

- Hong Kong explicit global record: current `1`, plain RRF `20`, scope-aware
  `1`.
- Ghana cross-market global record: current `1`, plain RRF `30`, scope-aware
  `1`.
- Finland follow-up required clause: current `7`, plain RRF `17`, scope-aware
  `6`.
- No required section that current retrieval had found moved later or became
  absent under scope-aware V2.
- The eight policy improvements remain improvements versus current. The Norway
  reapplication clause remains newly recovered inside top 30 (`24`), though it
  is weaker than plain RRF's `19` and still needs a dedicated retrieval fix.
- Tanzania remains absent from all captured candidate lists under all three
  strategies. Its capture has no target-country or ranking-query expansion;
  fusion cannot rank a record that was never retrieved.

## Verification

Using the repository's available absolute Python runtime and a task-owned
temporary base directory:

```
20 passed
```

The focused set included the new scope-aware tests, V2 offline-isolation
checks, and existing offline replay tests. Targeted `flake8` and
`git diff --check` both exited cleanly.

## Limitations and next review question

This capture has **no trusted context-resolution metadata on any of its 24
cases**, so the provenance-gated follow-up fallback was deliberately not
exercised. Finland improves through the general continuity signal, but that is
not proof that the runtime-history fallback works.

Also, the capture does not record a trusted policy-versus-directory intent
decision. An explicit directory country target is therefore sufficient to
protect a matching global row in this offline experiment, including cases where
country-policy evidence also exists. An independent reviewer must decide
whether the future capture should add a runtime-produced scope-intent field
before this candidate can be promoted.

The original 24 cases have now been used to develop and regress this candidate.
They are development/regression evidence, not fresh held-out release evidence.
A separately reviewed, untouched pack and a new read-only capture are required
before any production decision.
