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
