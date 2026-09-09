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

    The pipeline holds a market, a language, a declared role, and whatever the
    reader has said about themselves. It holds no purchase history, no rank and
    no record of what anyone has already done, so a sentence asserting one of
    those is invented however confidently it reads.

    Which category the answer may place the reader in depends on that context
    rather than on the wording: "As an existing FBO" is supported by an
    active_distributor session and is an assumption without one, and "As a
    Preferred Customer" is an assumption unless the reader said so.

    Critical, like an ungrounded figure, because the orchestrator's repair path
    only runs for critical findings: the sentence is removed, the answer is
    revalidated, and the rest of it survives. An answer that cannot be repaired
    is refused, which is the right outcome for an answer whose subject is a
    record we do not have.
    """

    name = "personal_history"

    def validate(self, context: ValidationContext, result: ValidationResult) -> None:
        claims = unsupported_personal_claims(
            context.chat_response.answer or "",
            role=context.role,
            user_context=context.user_context,
        )
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
