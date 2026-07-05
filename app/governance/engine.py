"""Governance engine entry point."""

from time import perf_counter

from app.metrics import STAGE_GOVERNANCE
from app.metrics.pipeline import record_pipeline_metric
from app.risk import PolicyAction, RiskContext, RiskDecision, RiskEngine, risk_engine
from utils.logging import get_logger

from .models import GovernanceAction, GovernanceDecision
from .registry import GovernanceRegistry, governance_registry

LOGGER = get_logger("app.governance")


class GovernanceEngine:
    """Coordinate risk and guardrail decisions behind one governance API."""

    def __init__(
        self,
        registry: GovernanceRegistry | None = None,
        default_provider: str = "bedrock_guardrails",
        risk: RiskEngine | None = None,
    ) -> None:
        self.registry = registry or governance_registry
        self.default_provider = default_provider
        self.risk_engine = risk or risk_engine

    def evaluate(
        self,
        *,
        text: str,
        country: str,
        language: str,
        correlation_id: str,
        role: str = "new_prospect",
    ) -> GovernanceDecision:
        """Evaluate text through risk policies and guardrail provider."""
        started = perf_counter()
        success = False
        try:
            risk_decision = self.risk_engine.evaluate(
                RiskContext(
                    user_message=text,
                    country=country,
                    language=language,
                    role=role,
                    correlation_id=correlation_id,
                )
            )
            if risk_decision.should_refuse():
                decision = self._from_risk_refusal(risk_decision, correlation_id)
                self._log_decision(decision, correlation_id)
                success = True
                return decision

            provider = self.registry.get(self.default_provider)
            LOGGER.info(
                "governance_provider_selected",
                correlation_id=correlation_id,
                provider=provider.name,
                configured_provider=self.default_provider,
                country=country,
                language=language,
            )
            try:
                guardrail_decision = provider.evaluate(
                    text=text, country=country, language=language, correlation_id=correlation_id
                )
            except Exception as exc:
                LOGGER.exception(
                    "governance_provider_failed",
                    correlation_id=correlation_id,
                    provider=provider.name,
                    configured_provider=self.default_provider,
                )
                decision = GovernanceDecision(
                    allowed=False,
                    action=GovernanceAction.BLOCK,
                    provider=provider.name,
                    reason="Governance provider failed.",
                    risk_level=risk_decision.highest_risk,
                    risk_action=risk_decision.action,
                    guardrail_action=GovernanceAction.BLOCK,
                    metadata={
                        "risk": _risk_metadata(risk_decision),
                        "providerError": type(exc).__name__,
                    },
                )
                self._log_decision(decision, correlation_id)
                success = False
                return decision
            decision = self._merge_decisions(risk_decision, guardrail_decision)
            self._log_decision(decision, correlation_id)
            success = decision.allowed
            return decision
        finally:
            record_pipeline_metric(
                stage=STAGE_GOVERNANCE,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                success=success,
                correlation_id=correlation_id,
                metadata={"country": country, "language": language, "role": role},
            )

    def _from_risk_refusal(self, risk_decision: RiskDecision, correlation_id: str) -> GovernanceDecision:
        """Build a governance decision when risk refuses before guardrails run."""
        return GovernanceDecision(
            allowed=False,
            action=GovernanceAction.BLOCK,
            provider="risk_engine",
            reason="Request blocked by risk policy.",
            risk_level=risk_decision.highest_risk,
            risk_action=risk_decision.action,
            guardrail_action=GovernanceAction.ALLOW,
            metadata={
                "correlationId": correlation_id,
                "risk": _risk_metadata(risk_decision),
                "guardrailSkipped": True,
            },
        )

    def _merge_decisions(
        self, risk_decision: RiskDecision, guardrail_decision: GovernanceDecision
    ) -> GovernanceDecision:
        """Merge risk and guardrail outcomes into a single decision."""
        action = GovernanceAction.ALLOW
        allowed = True
        reason = guardrail_decision.reason
        if guardrail_decision.action == GovernanceAction.BLOCK:
            action = GovernanceAction.BLOCK
            allowed = False
        elif risk_decision.action in {PolicyAction.WARN, PolicyAction.ESCALATE}:
            action = GovernanceAction.BLOCK
            allowed = False
            reason = "Request blocked by high-risk policy."
        elif risk_decision.action == PolicyAction.REDACT:
            action = GovernanceAction.REVIEW

        return GovernanceDecision(
            allowed=allowed,
            action=action,
            provider=guardrail_decision.provider,
            reason=reason,
            risk_level=risk_decision.highest_risk,
            risk_action=risk_decision.action,
            guardrail_action=guardrail_decision.action,
            metadata={
                **guardrail_decision.metadata,
                "risk": _risk_metadata(risk_decision),
            },
        )

    def _log_decision(self, decision: GovernanceDecision, correlation_id: str) -> None:
        """Log the unified governance decision."""
        log = LOGGER.warning if not decision.allowed else LOGGER.info
        log(
            "governance_decision",
            correlation_id=correlation_id,
            provider=decision.provider,
            risk=decision.risk_level.value,
            risk_action=decision.risk_action.value,
            guardrail=decision.guardrail_action.value,
            final=decision.action.value,
            allowed=decision.allowed,
        )


def _risk_metadata(risk_decision: RiskDecision) -> dict:
    """Return audit-safe risk decision metadata."""
    return {
        "highestRisk": risk_decision.highest_risk.value,
        "action": risk_decision.action.value,
        "allowed": risk_decision.allowed,
        "issueCount": len(risk_decision.issues),
        "issues": [
            {
                "code": issue.code,
                "level": issue.level.value,
                "action": issue.action.value,
                "source": issue.source,
                "policy": issue.policy,
                "policyVersion": issue.policy_version,
            }
            for issue in risk_decision.issues
        ],
    }


governance_engine = GovernanceEngine()
