"""CX Lane 6: offline evaluation matrix for the Phase 3 conversation-experience
layer (docs/conversation-quality/phase3/CX_LANES.md, CX_DESIGN.md).

deterministic/local proof + mocked dependency behaviour. No live model, no
real OpenSearch/embeddings, no AWS call, no network call happens anywhere in
this module -- ``_no_real_aws`` (autouse) fakes
``app.response.cx_render.localize_reviewed_copy`` deterministically and
guards ``services.aws_clients.get_aws_clients`` so a real Bedrock/boto3 call
attempt fails the test loudly instead of hanging or raising a confusing
botocore error.

v3 (coordinator review of b398dde: lanes 1-7 merged, the outcome contract is
wired into ``chat_orchestrator.py`` for real). Two kinds of check now happen
per case:

1. **Real, unconditional checks.** `outcome.kind` on the real
   `ChatResponse.metadata["outcome"]` -- attached by the orchestrator on
   every path, verified by reading `chat_orchestrator.py` and confirmed by
   running every fixture directly outside pytest -- and, where a case's
   `expected` names one, a direct call to a real Lane 2/3/5/7 PURE function
   (`conversation_repair.detect_repair`, `.typo_clarification`,
   `quality.confidence_framing_key`, `answer_language.resolve_answer_language`)
   that needs no orchestrator wiring at all. These always run, regardless of
   `FEATURE_FLAGS`, because the real code already exists and is already
   callable.
2. **Flag-gated checks.** Whether `cx_compose.py` (Lane 8, not built yet)
   has actually wired a lane's ADDITION into the delivered response --
   `ChatResponse.metadata["cx_applied"]` (a list of marker strings:
   `preamble_stripped`, `partial_note`, `personal_account_note`,
   `contact_offer`, `international_directory_note`, `suggestions`) and
   `ChatResponse.suggestions` (structured items; suggestions never go into
   the answer text). Gated behind `FEATURE_FLAGS`; today `cx_applied` is
   simply absent from every response (the composer isn't wired), so these
   checks fail for an honest, verified reason.

Every one of the 80 cases in `cases.json` was checked by actually running
its fixture directly (outside pytest's xfail wrapper) at least once while
writing this file; several `expected.kind` values are the DESIRED behaviour
rather than today's real result, on purpose, with the gap documented in that
case's own `notes` (`fallback_state_ambiguous_followup`,
`one_question_clarification`, `typo_tolerance`) -- this is how a case stays
able to fail for a real reason rather than passing vacuously.

## Reuse (not copy) of the existing pack's harness

`tests/conversation_pack` has no `__init__.py`, so its modules aren't
import-package-able; this file loads `test_conversation_pack.py` by file
path and reuses its fixture builders (`_policy_row`, `_global_directory_row`)
and fakes (`_Validator`, `AIOrchestrator`, `ChatRequest`,
`GovernanceDecision`, `GovernanceAction`, `chat_orchestrator`, `settings`,
`cache_module`) rather than redeclaring them -- see `_base_pack` below.

## A worktree-specific finding: "pt" cannot be a session language here

No market in `config/policy_locales.json` publishes Portuguese, so
`services.market_config.get_supported_language_codes()` -- the exact set
`utils.validators.ChatRequest` validates `language` against -- never
includes `"pt"`, in any country. `config/markets.json` (the customer-facing
market list, e.g. Brazil) is a DIFFERENT config not consulted by that
validator. Verified: the union of every market's languages in
`policy_locales.json` is *exactly* the 12 CX route locales, so there is no
session-level way to reach a non-route language in this worktree at all. The
non-route-locale ("does an unconfigured language still get real copy, via
the English-fallback path") requirement is therefore tested directly against
`app.response.cx_render.render("pt", ...)` -- a pure function untouched by
`ChatRequest` -- in the `non_route_language_fallback` cases, not through
`handle_chat`.

## The flip mechanism

`FEATURE_FLAGS` at the top of this file. `outcome_contract_wired` is `True`
(real, verified). Every other flag stays `False` until the coordinator wires
`cx_compose.py` into `chat_orchestrator.py` for that lane's addition; when it
does, flipping the flag removes the `xfail(strict=True)` mark from every
case naming it, and those cases' `cx_applied`/`response.suggestions`
assertions must pass for real from then on.

Case ids live only in `cases.json`; nothing under `app/` ever references one.
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
_PACK_MODULE_PATH = Path(__file__).resolve().parents[1] / "test_conversation_pack.py"
_spec = importlib.util.spec_from_file_location("_cx_base_pack", _PACK_MODULE_PATH)
_base_pack = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("_cx_base_pack", _base_pack)
_spec.loader.exec_module(_base_pack)  # type: ignore[union-attr]

import boto3  # noqa: E402

import app.evidence as evidence_module  # noqa: E402
from app.models.responses import ModelResponse  # noqa: E402
from app.orchestrator import answer_language  # noqa: E402
from app.orchestrator import conversation_repair  # noqa: E402
from app.response import cx_render  # noqa: E402
from app.response import partial_answer as partial_answer_module  # noqa: E402
from app.response import quality  # noqa: E402
from app.response.outcome import ConversationOutcome, OutcomeKind  # noqa: E402
from app.response.personal_account import detect_personal_account_request  # noqa: E402
from app.retrieval.models import RetrievalAvailability, RetrievalResult  # noqa: E402

# --- no real AWS, ever --------------------------------------------------------
#
# services/controlled_copy.py's localize_reviewed_copy is imported with
# `from ... import` into BOTH app/response/cx_render.py AND app/evidence.py
# (the latter via app.evidence.localized_conversation_response) -- each
# holds its OWN bound reference, so both call sites must be patched
# separately; patching services.controlled_copy itself would not reach
# either already-bound name. boto3.client / boto3.session.Session.client
# are also patched directly as a last-resort net: if some future call site
# reaches AWS through neither of the above, client construction itself
# fails loudly instead of a live call or a confusing botocore error.


def _raise_on_real_aws_client(*_a: object, **_k: object) -> None:
    raise AssertionError(
        "tests/conversation_pack/cx attempted a real AWS client -- every case "
        "must be reachable through a fixture/fake instead."
    )


@pytest.fixture(autouse=True)
def _no_real_aws(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cx_render, "localize_reviewed_copy", lambda *_, **__: None)
    monkeypatch.setattr(evidence_module, "localize_reviewed_copy", lambda *_, **__: None)
    monkeypatch.setattr(boto3, "client", _raise_on_real_aws_client)
    monkeypatch.setattr(boto3.session.Session, "client", _raise_on_real_aws_client)


# --- the flip mechanism ------------------------------------------------------
#
# v4 (coordinator review of c58ccbc: lanes 1-8 wired on b95abc9, "commit with
# the flags set True for every REQUIREMENT whose cases ALL pass, False for
# the rest"). Flags are keyed by `case["requirement"]` directly now, not by
# a shared lane concept: with the composer actually wired, requirements that
# used to share one lane flag (e.g. "localization") turned out to have
# different real pass/fail results (fallback_state_international_directory
# passes in full; fallback_state_evidence_missing does not, for a real
# product reason -- see CX_LANE6_EVALUATION.md's product-defect list). A
# shared flag could not represent that split, so each requirement gets its
# own. `case["requires"]` is kept in the case data as a historical/
# documentation field (which lane(s) a case's assertions touch) but no
# longer drives gating.
FEATURE_FLAGS: dict[str, bool] = {
    # Coordinator: chat_orchestrator.py attaches ChatResponse.metadata["outcome"]
    # on every path -- verified, applies to every case automatically.
    "outcome_contract_wired": True,
    # Blocked by a real product defect (CX_LANE6_EVALUATION.md P1): chat_orchestrator's
    # plain evidence_gate fallback (_insufficient_evidence_message) never renders
    # the evidence_missing_detail key.
    "fallback_state_evidence_missing": False,
    "fallback_state_dependency_unavailable": True,
    # Blocked by a real product defect (P3): app.evidence._names_another_market
    # does not recognise every market name tried (only Kenya passes).
    "fallback_state_cross_market_policy": False,
    "fallback_state_international_directory": True,
    # Blocked by a real product gap (P4): reference-narrowing between two
    # approved directory candidates is not wired; the higher-scored one is
    # answered instead of asking which one.
    "fallback_state_ambiguous_followup": False,
    # Blocked by a real product defect (P2): cx_compose.py only adds
    # personal_account_limit for an answer-shaped outcome; the realistic
    # personal-account question (no evidence exists for it) is evidence_missing.
    "fallback_state_personal_account": False,
    "fallback_state_safety_refusal": True,
    "non_route_language_fallback": True,
    "answer_language_parity": True,
    "direct_answer_first": True,
    "partial_answer": True,
    # Blocked by the same reference-narrowing gap as fallback_state_ambiguous_followup (P4).
    "one_question_clarification": False,
    "contact_escalation": True,
    "supported_only_suggestions": True,
    "conversation_repair": True,
    "typo_tolerance": True,
    "confidence_aware_language": True,
}


def _missing_flags(case: dict[str, Any]) -> list[str]:
    flags = ["outcome_contract_wired", case["requirement"]]
    return [flag for flag in flags if not FEATURE_FLAGS.get(flag, False)]


def _outcome_from_metadata(meta: dict[str, Any]) -> ConversationOutcome:
    return ConversationOutcome(
        kind=OutcomeKind(meta["kind"]),
        language=meta["language"],
        country=meta["country"],
        fields_requested=frozenset(meta.get("fields_requested") or ()),
        fields_answered=frozenset(meta.get("fields_answered") or ()),
        fields_unsupported=frozenset(meta.get("fields_unsupported") or ()),
        directory_target=meta.get("directory_target"),
        clarification_subject=meta.get("clarification_subject"),
        failure_layer=meta.get("failure_layer"),
        retrieval_availability=meta.get("retrieval_availability"),
    )


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
    def __init__(self, text: str, finish_reason: str) -> None:
        self._text = text
        self._finish_reason = finish_reason

    def generate(self, *_: object, **__: object) -> ModelResponse:
        return ModelResponse(
            text=self._text, citations=[], confidence=0.9, provider="cx-fixture",
            model_name="cx-fixture", finish_reason=self._finish_reason,
        )


class _CxGovernance:
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
    """Drive the real AIOrchestrator.handle_chat for this case's final turn."""
    stub = case["stub"]
    turns = case["turns"]
    last_turn = turns[-1]

    documents = [_build_document(doc) for doc in stub.get("documents", [])]
    availability = _AVAILABILITY[stub.get("availability")]
    retriever = _CxRetriever(documents, stub.get("confidence", 0.9), availability)
    router = _CxRouter(last_turn.get("scripted_answer", ""), stub.get("model_finish_reason", ""))
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


# --- always-real checks: pure Lane 2/3/5/7 functions, no orchestrator needed -


def _run_pure_function_checks(case: dict[str, Any]) -> None:
    """Assertions against real, already-callable pure functions.

    These run unconditionally (no FEATURE_FLAGS gate) because the functions
    genuinely exist and need no orchestrator wiring -- only whether
    `chat_orchestrator.py`/`cx_compose.py` actually CALLS them for a live
    turn is gated.
    """
    expected = case["expected"]
    last_turn = case["turns"][-1]
    language = last_turn.get("language", case["language"])

    if "repair_kind" in expected:
        prior_turns = [turn["message"] for turn in case["turns"][:-1] if turn.get("role", "user") == "user"]
        repair = conversation_repair.detect_repair(last_turn["message"], language, prior_turns)
        assert repair is not None, (case["id"], "detect_repair found no correction")
        assert repair.kind == expected["repair_kind"], case["id"]
        assert repair.replacement == expected["repair_replacement"], case["id"]

    if case["requirement"] == "typo_tolerance":
        clarification = conversation_repair.typo_clarification(last_turn["message"], language)
        assert clarification is not None, (case["id"], "typo_clarification found no collision")
        assert clarification.key == "clarify_field", case["id"]
        assert len(clarification.options) == 2, case["id"]

    if "confidence_framing_key_expected" in expected:
        coverage = partial_answer_module.assess_field_coverage(
            question=case["turns"][0]["message"] if len(case["turns"]) == 1 else last_turn["message"],
            language=language, answer_text=last_turn.get("scripted_answer", ""),
            evidence_documents=[_build_document(doc) for doc in case["stub"].get("documents", [])],
        )
        key = quality.confidence_framing_key(OutcomeKind(expected["kind"]), coverage)
        assert key == expected["confidence_framing_key_expected"], (case["id"], key)

    if case["requirement"] == "answer_language_parity":
        detection = answer_language.resolve_answer_language(last_turn["message"], case["language"])
        retrieval = answer_language.retrieval_language(case["language"], detection.answer_language)
        assert retrieval == expected["retrieval_language_unchanged"], (
            case["id"], "retrieval eligibility must stay anchored to session language"
        )

    if case["requirement"] == "fallback_state_personal_account":
        assert detect_personal_account_request(last_turn["message"], language) is expected.get(
            "personal_account_detected", True
        ), case["id"]


# --- flag-gated checks: did cx_compose actually apply the addition ----------


def _assert_gated_behaviour(case: dict[str, Any], response, outcome: ConversationOutcome) -> None:
    expected = case["expected"]
    applied = response.metadata.get("cx_applied") or []

    for marker in expected.get("cx_applied_expected", []):
        assert marker in applied, (case["id"], marker, applied)
    for marker in expected.get("cx_applied_absent", []):
        assert marker not in applied, (case["id"], marker, applied)

    if "suggestion_allowed_topics" in expected:
        allowed = set(expected["suggestion_allowed_topics"])
        offered = {item.get("key") if isinstance(item, dict) else item for item in response.suggestions}
        assert offered <= allowed, (case["id"], offered)
        # Suggestions are structured items, never appended into the answer text.
        for topic_key in offered:
            assert topic_key not in response.answer, (case["id"], topic_key)

    if "render_key" in expected:
        rendered = cx_render.render(
            expected["render_key"], case["language"], **expected.get("render_placeholders", {})
        )
        assert rendered, (case["id"], "render() must never return empty text")
        assert rendered in response.answer, (case["id"], expected["render_key"], rendered, response.answer)


# --- runner -------------------------------------------------------------------


def _run_render_only_case(case: dict[str, Any]) -> None:
    """Non-route-locale (pt) cases: call cx_render.render directly, no ChatRequest."""
    expected = case["expected"]
    rendered = cx_render.render(expected["render_key"], case["language"], **expected.get("render_placeholders", {}))
    assert rendered, (case["id"], "render() must never return empty text")
    assert not cx_render.mixed_language_or_empty(rendered, "en"), (
        case["id"], "the English-fallback floor must not read as empty/mixed-script", rendered
    )
    english = cx_render.render(expected["render_key"], "en", **expected.get("render_placeholders", {}))
    if expected.get("expect_english_fallback"):
        assert rendered == english, (
            case["id"], "with localize_reviewed_copy faked to always fail, pt must fall back to the English copy",
            rendered, english,
        )


def _run_case(case: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    if case["stub"].get("render_only"):
        _run_render_only_case(case)
        return

    response = _run_turn(monkeypatch, case)
    expected = case["expected"]

    outcome_metadata = response.metadata.get("outcome")
    assert outcome_metadata is not None, (case["id"], "ChatResponse.metadata has no 'outcome' key")
    assert outcome_metadata["kind"] == expected["kind"], (
        case["id"], outcome_metadata.get("kind"), expected["kind"]
    )
    outcome = _outcome_from_metadata(outcome_metadata)
    if "directory_target" in expected:
        assert outcome.directory_target == expected["directory_target"], case["id"]
    if "retrieval_availability" in expected:
        assert outcome.retrieval_availability == expected["retrieval_availability"], case["id"]
    if expected.get("no_numeric_confidence"):
        assert not re.search(r"\d{1,3}\s*%", response.answer), case["id"]
    if "coverage_unsupported" in expected:
        coverage = partial_answer_module.assess_field_coverage(
            question=case["turns"][-1]["message"], language=case["language"],
            answer_text=response.answer,
            evidence_documents=[_build_document(doc) for doc in case["stub"].get("documents", [])],
        )
        assert sorted(coverage.unsupported) == sorted(expected["coverage_unsupported"]), (
            case["id"], sorted(coverage.unsupported)
        )
    if "answer_starts_with" in expected:
        stripped = quality.strip_leading_preamble(response.answer, case["language"])
        assert stripped.startswith(expected["answer_starts_with"]), (case["id"], stripped[:80])

    _run_pure_function_checks(case)

    missing = _missing_flags(case)
    if missing:
        pytest.fail(
            f"{case['id']}: CX lane(s) not wired yet, cannot verify cx_compose behaviour: "
            f"{', '.join(sorted(missing))}"
        )

    _assert_gated_behaviour(case, response, outcome)


def _case_params() -> list:
    params = []
    for case in CASES:
        missing = _missing_flags(case)
        marks = []
        if missing:
            marks.append(pytest.mark.xfail(reason=f"CX lane not wired: {', '.join(sorted(missing))}", strict=True))
        params.append(pytest.param(case, marks=marks, id=case["id"]))
    return params


@pytest.mark.parametrize("case", _case_params())
def test_cx_case(case: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    _run_case(case, monkeypatch)


# --- manifest self-checks ------------------------------------------------------


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
        "fallback_state_evidence_missing", "fallback_state_dependency_unavailable",
        "fallback_state_cross_market_policy", "fallback_state_international_directory",
        "fallback_state_ambiguous_followup", "fallback_state_personal_account",
        "fallback_state_safety_refusal", "partial_answer", "one_question_clarification",
        "contact_escalation", "direct_answer_first", "supported_only_suggestions",
        "conversation_repair", "typo_tolerance", "confidence_aware_language",
        "answer_language_parity", "non_route_language_fallback",
    }
    present = {case["requirement"] for case in CASES}
    missing = required_requirements - present
    assert not missing, f"cases.json is missing coverage for: {missing}"


def test_every_fallback_state_has_multilingual_parity() -> None:
    required_languages = {"en", "es", "fr", "de", "fi", "sv", "ru"}
    fallback_states = {
        req for req in {case["requirement"] for case in CASES} if req.startswith("fallback_state_")
    }
    for requirement in fallback_states:
        languages = {case["language"] for case in CASES if case["requirement"] == requirement}
        missing = required_languages - languages
        assert not missing, f"{requirement} is missing languages: {missing}"


def test_non_route_language_fallback_uses_pt_directly() -> None:
    # pt cannot be a ChatRequest.language in this worktree (see module
    # docstring); it must still be exercised, directly against cx_render.
    non_route_cases = [case for case in CASES if case["requirement"] == "non_route_language_fallback"]
    assert non_route_cases, "no non-route-locale fallback coverage at all"
    for case in non_route_cases:
        assert case["language"] == "pt", case["id"]
        assert case["stub"].get("render_only") is True, (case["id"], "must not go through ChatRequest/handle_chat")


def test_answer_language_parity_covers_every_state_language() -> None:
    languages = {case["language"] for case in CASES if case["requirement"] == "answer_language_parity"}
    assert languages == {"en"}, "answer_language_parity keeps the session/document language fixed"
    message_languages = {
        case["turns"][-1]["message_language"] for case in CASES if case["requirement"] == "answer_language_parity"
    }
    assert {"en", "es", "fr", "de", "fi", "sv", "ru", "pt"} <= message_languages


def test_every_case_requires_the_outcome_contract() -> None:
    for case in CASES:
        assert "outcome_contract_wired" not in case["requires"], (
            case["id"], "outcome_contract_wired is applied automatically; do not list it"
        )


def test_no_hardcoded_case_ids_in_this_module() -> None:
    ids = {case["id"] for case in CASES}
    source = Path(__file__).read_text(encoding="utf-8")
    for case_id in ids:
        assert case_id not in source, f"{case_id} must not be hardcoded in this module"
