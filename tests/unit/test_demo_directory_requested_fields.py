"""B1: preserve every requested directory field.

Covers the fail-before scenarios in the implementation brief section "B." -
the old if/elif chain in `remove_unrequested_directory_fields` only ever
matched the first field named in a compound request (so "phone and email"
kept phone and silently dropped email), and
`restore_missing_requested_directory_fields` only ever restored business
hours despite its general name.
"""

from utils.directory_fields import (
    remove_unrequested_directory_fields,
    restore_missing_requested_directory_fields,
)


def test_phone_and_email_both_kept_unrelated_hours_removed() -> None:
    answer = (
        "Telephone Office: +254 712 434 328\n"
        "Email: info@example.test\n"
        "Business Hours Office: 09:00 - 17:00 (Mon - Fri)\n"
    )

    focused, changed = remove_unrequested_directory_fields(answer, "What is the phone and email for Kenya?")

    assert "Telephone Office: +254 712 434 328" in focused
    assert "Email: info@example.test" in focused
    assert "Business Hours Office" not in focused
    assert changed is True


def test_phone_and_email_reversed_order_gives_same_fields() -> None:
    answer = (
        "Telephone Office: +254 712 434 328\n"
        "Email: info@example.test\n"
        "Business Hours Office: 09:00 - 17:00 (Mon - Fri)\n"
    )

    focused, changed = remove_unrequested_directory_fields(answer, "What is the email and phone for Kenya?")

    assert "Telephone Office: +254 712 434 328" in focused
    assert "Email: info@example.test" in focused
    assert "Business Hours Office" not in focused
    assert changed is True


def test_office_phone_excludes_order_phone() -> None:
    answer = (
        "Telephone Office: +32 2 3743 000\n"
        "Telephone for Orders: +32 2 1234 567\n"
    )

    focused, changed = remove_unrequested_directory_fields(answer, "What is the office phone number for Belgium?")

    assert "+32 2 3743 000" in focused
    assert "+32 2 1234 567" not in focused
    assert changed is True


def test_office_and_order_phone_preserves_both() -> None:
    answer = (
        "Telephone Office: +32 2 3743 000\n"
        "Telephone for Orders: +32 2 1234 567\n"
    )

    focused, changed = remove_unrequested_directory_fields(
        answer, "What is the office and order phone number for Belgium?"
    )

    assert focused.strip() == answer.strip()
    assert changed is False


def test_italy_phone_number_question_not_replaced_by_hours() -> None:
    """Tracker row 22: an office-phone question must not end up stripping the
    phone and leaving only business hours, nor be misread as an hours
    question just because it mentions "office"."""
    answer = (
        "Telephone Office: +39 06 1234 5678\n"
        "Business Hours Office: 09:00 - 18:00 (Mon - Fri)\n"
    )

    focused, changed = remove_unrequested_directory_fields(
        answer, "What is the Italy office phone number?"
    )

    assert "+39 06 1234 5678" in focused
    assert "Business Hours Office" not in focused
    assert changed is True


def test_three_band_delivery_cost_fixture_keeps_all_bands_and_conditions() -> None:
    answer = (
        "Delivery Cost: Band A: under 0.5 CC costs 10 EUR. "
        "Band B: 0.5 CC to above 2 CC costs 5 EUR. "
        "Band C: above 2 CC is free, excluding VAT.\n"
        "Business Hours Office: 09:00 - 17:00 (Mon - Fri)\n"
    )

    focused, changed = remove_unrequested_directory_fields(answer, "What is the delivery cost?")

    assert "Band A: under 0.5 CC costs 10 EUR." in focused
    assert "Band B: 0.5 CC to above 2 CC costs 5 EUR." in focused
    assert "Band C: above 2 CC is free, excluding VAT." in focused
    assert "above 2 CC or more" not in focused
    assert "Business Hours Office" not in focused
    assert changed is True


def test_above_2_cc_and_excluding_vat_survive_unrelated_field_removal() -> None:
    answer = "Delivery Cost: above 2 CC is free, excluding VAT.\nEmail: info@example.test\n"

    focused, changed = remove_unrequested_directory_fields(answer, "What is the delivery cost?")

    assert "above 2 CC is free, excluding VAT." in focused
    assert "2 CC or more" not in focused
    assert "Email" not in focused
    assert changed is True


def test_unconfident_request_does_not_strip_anything() -> None:
    answer = "Telephone Office: +254 712 434 328\nBusiness Hours Office: 09:00 - 17:00 (Mon - Fri)\n"

    focused, changed = remove_unrequested_directory_fields(answer, "Tell me about Kenya.")

    assert focused == answer
    assert changed is False


def test_restores_two_requested_fields_from_primary_record() -> None:
    answer = "Here is the Kenya office information."
    fields = {
        "Country": "Kenya",
        "Telephone Office": "+254 712 434 328",
        "Email": "info@forever-kenya.example",
    }

    completed, restored = restore_missing_requested_directory_fields(
        answer, [fields], "What is the phone and email for Kenya?"
    )

    assert "Telephone Office: +254 712 434 328" in completed
    assert "Email: info@forever-kenya.example" in completed
    assert set(restored) == {"Telephone Office", "Email"}


def test_two_requested_fields_with_one_unknown_returns_only_the_known_value() -> None:
    answer = "Here is what we have on file."
    fields = {
        "Country": "Kenya",
        "Telephone Office": "+254 712 434 328",
        # No Email field in this record at all.
    }

    completed, restored = restore_missing_requested_directory_fields(
        answer, [fields], "What is the phone and email for Kenya?"
    )

    assert "Telephone Office: +254 712 434 328" in completed
    assert restored == ["Telephone Office"]
    assert "Email" not in completed


def test_wrong_country_adjacent_record_never_restored_even_with_matching_label() -> None:
    answer = "Here is the Italy office information."
    italy = {"Country": "Italy"}  # no phone on file for Italy
    mexico = {"Telephone Office": "+52 55 3300 9400"}  # same label, wrong country

    completed, restored = restore_missing_requested_directory_fields(
        answer, [italy, mexico], "What is the phone number for the Italy office?"
    )

    assert completed == answer
    assert restored == []
    assert "+52 55 3300 9400" not in completed


def test_restores_multiline_delivery_cost_value_without_truncating_at_a_period() -> None:
    """A multi-line/multi-band shipping schedule must not be cut at a
    decimal point or an abbreviation period, and must not have the
    order-size 80-character cutoff applied to it."""
    answer = "Here is the shipping information."
    fields = {
        "Delivery Cost": (
            "Band A: under 0.5 CC costs 10.50 EUR. Band B: above 2 CC is free, "
            "excluding VAT. Contact the office e.g. for large orders."
        ),
    }

    completed, restored = restore_missing_requested_directory_fields(
        answer, [fields], "What is the delivery cost?"
    )

    assert fields["Delivery Cost"] in completed
    assert restored == ["Delivery Cost"]


def test_all_contact_details_request_is_unaffected_by_new_field_set_logic() -> None:
    answer = "Telephone Office: +254 712 434 328\nEmail: info@example.test\n"

    focused, changed = remove_unrequested_directory_fields(answer, "Please give me all contact details for Kenya.")

    assert focused == answer
    assert changed is False
