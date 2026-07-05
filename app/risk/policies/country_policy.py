"""Country support risk policy."""

from app.risk.models import RiskContext, RiskIssue, RiskLevel
from app.risk.rules import RiskPolicyMetadata
from services.market_config import get_country_codes


class CountryPolicy:
    """Flag unsupported markets before retrieval."""

    metadata = RiskPolicyMetadata(
        name="country_support",
        version="2026.1",
        description="Detects requests for unsupported country or market codes.",
        enabled=True,
        risk_level=RiskLevel.CRITICAL,
    )

    def evaluate(self, context: RiskContext) -> list[RiskIssue]:
        country = (context.country or "").upper()
        if country in get_country_codes():
            return []
        return [
            RiskIssue(
                code="UNSUPPORTED_COUNTRY",
                message="Requested country is not configured as a supported market.",
                level=RiskLevel.CRITICAL,
                source="input",
                policy=self.metadata.name,
                policy_version=self.metadata.version,
            )
        ]
