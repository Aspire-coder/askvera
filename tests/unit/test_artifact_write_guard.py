"""The benchmark runner must not silently replace an existing result artifact.

A frozen baseline (``baseline-results.json``) was overwritten by a second,
failed ``run_benchmark.py --artifact`` execution pointed at the same path. It
was recovered byte-exact from session evidence, but nothing in the runner
stopped it. These tests pin the guard: an existing artifact is refused before
any fixture, configuration, SSM or model work unless ``--overwrite-artifact``
is given, and a run's own checkpoints to the artifact it created keep working.

No network: the dynamically imported canary, ``run_case_once`` and SSM loading
are all replaced, and every artifact lives under ``tmp_path``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, PROJECT_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


benchmark = _load("run_benchmark")

VALID_CASE = {
    "id": "case-1",
    "question": "What is the minimum order?",
    "country": "US",
    "language": "en",
    "role": "active_distributor",
    "intent_group": "directory",
    "expected": {"kind": "answer", "must_contain": ["2 Case Credits"]},
    "source_evidence": "Policy section 4.2 states the minimum.",
    "provenance": "Dumped from the index on 2026-09-07.",
}

FROZEN_BYTES = b'{"summary": {"status": "completed"}, "cases": ["frozen baseline"]}\n'


def _fixture(tmp_path: Path, cases: list[dict]) -> Path:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"schema_version": 1, "cases": cases}), encoding="utf-8")
    return path


def _run(**overrides) -> dict:
    run = {
        "answer": "The minimum order is 2 Case Credits.",
        "citations": 1,
        "abstained": False,
        "failure_layer": "",
        "removed_numeric_claims": [],
        "removed_but_present_in_source": [],
        "top_title": "UK Policy Manual",
        "sections": ["4.2"],
        "cited_sections": ["4.2"],
        "confidence": 0.9,
        "generation_input_tokens": 100,
        "generation_output_tokens": 20,
        "duration_ms": 500.0,
    }
    run.update(overrides)
    return run


def _replace_canary_import(monkeypatch) -> None:
    """Keep benchmark.main local by replacing its dynamically imported runner."""
    class Loader:
        def exec_module(self, _module):
            return None

    class Spec:
        loader = Loader()

    monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda *_: Spec())
    monkeypatch.setattr(importlib.util, "module_from_spec", lambda _: object())


def _forbid_any_work(monkeypatch) -> list[str]:
    """Record any fixture, canary, SSM or model work; the guard must precede all of it."""
    from config import settings

    attempted: list[str] = []

    def record(name):
        def stub(*_args, **_kwargs):
            attempted.append(name)
            raise AssertionError(f"{name} was attempted before the artifact guard refused")
        return stub

    monkeypatch.setattr(benchmark, "load_fixture", record("load_fixture"))
    monkeypatch.setattr(benchmark, "run_case_once", record("run_case_once"))
    monkeypatch.setattr(importlib.util, "spec_from_file_location", record("canary_import"))
    monkeypatch.setattr(settings, "load_ssm_config", record("load_ssm_config"))
    return attempted


def _argv(monkeypatch, *args: str) -> None:
    monkeypatch.setattr("sys.argv", ["run_benchmark.py", *args])


def test_existing_artifact_is_refused_before_any_work(tmp_path, monkeypatch, capsys):
    artifact = tmp_path / "baseline-results.json"
    artifact.write_bytes(FROZEN_BYTES)
    attempted = _forbid_any_work(monkeypatch)
    _argv(monkeypatch, "--fixture", str(tmp_path / "cases.json"), "--artifact", str(artifact),
          "--repeat", "1", "--load-ssm")

    exit_code = benchmark.main()

    assert exit_code != 0
    assert artifact.read_bytes() == FROZEN_BYTES
    assert not artifact.with_suffix(".json.tmp").exists()
    assert attempted == []
    error = capsys.readouterr().err
    assert str(artifact) in error
    assert "--overwrite-artifact" in error


def test_existing_artifact_is_refused_on_a_dry_run_too(tmp_path, monkeypatch, capsys):
    """A dry run of the exact command a paid run would use reveals the refusal for free."""
    artifact = tmp_path / "baseline-results.json"
    artifact.write_bytes(FROZEN_BYTES)
    attempted = _forbid_any_work(monkeypatch)
    _argv(monkeypatch, "--fixture", str(tmp_path / "cases.json"), "--artifact", str(artifact), "--dry-run")

    assert benchmark.main() != 0
    assert artifact.read_bytes() == FROZEN_BYTES
    assert attempted == []
    assert "--overwrite-artifact" in capsys.readouterr().err


def test_overwrite_flag_allows_replacing_and_records_what_was_replaced(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, [VALID_CASE])
    artifact = tmp_path / "baseline-results.json"
    artifact.write_bytes(FROZEN_BYTES)
    _replace_canary_import(monkeypatch)
    monkeypatch.setattr(benchmark, "run_case_once", lambda *_: _run())
    _argv(monkeypatch, "--fixture", str(fixture), "--artifact", str(artifact), "--repeat", "1",
          "--overwrite-artifact")

    assert benchmark.main() == 0
    saved = json.loads(artifact.read_text(encoding="utf-8"))

    assert saved["summary"]["status"] == "completed"
    assert [case["id"] for case in saved["cases"]] == ["case-1"]
    assert saved["summary"]["artifact_write"] == {
        "version": benchmark.ARTIFACT_WRITE_VERSION,
        "mode": "overwritten",
        "overwrite_flag": True,
        "replaced_sha256": hashlib.sha256(FROZEN_BYTES).hexdigest(),
        "replaced_bytes": len(FROZEN_BYTES),
    }


def test_new_artifact_path_is_created(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, [VALID_CASE])
    artifact = tmp_path / "exports" / "nested" / "candidate-results.json"
    _replace_canary_import(monkeypatch)
    monkeypatch.setattr(benchmark, "run_case_once", lambda *_: _run())
    _argv(monkeypatch, "--fixture", str(fixture), "--artifact", str(artifact), "--repeat", "1")

    assert benchmark.main() == 0
    saved = json.loads(artifact.read_text(encoding="utf-8"))

    assert saved["summary"]["status"] == "completed"
    assert saved["summary"]["artifact_write"] == {
        "version": benchmark.ARTIFACT_WRITE_VERSION,
        "mode": "created",
        "overwrite_flag": False,
    }
    assert not artifact.with_suffix(".json.tmp").exists()


def test_the_runs_own_checkpoints_keep_updating_the_artifact_it_created(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, [VALID_CASE, {**VALID_CASE, "id": "case-2"}, {**VALID_CASE, "id": "case-3"}])
    artifact = tmp_path / "candidate-results.json"
    _replace_canary_import(monkeypatch)
    observed: list[tuple[str, int]] = []

    def run_case(*_args):
        if artifact.exists():
            summary = json.loads(artifact.read_text(encoding="utf-8"))["summary"]
            observed.append((summary["status"], summary["completed_cases"]))
        return _run()

    monkeypatch.setattr(benchmark, "run_case_once", run_case)
    _argv(monkeypatch, "--fixture", str(fixture), "--artifact", str(artifact), "--repeat", "1")

    assert benchmark.main() == 0
    saved = json.loads(artifact.read_text(encoding="utf-8"))

    # The file existed from case 2 onwards because this run wrote it, and each
    # later checkpoint replaced it rather than being refused.
    assert observed == [("in_progress", 1), ("in_progress", 2)]
    assert saved["summary"]["status"] == "completed"
    assert saved["summary"]["completed_cases"] == 3
    assert saved["summary"]["artifact_write"]["mode"] == "created"


def test_a_stopped_run_still_checkpoints_the_artifact_it_created(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, [VALID_CASE, {**VALID_CASE, "id": "case-2"}])
    artifact = tmp_path / "stopped.json"
    _replace_canary_import(monkeypatch)
    calls = iter([_run(), RuntimeError("network stopped")])

    def run_case(*_args):
        value = next(calls)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(benchmark, "run_case_once", run_case)
    _argv(monkeypatch, "--fixture", str(fixture), "--artifact", str(artifact), "--repeat", "1")

    assert benchmark.main() == 1
    saved = json.loads(artifact.read_text(encoding="utf-8"))

    assert saved["summary"]["status"] == "stopped"
    assert saved["summary"]["completed_cases"] == 1
    assert saved["summary"]["artifact_write"]["mode"] == "created"


def test_an_artifact_that_appears_after_startup_is_not_replaced(tmp_path, monkeypatch, capsys):
    """The overwrite happened from a run that had been going for ~45 minutes.

    A check only at startup cannot see a file another run writes later, so the
    first write re-checks. A run that never wrote the file does not own it.
    """
    fixture = _fixture(tmp_path, [VALID_CASE, {**VALID_CASE, "id": "case-2"}])
    artifact = tmp_path / "baseline-results.json"
    _replace_canary_import(monkeypatch)
    calls: list[int] = []

    def run_case(*_args):
        calls.append(1)
        if len(calls) == 1:
            artifact.write_bytes(FROZEN_BYTES)  # another run finishes meanwhile
        return _run()

    monkeypatch.setattr(benchmark, "run_case_once", run_case)
    _argv(monkeypatch, "--fixture", str(fixture), "--artifact", str(artifact), "--repeat", "1")

    assert benchmark.main() != 0
    assert artifact.read_bytes() == FROZEN_BYTES
    assert not artifact.with_suffix(".json.tmp").exists()
    # Refused at the first checkpoint rather than spending on further cases.
    assert len(calls) == 1
    assert "--overwrite-artifact" in capsys.readouterr().err


def test_dry_run_without_artifact_is_unaffected(tmp_path, monkeypatch, capsys):
    fixture = _fixture(tmp_path, [VALID_CASE])
    _argv(monkeypatch, "--fixture", str(fixture), "--dry-run", "--repeat", "1")

    exit_code = benchmark.main()
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert report["status"] == "valid"
    assert "artifact_write" not in report
    assert sorted(report) == sorted([
        "status", "cases", "runs", "generation_calls", "fixture_sha256",
        "transport_override_cases", "transport_overrides_sha256",
        "unsupported_request_countries", "transport_report", "note",
        "case_ids_requested",
    ])
    # Unconditional and empty: this run passed no --case-id.
    assert report["case_ids_requested"] == []
    assert list(tmp_path.iterdir()) == [fixture]


def test_dry_run_with_a_new_artifact_path_writes_nothing(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, [VALID_CASE])
    artifact = tmp_path / "not-yet.json"
    _argv(monkeypatch, "--fixture", str(fixture), "--artifact", str(artifact), "--dry-run")

    assert benchmark.main() == 0
    assert not artifact.exists()


# --- Unique temporary names, and a kept copy of what --overwrite-artifact replaces ---


def _record_replacements(monkeypatch) -> list[str]:
    """Names of the temporary files renamed over an artifact, in order."""
    names: list[str] = []
    original = Path.replace

    def replace(self, target):
        names.append(self.name)
        return original(self, target)

    monkeypatch.setattr(Path, "replace", replace)
    return names


def test_each_checkpoint_uses_its_own_temporary_file_and_leaves_a_shared_name_alone(tmp_path, monkeypatch):
    """Every run on one path used to write through the same ``<artifact>.tmp``."""
    fixture = _fixture(tmp_path, [VALID_CASE, {**VALID_CASE, "id": "case-2"}])
    artifact = tmp_path / "candidate-results.json"
    shared = tmp_path / "candidate-results.json.tmp"
    shared.write_bytes(b"another run's partial checkpoint")
    _replace_canary_import(monkeypatch)
    monkeypatch.setattr(benchmark, "run_case_once", lambda *_: _run())
    names = _record_replacements(monkeypatch)
    _argv(monkeypatch, "--fixture", str(fixture), "--artifact", str(artifact), "--repeat", "1")

    assert benchmark.main() == 0

    assert shared.read_bytes() == b"another run's partial checkpoint"
    # Two in-progress checkpoints and the completed record, each through its own file.
    assert len(names) == 3 and len(set(names)) == 3
    assert all(name.startswith("candidate-results.json.") and name.endswith(".tmp") for name in names)
    assert shared.name not in names
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted([fixture.name, artifact.name, shared.name])


def test_two_writes_to_one_path_never_share_a_temporary_name(tmp_path, monkeypatch):
    artifact = tmp_path / "results.json"
    names = _record_replacements(monkeypatch)

    benchmark._write_artifact(artifact, {"checkpoint": 1}, [])
    benchmark._write_artifact(artifact, {"checkpoint": 2}, [])

    assert len(set(names)) == 2
    assert json.loads(artifact.read_text(encoding="utf-8"))["summary"] == {"checkpoint": 2}
    assert [path.name for path in tmp_path.iterdir()] == [artifact.name]


def test_a_failed_checkpoint_removes_only_its_own_temporary_file(tmp_path, monkeypatch):
    artifact = tmp_path / "results.json"
    artifact.write_bytes(FROZEN_BYTES)
    shared = tmp_path / "results.json.tmp"
    shared.write_bytes(b"foreign")

    def locked(self, target):
        raise PermissionError("artifact is locked")

    monkeypatch.setattr(Path, "replace", locked)

    with pytest.raises(PermissionError):
        benchmark._write_artifact(artifact, {"checkpoint": 1}, [])

    assert artifact.read_bytes() == FROZEN_BYTES
    assert shared.read_bytes() == b"foreign"
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted([artifact.name, shared.name])


def _backup_path(artifact: Path, content: bytes) -> Path:
    return artifact.with_name(f"{artifact.name}.replaced-{hashlib.sha256(content).hexdigest()[:8]}")


def test_overwrite_keeps_a_verified_copy_of_the_replaced_artifact(tmp_path, monkeypatch):
    """Hashing the replaced file said what was lost; the copy keeps it."""
    fixture = _fixture(tmp_path, [VALID_CASE])
    artifact = tmp_path / "baseline-results.json"
    artifact.write_bytes(FROZEN_BYTES)
    _replace_canary_import(monkeypatch)
    monkeypatch.setattr(benchmark, "run_case_once", lambda *_: _run())
    _argv(monkeypatch, "--fixture", str(fixture), "--artifact", str(artifact), "--repeat", "1",
          "--overwrite-artifact")

    assert benchmark.main() == 0

    backup = _backup_path(artifact, FROZEN_BYTES)
    assert backup.read_bytes() == FROZEN_BYTES
    summary = json.loads(artifact.read_text(encoding="utf-8"))["summary"]
    assert summary["artifact_backup"] == {
        "version": benchmark.ARTIFACT_BACKUP_VERSION,
        "path": str(backup),
        "sha256": hashlib.sha256(FROZEN_BYTES).hexdigest(),
        "bytes": len(FROZEN_BYTES),
        "created": True,
    }
    assert summary["artifact_write"]["mode"] == "overwritten"


def test_the_copy_holds_the_bytes_actually_replaced_not_those_seen_at_startup(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, [VALID_CASE])
    artifact = tmp_path / "baseline-results.json"
    artifact.write_bytes(FROZEN_BYTES)
    later = b'{"summary": {"status": "completed"}, "cases": ["written by another run meanwhile"]}\n'

    def run_case(*_args):
        artifact.write_bytes(later)
        return _run()

    _replace_canary_import(monkeypatch)
    monkeypatch.setattr(benchmark, "run_case_once", run_case)
    _argv(monkeypatch, "--fixture", str(fixture), "--artifact", str(artifact), "--repeat", "1",
          "--overwrite-artifact")

    assert benchmark.main() == 0

    summary = json.loads(artifact.read_text(encoding="utf-8"))["summary"]
    assert _backup_path(artifact, later).read_bytes() == later
    assert not _backup_path(artifact, FROZEN_BYTES).exists()
    assert summary["artifact_write"]["replaced_sha256"] == hashlib.sha256(FROZEN_BYTES).hexdigest()
    assert summary["artifact_backup"]["sha256"] == hashlib.sha256(later).hexdigest()


def test_an_existing_identical_copy_is_reused(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, [VALID_CASE])
    artifact = tmp_path / "baseline-results.json"
    artifact.write_bytes(FROZEN_BYTES)
    backup = _backup_path(artifact, FROZEN_BYTES)
    backup.write_bytes(FROZEN_BYTES)
    _replace_canary_import(monkeypatch)
    monkeypatch.setattr(benchmark, "run_case_once", lambda *_: _run())
    _argv(monkeypatch, "--fixture", str(fixture), "--artifact", str(artifact), "--repeat", "1",
          "--overwrite-artifact")

    assert benchmark.main() == 0

    assert backup.read_bytes() == FROZEN_BYTES
    assert json.loads(artifact.read_text(encoding="utf-8"))["summary"]["artifact_backup"]["created"] is False


def test_a_copy_path_holding_other_bytes_blocks_the_overwrite(tmp_path, monkeypatch, capsys):
    """A copy that cannot be verified is not a copy; nothing is replaced."""
    fixture = _fixture(tmp_path, [VALID_CASE, {**VALID_CASE, "id": "case-2"}])
    artifact = tmp_path / "baseline-results.json"
    artifact.write_bytes(FROZEN_BYTES)
    occupied = _backup_path(artifact, FROZEN_BYTES)
    occupied.write_bytes(b"unrelated bytes")
    calls: list[int] = []

    def run_case(*_args):
        calls.append(1)
        return _run()

    _replace_canary_import(monkeypatch)
    monkeypatch.setattr(benchmark, "run_case_once", run_case)
    _argv(monkeypatch, "--fixture", str(fixture), "--artifact", str(artifact), "--repeat", "1",
          "--overwrite-artifact")

    assert benchmark.main() != 0

    assert artifact.read_bytes() == FROZEN_BYTES
    assert occupied.read_bytes() == b"unrelated bytes"
    assert len(calls) == 1
    assert "verified copy" in capsys.readouterr().err


def test_no_copy_is_made_when_nothing_is_replaced(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, [VALID_CASE, {**VALID_CASE, "id": "case-2"}])
    artifact = tmp_path / "fresh-results.json"
    _replace_canary_import(monkeypatch)
    monkeypatch.setattr(benchmark, "run_case_once", lambda *_: _run())
    _argv(monkeypatch, "--fixture", str(fixture), "--artifact", str(artifact), "--repeat", "1",
          "--overwrite-artifact")

    assert benchmark.main() == 0

    assert not list(tmp_path.glob("*.replaced-*"))
    assert "artifact_backup" not in json.loads(artifact.read_text(encoding="utf-8"))["summary"]


def test_the_runs_own_later_checkpoints_are_not_copied(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, [VALID_CASE, {**VALID_CASE, "id": "case-2"}, {**VALID_CASE, "id": "case-3"}])
    artifact = tmp_path / "baseline-results.json"
    artifact.write_bytes(FROZEN_BYTES)
    _replace_canary_import(monkeypatch)
    monkeypatch.setattr(benchmark, "run_case_once", lambda *_: _run())
    _argv(monkeypatch, "--fixture", str(fixture), "--artifact", str(artifact), "--repeat", "1",
          "--overwrite-artifact")

    assert benchmark.main() == 0

    assert [path.name for path in tmp_path.glob("*.replaced-*")] == [_backup_path(artifact, FROZEN_BYTES).name]


def test_a_dry_run_with_the_overwrite_flag_copies_nothing(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, [VALID_CASE])
    artifact = tmp_path / "baseline-results.json"
    artifact.write_bytes(FROZEN_BYTES)
    _argv(monkeypatch, "--fixture", str(fixture), "--artifact", str(artifact), "--dry-run",
          "--overwrite-artifact")

    assert benchmark.main() == 0

    assert artifact.read_bytes() == FROZEN_BYTES
    assert not list(tmp_path.glob("*.replaced-*"))
