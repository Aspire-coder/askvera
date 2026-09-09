"""Reject an answer that tells the reader what their own record says."""

from app.validation.models import (
    ValidationContext,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)
from utils.personal_claims import unsupported_personal_claims


class PersonalHistoryValidator:
    """Fail closed on claims about this reader that nothing could support.

    The pipeline holds a market, a language and a declared role. It holds no
    purchase history, no rank and no record of what anyone has already done, so
    a sentence asserting one of those is invented however confidently it reads.

    Critical, like an ungrounded figure, because the orchestrator's repair path
    only runs for critical findings: the sentence is removed, the answer is
    revalidated, and the rest of it survives. An answer that cannot be repaired
    is refused, which is the right outcome for an answer whose subject is a
    record we do not have.
    """

    name = "personal_history"

    def validate(self, context: ValidationContext, result: ValidationResult) -> None:
        claims = unsupported_personal_claims(context.chat_response.answer or "")
        if not claims:
            return
        result.add_issue(
            ValidationIssue(
                code="PERSONAL_HISTORY_UNSUPPORTED",
                message=(
                    "Chat response asserts the reader's own history or status, "
                    f"which no source or session provides ({len(claims)} sentence(s))."
                ),
                severity=ValidationSeverity.CRITICAL,
                field="answer",
            )
        )
