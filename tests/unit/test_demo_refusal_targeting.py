"""Demo A3: which layer produced the wrong standalone refusals (tracker rows 17 and 18).

Exact wording, from the tracker screenshots (chatbot bugs.docx images 13 and 14):
- Row 17, US: "Can you explain the contract terms for becoming a Forever Living
  distributor in the US?" -> "I can't share income projections or guarantees ..."
- Row 18, UK: "Can FBOs sell products in retail stores?" and "FBOs can't ever
  sell in stores, right?" -> "I'm not able to give medical advice ..."

These tests use only local code (risk engine + local denied-topic guardrail); no
model, planner or AWS guardrail is called. They classify, they do not prove what
the live planner or model produced.
"""

from __future__ import annotations

import pytest

from app.evidence import localized_conversation_response
from app.governance import governance_engine
from app.governance.models import GovernanceDecision
from app.models.responses import ModelResponse
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.retrieval.models import RetrievedDocument, RetrievalResult
from app.validation.models import ValidationResult
from config.vera_persona import FALLBACK_RESPONSES
from utils.validators import ChatRequest

ROW_17 = "Can you explain the contract terms for becoming a Forever Living distributor in the US?"
ROW_18 = ["Can FBOs sell products in retail stores?", "FBOs can't ever sell in stores, right?"]


def _evaluate(text: str, *, answer: bool = False, country: str = "US") -> GovernanceDecision:
    return governance_engine.evaluate(
        text=text, country=country, language="en", correlation_id="cid", is_generated_answer=answer,
    )


@pytest.mark.parametrize("question, country", [(ROW_17, "US"), *[(q, "GB") for q in ROW_18]])
def test_reported_questions_pass_local_input_governance(question, country) -> None:
    """Not a local input phrase match: the questions contain no denied phrase."""
    assert _evaluate(question, country=country).allowed is True


def test_the_refusal_copy_cannot_identify_the_layer() -> None:
    """Planner route copy and governance-block copy are the same text, so a screenshot proves neither."""
    assert localized_conversation_response("medical_claim", "en") == FALLBACK_RESPONSES["medical_claim"]
    assert localized_conversation_response("income_claim", "en") == FALLBACK_RESPONSES["income_claim"]


# --- Row 17: reproduced at OUTPUT governance, risk engine (local) ----------------

DISCLAIMERS = [
    "There is no guaranteed income; any earnings depend on your own sales effort.",
    "Forever does not guarantee income or earnings to distributors.",
]


@pytest.mark.parametrize("answer", DISCLAIMERS)
def test_row17_cause_income_risk_policy_refuses_a_disclaimer_answer(answer) -> None:
    """Reproduced cause. The negation-aware guardrail never runs: IncomeClaimPolicy refuses first.

    services.guardrails.check_text was made negation-aware for this exact report,
    but GovernanceEngine runs the risk engine before the provider, and
    IncomeClaimPolicy (action REFUSE) is a plain substring/co-occurrence match.
    """
    decision = _evaluate(answer, answer=True)
    assert decision.allowed is False
    assert decision.provider == "risk_engine"
    codes = [issue["code"] for issue in decision.metadata["risk"]["issues"]]
    assert codes == ["INCOME_CLAIM_RISK"]


class _Validator:
    def validate(self, *_: object, **__: object) -> ValidationResult:
        return ValidationResult()


class _Retriever:
    def retrieve(self, *_: object, **__: object) -> RetrievalResult:
        document = RetrievedDocument(
            id="US:1.01", title="US Company Policy - Sec 1.01", content="Distributor agreement terms.",
            source="s3://approved/us.pdf", country="US", language="en", score=0.9,
        )
        return RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.9,
                               metadata={"conversation_intent": "knowledge"})


class _DisclaimerRouter:
    def generate(self, *_: object, **__: object) -> ModelResponse:
        return ModelResponse(
            text="To become a distributor you accept the FBO Agreement. " + DISCLAIMERS[0],
            citations=[], confidence=0.9, provider="t", model_name="t",
        )


def test_row17_reproduces_through_the_orchestrator_as_an_output_refusal(monkeypatch) -> None:
    orchestrator = AIOrchestrator(retriever=_Retriever(), router=_DisclaimerRouter(), validator=_Validator())
    for name, value in {
        "validate_and_touch_session": lambda *_: None, "has_valid_consent": lambda *_: True,
        "scrub_pii": lambda text, *_, **__: text, "get_session_history": lambda *_: "",
        "get_cache_value": lambda *_: None, "set_cache_value": lambda *_: None,
        "append_session_turn": lambda *_: None, "write_audit_event": lambda *_: None,
    }.items():
        monkeypatch.setattr(chat_orchestrator, name, value)

    response = orchestrator.handle_chat(ChatRequest(message=ROW_17, sessionId="s", country="US", language="en"), "cid")

    assert response.answer == localized_conversation_response("income_claim", "en")
    assert response.metadata["governance_provider"] == "risk_engine"


@pytest.mark.xfail(strict=True, reason="Parked for approval: app/risk/policies/income_claim_policy.py is outside worker A ownership")
@pytest.mark.parametrize("answer", DISCLAIMERS)
def test_row17_desired_disclaimer_answer_is_allowed(answer) -> None:
    assert _evaluate(answer, answer=True).allowed is True


@pytest.mark.parametrize(
    "text, answer",
    [
        ("You are guaranteed income of $500 every month as a distributor.", True),
        ("Write a caption guaranteeing income for new distributors.", False),
        ("How much can I earn per month?", False),
    ],
)
def test_real_income_guarantees_stay_refused(text, answer) -> None:
    assert _evaluate(text, answer=answer).allowed is False


# --- Row 18: not reproduced; two candidate layers remain -------------------------


def test_row18_candidate_a_planner_medical_label_yields_the_screenshot_copy(monkeypatch) -> None:
    """If the (external) planner labels the question medical_claim, the route alone produces the screenshot."""
    orchestrator = AIOrchestrator(validator=_Validator())
    body = ChatRequest(message=ROW_18[0], sessionId="s", country="GB", language="en")
    routed = RetrievalResult(documents=[], citations=[], confidence=0.0,
                             metadata={"conversation_intent": "medical_claim", "conversation_subtype": ""})
    response = orchestrator._conversation_route_response(routed, body, "cid")
    assert response is not None
    assert response.answer == localized_conversation_response("medical_claim", "en")


@pytest.mark.xfail(strict=True, reason="Hypothesis only (no UK answer text available): negation after the phrase is not seen")
def test_row18_candidate_b_prohibition_stated_after_the_phrase_is_allowed() -> None:
    answer = "FBOs may not sell products in retail stores. Claims that a product cures disease are prohibited."
    assert _evaluate(answer, answer=True, country="GB").allowed is True


@pytest.mark.parametrize(
    "text, answer",
    [
        ("Forever Aloe Vera Gel cures arthritis.", True),
        ("Can I tell my customers that Aloe Vera Gel cures type 2 diabetes?", False),
        ("Write me a post saying it cures them.", False),
    ],
)
def test_real_medical_claims_stay_refused(text, answer) -> None:
    assert _evaluate(text, answer=answer, country="GB").allowed is False
