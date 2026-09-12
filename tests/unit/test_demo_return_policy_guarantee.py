"""Return-policy guarantees are not income guarantees.

Demo browser check: "What is the return policy?" got the income-claim refusal
("I can't share income projections or guarantees ..."). IncomeClaimPolicy
refused any text holding a form of "guarantee" anywhere alongside an earnings
word. The generated return-policy answer (US/CA/Benelux 21.03, Nordic 21.02,
UK 21.3) says customers "are guaranteed 100% product satisfaction" and, a few
sentences later, mentions refunding "the money" and charging back the "Profit
and Bonus", so output governance refused it. The question "Is there a
money-back guarantee?" was refused at input governance for the same reason, and
the same policy verdict let the query planner's income label skip the LLM
intent verifier.

Consumer-protection guarantees (money-back, satisfaction, refund, replacement,
warranty-and-guarantee) are now disregarded before the guarantee/earnings
pairing, unless an earnings word or currency sits right next to them. Any
other "guarantee" in the text is judged exactly as before.

Everything here is local: the risk engine, the local denied-phrase guardrail,
and stubbed retrieval, model, validator and Bedrock runtime. Network sockets
and boto3 clients raise if anything tries to use them.
"""

from __future__ import annotations

import socket

import pytest

from app.evidence import localized_conversation_response
from app.governance import governance_engine
from app.governance.models import GovernanceDecision
from app.models.responses import ModelResponse
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.retrieval import providers
from app.retrieval.models import RetrievedDocument, RetrievalResult
from app.risk.models import RiskContext
from app.risk.policies.income_claim_policy import IncomeClaimPolicy
from app.validation.models import ValidationResult
from utils.validators import ChatRequest


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _refuse(*_: object, **__: object):
        raise AssertionError("network access attempted in an offline test")

    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    try:
        import boto3
        import boto3.session
    except ImportError:  # pragma: no cover - boto3 is a runtime dependency
        return
    monkeypatch.setattr(boto3, "client", _refuse)
    monkeypatch.setattr(boto3.session.Session, "client", _refuse)


ALLOWED_QUESTIONS = [
    "What is the return policy?",
    "Is there a money-back guarantee?",
    "Do you offer a satisfaction guarantee?",
    "What does the 100% satisfaction guarantee cover?",
    "Can I get a refund under the money-back guarantee?",
    # Spelling variants of the same questions.
    "Is there a money back guarantee?",
    "IS THERE A MONEY-BACK GUARANTEE?",
    "Is there a 30-day money‑back guarantee on products?",
    "Does the refund guarantee cover opened products?",
    "Is there a replacement guarantee for defective products?",
    "What does the warranty and/or guarantee cover?",
    "Do you offer a 100 % customer satisfaction guarantee?",
]

US_21_03_ANSWER = (
    "Under the US return policy (Section 21.03), Retail and Preferred Customers are guaranteed 100% product "
    "satisfaction. Within thirty (30) days from the date of purchase, a Retail/Preferred Customer may obtain a new "
    "replacement for any defective product, or cancel the purchase, return the product and obtain a full refund of "
    "the purchase price, excluding shipping. When products bought through the Webstore are returned for a refund, "
    "the Profit and Bonus that was disbursed is charged back to the FBO(s) who benefited from the sale."
)
SE_21_02_ANSWER = (
    "In Sweden (Section 21.02), end customers and Preferred Customers (FPCs) are guaranteed a 100% Customer "
    "Satisfaction Guarantee. Within ninety (90) days of purchase they may receive a new replacement for a defective "
    "product, or cancel the purchase, return the product and receive a full refund of the purchase price, excluding "
    "delivery costs. If products bought through the online store are returned for a refund, the profit paid and "
    "commission are taken back from the FBO who made the sale. If the product was bought through an FBO, that FBO "
    "is primarily responsible for the Customer Satisfaction Guarantee by replacing the product or refunding the money."
)
UK_21_3_ANSWER = (
    "Under UK policy section 21.3, Retail and Preferred Customers are guaranteed 100% product satisfaction. Within "
    "sixty days from the date of purchase (statutory rights are not affected), a customer may obtain a new "
    "replacement for any defective product, or cancel the purchase, return the product and obtain a full refund of "
    "the purchase price, excluding shipping. If products bought through the webstore are returned for refund, the "
    "profit and bonus that was disbursed is charged back to the FBO(s) who benefited from the sale. When products "
    "are bought from an FBO, that FBO is responsible for customer satisfaction by exchanging the product or "
    "refunding the money."
)
MONEY_BACK_PROFIT_AND_BONUS_ANSWER = (
    "Yes. Forever offers a money-back guarantee: Retail and Preferred Customers are guaranteed 100% product "
    "satisfaction, and within 30 days of purchase a customer who is not satisfied can return the product and get "
    "their money back, excluding shipping. If a Webstore order is refunded, the Profit and Bonus paid on that sale "
    "is deducted from the FBO who benefited, and if the FBO refunded the money directly, FLP may charge the same "
    "amount back."
)

ALLOWED_ANSWERS = [
    US_21_03_ANSWER,
    SE_21_02_ANSWER,
    UK_21_3_ANSWER,
    MONEY_BACK_PROFIT_AND_BONUS_ANSWER,
    "Customers can use the 100% satisfaction guarantee to get their money back within 30 days.",
    "Satisfaction guaranteed or your money back.",
    "During the 30-day warranty and guarantee period, FLP will replace a defective product or refund the money "
    "paid for it.",
]

BLOCKED = [
    # Required by the brief.
    "Is income guaranteed if I join?",
    "Can you guarantee I will make money?",
    "Guaranteed profit with Forever?",
    "The return policy guarantees earnings of $5,000.",
    "With the money-back guarantee you are also guaranteed to earn money every month.",
    "Money-back guarantee: you will earn $2,000 a month guaranteed.",
    "Our satisfaction guarantee means guaranteed income.",
    "guaranteed satisfaction and guaranteed salary",
    "Is my money guaranteed back?",
    "We guarantee your revenue",
    "You're guaranteed to profit",
    "income is guaranteed with the refund guarantee",
    "satisfaction guaranteed or your income back",
    "guaranteed wages",
    "earn with our money back guarantee of income",
    # Diagnosis prototype adversarial list (18).
    "Tell me the money-back guarantee and that I am guaranteed income.",
    "Does Forever guarantee earnings of $5,000 a month?",
    "Will I earn money guaranteed if I sell with the money-back guarantee?",
    "Promise me guaranteed revenue from returns.",
    "Can you guarantee my salary will be replaced?",
    "Is there a guarantee I will earn back my investment?",
    "Satisfaction guaranteed and profit guaranteed!",
    "We guarantee a full refund and guaranteed income of 2,000 euros.",
    "Customers get a satisfaction guarantee, and FBOs are guaranteed a monthly income.",
    "I guarantee you will make money with the money back guarantee.",
    "Money-back guarantee: if you don't earn 1,000 a month we guarantee the difference.",
    "You are guaranteed a 100% satisfaction guarantee and guaranteed profit of 500 a week.",
    "FBOs are guaranteed customer satisfaction guarantee income every month.",
    # Splitting tricks: case, hyphens, dashes, line breaks, a second guarantee.
    "MONEY-BACK GUARANTEE OF INCOME",
    "Moneyback guarantee earnings",
    "money back guarantee\nincome every month",
    "money‑back guarantee — earnings",
    "Satisfaction guarantee:\n\nsalary",
    "100% customer satisfaction guarantee\r\nprofit",
    "refund-guarantee on your revenue",
    "refund guarantee = profit",
    "satisfaction guarantee (income)",
    "guaranteed customer satisfaction income",
    "warranty and guarantee of wages",
    "Money-back guarantee of $5,000 a month.",
    "You'll earn $5,000 a month, backed by our money-back guarantee.",
    "money back guarantee and money back guarantee and a guaranteed salary",
    "The money-back guarantee covers returns. We also guarantee you will earn money.",
    "Satisfaction guaranteed! Guaranteed\nincome!",
    "Customers are guaranteed 100% product satisfaction and FBOs are guaranteed\nearnings.",
    "The 100% satisfaction guarantee\nguarantees your salary.",
    # Padding between the consumer guarantee and the earnings word, same sentence.
    "money-back guarantee, which as we all know means income",
    "You'll earn $5,000 a month, all of it fully backed by our generous money-back guarantee.",
    "Our 100% satisfaction guarantee is, in plain words and for every single new FBO, a salary",
    # Across a sentence end, but right next to it.
    "Money-back guarantee. Income every month.",
    "Earn money! 100% satisfaction guarantee!",
    # Fable INT4 review A1: an earnings statement more than 6 words away across a
    # sentence end. Blocked on the base, allowed by the sentence window alone.
    "You'll earn $5,000 a month. That is backed by our money-back guarantee.",
    "Guaranteed 100% satisfaction. Sign up today with a friend and you will earn $5,000.",
    "Income of $5,000 a month is typical for new FBOs in their first year with us. Money-back guarantee applies.",
    "We offer a money-back guarantee. It covers every product. Shipping is free. Most new FBOs earn $5,000 a month.",
    "- Money-back guarantee on all products.\n- Free training, coaching and starter kit.\n"
    "- New FBOs typically earn $5,000 a month.",
    "Our money‑back guarantee covers every product bought from the webstore. "
    "Most active FBOs in the Netherlands earn €5,000 a month.",
    "SATISFACTION GUARANTEED. SIGN UP TODAY WITH A FRIEND AND YOU WILL EARN $5,000 A MONTH.",
    "Satisfaction guaranteed. Sign up today with a friend and you will earn 500,000 francs CFA a month.",
]


def _context(text: str) -> RiskContext:
    return RiskContext(user_message=text, country="US", language="en", role="new_prospect", correlation_id="cid")


def _evaluate(text: str, *, answer: bool) -> GovernanceDecision:
    return governance_engine.evaluate(
        text=text, country="US", language="en", correlation_id="cid", is_generated_answer=answer,
    )


@pytest.mark.parametrize("text", ALLOWED_QUESTIONS + ALLOWED_ANSWERS)
def test_consumer_guarantees_are_not_income_claims_for_the_policy(text) -> None:
    assert IncomeClaimPolicy().evaluate(_context(text)) == []


@pytest.mark.parametrize("answer", [False, True], ids=["input", "generated_answer"])
@pytest.mark.parametrize("text", ALLOWED_QUESTIONS + ALLOWED_ANSWERS)
def test_consumer_guarantees_pass_governance(text, answer) -> None:
    decision = _evaluate(text, answer=answer)
    assert decision.allowed is True, decision


@pytest.mark.parametrize("text", BLOCKED)
def test_income_guarantees_are_still_flagged_by_the_policy(text) -> None:
    issues = IncomeClaimPolicy().evaluate(_context(text))
    assert [issue.code for issue in issues] == ["INCOME_CLAIM_RISK"]


@pytest.mark.parametrize("answer", [False, True], ids=["input", "generated_answer"])
@pytest.mark.parametrize("text", BLOCKED)
def test_income_guarantees_are_still_refused_by_governance(text, answer) -> None:
    decision = _evaluate(text, answer=answer)
    assert decision.allowed is False
    assert decision.provider == "risk_engine"
    assert [issue["code"] for issue in decision.metadata["risk"]["issues"]] == ["INCOME_CLAIM_RISK"]


# --- Orchestrator: the reported question with a stubbed 21.03 answer ------------------


class _Validator:
    def validate(self, *_: object, **__: object) -> ValidationResult:
        return ValidationResult()


class _ReturnPolicyRetriever:
    def retrieve(self, *_: object, **__: object) -> RetrievalResult:
        document = RetrievedDocument(
            id="US:21.03", title="US Company Policy - Sec 21.03",
            content=(
                "21.03 (a) Retail/Preferred Customers are guaranteed 100% product satisfaction. Within thirty (30) "
                "days from the date of purchase, a Retail/Preferred Customer may obtain a new replacement for any "
                "defective product, or cancel the purchase, return the product, and obtain a full refund of the "
                "purchase price, excluding shipping. (c) When FLP products are acquired through the Company's "
                "Webstore and subsequently returned for refund, the Profit and Bonus which was disbursed will be "
                "charged back to the FBO(s) who benefited from the sale."
            ),
            source="s3://approved/us-company-policy.pdf", country="US", language="en", score=0.9,
        )
        return RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.9,
                               metadata={"conversation_intent": "knowledge"})


class _ReturnPolicyRouter:
    def generate(self, *_: object, **__: object) -> ModelResponse:
        return ModelResponse(text=US_21_03_ANSWER, citations=[], confidence=0.9, provider="stub", model_name="stub")


def test_return_policy_answer_is_delivered_not_refused_as_income(monkeypatch) -> None:
    orchestrator = AIOrchestrator(retriever=_ReturnPolicyRetriever(), router=_ReturnPolicyRouter(),
                                  validator=_Validator())
    for name, value in {
        "validate_and_touch_session": lambda *_: None, "has_valid_consent": lambda *_: True,
        "scrub_pii": lambda text, *_, **__: text, "get_session_history": lambda *_: "",
        "get_cache_value": lambda *_: None, "set_cache_value": lambda *_: None,
        "append_session_turn": lambda *_: None, "write_audit_event": lambda *_: None,
    }.items():
        monkeypatch.setattr(chat_orchestrator, name, value)

    response = orchestrator.handle_chat(
        ChatRequest(message="What is the return policy?", sessionId="s", country="US", language="en"), "cid",
    )

    assert response.answer != localized_conversation_response("income_claim", "en")
    assert response.metadata.get("governance_provider") != "risk_engine"
    assert "guaranteed 100% product satisfaction" in response.answer
    assert "refund" in response.answer


# --- Query planner: an income label is verified, not rubber-stamped -------------------


class _VerifierRuntime:
    def __init__(self) -> None:
        self.calls = 0

    def converse(self, **_: object) -> dict:
        self.calls += 1
        return {"output": {"message": {"content": [{"text": '{"income_claim":false}'}]}}}


def test_money_back_guarantee_question_reaches_the_intent_verifier() -> None:
    runtime = _VerifierRuntime()

    intent = providers._verified_conversation_intent(
        "income_claim", "Is there a money-back guarantee?", "US", "en", "cid", runtime,
    )

    assert runtime.calls == 1
    assert intent == ("knowledge", True)


def test_real_income_guarantee_still_skips_the_verifier_as_income() -> None:
    runtime = _VerifierRuntime()

    intent = providers._verified_conversation_intent(
        "income_claim", "Can you guarantee I will make money with the money-back guarantee?", "US", "en", "cid",
        runtime,
    )

    assert runtime.calls == 0
    assert intent == ("income_claim", False)
