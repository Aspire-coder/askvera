"""CX Lane 6: offline evaluation matrix for the Phase 3 conversation-experience
layer (docs/conversation-quality/phase3/CX_LANES.md, CX_DESIGN.md).

deterministic/local proof + mocked dependency behaviour. Every case in
cases.json drives the REAL `AIOrchestrator.handle_chat` end to end -- the
same offline harness pattern `tests/conversation_pack/test_conversation_pack.py`
already uses (a fixture retriever returning fake `RetrievedDocument`s, a fake
router/model, monkeypatched session/cache/consent/audit hooks). This module
imports that pack's module by file path and reuses its fixture builders
(`_policy_row`, `_global_directory_row`) and shared fakes (`_Validator`,
`AIOrchestrator`, `ChatRequest`, ...) rather than redeclaring them -- see
`_base_pack` below.

No live model, no real OpenSearch/embeddings, no AWS call, no network call
happens anywhere in this module.

## Why full `handle_chat`, not a hand-built `derive_outcome` stub

An earlier version of this file (28272cb) called
`app.response.outcome.derive_outcome` directly on a hand-built metadata/
`EvidenceDecision` stub. The coordinator's review of that commit is right
that this only re-proves Lane 1's own unit tests
(`tests/unit/test_conversation_outcome.py`) and would let a real wiring bug
-- retrieval returning the wrong documents, evidence approval never being
called, the governance path never reaching `_governance_fallback` -- through
completely undetected, because nothing about it depends on the real
orchestrator's control flow. Every case here instead builds real
`RetrievedDocument`/`RetrievalResult` fixtures, a real `ChatRequest`, and
calls the real `handle_chat`, then asserts on the real returned
`ChatResponse`.

## What is, and is not, checkable today

`chat_orchestrator.py` does not yet attach `ChatResponse.metadata["outcome"]`
(Lane 1's `derive_outcome` exists but nothing calls it from the orchestrator
-- see `CX_LANE1_OUTCOME.md`: "The coordinator wires
`ChatResponse.metadata["outcome"] = outcome.to_metadata()` into
`chat_orchestrator.py`; this lane does not touch that file"). So *every*
case's primary assertion -- `metadata["outcome"]["kind"]` -- fails today
regardless of how faithfully its fixture reproduces the real trigger
condition, which is what makes it safe to gate every single case behind the
`outcome_contract_wired` flag (see `FEATURE_FLAGS`) without risking an
accidental full pass. Message-key / contact / suggestion / repair /
answer-language checks are additionally gated behind their own lane flags.

## The flip mechanism

A case's `requires` list names the flags its full assertion needs, on top of
the always-required `outcome_contract_wired`. Any flag still `False` makes
that case `xfail(strict=True)` at collection time (`_case_params`), so an
adapter that suddenly succeeds while its flag is still `False` fails the
suite loudly instead of hiding a stale flag. When the coordinator wires a
lane, flipping its one flag to `True` removes the xfail mark and the case
must pass for real from then on. Case data never needs to change for a flip;
only an adapter function (`_render_cx`, `_partial_answer`, ...) might, if the
real lane module's signature differs from its current best-effort guess.

Case ids live only in `cases.json`; nothing under `app/` ever references one
(`test_no_hardcoded_case_ids_in_this_module` checks this file itself, per
`tests/unit/test_conversation_outcome.py`'s own such check).
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

CASES_PATH = Path(__file__).parent / "cases.json"
CASES: list[dict[str, Any]] = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]

# --- reuse (not copy) the existing pack's harness ----------------------------
#
# tests/conversation_pack has no __init__.py (see conftest/pytest.ini: plain
# rootdir-relative test discovery), so its modules are not importable as a
# package. Loading test_conversation_pack.py by file path -- rather than
# redeclaring _policy_row/_global_directory_row/_Validator/AIOrchestrator/
# ChatRequest here -- is how this file avoids duplicating that pack's fixture
# builders, per the coordinator's review.
_PACK_MODULE_PATH = Path(__file__).resolve().parents[1] / "test_conversation_pack.py"
_spec = importlib.util.spec_from_file_location("_cx_base_pack", _PACK_MODULE_PATH)
_base_pack = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("_cx_base_pack", _base_pack)
_spec.loader.exec_module(_base_pack)  # type: ignore[union-attr]

from app.models.responses import ModelResponse  # noqa: E402
from app.retrieval.models import RetrievalAvailability, RetrievalResult  # noqa: E402

# --- the flip mechanism ------------------------------------------------------

FEATURE_FLAGS: dict[str, bool] = {
    # Coordinator: chat_orchestrator.py attaches ChatResponse.metadata["outcome"].
    "outcome_contract_wired": False,
    "partial_answer": False,  # Lane 2: app/response/partial_answer.py
    "contact_and_suggestions": False,  # Lane 3: contact_completion.py (extend), suggestions.py
    "personal_account": False,  # Lane 3: app/response/personal_account.py
    "localization": False,  # Lane 4: app/response/cx_render.py, CX conversation_routes.json keys
    "repair": False,  # Lane 5: app/orchestrator/conversation_repair.py
    "typo_clarify": False,  # Lane 5: candidate_narrowing_fallback -> CX clarify render
    "answer_language": False,  # Lane 7: app/orchestrator/answer_language.py
    "quality_checks": False,  # Lane 2: lead-with-the-fact / preamble stripping
}


def _effective_requires(case: dict[str, Any]) -> list[str]:
    # outcome_contract_wired gates every case: the primary assertion below
    # always reads ChatResponse.metadata["outcome"].
    return ["outcome_contract_wired", *case["requires"]]


def _missing_flags(case: dict[str, Any]) -> list[str]:
    return [flag for flag in _effective_requires(case) if not FEATURE_FLAGS.get(flag, False)]


# --- fixture construction: real RetrievedDocument/RetrievalResult -----------


def _build_document(spec: dict[str, Any]):
    if spec["kind"] == "policy":
        return _base_pack._policy_row(
            spec["section_id"], spec["title"], spec["content"], spec["country"], spec.get("score", 0.9)
        )
    if spec["kind"] == "directory":
        return _base_pack._global_directory_row(
            spec["record_id"], spec["record_country"], spec["content"], spec.get("score", 0.9)
        )
    raise KeyError(f"unknown document kind {spec['kind']!r}")


class _CxRetriever:
    """A fixture retriever: returns exactly the case's documents/availability."""

    def __init__(self, documents: list, confidence: float, availability: RetrievalAvailability) -> None:
        self._documents = documents
        self._confidence = confidence
        self._availability = availability

    def retrieve(self, query: str, country: str, language: str, role: str, correlation_id: str) -> RetrievalResult:
        return RetrievalResult(
            documents=self._documents,
            citations=[doc.to_source() for doc in self._documents],
            confidence=self._confidence,
            availability=self._availability,
        )


class _CxRouter:
    """A fixture model: returns exactly the case's scripted answer."""

    def __init__(self, text: str, finish_reason: str) -> None:
        self._text = text
        self._finish_reason = finish_reason

    def generate(self, *_: object, **__: object) -> ModelResponse:
        return ModelResponse(
            text=self._text, citations=[], confidence=0.9, provider="cx-fixture",
            model_name="cx-fixture", finish_reason=self._finish_reason,
        )


class _CxGovernance:
    """A fixture governance engine: allows, or blocks with a chosen shape.

    `block_spec` mirrors the fields `chat_orchestrator._governance_failure_layer`
    actually branches on (`provider`, `guardrail_action`), so a case can drive
    either real outcome (`local_guardrail` vs `risk_policy`) without importing
    the real governance engine's rule tables.
    """

    def __init__(self, block_spec: dict[str, str] | None) -> None:
        self._block_spec = block_spec

    def evaluate(self, **_: object):
        if self._block_spec is None:
            return _base_pack.GovernanceDecision(
                allowed=True, action=_base_pack.GovernanceAction.ALLOW, provider="cx-fixture",
            )
        return _base_pack.GovernanceDecision(
            allowed=False,
            action=_base_pack.GovernanceAction.BLOCK,
            provider=self._block_spec.get("provider", "cx-fixture"),
            guardrail_action=_base_pack.GovernanceAction(self._block_spec.get("guardrail_action", "BLOCK")),
        )


_AVAILABILITY = {
    None: RetrievalAvailability.AVAILABLE,
    "unavailable": RetrievalAvailability.UNAVAILABLE,
    "degraded": RetrievalAvailability.DEGRADED,
}


def _history_text(turns: list[dict[str, Any]]) -> str:
    lines = []
    for turn in turns:
        speaker = "user" if turn.get("role", "user") == "user" else "vera"
        lines.append(f"{speaker}: {turn['message']}")
    return "\n".join(lines)


def _run_turn(monkeypatch: pytest.MonkeyPatch, case: dict[str, Any]):
    """Drive the real AIOrchestrator.handle_chat for this case's final turn.

    Monkeypatches the same session/cache/consent/audit seams
    `test_conversation_pack.py::_run_isolation_session` patches, referencing
    that pack's own `chat_orchestrator`/`settings`/`cache_module` module
    objects (reused, not reimplemented) so this stays in lockstep with
    whatever those hooks are named there.
    """
    stub = case["stub"]
    turns = case["turns"]
    last_turn = turns[-1]

    documents = [_build_document(doc) for doc in stub.get("documents", [])]
    availability = _AVAILABILITY[stub.get("availability")]
    retriever = _CxRetriever(documents, stub.get("confidence", 0.9), availability)
    router = _CxRouter(
        last_turn.get("scripted_answer", ""), stub.get("model_finish_reason", ""),
    )
    governance = _CxGovernance(stub.get("governance_block"))

    orchestrator = _base_pack.AIOrchestrator(
        retriever=retriever, router=router, validator=_base_pack._Validator(), governance=governance,
    )

    history = _history_text(turns[:-1])
    chat_orchestrator = _base_pack.chat_orchestrator
    monkeypatch.setattr(_base_pack.settings, "CHAT_MEMORY_BACKEND", "memory")
    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
    monkeypatch.setattr(chat_orchestrator, "get_session_history", lambda *_: history)
    monkeypatch.setattr(chat_orchestrator, "build_cache_key", _base_pack.cache_module.build_cache_key)
    monkeypatch.setattr(chat_orchestrator, "get_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "set_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "semantic_cache_active", lambda: False)
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "write_audit_event", lambda *_: None)

    body = _base_pack.ChatRequest(
        message=last_turn["message"], sessionId=f"cx-{case['id']}",
        country=case["session_country"], language=case["language"],
    )
    return orchestrator.handle_chat(body, "cid")


# --- adapters into not-yet-wired lane modules --------------------------------
#
# Each adapter is the single place a not-yet-existing lane module is
# imported. Until FEATURE_FLAGS[<lane>] is True the corresponding cases are
# xfail-marked, so the ImportError these raise today is the expected failure.
# When a lane lands, only the adapter body (never the case data) may need to
# change to match its real signature.


def _render_cx(outcome_metadata: dict[str, Any], *, question: str, language: str):
    from app.response.cx_render import render_outcome  # Lane 4

    return render_outcome(outcome_metadata, question=question, language=language)


def _partial_answer(outcome_metadata: dict[str, Any], *, answer_text: str, fields_requested):
    from app.response.partial_answer import compute_partial_answer  # Lane 2

    return compute_partial_answer(outcome_metadata, answer_text=answer_text, fields_requested=fields_requested)


def _contact_supplement(outcome_metadata: dict[str, Any], *, country: str):
    from app.response.contact_completion import build_cx_contact_supplement  # Lane 3

    return build_cx_contact_supplement(outcome_metadata, country=country)


def _suggestions(outcome_metadata: dict[str, Any]):
    from app.response.suggestions import suggest_topics  # Lane 3

    return suggest_topics(outcome_metadata)


def _repair(*, history: str, message: str, language: str):
    from app.orchestrator.conversation_repair import repair_turn  # Lane 5

    return repair_turn(history=history, message=message, language=language)


def _answer_language(*, message: str, session_language: str):
    from app.orchestrator.answer_language import detect_answer_language  # Lane 7

    return detect_answer_language(message=message, session_language=session_language)


# --- per-requirement behavioural assertions (only reached once wired) -------


def _assert_behaviour(case: dict[str, Any], response) -> None:
    expected = case["expected"]
    requirement = case["requirement"]
    last_turn = case["turns"][-1]
    question = last_turn["message"]
    language = last_turn.get("language", case["language"])
    outcome_metadata = response.metadata["outcome"]

    if requirement == "direct_answer_first":
        assert response.answer.startswith(expected["answer_starts_with"]), (
            case["id"], response.answer[:80]
        )
        return

    if "localization" in case["requires"]:
        rendered = _render_cx(outcome_metadata, question=question, language=language)
        for key in expected.get("message_keys_present", []):
            assert key in rendered.message_keys, (case["id"], key, rendered.message_keys)
        for key in expected.get("message_keys_absent", []):
            assert key not in rendered.message_keys, (case["id"], key, rendered.message_keys)
        if "clarification_question_count" in expected:
            assert rendered.question_count == expected["clarification_question_count"], case["id"]
        for option in expected.get("clarify_options", []):
            assert option in rendered.clarify_options, (case["id"], option)

    if "partial_answer" in case["requires"]:
        partial = _partial_answer(
            outcome_metadata, answer_text=response.answer,
            fields_requested=outcome_metadata.get("fields_requested", []),
        )
        if "partial_note_present" in expected:
            assert bool(partial.partial_note) is expected["partial_note_present"], case["id"]
        if expected.get("no_numeric_confidence"):
            assert not re.search(r"\d{1,3}\s*%", partial.partial_note or ""), case["id"]

    if "contact_and_suggestions" in case["requires"] and requirement == "contact_escalation":
        supplement = _contact_supplement(outcome_metadata, country=case["session_country"])
        assert supplement.contact_market == expected["contact_market"], case["id"]
        assert supplement.duplicated is False, case["id"]

    if "contact_and_suggestions" in case["requires"] and requirement == "supported_only_suggestions":
        suggestions = _suggestions(outcome_metadata)
        allowed = set(expected["suggestion_allowed_topics"])
        assert set(suggestions) <= allowed, (case["id"], suggestions)

    if "repair" in case["requires"]:
        history = _history_text(case["turns"][:-1])
        result = _repair(history=history, message=question, language=language)
        assert result.acknowledged is True, case["id"]
        if "repair_country" in expected:
            assert result.corrected_country == expected["repair_country"], case["id"]

    if "answer_language" in case["requires"]:
        message_language = last_turn.get("message_language", language)
        detected = _answer_language(message=question, session_language=case["language"])
        assert detected.answer_language == expected["answer_language"], case["id"]
        assert detected.answer_language == message_language, case["id"]
        # The retrieval-eligibility invariant (CX_DESIGN.md "Answer language"):
        # switching the rendered answer's language must never change which
        # country/document-language sources were eligible for retrieval.
        assert detected.retrieval_language == expected["retrieval_language_unchanged"], (
            case["id"], "retrieval eligibility must stay anchored to session language"
        )


# --- runner -------------------------------------------------------------------


def _run_case(case: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    response = _run_turn(monkeypatch, case)
    expected = case["expected"]

    outcome_metadata = response.metadata.get("outcome")
    assert outcome_metadata is not None, (
        case["id"], "ChatResponse.metadata has no 'outcome' key "
        "(chat_orchestrator.py does not call derive_outcome yet)"
    )
    assert outcome_metadata["kind"] == expected["kind"], (
        case["id"], outcome_metadata.get("kind"), expected["kind"]
    )

    missing = _missing_flags(case)
    if missing:
        pytest.fail(
            f"{case['id']}: CX lane(s) not wired yet, cannot verify rendering/"
            f"behaviour: {', '.join(sorted(missing))}"
        )

    _assert_behaviour(case, response)


def _case_params() -> list:
    params = []
    for case in CASES:
        missing = _missing_flags(case)
        marks = []
        if missing:
            marks.append(
                pytest.mark.xfail(
                    reason=f"CX lane not wired: {', '.join(sorted(missing))}",
                    strict=True,
                )
            )
        params.append(pytest.param(case, marks=marks, id=case["id"]))
    return params


@pytest.mark.parametrize("case", _case_params())
def test_cx_case(case: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    _run_case(case, monkeypatch)


# --- manifest self-checks (mirror tests/conversation_pack/test_conversation_pack.py) --


def test_every_case_has_required_manifest_fields() -> None:
    required = {
        "id", "requirement", "requires", "language", "session_country",
        "turns", "stub", "expected", "notes",
    }
    seen_ids: set[str] = set()
    for case in CASES:
        missing = required - case.keys()
        assert not missing, f"{case.get('id')} missing manifest fields: {missing}"
        assert case["id"] not in seen_ids, f"duplicate case id {case['id']}"
        seen_ids.add(case["id"])
        assert case["turns"], (case["id"], "must have at least one turn")
        assert len(case["notes"]) > 40, (case["id"], "notes must explain how this case can fail")


def test_every_required_matrix_item_is_covered() -> None:
    required_requirements = {
        "fallback_state_evidence_missing",
        "fallback_state_dependency_unavailable",
        "fallback_state_cross_market_policy",
        "fallback_state_international_directory",
        "fallback_state_ambiguous_followup",
        "fallback_state_personal_account",
        "fallback_state_safety_refusal",
        "partial_answer",
        "one_question_clarification",
        "contact_escalation",
        "direct_answer_first",
        "supported_only_suggestions",
        "conversation_repair",
        "typo_tolerance",
        "confidence_aware_language",
        "answer_language_parity",
    }
    present = {case["requirement"] for case in CASES}
    missing = required_requirements - present
    assert not missing, f"cases.json is missing coverage for: {missing}"


def test_every_fallback_state_has_multilingual_parity() -> None:
    required_languages = {"en", "es", "fr", "de", "fi", "sv", "ru"}
    fallback_states = {
        req for req in {case["requirement"] for case in CASES}
        if req.startswith("fallback_state_")
    }
    for requirement in fallback_states:
        languages = {case["language"] for case in CASES if case["requirement"] == requirement}
        missing = required_languages - languages
        assert not missing, f"{requirement} is missing languages: {missing}"
        non_route = languages - {
            "en", "es", "fr", "de", "fi", "sv", "ru", "it", "nl", "no", "da", "pl",
        }
        assert non_route, (
            f"{requirement} has no non-route-locale language exercising the "
            "English-copy fallback path"
        )


def test_answer_language_parity_covers_every_state_language() -> None:
    languages = {case["language"] for case in CASES if case["requirement"] == "answer_language_parity"}
    assert languages == {"en"}, "answer_language_parity keeps the session/document language fixed"
    message_languages = {
        case["turns"][-1]["message_language"]
        for case in CASES if case["requirement"] == "answer_language_parity"
    }
    assert {"en", "es", "fr", "de", "fi", "sv", "ru", "pt"} <= message_languages


def test_every_case_requires_the_outcome_contract() -> None:
    # Every case's primary assertion reads ChatResponse.metadata["outcome"],
    # so every case must be xfail today (see module docstring); a case that
    # forgot to depend on the shared gate would let a false pass through
    # once some OTHER flag were flipped on its own.
    for case in CASES:
        assert "outcome_contract_wired" not in case["requires"], (
            case["id"], "outcome_contract_wired is applied automatically; do not list it"
        )


def test_no_hardcoded_case_ids_in_this_module() -> None:
    # Same meta-check as tests/unit/test_conversation_outcome.py's own: case
    # ids live only in cases.json, never as a literal in code.
    ids = {case["id"] for case in CASES}
    source = Path(__file__).read_text(encoding="utf-8")
    for case_id in ids:
        assert case_id not in source, f"{case_id} must not be hardcoded in this module"
