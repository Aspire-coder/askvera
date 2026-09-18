"""D1: a contact recommendation must use the right contact TYPE and the right
COUNTRY, preserve digits exactly, and never invent one.

These pin already-mature behaviour in utils/directory_fields.py and
app/response/quality.py rather than fix a defect: reproducing through the
real functions (no fakes) turned up no invented contact and no order-phone/
customer-care mix-up, so no code change was made for these cases. Negative
controls below prove a mix-up or a fabricated number would actually be
caught (regression guard), rather than the assertions trivially passing.

Label: deterministic/local proof. No model, no fakes, no monkeypatching -
these call the real functions directly with real config fixtures
(config/public_contacts.json via contact_for_country) and assert on their
actual return values.
"""

from __future__ import annotations

from app.response.quality import contact_for_country, remove_or_replace_contact_placeholders
from utils.directory_fields import build_support_contact_supplement


def test_order_phone_is_never_chosen_over_office_phone_for_the_supplement() -> None:
    """A record with both an office phone and an order phone must surface only
    the office phone in the customer-care supplement - an order line is a
    different contact type and must not be presented as customer care."""
    approved_fields = {
        "Telephone Office": "+254 20 1234567",
        "Telephone for Orders": "+254 20 7654321",
    }
    result = build_support_contact_supplement(
        "I couldn't find enough detail; please reach out to customer support.",
        approved_fields,
        recommends_customer_care=True,
    )
    assert result is not None
    block, _labels = result
    assert "+254 20 1234567" in block
    assert "+254 20 7654321" not in block


def test_email_and_website_can_join_the_phone_without_duplicating_kind() -> None:
    approved_fields = {
        "Telephone Office": "+254 20 1234567",
        "Email": "kenya@foreverliving.com",
    }
    result = build_support_contact_supplement(
        "Please contact customer support for the exact figure.",
        approved_fields,
        recommends_customer_care=True,
    )
    assert result is not None
    block, labels = result
    assert "+254 20 1234567" in block
    assert "kenya@foreverliving.com" in block
    assert len(labels) == 2


def test_no_approved_fields_never_fabricates_a_contact() -> None:
    result = build_support_contact_supplement(
        "Please contact customer support for the exact figure.",
        {},
        recommends_customer_care=True,
    )
    assert result is None


def test_answer_without_a_care_recommendation_gets_no_supplement_even_with_fields() -> None:
    approved_fields = {"Telephone Office": "+254 20 1234567"}
    result = build_support_contact_supplement(
        "The minimum order for an active FBO is $200 per quarter.",
        approved_fields,
        recommends_customer_care=False,
    )
    assert result is None


def test_country_without_a_configured_phone_gets_the_placeholder_line_removed_not_a_borrowed_number() -> None:
    """Only US carries a reviewed customerCarePhone in config/public_contacts.json.
    A market with none must have the [PHONE] line dropped cleanly, never
    filled in with the US number or any other market's number."""
    us_contacts = contact_for_country("US")
    assert us_contacts.get("customerCarePhone") == "1-888-440-ALOE (2563)"

    unconfigured_contacts = contact_for_country("KE")
    assert "customerCarePhone" not in unconfigured_contacts

    answer = "I couldn't find enough detail.\n\nYou can also reach Forever Living Customer Care at [PHONE]."
    resolved, changes = remove_or_replace_contact_placeholders(answer, "KE")
    assert "[PHONE]" not in resolved
    assert "1-888-440-ALOE" not in resolved
    assert "phone_line_removed" in changes


def test_country_with_a_configured_phone_gets_its_own_exact_number() -> None:
    answer = "I couldn't find enough detail.\n\nYou can also reach Forever Living Customer Care at [PHONE]."
    resolved, changes = remove_or_replace_contact_placeholders(answer, "US")
    assert "1-888-440-ALOE (2563)" in resolved
    assert "phone_replaced" in changes
