# V2-10 Sol provenance correction - local handoff

Date: 2026-09-18

## Correction

Sol's provenance findings are addressed in the isolated Evidence-First V2
candidate only.

1. A named market or shared-office match still permits the existing global
   search, but cannot by itself produce trusted `directory` intent. Only an
   actual deterministic directory route can do that. The country-named policy
   control, "What are manager qualifications in Canada?", remains globally
   searchable and records `ambiguous` plus `planner_global_scope_only`.
2. `app.experimental.evidence_first_v2.capture_provenance` is the one strict
   validator used by rank-list conversion, direct replay, and direct fusion.
   It accepts only exact intent/source pairs and exact context-record keys.
3. A resolved follow-up needs an opaque ID matching
   `history-user-[1-9][0-9]*-[0-9a-f]{16}`. Raw prior text, extra keys, missing
   IDs, and status/ID mismatches are rejected.

## Adversarial coverage

- Country-named manager-policy request retains global-search compatibility but
  is not trusted directory intent.
- Mismatched intent/source pairs and extra provenance keys are rejected.
- Raw-message turn IDs and extra context keys are rejected.
- The direct `fuse()` and `compare_capture()` callers reject malformed records,
  so validation is not limited to artifact conversion.

## Status

Experimental only. No AWS, model call, deployment, frozen-pack edit, or
production ranking wiring occurred. A fresh authorized development capture is
still required before the new V2 replay can supply ranking evidence.

## Verification

Using the absolute repository `.codex-py311-venv` Python, task-owned pytest
temporary directories, and no pytest cache:

| Check | Result |
| --- | --- |
| V2 fusion, rank-list capture, and offline replay | **81 passed** |
| Orchestrator, retrieval-plan, OpenSearch, and diagnostic-capture compatibility | **222 passed** |
| Targeted flake8 | clean (`test_retrieval_service.py` retains one pre-existing unused-import warning, excluded as `F401`) |
| `git diff --check` | clean |
