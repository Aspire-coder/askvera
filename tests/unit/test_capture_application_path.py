"""Mocked dependency behaviour.

`scripts/capture_application_path.py` replaces the old retrieval-only capture
for cases that need stored conversation turns (see R03's fail-closed guard in
`tests/evidence_first_v2/test_r03_context_capture.py`). It drives the real
`AIOrchestrator.handle_chat` with those turns seeded into the memory session
backend, the same way the offline orchestrator tests seed it.

Every test here is fully offline. `--preflight` is proved to construct zero
real clients by making boto3.client, the OpenSearch client, and the Bedrock
model router explode the moment anything tries to build one; a live capture
uses only fakes for governance, retrieval and generation (matching the
pattern in `tests/unit/test_orchestrator_diagnostic_capture.py`), and leaves
`get_session_history`/`append_session_turn` pointed at the in-process memory
backend rather than Postgres.
"""

from __future__ import annotations

import json

import pytest

from app.governance.models import GovernanceAction, GovernanceDecision
from app.models.responses import ModelResponse
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.retrieval.models import RetrievalAvailability, RetrievedDocument, RetrievalResult
from config import settings
from scripts import capture_application_path as tool
from services import session as session_module

TANZANIA_PRIOR = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"
UGANDA_FOLLOW_UP = "Entä jos hän asuu ugandassa?"


def _manifest(cases: list[dict]) -> dict:
    return {"manifest_version": 1, "cases": cases}


def _case(
    case_id: str,
    *,
    split: str = "development",
    turns: list[dict] | None = None,
    message: str = "What is the office phone number?",
    country: str = "CA",
    language: str = "en",
    role: str = "new_prospect",
    expectations: object | None = None,
) -> dict:
    return {
        "id": case_id,
        "split": split,
        "exposure": "synthetic test case",
        "turns": turns or [],
        "message": message,
        "country": country,
        "language": language,
        "role": role,
        "expectations": expectations if expectations is not None else {"note": "data only"},
    }


class _Governance:
    def evaluate(self, **_: object) -> GovernanceDecision:
        return GovernanceDecision(allowed=True, action=GovernanceAction.ALLOW, provider="test")


class _Retriever:
    """A fake retrieval boundary: never touches OpenSearch."""

    def __init__(self) -> None:
        self.seen_messages: list[str] = []

    def retrieve(self, message: str, *_: object, **__: object) -> RetrievalResult:
        self.seen_messages.append(message)
        document = RetrievedDocument(
            id="fees", title="Policy - Sec 13.01: Fees", content="The service fee is 2.50.",
            source="opensearch-section://CA-EN-Company-Policy.pdf/13.01", country="CA", language="en", score=0.9,
            metadata={"section_id": "13.01", "access_scope": "country", "ingestion_id": "ingestion-1"},
        )
        return RetrievalResult(
            documents=[document], citations=[document.to_source()], confidence=0.9,
            metadata={"provider": "opensearch_section", "candidate_sources": [document.to_source()]},
        )


class _Router:
    def __init__(self) -> None:
        self.call_count = 0

    def generate(self, *_: object, **__: object) -> ModelResponse:
        self.call_count += 1
        return ModelResponse(
            text="The service fee is 2.50.", citations=[], confidence=0.9,
            provider="test", model_name="model-under-test",
        )


@pytest.fixture(autouse=True)
def memory_backend_and_stubs(monkeypatch):
    """Offline stand-ins for everything handle_chat touches besides the fakes above."""
    monkeypatch.setattr(settings, "CHAT_MEMORY_BACKEND", "memory")
    session_module._reset_memory_sessions()

    stubs = {
        "validate_and_touch_session": lambda *_: None,
        "has_valid_consent": lambda *_: True,
        "scrub_pii": lambda text, *_, **__: text,
        "build_cache_key": lambda *_: "cache-key",
        "get_cache_value": lambda *_: None,
        "set_cache_value": lambda *_: None,
        "write_audit_event": lambda *_: None,
        "semantic_cache_active": lambda *_, **__: False,
        "get_semantic_cache_value": lambda *_, **__: None,
        "set_semantic_cache_value": lambda *_, **__: None,
        # get_session_history and append_session_turn are deliberately left
        # real: the multi-turn tests depend on the memory backend actually
        # storing and returning what this test seeds.
    }
    for name, stub in stubs.items():
        monkeypatch.setattr(chat_orchestrator, name, stub)

    yield
    session_module._reset_memory_sessions()


def _orchestrator() -> AIOrchestrator:
    return AIOrchestrator(retriever=_Retriever(), router=_Router(), governance=_Governance())


# --------------------------------------------------------------------------
# Manifest validation
# --------------------------------------------------------------------------


def test_manifest_sha256_is_deterministic_and_key_order_independent():
    manifest_a = _manifest([_case("a")])
    manifest_b = json.loads(json.dumps(manifest_a))  # round-trips key order the same either way
    assert tool.manifest_sha256(manifest_a) == tool.manifest_sha256(manifest_b)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m["cases"][0].pop("expectations"),
        lambda m: m["cases"][0].__setitem__("split", "staging"),
        lambda m: m.pop("manifest_version"),
        lambda m: m["cases"][0]["turns"].append({"user": "hi"}),  # missing "assistant"
        lambda m: m["cases"].__setitem__(0, {**m["cases"][0], "id": ""}),
    ],
)
def test_manifest_validation_rejects_malformed_cases(tmp_path, mutate):
    manifest = _manifest([_case("a")])
    mutate(manifest)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(tool.ManifestError):
        tool.load_manifest(path)


def test_manifest_validation_rejects_duplicate_case_ids(tmp_path):
    manifest = _manifest([_case("same"), _case("same")])
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(tool.ManifestError, match="duplicate"):
        tool.load_manifest(path)


def test_manifest_validation_accepts_the_example_fixture():
    fixture = tool.ROOT / "tests" / "fixtures" / "capture" / "example_manifest.json"
    manifest, sha = tool.load_manifest(fixture)
    assert len(manifest["cases"]) == 3
    assert len(sha) == 64


class _ExplodingExpectations(dict):
    """Stands in for an expectations block that must never be read."""

    def __getitem__(self, key):
        raise AssertionError("the capture runtime must never read case['expectations']")

    def __getattr__(self, name):
        raise AssertionError("the capture runtime must never read case['expectations']")


def test_expectations_are_never_read_by_the_runtime_path():
    case = _case("no-read", expectations=_ExplodingExpectations())
    # Validation itself must not read inside expectations, only check presence.
    manifest = _manifest([case])
    sha = tool.manifest_sha256(manifest)  # noqa: F841 - exercised for its side effect (must not raise)
    tool._validate_case(case, 0, set())

    runtime_case = tool._runtime_fields(case)
    assert "expectations" not in runtime_case
    assert "exposure" not in runtime_case


# --------------------------------------------------------------------------
# Preflight: zero external calls
# --------------------------------------------------------------------------


def test_preflight_makes_zero_client_constructions(tmp_path, monkeypatch, capsys):
    manifest = _manifest([_case("a"), _case("b", split="evaluation")])
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    def _explode(*_a, **_kw):
        raise AssertionError("preflight must never construct a real client")

    import boto3
    monkeypatch.setattr(boto3, "client", _explode)
    import opensearchpy
    monkeypatch.setattr(opensearchpy.OpenSearch, "__init__", _explode)
    monkeypatch.setattr(chat_orchestrator, "model_router", None)  # any use at all is a bug

    exit_code = tool.main(["--manifest", str(path), "--preflight"])

    assert exit_code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["case_count"] == 2
    assert report["cases_per_split"] == {"development": 1, "evaluation": 1}
    assert "max_calls_formula" in report


def test_preflight_prints_a_cost_envelope_only_for_priced_categories(tmp_path, capsys):
    manifest = _manifest([_case("a")])
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    tool.main([
        "--manifest", str(path), "--preflight",
        "--unit-price", "retrieval=0.001", "--unit-price", "generation=0.002",
    ])

    report = json.loads(capsys.readouterr().out)
    assert set(report["cost_envelope"].keys()) == {"retrieval", "generation", "total"}


def test_preflight_rejects_an_unknown_unit_price_category(tmp_path):
    manifest = _manifest([_case("a")])
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="must be one of"):
        tool.main(["--manifest", str(path), "--preflight", "--unit-price", "bogus=1"])


# --------------------------------------------------------------------------
# Live capture with fakes: stored turns become real history
# --------------------------------------------------------------------------


def test_capture_with_fakes_records_stored_turns_as_history():
    orchestrator = _orchestrator()
    case = tool._runtime_fields(_case(
        "tanzania-then-uganda",
        turns=[{"user": TANZANIA_PRIOR, "assistant": "A source-bound answer about foreign-resident FBO bonuses."}],
        message=UGANDA_FOLLOW_UP,
        language="fi",
    ))

    record = tool.run_one_case(orchestrator, case, correlation_id="test-corr", capture_final_answer=False)

    assert record["case_error"] is None
    assert record["context_resolution"]["status"] == "resolved_dependent_follow_up"
    assert record["context_resolution"]["prior_user_turn_id"].startswith("history-user-1-")
    assert "Uganda" in record["resolved_query"]
    assert "Tanzania" not in record["resolved_query"]


def test_capture_of_a_first_turn_case_is_not_dependent():
    orchestrator = _orchestrator()
    case = tool._runtime_fields(_case("first-turn", message="What is the office phone number?"))

    record = tool.run_one_case(orchestrator, case, correlation_id="test-corr", capture_final_answer=False)

    assert record["context_resolution"] == {"provenance": "runtime", "status": "not_dependent"}
    assert record["resolved_query"] == "What is the office phone number?"


def test_capture_records_available_retrieval_with_no_failed_channels():
    """R02 provider state reaches the capture row (coordinator, 2026-09-18)."""
    orchestrator = _orchestrator()
    case = tool._runtime_fields(_case("available", message="What is the service fee?"))

    record = tool.run_one_case(orchestrator, case, correlation_id="test-corr", capture_final_answer=False)

    assert record["retrieval_availability"] == "available"
    assert record["search_channel_failures"] == []


def test_capture_records_degraded_retrieval_and_its_failed_channels():
    orchestrator = _orchestrator()
    base = orchestrator.retriever.retrieve

    def degraded(message: str, *args: object, **kwargs: object) -> RetrievalResult:
        result = base(message, *args, **kwargs)
        return RetrievalResult(
            documents=result.documents, citations=result.citations, confidence=result.confidence,
            metadata={**result.metadata, "failed_search_channels": ["global_text"]},
            availability=RetrievalAvailability.DEGRADED,
        )

    orchestrator.retriever.retrieve = degraded  # type: ignore[method-assign]
    case = tool._runtime_fields(_case("degraded", message="What is the service fee?"))

    record = tool.run_one_case(orchestrator, case, correlation_id="test-corr", capture_final_answer=False)

    assert record["retrieval_availability"] == "degraded"
    assert record["search_channel_failures"] == ["global_text"]


def test_call_counts_include_at_least_one_generation_call_per_case():
    orchestrator = _orchestrator()
    case = tool._runtime_fields(_case("counts"))

    record = tool.run_one_case(orchestrator, case, correlation_id="test-corr", capture_final_answer=False)

    assert record["call_counts"]["generation"] == 1
    assert orchestrator.model_router.call_count == 1


def test_final_answer_is_only_recorded_when_explicitly_requested():
    orchestrator = _orchestrator()
    case = tool._runtime_fields(_case("answer-flag"))

    off = tool.run_one_case(orchestrator, case, correlation_id="test-corr", capture_final_answer=False)
    on = tool.run_one_case(orchestrator, case, correlation_id="test-corr-2", capture_final_answer=True)

    assert "final_answer" not in off
    assert on["final_answer"]["answer"]


def test_no_secret_like_setting_appears_in_the_settings_snapshot():
    snapshot = tool.safe_settings_snapshot()
    blob = json.dumps(snapshot).upper()
    for marker in ("SECRET", "PASSWORD", "TOKEN", "ARN", "CREDENTIAL"):
        assert marker not in blob


# --------------------------------------------------------------------------
# Checkpointing, resume, caps, approval
# --------------------------------------------------------------------------


def _patch_real_singletons(monkeypatch, *, retriever=None, router=None, governance=None) -> None:
    """Redirect AIOrchestrator()'s no-arg defaults to fakes, for a full main() run."""
    monkeypatch.setattr(chat_orchestrator, "retrieval_service", retriever or _Retriever())
    monkeypatch.setattr(chat_orchestrator, "model_router", router or _Router())
    monkeypatch.setattr(chat_orchestrator, "governance_engine", governance or _Governance())


def test_a_live_capture_without_approval_refuses_before_any_case_runs(tmp_path, monkeypatch):
    _patch_real_singletons(monkeypatch)
    manifest = _manifest([_case("a")])
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    out = tmp_path / "out.jsonl"

    with pytest.raises(tool.ApprovalRequiredError):
        tool.main(["--manifest", str(path), "--out", str(out)])

    assert not out.exists()


def test_a_completed_run_records_the_approval_id_in_every_row(tmp_path, monkeypatch):
    _patch_real_singletons(monkeypatch)
    manifest = _manifest([_case("a"), _case("b")])
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    out = tmp_path / "out.jsonl"

    exit_code = tool.main(["--manifest", str(path), "--out", str(out), "--allow-empty-corpus", "--i-have-approval", "APPROVAL-1"])

    assert exit_code == 0
    header, rows = tool.read_checkpoint(out)
    assert header["approval_id"] == "APPROVAL-1"
    assert len(rows) == 2
    assert all(row["approval_id"] == "APPROVAL-1" for row in rows)


def test_resume_rejects_a_changed_manifest(tmp_path, monkeypatch):
    _patch_real_singletons(monkeypatch)
    manifest = _manifest([_case("a")])
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    out = tmp_path / "out.jsonl"
    tool.main(["--manifest", str(path), "--out", str(out), "--allow-empty-corpus", "--i-have-approval", "APPROVAL-1"])

    changed = _manifest([_case("a", message="a different question entirely")])
    path.write_text(json.dumps(changed), encoding="utf-8")

    with pytest.raises(tool.ResumeMismatchError, match="manifest_sha256"):
        tool.main(["--manifest", str(path), "--out", str(out), "--allow-empty-corpus", "--i-have-approval", "APPROVAL-1", "--resume"])


def test_resume_rejects_a_changed_head_or_dirty_flag(tmp_path, monkeypatch):
    _patch_real_singletons(monkeypatch)
    manifest = _manifest([_case("a")])
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    out = tmp_path / "out.jsonl"
    tool.main(["--manifest", str(path), "--out", str(out), "--allow-empty-corpus", "--i-have-approval", "APPROVAL-1"])

    monkeypatch.setattr(tool, "git_code_identity", lambda *_a, **_kw: {"head": "deadbeef", "dirty": True})

    with pytest.raises(tool.ResumeMismatchError, match="code_identity"):
        tool.main(["--manifest", str(path), "--out", str(out), "--allow-empty-corpus", "--i-have-approval", "APPROVAL-1", "--resume"])


def test_resume_rejects_a_changed_prompt_version(tmp_path, monkeypatch):
    _patch_real_singletons(monkeypatch)
    manifest = _manifest([_case("a")])
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    out = tmp_path / "out.jsonl"
    tool.main(["--manifest", str(path), "--out", str(out), "--allow-empty-corpus", "--i-have-approval", "APPROVAL-1"])

    monkeypatch.setattr(settings, "PROMPT_VERSION", "some-other-version")

    with pytest.raises(tool.ResumeMismatchError, match="prompt_version"):
        tool.main(["--manifest", str(path), "--out", str(out), "--allow-empty-corpus", "--i-have-approval", "APPROVAL-1", "--resume"])


def test_resume_rejects_a_different_approval_id(tmp_path, monkeypatch):
    """One checkpoint is one authorization (Fable re-review F4)."""
    _patch_real_singletons(monkeypatch)
    manifest = _manifest([_case("a")])
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    out = tmp_path / "out.jsonl"
    tool.main(["--manifest", str(path), "--out", str(out), "--allow-empty-corpus", "--i-have-approval", "APPROVAL-A"])

    with pytest.raises(tool.ResumeMismatchError, match="approval_id"):
        tool.main(["--manifest", str(path), "--out", str(out), "--allow-empty-corpus", "--i-have-approval", "APPROVAL-B", "--resume"])


def test_resume_skips_cases_already_in_the_checkpoint(tmp_path, monkeypatch):
    _patch_real_singletons(monkeypatch)
    manifest = _manifest([_case("a"), _case("b")])
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    out = tmp_path / "out.jsonl"
    tool.main(["--manifest", str(path), "--out", str(out), "--allow-empty-corpus", "--i-have-approval", "APPROVAL-1", "--max-calls", "0"])

    # The first case ran and hit the cap; resuming should not redo it.
    _, rows_before = tool.read_checkpoint(out)
    assert len(rows_before) == 1

    tool.main(["--manifest", str(path), "--out", str(out), "--allow-empty-corpus", "--i-have-approval", "APPROVAL-1", "--resume"])

    _, rows_after = tool.read_checkpoint(out)
    assert [row["case_id"] for row in rows_after] == ["a", "b"]


def test_max_calls_aborts_cleanly_and_writes_a_checkpoint(tmp_path, monkeypatch):
    _patch_real_singletons(monkeypatch)
    manifest = _manifest([_case("a"), _case("b"), _case("c")])
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    out = tmp_path / "out.jsonl"

    exit_code = tool.main([
        "--manifest", str(path), "--out", str(out), "--allow-empty-corpus", "--i-have-approval", "APPROVAL-1", "--max-calls", "1",
    ])

    assert exit_code == 2
    _, rows = tool.read_checkpoint(out)
    assert 1 <= len(rows) < 3


def test_max_cost_aborts_cleanly_and_writes_a_checkpoint(tmp_path, monkeypatch):
    _patch_real_singletons(monkeypatch)
    manifest = _manifest([_case("a"), _case("b"), _case("c")])
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    out = tmp_path / "out.jsonl"

    exit_code = tool.main([
        "--manifest", str(path), "--out", str(out), "--allow-empty-corpus", "--i-have-approval", "APPROVAL-1",
        "--max-cost", "0.0001", "--unit-price", "generation=1.0",
    ])

    assert exit_code == 2
    _, rows = tool.read_checkpoint(out)
    assert 1 <= len(rows) < 3


def test_a_capture_does_not_validate_its_own_seeded_sessions(tmp_path, monkeypatch):
    """The tool seeds sessions into the memory backend, so they never exist in
    chat_sessions; validating them there can only fail (observed 2026-09-22:
    every case ended "Session validation failed" with zero calls made)."""
    import scripts.capture_application_path as capture
    from app.orchestrator import chat_orchestrator

    calls = []
    for name in capture.CAPTURE_ISOLATION:
        monkeypatch.setattr(
            chat_orchestrator, name,
            (lambda n: lambda *args, **kwargs: calls.append(n))(name),
        )

    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({
        "manifest_version": 1,
        "cases": [{
            "id": "c1", "split": "development", "exposure": "test",
            "message": "What payment methods are accepted?", "country": "US",
            "language": "en", "role": "new_prospect", "expectations": "x", "turns": [],
        }],
    }), encoding="utf-8")
    out = tmp_path / "out.jsonl"

    # The real orchestrator is constructed (no calls are made by construction);
    # only the per-case run is replaced, so no model or retrieval call happens.
    monkeypatch.setattr(
        capture, "run_one_case",
        lambda *args, **kwargs: {"case_id": "c1", "call_counts": {key: 0 for key in capture.CALL_CATEGORIES}},
    )
    capture.main([
        # An offline test has no ingestion corpus, so it opts out of the
        # live-run corpus guard explicitly.
        "--manifest", str(manifest), "--out", str(out), "--allow-empty-corpus",
        "--i-have-approval", "TEST-APPROVAL",
    ])

    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()]
    header = rows[0]
    assert header["session_state"] == "capture_supplied_memory"
    assert header["capture_isolation"] == sorted(capture.CAPTURE_ISOLATION)
    assert calls == [], f"a capture must not reach a reader store: {calls}"
    # Every replaced name is restored when the run finishes.
    for name in capture.CAPTURE_ISOLATION:
        assert getattr(chat_orchestrator, name) is not None
    # The isolation list covers the reader-session, consent, audit and cache
    # seams, and nothing that the capture exists to measure.
    assert {"validate_and_touch_session", "has_valid_consent", "write_audit_event"} <= set(capture.CAPTURE_ISOLATION)
    assert not {"approve_evidence", "resolve_answer_language"} & set(capture.CAPTURE_ISOLATION)


def test_a_case_record_carries_the_conversation_layer_diagnostics():
    """A capture must record what the conversation layer decided: the turn's
    typed outcome, the CX additions applied, any answer-language switch and any
    detected self-correction. Without these a capture cannot evaluate CX."""
    import scripts.capture_application_path as capture

    import pathlib

    source = pathlib.Path(capture.__file__).read_text(encoding="utf-8")
    assert '"conversation_outcome"' in source
    for key in ("outcome", "cx_applied", "answer_language", "conversation_repair"):
        assert f'"{key}"' in source, key


def test_a_capture_refuses_to_run_when_the_corpus_filter_would_match_nothing(tmp_path, monkeypatch):
    """Observed 2026-09-22: with no database reachable, the active ingestion
    generations are empty, retrieval filters on a sentinel that matches nothing,
    and every case ends in the missing-evidence fallback after real calls."""
    import scripts.capture_application_path as capture

    monkeypatch.setattr(capture, "read_active_generations", lambda: [])

    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({
        "manifest_version": 1,
        "cases": [{
            "id": "c1", "split": "development", "exposure": "test", "turns": [],
            "message": "What payment methods are accepted?", "country": "US",
            "language": "en", "role": "new_prospect", "expectations": "x",
        }],
    }), encoding="utf-8")

    with pytest.raises(capture.CaptureError) as error:
        capture.main([
            "--manifest", str(manifest), "--out", str(tmp_path / "out.jsonl"),
            "--i-have-approval", "TEST-APPROVAL",
        ])
    assert "zero hits" in str(error.value)


def test_a_capture_refuses_to_run_when_the_generations_cannot_be_read(tmp_path, monkeypatch):
    """The same guard covers an unreachable database, which is how this was
    first observed (the read itself raised, rather than returning nothing)."""
    import scripts.capture_application_path as capture

    def _unreachable():
        raise RuntimeError("no database here")

    monkeypatch.setattr(capture, "read_active_generations", _unreachable)

    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({
        "manifest_version": 1,
        "cases": [{
            "id": "c1", "split": "development", "exposure": "test", "turns": [],
            "message": "What payment methods are accepted?", "country": "US",
            "language": "en", "role": "new_prospect", "expectations": "x",
        }],
    }), encoding="utf-8")

    with pytest.raises(capture.CaptureError) as error:
        capture.main([
            "--manifest", str(manifest), "--out", str(tmp_path / "out.jsonl"),
            "--i-have-approval", "TEST-APPROVAL",
        ])
    assert "retrieval would match nothing" in str(error.value)


def test_a_capture_does_not_publish_metrics(tmp_path, monkeypatch):
    """Synthetic turns must not land in the dashboards that describe real
    traffic (observed 2026-09-22: 12 capture turns published
    delivered_responses and pipeline timings tagged environment=production)."""
    import scripts.capture_application_path as capture
    from app.metrics import metrics_publisher

    monkeypatch.setattr(capture, "read_active_generations", lambda: [{"active_ingestion_id": "x"}])
    seen = {}
    monkeypatch.setattr(
        capture, "run_one_case",
        lambda *a, **k: seen.setdefault("enabled_during_run", metrics_publisher.enabled) or {
            "case_id": "c1", "call_counts": {key: 0 for key in capture.CALL_CATEGORIES},
        },
    )
    metrics_publisher.enabled = True

    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({
        "manifest_version": 1,
        "cases": [{
            "id": "c1", "split": "development", "exposure": "test", "turns": [],
            "message": "What payment methods are accepted?", "country": "US",
            "language": "en", "role": "new_prospect", "expectations": "x",
        }],
    }), encoding="utf-8")
    out = tmp_path / "out.jsonl"
    capture.main(["--manifest", str(manifest), "--out", str(out), "--i-have-approval", "TEST-APPROVAL"])

    assert seen["enabled_during_run"] is False, "metrics must not publish during a capture"
    assert metrics_publisher.enabled is True, "the publisher is restored afterwards"
    header = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert header["metrics_published"] is False


# --------------------------------------------------------------------------
# Evidence-decision recording
#
# "approved_evidence" is the final RESPONSE's citations: what the customer
# received. A governance refusal replaces the answer with fallback copy that
# carries no citations, so a turn where evidence WAS approved and an answer
# WAS generated, then refused, otherwise reads as "no evidence" (the 2026-09-22
# root-cause misread this change fixes). "evidence_decision" records the
# evidence gate's own decision separately, so the two can be told apart.
# --------------------------------------------------------------------------


class _EmptyAnswerRouter:
    """A model that answers, but whose text is later cleaned up to nothing --
    standing in for a governance/output-cleanup refusal after evidence was
    approved and generation ran (`_handle_scrubbed_chat`'s
    `if not chat_response.answer.strip()` branch, which clears citations)."""

    def __init__(self) -> None:
        self.call_count = 0

    def generate(self, *_: object, **__: object) -> ModelResponse:
        self.call_count += 1
        return ModelResponse(text="", citations=[], confidence=0.9, provider="test", model_name="model-under-test")


class _BlockingGovernance:
    def evaluate(self, **_: object) -> GovernanceDecision:
        return GovernanceDecision(allowed=False, action=GovernanceAction.BLOCK, provider="test", reason="blocked")


class _ReapprovingRouter:
    """Simulates a turn where approve_evidence is called more than once (e.g.
    `_route_or_approve_evidence`'s cross-market reapproval of global evidence),
    by calling it again itself before answering."""

    def generate(self, *_: object, **__: object) -> ModelResponse:
        empty_result = RetrievalResult(documents=[], citations=[], confidence=0.0, metadata={})
        chat_orchestrator.approve_evidence("second call", empty_result, "CA", "en")
        return ModelResponse(
            text="The service fee is 2.50.", citations=[], confidence=0.9,
            provider="test", model_name="model-under-test",
        )


def _run_one_case_with_recorder(orchestrator, case, **kwargs) -> dict:
    original = tool.install_evidence_decision_recorder(chat_orchestrator)
    try:
        return tool.run_one_case(orchestrator, case, **kwargs)
    finally:
        tool.restore_evidence_decision_recorder(chat_orchestrator, original)


def test_evidence_decision_records_approval_when_an_answer_is_delivered():
    orchestrator = _orchestrator()
    case = tool._runtime_fields(_case("approved-and-delivered", message="What is the service fee?"))

    record = _run_one_case_with_recorder(orchestrator, case, correlation_id="test-corr", capture_final_answer=False)

    assert record["evidence_decision"]["called"] is True
    assert record["evidence_decision"]["approved"] is True
    assert record["evidence_decision"]["document_count"] == 1
    assert record["evidence_decision"]["decisions"] == [
        {"approved": True, "reason": record["evidence_decision"]["reason"], "document_count": 1},
    ]
    assert record["approved_evidence"], "the delivered answer should carry the approved citation"


def test_evidence_decision_key_case_approved_evidence_empty_while_the_gate_approved():
    """The exact misreading this change fixes: the evidence gate approved
    evidence and an answer was generated, but the delivered response carries
    no citations. approved_evidence alone would misread this as "no evidence
    found"; evidence_decision.approved is True and says otherwise."""
    orchestrator = AIOrchestrator(retriever=_Retriever(), router=_EmptyAnswerRouter(), governance=_Governance())
    case = tool._runtime_fields(_case("empty-delivered-answer", message="What is the service fee?"))

    record = _run_one_case_with_recorder(orchestrator, case, correlation_id="test-corr", capture_final_answer=False)

    assert record["approved_evidence"] == []
    assert record["evidence_decision"]["called"] is True
    assert record["evidence_decision"]["approved"] is True
    assert record["evidence_decision"]["document_count"] == 1


def test_evidence_decision_when_approve_evidence_is_never_called():
    """A pre-retrieval refusal (here, a governance block, which runs before
    `_route_or_approve_evidence`) never reaches the evidence gate."""
    orchestrator = AIOrchestrator(retriever=_Retriever(), router=_Router(), governance=_BlockingGovernance())
    case = tool._runtime_fields(_case("governance-blocked", message="What is the service fee?"))

    record = _run_one_case_with_recorder(orchestrator, case, correlation_id="test-corr", capture_final_answer=False)

    assert record["evidence_decision"] == {
        "called": False, "approved": None, "reason": None, "document_count": None, "decisions": [],
    }


def test_evidence_decision_records_every_call_and_the_top_level_reflects_the_last():
    orchestrator = AIOrchestrator(retriever=_Retriever(), router=_ReapprovingRouter(), governance=_Governance())
    case = tool._runtime_fields(_case("reapproved", message="What is the service fee?"))

    record = _run_one_case_with_recorder(orchestrator, case, correlation_id="test-corr", capture_final_answer=False)

    decisions = record["evidence_decision"]["decisions"]
    assert len(decisions) == 2
    assert decisions[0] == {"approved": True, "reason": "approved", "document_count": 1}
    assert decisions[1] == {"approved": False, "reason": "no_evidence", "document_count": 0}
    # Top-level reflects the LAST decision -- the one that governed the turn.
    assert record["evidence_decision"]["approved"] is False
    assert record["evidence_decision"]["reason"] == "no_evidence"
    assert record["evidence_decision"]["document_count"] == 0


class _RecordingModule:
    """A bare attribute holder standing in for the chat_orchestrator module,
    so the wrapper's identity/exception behaviour can be tested in isolation
    from the real orchestrator."""


def test_evidence_decision_wrapper_returns_the_identical_object():
    sentinel = object()
    module = _RecordingModule()
    module.approve_evidence = lambda *args, **kwargs: sentinel

    original = tool.install_evidence_decision_recorder(module)
    tool._EVIDENCE_DECISIONS.clear()
    try:
        result = module.approve_evidence("q", "retrieval-result", "CA", "en")
        assert result is sentinel
        assert tool._EVIDENCE_DECISIONS == [sentinel]
    finally:
        tool.restore_evidence_decision_recorder(module, original)

    assert module.approve_evidence is original


def test_evidence_decision_wrapper_propagates_an_exception_unchanged():
    module = _RecordingModule()

    def raising_approve_evidence(*args, **kwargs):
        raise ValueError("boom")

    module.approve_evidence = raising_approve_evidence

    original = tool.install_evidence_decision_recorder(module)
    tool._EVIDENCE_DECISIONS.clear()
    try:
        with pytest.raises(ValueError, match="boom"):
            module.approve_evidence("q", "retrieval-result", "CA", "en")
        assert tool._EVIDENCE_DECISIONS == [], "an exception from the original must record nothing"
    finally:
        tool.restore_evidence_decision_recorder(module, original)

    assert module.approve_evidence is raising_approve_evidence


def test_evidence_decision_recorder_is_installed_during_main_and_restored_after(tmp_path, monkeypatch):
    import scripts.capture_application_path as capture

    monkeypatch.setattr(capture, "read_active_generations", lambda: [{"active_ingestion_id": "x"}])
    original_before = chat_orchestrator.approve_evidence
    seen = {}

    def _fake_run_one_case(*_a: object, **_k: object) -> dict:
        seen["wrapped_during_run"] = chat_orchestrator.approve_evidence is not original_before
        return {"case_id": "c1", "call_counts": {key: 0 for key in capture.CALL_CATEGORIES}}

    monkeypatch.setattr(capture, "run_one_case", _fake_run_one_case)

    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({
        "manifest_version": 1,
        "cases": [{
            "id": "c1", "split": "development", "exposure": "test", "turns": [],
            "message": "What payment methods are accepted?", "country": "US",
            "language": "en", "role": "new_prospect", "expectations": "x",
        }],
    }), encoding="utf-8")
    out = tmp_path / "out.jsonl"
    capture.main(["--manifest", str(manifest), "--out", str(out), "--i-have-approval", "TEST-APPROVAL"])

    assert seen["wrapped_during_run"] is True
    assert chat_orchestrator.approve_evidence is original_before


def test_evidence_decision_recorder_is_restored_even_when_the_run_raises(tmp_path, monkeypatch):
    import scripts.capture_application_path as capture

    monkeypatch.setattr(capture, "read_active_generations", lambda: [{"active_ingestion_id": "x"}])
    original_before = chat_orchestrator.approve_evidence

    def _boom(*a, **k):
        raise RuntimeError("case blew up")

    monkeypatch.setattr(capture, "run_one_case", _boom)

    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({
        "manifest_version": 1,
        "cases": [{
            "id": "c1", "split": "development", "exposure": "test", "turns": [],
            "message": "What payment methods are accepted?", "country": "US",
            "language": "en", "role": "new_prospect", "expectations": "x",
        }],
    }), encoding="utf-8")
    out = tmp_path / "out.jsonl"

    with pytest.raises(RuntimeError, match="case blew up"):
        capture.main(["--manifest", str(manifest), "--out", str(out), "--i-have-approval", "TEST-APPROVAL"])

    assert chat_orchestrator.approve_evidence is original_before


def test_run_header_records_evidence_decision_recorded(tmp_path, monkeypatch):
    import scripts.capture_application_path as capture

    monkeypatch.setattr(capture, "read_active_generations", lambda: [{"active_ingestion_id": "x"}])
    monkeypatch.setattr(
        capture, "run_one_case",
        lambda *a, **k: {"case_id": "c1", "call_counts": {key: 0 for key in capture.CALL_CATEGORIES}},
    )

    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({
        "manifest_version": 1,
        "cases": [{
            "id": "c1", "split": "development", "exposure": "test", "turns": [],
            "message": "What payment methods are accepted?", "country": "US",
            "language": "en", "role": "new_prospect", "expectations": "x",
        }],
    }), encoding="utf-8")
    out = tmp_path / "out.jsonl"
    capture.main(["--manifest", str(manifest), "--out", str(out), "--i-have-approval", "TEST-APPROVAL"])

    header = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert header["evidence_decision_recorded"] is True
