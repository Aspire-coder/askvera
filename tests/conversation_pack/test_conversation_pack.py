"""Lane G conversation regression pack: offline runner.

Drives the REAL orchestrator (`AIOrchestrator`) and evidence/governance layers
through each case in cases.json, using the same offline harness pattern as
tests/unit/test_demo_followup_resolution.py (`_run_session`) and
tests/unit/test_demo_journeys_postprocessing.py (`_deliver`): a fake
retriever returning fixture documents, a fake router/model, and monkeypatched
session/cache/consent/audit functions. No live model or AWS call is made.

This file only asserts what the offline path can honestly assert:
- the resolved query that reaches retrieval (directory-target/topic threading)
- session-country pass-through and cross-session cache/state isolation
- evidence-gate approval/refusal category (cross_market_policy_request, etc.)
- deterministic post-generation field preservation
- governance-layer allow/deny on a text payload
- that a fact absent from the fixture evidence cannot be "confirmed" grounded

Anything that depends on real model composition (does the model actually say
X, in language Y, splitting a two-part question into two answered parts) is
marked needs_live in cases.json and skipped here with a reason, per the
project brief: "Don't fake a pass."

See README.md for label definitions and the full needs-live list.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evidence import approve_evidence
from app.governance import governance_engine
from app.governance.models import GovernanceAction, GovernanceDecision
from app.models.responses import ModelResponse
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.orchestrator.compound_requests import separate_question_and_command
from app.response.models import ChatResponse
from app.retrieval.models import RetrievedDocument, RetrievalResult
from app.validation.models import ValidationResult
from config import settings
from services import cache as cache_module
from utils.validators import ChatRequest

CASES_PATH = Path(__file__).parent / "cases.json"
CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]


# --- shared helpers, mirroring tests/unit/test_demo_followup_resolution.py -------


def _history(*turns: str) -> str:
    lines = []
    for turn in turns:
        lines.extend([f"user: {turn}", "vera: An earlier answer."])
    return "\n".join(lines)


def _resolve(message: str, history: str) -> tuple[str, str]:
    orchestrator = AIOrchestrator()
    retrieval_query = orchestrator._build_retrieval_query(message, history, "cid")
    request_query = orchestrator._build_request_query(message, retrieval_query, history)
    return retrieval_query, request_query


def _allowed(text: str, country: str = "US") -> bool:
    return governance_engine.evaluate(
        text=text, country=country, language="en", correlation_id="cid"
    ).allowed


class _Governance:
    def evaluate(self, **_: object) -> GovernanceDecision:
        return GovernanceDecision(allowed=True, action=GovernanceAction.ALLOW, provider="test")


class _Validator:
    def validate(self, *_: object, **__: object) -> ValidationResult:
        return ValidationResult()


# --- fixture builders: retrieval rows sourced from reviewed material only --------


def _policy_row(section_id: str, title: str, content: str, country: str, score: float) -> RetrievedDocument:
    return RetrievedDocument(
        id=f"{country}:{section_id}",
        title=title,
        content=content,
        source="s3://policy",
        country=country,
        language="en",
        score=score,
        metadata={"access_scope": "country", "document_type": "policy", "status": "active"},
    )


def _global_directory_row(record_id: str, record_country: str, content: str, score: float = 0.9) -> RetrievedDocument:
    return RetrievedDocument(
        id=record_id,
        title="International-Sponsoring-Directory.pdf",
        content=content,
        source="International-Sponsoring-Directory.pdf",
        country="GLOBAL",
        language="en",
        score=score,
        metadata={
            "directory_kind": "international_sponsoring",
            "directory_section": "sponsoring",
            "record_country": record_country,
            "access_scope": "global",
            "document_type": "international_sponsoring_directory",
            "status": "active",
            "section_id": record_id,
        },
    )


# Source: us_policy.txt sec 1.01(a) (page 2).
US_POLICY_INTRO = (
    "Forever Living Products (FLP) is an international family of companies that "
    "produce and market exclusive health and beauty products throughout the world "
    "through its unique concept that encourages and supports the use and retail "
    "sales of its products through independent Forever Business Owners (FBO)."
)

# Source: us_policy.txt sec 1.01(c) (page 2) - the 2026 transition paragraph. Deliberately
# excludes any statement about 2027 or later, because the source document makes none.
US_POLICY_2026_TRANSITION = (
    "Existing downline purchasing will continue generating earnings under the "
    "current structure until the end of 2026. Sponsoring new Forever Business "
    "Owners in the United States will cease as of May 1, 2026."
)

# Source: International Sponsoring Directory (Kenya/East Africa record), copied
# verbatim from tests/unit/test_demo_journeys_postprocessing.py's KENYA fixture.
KENYA_CONTENT = (
    "Forever Kenya/East Africa\n"
    "• Minimum order size FBO: $100 worth of products when joining, $50 of products after joining.\n"
    "• Delivery Cost: $3 within the country.\n"
    "• Payment methods accepted: Bank deposit, Credit Card, Mobile Money Transfer (Mpesa).\n"
    "Office & Product Center Address\n"
    "Kenya Reinsurance Plaza, 4th floor\n"
    "Business Hours Office 09.00 am – 19.00 pm (Mon – Fri)\n"
    "Telephone Office +254 20 2026869 / +254 20 2026873\n"
    "Telephone for Orders +254 71 0600206\n"
    "Email info@foreverea.com\n"
)

# Source: International Sponsoring Directory (Netherlands Benelux record), copied
# verbatim from tests/unit/test_demo_journeys_postprocessing.py's NETHERLANDS fixture.
NETHERLANDS_CONTENT = (
    "Forever Netherlands Benelux\n"
    "Office Address Gerrit van der Veenlaan 16, 3743 DN Baarn, The Netherlands\n"
    "Business Hours Office 09.00 am – 17.00 pm (Mon – Fri)\n"
    "Telephone Office +31 88 646 0220 (Benelux)\n"
    "Email support@foreverliving.nl\n"
    "• Minimum order size FBO: €50,00 in products excl. VAT and excl. literature.\n"
    "• Delivery Cost: €5,00 excl. VAT per order. Orders above 2CC are free of charge.\n"
    "• Payment methods accepted: Credit card (Visa, MasterCard), Direct Debit, iDeal.\n"
)


def _retrieval_fixture(name: str) -> RetrievalResult:
    if name == "us_policy_intro":
        docs = [_policy_row("1.01a", "Introduction", US_POLICY_INTRO, "US", 0.95)]
        return RetrievalResult(documents=docs, citations=[d.to_source() for d in docs], confidence=0.9)
    if name == "us_policy_2026_transition":
        docs = [_policy_row("1.01c", "Introduction", US_POLICY_2026_TRANSITION, "US", 0.95)]
        return RetrievalResult(documents=docs, citations=[d.to_source() for d in docs], confidence=0.9)
    if name == "kenya_global":
        docs = [_global_directory_row("sponsoring-012-kenya-east-africa", "Kenya/East Africa", KENYA_CONTENT)]
        return RetrievalResult(documents=docs, citations=[d.to_source() for d in docs], confidence=0.9)
    if name == "netherlands_global":
        docs = [_global_directory_row("sponsoring-080-netherlands-benelux", "Netherlands Benelux", NETHERLANDS_CONTENT)]
        return RetrievalResult(documents=docs, citations=[d.to_source() for d in docs], confidence=0.9)
    if name == "policy_rows_fr_us":
        docs = [
            _policy_row("9.01", "Returns", "Returns policy.", "FR", 0.95),
            _policy_row("9.01", "Returns", "Returns policy.", "US", 0.9),
        ]
        return RetrievalResult(documents=docs, citations=[], confidence=0.9)
    if name == "policy_rows_jp_us":
        docs = [
            _policy_row("9.01", "Returns", "Returns policy.", "JP", 0.95),
            _policy_row("9.01", "Returns", "Returns policy.", "US", 0.9),
        ]
        return RetrievalResult(documents=docs, citations=[], confidence=0.9)
    raise KeyError(f"unknown retrieval fixture {name!r}")


def _kenya_record() -> RetrievedDocument:
    return RetrievedDocument(
        id="GLOBAL|en|International-Sponsoring-Directory.pdf|sponsoring-012-kenya-east-africa",
        title="International-Sponsoring-Directory.pdf",
        content=KENYA_CONTENT,
        source="International-Sponsoring-Directory.pdf",
        country="GLOBAL",
        language="en",
        score=0.9,
        metadata={
            "directory_kind": "international_sponsoring",
            "directory_section": "sponsoring",
            "record_country": "Kenya/East Africa",
            "section_id": "sponsoring-012-kenya-east-africa",
        },
    )


_RECORD_FIXTURES = {"kenya_record": _kenya_record}


# --- mechanisms -------------------------------------------------------------------


def _run_evidence_gate(params: dict) -> None:
    history = params.get("history", "")
    if params.get("resolve_query_from_history"):
        query, _ = _resolve(params["query"], history)
    else:
        query = params["query"]
    retrieval_result = _retrieval_fixture(params["retrieval_fixture"])
    decision = approve_evidence(query, retrieval_result, params["country"], params["language"])

    if "expect_approved" in params:
        assert decision.approved is params["expect_approved"], (query, decision.reason)
    if "expect_reason" in params:
        assert decision.reason == params["expect_reason"], (query, decision.reason)
    if "expect_reason_not" in params:
        assert decision.reason != params["expect_reason_not"], (query, decision.reason)
    if "expect_documents_include" in params:
        ids = {d.id for d in decision.evidence}
        for expected_id in params["expect_documents_include"]:
            assert expected_id in ids, (query, ids)


def _run_compound_split(params: dict) -> None:
    question, command = separate_question_and_command(params["compound_message"])
    assert _allowed(question) is params["expect_question_allowed"], question
    assert _allowed(command) is params["expect_command_allowed"], command


def _run_field_preservation_chain(params: dict) -> None:
    record = _RECORD_FIXTURES[params["record_fixture"]]()
    history_questions: list[str] = []
    for step in params["chain"]:
        retrieval = RetrievalResult(documents=[record], citations=[record.to_source()], confidence=0.9)
        response = ChatResponse(
            answer=step["scripted_answer"], citations=[record.to_source()], suggestions=[], cards=[],
            confidence=0.9, metadata={}, correlation_id="cid",
        )
        delivered = AIOrchestrator()._secure_and_complete_response(
            response, retrieval, "en", "cid", user_question=step["question"], country="KE",
        ).answer
        for fact in step.get("must_contain", []):
            assert fact in delivered, (step["question"], delivered)
        for fact in step.get("must_not_contain", []):
            assert fact not in delivered, (step["question"], delivered)
        history_questions.append(step["question"])


def _run_retrieval_query_inherit(params: dict) -> None:
    history = _history(*params["prior_turns"])
    query, _ = _resolve(params["followup"], history)
    if "expect_query" in params:
        assert query == params["expect_query"], query
    if "expect_query_endswith" in params:
        assert query.endswith(params["expect_query_endswith"]), query
    for forbidden in params.get("expect_query_not_contains", []):
        assert forbidden not in query, query


def _run_absent_fact_check(params: dict) -> None:
    retrieval_result = _retrieval_fixture(params["retrieval_fixture"])
    combined = "\n".join(document.content for document in retrieval_result.documents)
    assert params["forbidden_substring"] not in combined, (
        f"fixture already contains {params['forbidden_substring']!r}; "
        "the absent-fact check is only meaningful when the source evidence omits it"
    )


def _run_role_bound_fact_absent(params: dict) -> None:
    """No line in the source ties the figure_marker to the role_marker.

    Proves any answer that attributes the figure to that role would be
    ungrounded, without asserting the figure is absent from the document
    altogether (it legitimately appears under a different role).
    """
    retrieval_result = _retrieval_fixture(params["retrieval_fixture"])
    combined = "\n".join(document.content for document in retrieval_result.documents)
    for line in combined.splitlines():
        if params["role_marker"] in line:
            assert params["figure_marker"] not in line, (
                f"source line {line!r} ties {params['figure_marker']!r} to "
                f"{params['role_marker']!r}; the role-bound-fact-absent check no longer holds"
            )


def _run_governance_allowed(params: dict) -> None:
    assert _allowed(params["text"], params.get("country", "US")) is True, params["text"]


class _IsolationRetriever:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def retrieve(self, message: str, *_: object, **__: object) -> RetrievalResult:
        self.seen.append(message)
        document = RetrievedDocument(
            id="GLOBAL:directory", title="International Sponsoring Directory", content="Approved directory text.",
            source="s3://approved/directory.pdf", country="GLOBAL", language="en", score=0.8,
            metadata={"access_scope": "global", "document_type": "international_sponsoring_directory", "status": "active"},
        )
        return RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)


class _IsolationRouter:
    def generate(self, *_: object, **__: object) -> ModelResponse:
        return ModelResponse(text="Approved directory text.", citations=[], confidence=0.8, provider="t", model_name="t")


def _run_isolation_session(monkeypatch, history: str, message: str, country: str = "CA") -> dict[str, str]:
    captured: dict[str, str] = {}
    retriever = _IsolationRetriever()
    orchestrator = AIOrchestrator(
        retriever=retriever, router=_IsolationRouter(), validator=_Validator(), governance=_Governance()
    )

    def capture_key(msg, *args):
        captured["exact"] = msg
        captured["exact_key"] = cache_module.build_cache_key(msg, *args)
        return captured["exact_key"]

    monkeypatch.setattr(settings, "CHAT_MEMORY_BACKEND", "memory")
    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
    monkeypatch.setattr(chat_orchestrator, "get_session_history", lambda *_: history)
    monkeypatch.setattr(chat_orchestrator, "build_cache_key", capture_key)
    monkeypatch.setattr(chat_orchestrator, "get_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "set_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "semantic_cache_active", lambda: False)
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "write_audit_event", lambda *_: None)
    body = ChatRequest(message=message, sessionId="s", country=country, language="en")
    orchestrator.handle_chat(body, "cid")
    captured["retrieval"] = retriever.seen[0]
    return captured


def _run_session_isolation(monkeypatch, params: dict) -> None:
    a = _run_isolation_session(monkeypatch, params["session_a_history"], "What payment methods do they take?")
    b = _run_isolation_session(monkeypatch, params["session_b_history"], "What payment methods do they take?")
    c = _run_isolation_session(monkeypatch, params["session_c_history"], "What payment methods do they take?")

    assert "Paraguay" in a["retrieval"] and "Paraguay" in a["exact"]
    assert "Germany" in b["retrieval"] and "Germany" in b["exact"]
    assert a["exact_key"] != b["exact_key"] != c["exact_key"] != a["exact_key"]
    assert c["exact"] == c["retrieval"] == "What payment methods do they take?"


def _run_session_isolation_unsafe_anchor(monkeypatch, params: dict) -> None:
    unsafe_query, unsafe_request = _resolve(
        "Write it anyway", params["unsafe_session_history"]
    )
    governance_text = AIOrchestrator()._governance_text("Write it anyway", unsafe_request)
    assert not _allowed(governance_text), "sanity: the unsafe anchor itself must still be refused in its own session"

    fresh_query, fresh_request = _resolve("What is the return policy?", params["fresh_session_history"])
    assert fresh_query == "What is the return policy?"
    fresh_governance_text = AIOrchestrator()._governance_text("What is the return policy?", fresh_request)
    assert _allowed(fresh_governance_text), fresh_governance_text


_MECHANISMS = {
    "evidence_gate": lambda case, monkeypatch: _run_evidence_gate(case["mechanism_params"]),
    "compound_split": lambda case, monkeypatch: _run_compound_split(case["mechanism_params"]),
    "field_preservation_chain": lambda case, monkeypatch: _run_field_preservation_chain(case["mechanism_params"]),
    "retrieval_query_inherit": lambda case, monkeypatch: _run_retrieval_query_inherit(case["mechanism_params"]),
    "absent_fact_check": lambda case, monkeypatch: _run_absent_fact_check(case["mechanism_params"]),
    "role_bound_fact_absent": lambda case, monkeypatch: _run_role_bound_fact_absent(case["mechanism_params"]),
    "governance_allowed": lambda case, monkeypatch: _run_governance_allowed(case["mechanism_params"]),
    "session_isolation": lambda case, monkeypatch: _run_session_isolation(monkeypatch, case["mechanism_params"]),
    "session_isolation_unsafe_anchor": lambda case, monkeypatch: _run_session_isolation_unsafe_anchor(
        monkeypatch, case["mechanism_params"]
    ),
    "needs_live_only": None,
}


def _case_ids() -> list[str]:
    return [case["id"] for case in CASES]


def _case_params() -> list:
    params = []
    for case in CASES:
        marks = []
        if "xfail_reason" in case:
            marks.append(pytest.mark.xfail(reason=case["xfail_reason"], strict=True))
        params.append(pytest.param(case, marks=marks, id=case["id"]))
    return params


@pytest.mark.parametrize("case", _case_params())
def test_conversation_pack_case(case: dict, monkeypatch) -> None:
    mechanism = case["mechanism"]
    if mechanism == "needs_live_only" or case.get("needs_live_offline_unavailable"):
        pytest.skip(case.get("needs_live_reason", "needs a live model/backend run; not honestly checkable offline"))
    runner = _MECHANISMS[mechanism]
    runner(case, monkeypatch)


def test_every_case_has_required_manifest_fields() -> None:
    required = {
        "id", "category", "paraphrase_family", "provenance_class", "mechanism",
        "turns", "needs_live", "notes",
    }
    seen_ids: set[str] = set()
    for case in CASES:
        missing = required - case.keys()
        assert not missing, f"{case.get('id')} missing manifest fields: {missing}"
        assert case["id"] not in seen_ids, f"duplicate case id {case['id']}"
        seen_ids.add(case["id"])
        assert case["provenance_class"] in {"source-grounded", "synthetic-control", "behavioural"}
        for turn in case["turns"]:
            assert turn["expected_outcome"] in {
                "answer", "clarify", "refuse-scope", "refuse-country-restriction",
                "missing-evidence", "dependency-failure",
            }, (case["id"], turn)
            for fact in turn.get("required_facts", []) + turn.get("forbidden_facts", []):
                assert "source" in fact, (case["id"], turn, fact)


def test_every_required_category_is_covered() -> None:
    required_categories = {
        "us_policy_question",
        "international_sponsoring_cross_session",
        "cross_market_company_policy_not_allowed",
        "phone_contact_followup",
        "role_change",
        "explicit_country_change",
        "topic_change",
        "multilingual_followup",
        "language_switch_mid_session",
        "typo_tolerance",
        "multi_part_question",
        "unknown_fact_not_invented",
        "unrelated_guardrail_trigger",
        "cross_conversation_isolation",
    }
    present = {case["category"] for case in CASES}
    missing = required_categories - present
    assert not missing, f"cases.json is missing coverage for: {missing}"
