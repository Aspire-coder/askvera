from types import SimpleNamespace

from app.validation.validators.numeric_grounding_validator import unsupported_numeric_claims


SOURCE = "• Minimum order size FBO: First order requirements is US$100 +3% VAT +3% Handling charge."


def _document():
    return SimpleNamespace(content=SOURCE, title="Ghana", id="ghana", metadata={})


def test_full_fbo_role_preserves_supported_figure() -> None:
    answer = "As a Forever Business Owner in Ghana, your first order must be US$100, plus 3% VAT."
    assert unsupported_numeric_claims(answer, [_document()]) == []


def test_wrong_currency_stays_unsupported() -> None:
    answer = "As a Forever Business Owner in Ghana, your first order must be 100 EUR."
    assert any(claim.text == "100" for claim in unsupported_numeric_claims(answer, [_document()]))


def test_later_customer_label_does_not_detach_fbo_figure() -> None:
    """A later role in one directory bullet belongs to its own rule, not €81."""
    document = SimpleNamespace(
        content=(
            "Minimum order size FBO: €81. "
            "Preferred Customers have no minimum order size."
        ),
        title="International-Sponsoring-Directory.pdf - Forever Benin",
        id="benin",
        metadata={},
    )

    answer = "For a Forever Business Owner in Benin, the minimum order is €81."

    assert unsupported_numeric_claims(answer, [document]) == []


def test_later_customer_label_does_not_approve_fbo_figure_for_customer() -> None:
    """The role binding remains directional: FBO's amount is not a customer rule."""
    document = SimpleNamespace(
        content=(
            "Minimum order size FBO: €81. "
            "Minimum order size Preferred Customer: €50."
        ),
        title="International-Sponsoring-Directory.pdf - Forever Benin",
        id="benin",
        metadata={},
    )

    # Lower-case role wording leaves no capitalized subject token set, so the
    # ordinary lexical-overlap fallback would approve this without the explicit
    # role-label guard.
    answer = "The preferred customer minimum order in Benin is €81."

    assert any(claim.text == "81" for claim in unsupported_numeric_claims(answer, [document]))
