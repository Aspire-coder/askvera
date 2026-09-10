from app.validation.validators.numeric_grounding_validator import _drop_orphaned_lead_ins


def test_bold_heading_keeps_the_preceding_france_direct_answer() -> None:
    answer = (
        "There is no minimum order requirement for FBOs in France. "
        "However, there is an important distinction:\n\n"
        "**For Newly Sponsored Preferred Customers:**\n"
        "A newly sponsored Preferred Customer must place an order."
    )

    assert "no minimum order requirement for FBOs in France" in _drop_orphaned_lead_ins(answer)
    assert "important distinction:" in _drop_orphaned_lead_ins(answer)


def test_genuinely_orphaned_lead_in_is_still_removed() -> None:
    answer = "For Sweden, the delivery costs are:\n\nThe average lead time is 4-7 days."

    repaired = _drop_orphaned_lead_ins(answer)

    assert "delivery costs are:" not in repaired
    assert "average lead time" in repaired
