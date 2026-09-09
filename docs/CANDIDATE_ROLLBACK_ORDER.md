# Candidate rollback order

Written 2026-09-08 after checking, not after reasoning. Separate commits do not
establish that a candidate can be taken back out on its own: a later one can
import an earlier one's helper, and then reverting the earlier one leaves the
later one calling a function that no longer exists. `git revert` will not tell
you, because the patch applies cleanly.

**A previous statement that "each reverts alone" was wrong and is withdrawn.**
Two of the six do not.

## What was run

Each candidate reverted for real, the whole suite and flake8 run against the
result, the tree restored. Every number here was re-measured at `76c4efe`
after two later commits landed, rather than left as a result about an older
tree. Nothing committed, nothing pushed.
Untracked working-tree files were verified unchanged afterwards.

## The six candidates

| | Candidate | Commits, newest first | Reverts alone |
|---|---|---|---|
| A | Catalogue country-name expansion | `7fb6f5c` | **yes** — 1790 passed, 15 skipped |
| B | Locale-aware number reading | `7090de0`, `8cf6f35` | **no** |
| C | Answer completeness and conditions | `0832812`, `3d08801` | **no** |
| D | No invented personal history | `c89b18e`, `d0f1a6d` | **yes** — 1786 passed, 15 skipped |
| E | Clarification scoring and coverage matrix | `83d4089` | **yes** — 1807 passed, 15 skipped |
| F | Preflight honours the case selection | `76c4efe` | **yes** — 1817 passed, 15 skipped |

## Why B and C do not

Reuse, and the reuse is worth keeping. Duplicating these helpers to make the
commits independent would leave two copies of a rule about how a figure is
read, which is a worse problem than an ordering constraint.

```
utils/number_notation.py   (B)
        ^
utils/qualifications.py    (C)   also used by utils/directory_fields.py
        ^
utils/personal_claims.py   (D)   used by the validator and the orchestrator
```

So B, C and D are a stack, not three independent candidates. A and E are
genuinely independent of everything, including of each other.

## The order that works

Verified cumulatively, the way a rollback actually happens:

| Step | Result |
|---|---|
| revert D | clean — 1786 passed, 15 skipped |
| revert D, then C | clean — 1756 passed, 15 skipped |
| revert D, then C, then B | clean — 1723 passed, 15 skipped |
| revert all six | clean — **1680 passed, 15 skipped** |

The last line is the baseline this work started from, which is the check that
the reverts are complete rather than merely applying.

A, E and F may be reverted at any point, before or after any of the above.
F touches only the comparison harness and no candidate module imports it.

## What this does not establish

- Nothing about behaviour in the live pipeline. These are local test runs.
- Reverting restores the code, not the index or any data. No candidate here
  changes either, but that is a property of these candidates and not a general
  guarantee.
- `OPENSEARCH_COUNTRY_NAME_EXPANSION_ENABLED` defaults to true in code and is
  unset in deployment configuration. Turning candidate A off is a
  configuration change and does not need a revert; that decision has not been
  made and no configuration was touched.
