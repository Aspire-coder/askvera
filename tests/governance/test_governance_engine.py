"""Unit tests for governance decision merging."""

from app.governance.engine import GovernanceEngine
from app.governance.models import GovernanceAction, GovernanceDecision
from app.risk.models import PolicyAction, RiskDecision, RiskIssue, RiskLevel


class FakeRegistry:
    def __init__(self, provider) -> None:
        self.provider = provider

    def get(self, name: str):
        return self.provider


class FakeProvider:
    name = "fake_guardrail"

    def __init__(self, decision: GovernanceDecision | None = None, exc: Exception | None = None) -> None:
        self.decision = decision or GovernanceDecision(
            allowed=True,
            action=GovernanceAction.ALLOW,
            provider=self.name,
            guardrail_action=GovernanceAction.ALLOW,
        )
        self.exc = exc
        self.called = False

    def evaluate(
        self,
        *,
        text: str,
        country: str,
        language: str,
        correlation_id: str,
        allow_claim_topics: bool = False,
        is_generated_answer: bool = False,
    ) -> GovernanceDecision:
        self.called = True
        self.allow_claim_topics = allow_claim_topics
        self.is_generated_answer = is_generated_answer
        if self.exc:
            raise self.exc
        return self.decision


class FakeRiskEngine:
    def __init__(self, decision: RiskDecision) -> None:
        self.decision = decision

    def evaluate(self, context):
        return self.decision


def _engine(risk_decision: RiskDecision, provider: FakeProvider) -> GovernanceEngine:
    return GovernanceEngine(registry=FakeRegistry(provider), default_provider=provider.name, risk=FakeRiskEngine(risk_decision))


def _risk_decision(level: RiskLevel = RiskLevel.LOW, action: PolicyAction = PolicyAction.ALLOW) -> RiskDecision:
    decision = RiskDecision()
    if action != PolicyAction.ALLOW:
        decision.add_issue(
            RiskIssue(
                code="TEST_RISK",
                message="Test risk.",
                level=level,
                action=action,
                source="test",
                policy="test_policy",
                policy_version="1",
            )
        )
    return decision


def test_allow_claim_topics_is_forwarded_to_the_provider() -> None:
    """The output-guardrail exemption must reach the provider, defaulting off."""
    provider = FakeProvider()
    _engine(_risk_decision(), provider).evaluate(
        text="hello", country="US", language="en", correlation_id="cid"
    )
    assert provider.allow_claim_topics is False

    provider = FakeProvider()
    _engine(_risk_decision(), provider).evaluate(
        text="hello", country="US", language="en", correlation_id="cid", allow_claim_topics=True
    )
    assert provider.allow_claim_topics is True


def test_allow_claim_topics_does_not_bypass_a_refusing_risk_policy() -> None:
    """Risk policies run before the provider and are unaffected by the exemption."""
    provider = FakeProvider()
    decision = _engine(_risk_decision(RiskLevel.HIGH, PolicyAction.REFUSE), provider).evaluate(
        text="guaranteed income", country="US", language="en",
        correlation_id="cid", allow_claim_topics=True,
    )
    assert decision.allowed is False
    assert provider.called is False


def test_governance_allows_when_risk_and_guardrails_allow() -> None:
    decision = _engine(_risk_decision(), FakeProvider()).evaluate(
        text="hello", country="US", language="en", correlation_id="cid"
    )

    assert decision.allowed is True
    assert decision.action == GovernanceAction.ALLOW
    assert decision.risk_level == RiskLevel.LOW
    assert decision.guardrail_action == GovernanceAction.ALLOW


def test_governance_blocks_when_guardrails_block() -> None:
    provider = FakeProvider(
        GovernanceDecision(
            allowed=False,
            action=GovernanceAction.BLOCK,
            provider="fake_guardrail",
            reason="Blocked by guardrail.",
            guardrail_action=GovernanceAction.BLOCK,
        )
    )
    decision = _engine(_risk_decision(), provider).evaluate(
        text="blocked", country="US", language="en", correlation_id="cid"
    )

    assert decision.allowed is False
    assert decision.action == GovernanceAction.BLOCK
    assert decision.reason == "Blocked by guardrail."


def test_governance_allows_warn_risk_when_guardrails_allow() -> None:
    decision = _engine(_risk_decision(RiskLevel.HIGH, PolicyAction.WARN), FakeProvider()).evaluate(
        text="high risk", country="US", language="en", correlation_id="cid"
    )

    assert decision.allowed is True
    assert decision.action == GovernanceAction.ALLOW
    assert decision.risk_level == RiskLevel.HIGH
    assert decision.risk_action == PolicyAction.WARN


def test_governance_blocks_escalated_risk_even_when_guardrails_allow() -> None:
    decision = _engine(_risk_decision(RiskLevel.HIGH, PolicyAction.ESCALATE), FakeProvider()).evaluate(
        text="high risk", country="US", language="en", correlation_id="cid"
    )

    assert decision.allowed is False
    assert decision.action == GovernanceAction.BLOCK
    assert decision.risk_level == RiskLevel.HIGH
    assert decision.risk_action == PolicyAction.ESCALATE


def test_governance_short_circuits_critical_risk() -> None:
    provider = FakeProvider()
    decision = _engine(_risk_decision(RiskLevel.CRITICAL, PolicyAction.REFUSE), provider).evaluate(
        text="critical", country="US", language="en", correlation_id="cid"
    )

    assert provider.called is False
    assert decision.allowed is False
    assert decision.action == GovernanceAction.BLOCK
    assert decision.metadata["guardrailSkipped"] is True


def test_governance_metadata_includes_risk_summary() -> None:
    decision = _engine(_risk_decision(RiskLevel.HIGH, PolicyAction.WARN), FakeProvider()).evaluate(
        text="high risk", country="US", language="en", correlation_id="cid"
    )

    assert decision.metadata["risk"]["highestRisk"] == "HIGH"
    assert decision.metadata["risk"]["action"] == "WARN"
    assert decision.metadata["risk"]["issueCount"] == 1


def test_governance_blocks_provider_failure() -> None:
    decision = _engine(_risk_decision(), FakeProvider(exc=RuntimeError("boom"))).evaluate(
        text="hello", country="US", language="en", correlation_id="cid"
    )

    assert decision.allowed is False
    assert decision.action == GovernanceAction.BLOCK
    assert decision.metadata["providerError"] == "RuntimeError"


def test_is_generated_answer_is_forwarded_to_the_provider() -> None:
    """Negation-aware guardrailing must reach the provider, defaulting off.

    It relaxes the denied-phrase check so an answer stating there is no
    guaranteed income is not read as claiming one. That relaxation is only
    sound for text this system generated, so the default has to be off and the
    flag has to arrive where it is used.
    """
    provider = FakeProvider()
    _engine(_risk_decision(), provider).evaluate(
        text="hello", country="US", language="en", correlation_id="cid"
    )
    assert provider.is_generated_answer is False

    provider = FakeProvider()
    _engine(_risk_decision(), provider).evaluate(
        text="hello", country="US", language="en", correlation_id="cid", is_generated_answer=True
    )
    assert provider.is_generated_answer is True
