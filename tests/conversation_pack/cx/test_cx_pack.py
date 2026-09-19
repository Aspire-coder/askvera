"""CX Lane 6: offline evaluation matrix for the Phase 3 conversation-experience
layer (docs/conversation-quality/phase3/CX_LANES.md, CX_DESIGN.md).

deterministic/local proof + mocked dependency behaviour. This module drives
two things, and never guesses at a third:

1. **`app.response.outcome.derive_outcome` (Lane 1, already wired).** This is
   real, already-shipped code, so every case's ``expected.kind`` is checked
   against it for real, today, with no mock beyond the plain ``metadata`` /
   ``EvidenceDecision``-shaped stub each case supplies (the same duck-typed
   stub shape ``tests/unit/test_conversation_outcome.py`` uses).
2. **Lanes 2-5 and 7 (not wired yet).** `chat_orchestrator.py` is
   single-writer and the coordinator has not wired these lanes' hooks into it,
   so nothing downstream of the outcome -- localized message keys, the
   partial-answer note, contact dedup, suggestion topics, repair
   acknowledgement, typo clarification wording, or answer-language detection
   -- exists to call yet. Each of those checks routes through a single small
   adapter function below (``_render_cx``, ``_partial_answer``, ...) that
   imports the real lane module by its CX_LANES.md write-scope path. Until
   that module exists the import itself fails, which is the correct,
   self-updating signal: no guessed behaviour is faked here.

## The flip mechanism

``FEATURE_FLAGS`` at the top of this file is the single source of "is lane N
wired into the offline path yet". A case's ``requires`` list names the flags
its full assertion needs. Any flag still False makes that case
``xfail(strict=True)`` at collection time (see ``_case_params``), so:

- unexpected passes are flagged loudly (an adapter that suddenly succeeds
  while its flag is still False means the flag is stale), and
- once the coordinator wires a lane's hook into ``chat_orchestrator.py`` (or,
  for these offline cases, once this module's adapter can reach the real
  lane module), flipping that one flag to ``True`` removes the xfail mark and
  the case must pass for real from then on -- no other edit required here
  unless the real API shape differs from the adapter's guess, in which case
  only the adapter function needs updating, never the case data.

Case ids live only in ``cases.json``; nothing under ``app/`` ever references
one (checked by ``test_no_hardcoded_case_ids_in_this_module`` below, mirroring
``tests/unit/test_conversation_outcome.py``'s own such check).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.response.outcome import ConversationOutcome, OutcomeKind, derive_outcome

CASES_PATH = Path(__file__).parent / "cases.json"
CASES: list[dict[str, Any]] = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]

# --- the flip mechanism ------------------------------------------------------

# True only once the named lane's behaviour is actually reachable from an
# offline case in this file. "outcome_contract" is Lane 1, already wired
# (app/response/outcome.py exists and chat_orchestrator's failure_layer
# vocabulary already flows through it in tests/unit/test_conversation_outcome.py);
# every other flag is Phase 3 work not yet wired anywhere.
FEATURE_FLAGS: dict[str, bool] = {
    "outcome_contract": True,
    "partial_answer": False,  # Lane 2: app/response/partial_answer.py
    "contact_and_suggestions": False,  # Lane 3: app/response/contact_completion.py (extend), suggestions.py
    "personal_account": False,  # Lane 3: app/response/personal_account.py
    "localization": False,  # Lane 4: app/response/cx_render.py, config/conversation_routes.json CX keys
    "repair": False,  # Lane 5: app/orchestrator/conversation_repair.py
    "typo_clarify": False,  # Lane 5: candidate_narrowing_fallback -> CX clarify render
    "answer_language": False,  # Lane 7: app/orchestrator/answer_language.py
}


def _missing_flags(case: dict[str, Any]) -> list[str]:
    return [flag for flag in case["requires"] if not FEATURE_FLAGS.get(flag, False)]


# --- Lane-1-only outcome derivation (real, runs today) -----------------------


class _FakeDocument:
    def __init__(self, metadata: dict[str, Any]) -> None:
        self.metadata = metadata


class _FakeEvidenceDecision:
    def __init__(self, reason: str, documents: list[dict[str, Any]]) -> None:
        self.reason = reason
        self.evidence = [_FakeDocument(doc) for doc in documents]


def _derive_case_outcome(case: dict[str, Any]) -> ConversationOutcome:
    stub = case["stub"]
    last_turn = case["turns"][-1]
    question = last_turn["message"]
    language = last_turn.get("language", case["language"])

    metadata: dict[str, Any] = {}
    if stub.get("failure_layer"):
        metadata["failure_layer"] = stub["failure_layer"]
    if "retrieval_availability" in stub:
        metadata["retrieval_availability"] = stub["retrieval_availability"]
    metadata.update(stub.get("metadata_extra", {}))

    evidence_decision = None
    if "evidence_decision" in stub:
        ed = stub["evidence_decision"]
        evidence_decision = _FakeEvidenceDecision(ed["reason"], ed.get("documents", []))

    return derive_outcome(
        metadata=metadata,
        language=language,
        country=case["session_country"],
        question=question,
        answer_text=last_turn.get("scripted_answer", ""),
        evidence_decision=evidence_decision,
    )


def _history_text(turns: list[dict[str, Any]]) -> str:
    lines = []
    for turn in turns:
        speaker = "user" if turn.get("role", "user") == "user" else "vera"
        lines.append(f"{speaker}: {turn['message']}")
    return "\n".join(lines)


# --- adapters into not-yet-wired lane modules --------------------------------
#
# Each adapter is the single place a not-yet-existing lane module is
# imported. Until FEATURE_FLAGS[<lane>] is True the corresponding cases are
# xfail-marked, so the ImportError these raise today is the expected failure.
# When a lane lands, only the adapter body (never the case data) may need to
# change to match its real signature.


def _render_cx(outcome: ConversationOutcome, *, question: str, language: str):
    from app.response.cx_render import render_outcome  # Lane 4

    return render_outcome(outcome, question=question, language=language)


def _partial_answer(outcome: ConversationOutcome, *, answer_text: str):
    from app.response.partial_answer import compute_partial_answer  # Lane 2

    return compute_partial_answer(
        outcome, answer_text=answer_text, fields_requested=outcome.fields_requested
    )


def _contact_supplement(outcome: ConversationOutcome, *, country: str):
    from app.response.contact_completion import build_cx_contact_supplement  # Lane 3

    return build_cx_contact_supplement(outcome, country=country)


def _suggestions(outcome: ConversationOutcome):
    from app.response.suggestions import suggest_topics  # Lane 3

    return suggest_topics(outcome)


def _repair(*, history: str, message: str, language: str):
    from app.orchestrator.conversation_repair import repair_turn  # Lane 5

    return repair_turn(history=history, message=message, language=language)


def _answer_language(*, message: str, session_language: str):
    from app.orchestrator.answer_language import detect_answer_language  # Lane 7

    return detect_answer_language(message=message, session_language=session_language)


# --- per-requirement behavioural assertions (only reached once wired) -------


def _assert_behaviour(case: dict[str, Any], outcome: ConversationOutcome) -> None:
    expected = case["expected"]
    requirement = case["requirement"]
    last_turn = case["turns"][-1]
    question = last_turn["message"]
    language = last_turn.get("language", case["language"])

    needs_localization = "localization" in case["requires"]
    needs_partial = "partial_answer" in case["requires"]
    needs_contacts = "contact_and_suggestions" in case["requires"]
    needs_repair = "repair" in case["requires"]
    needs_answer_language = "answer_language" in case["requires"]

    rendered = None
    if needs_localization:
        rendered = _render_cx(outcome, question=question, language=language)
        for key in expected.get("message_keys_present", []):
            assert key in rendered.message_keys, (case["id"], key, rendered.message_keys)
        for key in expected.get("message_keys_absent", []):
            assert key not in rendered.message_keys, (case["id"], key, rendered.message_keys)
        if "clarification_question_count" in expected:
            assert rendered.question_count == expected["clarification_question_count"], case["id"]
        for option in expected.get("clarify_options", []):
            assert option in rendered.clarify_options, (case["id"], option)
        if "repair_country" in expected:
            assert rendered.resolved_target == expected["repair_country"], case["id"]

    if needs_partial:
        partial = _partial_answer(outcome, answer_text=last_turn.get("scripted_answer", ""))
        if "partial_note_present" in expected:
            assert bool(partial.partial_note) is expected["partial_note_present"], case["id"]
        if expected.get("no_numeric_confidence"):
            assert not re.search(r"\d{1,3}\s*%", partial.partial_note or ""), case["id"]

    if needs_contacts and requirement == "contact_escalation":
        supplement = _contact_supplement(outcome, country=case["session_country"])
        assert supplement.contact_market == expected["contact_market"], case["id"]
        assert supplement.duplicated is False, case["id"]

    if needs_contacts and requirement == "supported_only_suggestions":
        suggestions = _suggestions(outcome)
        allowed = set(expected["suggestion_allowed_topics"])
        assert set(suggestions) <= allowed, (case["id"], suggestions)

    if needs_repair:
        history = _history_text(case["turns"][:-1])
        result = _repair(history=history, message=question, language=language)
        assert result.acknowledged is True, case["id"]
        if "repair_country" in expected:
            assert result.corrected_country == expected["repair_country"], case["id"]

    if needs_answer_language:
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


def _run_case(case: dict[str, Any]) -> None:
    outcome = _derive_case_outcome(case)
    expected = case["expected"]
    assert outcome.kind is OutcomeKind(expected["kind"]), (
        case["id"], outcome.kind.value, expected["kind"]
    )

    missing = _missing_flags(case)
    if missing:
        pytest.fail(
            f"{case['id']}: CX lane(s) not wired yet, cannot verify rendering/"
            f"behaviour: {', '.join(sorted(missing))} "
            f"(outcome kind matched: {outcome.kind.value})"
        )

    _assert_behaviour(case, outcome)


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
def test_cx_case(case: dict[str, Any]) -> None:
    _run_case(case)


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
        OutcomeKind(case["expected"]["kind"])  # raises ValueError if not a real kind


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


def test_no_hardcoded_case_ids_in_this_module() -> None:
    # Same meta-check as tests/unit/test_conversation_outcome.py's own: case
    # ids live only in cases.json, never as a literal in code.
    ids = {case["id"] for case in CASES}
    source = Path(__file__).read_text(encoding="utf-8")
    for case_id in ids:
        assert case_id not in source, f"{case_id} must not be hardcoded in this module"
