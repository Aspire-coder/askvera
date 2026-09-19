# V2-11 isolation allowlist milestone

**Status:** approved (governance approval-queue item 10, option a; 2026-09-18). No production wiring; this is a test-fixture and audit-ledger change only.

## Reason

`tests/evidence_first_v2/test_offline_isolation.py::test_package_imports_use_a_narrow_allowlist` was pinned at its V2-02 accepted hash and its `ALLOWED_RELATIVE_IMPORTS` allowlist predates V2-09/V2-10. Since V2-10 (`app/experimental/evidence_first_v2/capture_provenance.py`), `scope_aware_fusion.py` legitimately imports `capture_provenance` with `from .capture_provenance import validate_capture_provenance` (a single, static, level-1 `ImportFrom`). That import has been a known, visible, un-hidden failure tracked as PROGRAMME_LEDGER N7 and documented in `tests/evidence_first_v2/test_offline_isolation_current_graph.py`, which already carries the corrected allowlist for the current package graph and recommends this exact addition (R08).

## Allowlist delta

`ALLOWED_RELATIVE_IMPORTS` in `tests/evidence_first_v2/test_offline_isolation.py` gains exactly one entry:

- added: `capture_provenance` (justified above; the only static relative import outside the prior allowlist found by an AST walk of every `*.py` file in `app/experimental/evidence_first_v2/`).

No other entry is added, removed, or renamed. `ALLOWED_ABSOLUTE_IMPORTS` is unchanged. No assertion in `test_offline_isolation.py` is removed or weakened; the allowlist is only widened by the one proven-legitimate name.

Six modules (`comparison.py`, `comparison_exposure.py`, `comparison_fixture.py`, `orchestration.py`, `ranking.py`, `ranking_fixture.py`) additionally resolve siblings dynamically via `__import__(__package__ + ".x")`, which an `ast.ImportFrom`-only walk does not observe and which `test_package_imports_use_a_narrow_allowlist` therefore does not check. Those dynamic imports are out of this milestone's scope; they are separately enumerated and checked against an explicit allowlist by `tests/evidence_first_v2/test_offline_isolation_current_graph.py::test_every_dynamic_import_resolves_to_an_allowed_sibling`, which is not part of the audit-pinned ledger and is left untouched here.

## Supersession

This milestone supersedes the V2-02 accepted bytes of `tests/evidence_first_v2/test_offline_isolation.py` with the new bytes containing the widened allowlist:

- from: V2-02, `tests/evidence_first_v2/test_offline_isolation.py`, `0cbcac336a5c847d588e8d6b14870866ad2d509d9fee7ed99fda099a00bed25b`
- to: V2-11, `tests/evidence_first_v2/test_offline_isolation.py`, new accepted hash recorded in `_MILESTONE_MANIFESTS[6]` in `app/experimental/evidence_first_v2/audit.py`.

This mirrors the V2-01-to-V2-02 precedent exactly: one file's accepted bytes are superseded by name, the superseded milestone's own manifest and aggregate stay byte-identical, and the earlier identity remains independently recomputable and checkable through `verify_approved`.

## Unchanged

The V2-01 through V2-06 manifests, their serialization rules, their recomputed aggregates, and the existing V2-01-to-V2-02 supersession row are unchanged. Nothing in this milestone alters production wiring, the absolute-import allowlist, the offline-isolation subprocess boundary check, or any other pinned test file.
