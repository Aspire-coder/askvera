from types import SimpleNamespace

import pytest

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


def test_semicolon_customer_clause_does_not_detach_fbo_figure() -> None:
    """A semicolon ends the FBO rule; the customer wording after it is a separate rule."""
    document = SimpleNamespace(
        content="Minimum order size FBO: €81; Preferred Customers have no minimum",
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


def test_customer_prose_does_not_approve_fbo_figure_for_customer() -> None:
    """Benin in prose: a separate sentence about customers does not free the FBO €81."""
    document = SimpleNamespace(
        content=(
            "Minimum order size FBO: €81. "
            "Preferred Customers have no minimum order size."
        ),
        title="International-Sponsoring-Directory.pdf - Forever Benin",
        id="benin",
        metadata={},
    )

    answer = "The preferred customer minimum order in Benin is €81."

    assert any(claim.text == "81" for claim in unsupported_numeric_claims(answer, [document]))


# Verbatim corpus text, as in test_numeric_notation_coverage.py. The heading
# "Minimum order size FBO:" precedes every figure, but the clause after 0,200CC
# gives it to Preferred Customers, and 5 000 DZD ($43) is for all FBOs.
ALGERIA_SPONSORING = (
    "Welcome to Forever Algeria! Minimum order size FBO: 0,200CC as a first order for Preferred "
    "Customers, 7 800DZD ($60) and the equivalent of 5 000 DZD ($43) after the first purchase for "
    "all FBOs. Delivery Cost: 900 DZD ($7.5)."
)


def _algeria():
    return SimpleNamespace(
        content=ALGERIA_SPONSORING,
        title="International-Sponsoring-Directory.pdf - Forever Algeria",
        id="algeria",
        metadata={},
    )


def _unsupported(answer: str) -> list[str]:
    return [claim.text for claim in unsupported_numeric_claims(answer, [_algeria()])]


@pytest.mark.parametrize("figure", ["0,200CC", "0.200 CC"])
def test_heading_label_does_not_override_the_role_the_clause_names(figure: str) -> None:
    """Regression: "FBO:" is a heading here, so a customer answer keeps its own 0,200CC."""
    answer = f"As a new Preferred Customer in Algeria, your first order must be {figure}."

    assert _unsupported(answer) == []


@pytest.mark.parametrize("figure, number", [("0,200CC", "0,200"), ("0.200 CC", "0.200")])
def test_fbo_cannot_borrow_the_customer_figure_under_an_fbo_heading(figure: str, number: str) -> None:
    """The same heading must not hand the Preferred Customer figure to an FBO."""
    answer = f"As a new Forever Business Owner in Algeria, your first order must be {figure}."

    assert number in _unsupported(answer)


def test_fbo_figure_after_a_customer_clause_stays_supported() -> None:
    answer = (
        "As an existing Forever Business Owner in Algeria, your minimum order is the equivalent of "
        "5,000 DZD ($43) after your first purchase."
    )

    assert _unsupported(answer) == []
