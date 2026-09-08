"""Tests for generic structured directory response completion."""

from utils.directory_fields import (
    parse_directory_fields,
    preserve_directory_role_labels,
    correct_directory_source_contradictions,
    remove_unrequested_directory_fields,
    restore_missing_requested_order_size,
    restore_missing_directory_contacts,
    restore_missing_requested_directory_fields,
)


def test_parses_same_line_directory_fields_from_pdf_layout() -> None:
    content = """Welcome to Forever Cameroon!
    Forever Living Products Cameroon S.A.R.L.
    Business Hours Office 08.30 am - 17.30 pm (Mon - Fri)
    Business Hours Product Centre 08.30 am - 17.30 pm (Mon - Fri)
    Telephone Office +237 233 472 448
    Telephone for Orders (see above)
    Email info@example.test
    Website www.example.test
    """

    fields = parse_directory_fields(content)

    assert fields["Business Hours Office"] == "08.30 am - 17.30 pm (Mon - Fri)"
    assert fields["Business Hours Product Centre"] == "08.30 am - 17.30 pm (Mon - Fri)"
    assert fields["Telephone Office"] == "+237 233 472 448"
    assert fields["Telephone for Orders"] == "(see above)"
    assert fields["Email"] == "info@example.test"


def test_parses_sponsoring_directory_record_fields_without_country_metadata() -> None:
    content = """Welcome to Forever Kenya/East Africa!
    General Information
    Business Hours Office
    09:00 - 17:00 (Mon - Fri)
    10:00 - 14:00 (Sat)
    Telephone Office
    +254 712 434 328
    """

    fields = parse_directory_fields(content)

    assert fields["Business Hours Office"] == "09:00 - 17:00 (Mon - Fri) 10:00 - 14:00 (Sat)"
    assert fields["Telephone Office"] == "+254 712 434 328"


def test_parses_multiline_directory_fields_without_mixing_next_label() -> None:
    content = """Example market
    Address
    10 Example Road
    Capital City
    Business Hours Office 09.00 am - 17.00 pm
    """

    fields = parse_directory_fields(content)

    assert fields["Address"] == "10 Example Road Capital City"
    assert fields["Business Hours Office"] == "09.00 am - 17.00 pm"


def test_restores_exact_missing_contact_fields_for_any_country() -> None:
    answer = "Voici le bureau approuve.\n\n**Office Email:** support@example.test"
    fields = {
        "Country": "Exampleland",
        "Office Address": "10 Example Road, Capital City",
        "Office Phone 1": "+99 123 456 7890",
        "Office Email": "support@example.test",
    }

    completed, restored = restore_missing_directory_contacts(answer, [fields])

    assert "Office Address: 10 Example Road, Capital City" in completed
    assert "Office Phone 1: +99 123 456 7890" in completed
    assert completed.count("support@example.test") == 1
    assert restored == ["Office Address", "Office Phone 1"]


def test_does_not_duplicate_reformatted_phone_number() -> None:
    answer = "Telephone: +99 (123) 456-7890"
    fields = {"Office Phone": "+99 123 456 7890"}

    completed, restored = restore_missing_directory_contacts(answer, [fields])

    assert completed == answer
    assert restored == []


def test_does_not_append_a_see_above_cross_reference_as_a_standalone_answer() -> None:
    """A print-layout cross reference ("(see above)") means something on a
    printed page but is meaningless as an isolated bullet in a chat answer -
    live example: Chile's answer ended with "Telephone for Orders: (see
    above)" and nothing for it to visibly refer to."""
    answer = "Contact Forever Chile for support:\n- Phone: +56 9 44727070"
    fields = {
        "Phone": "+56 9 44727070",
        "Telephone for Orders": "(see above)",
    }

    completed, restored = restore_missing_directory_contacts(answer, [fields])

    assert "see above" not in completed.lower()
    assert "Telephone for Orders" not in restored


def test_does_not_correct_a_labeled_line_into_a_see_above_reference() -> None:
    answer = "Telephone for Orders: +56 9 00000000"
    fields = {"Telephone for Orders": "(see above)"}

    completed, restored = restore_missing_directory_contacts(answer, [fields])

    assert completed == answer
    assert restored == []


def test_ignores_non_contact_directory_metadata() -> None:
    answer = "The office is in Exampleland."
    fields = {"Country": "Exampleland", "Main Admin. Title": "Director"}

    completed, restored = restore_missing_directory_contacts(answer, [fields])

    assert completed == answer
    assert restored == []


def test_does_not_append_contacts_to_a_no_match_answer() -> None:
    answer = "I don't have information about Dejan in the approved directory."
    fields = {
        "Country": "Exampleland",
        "Office Phone": "+99 123 456 7890",
        "Office Email": "other@example.test",
    }

    completed, restored = restore_missing_directory_contacts(answer, [fields])

    assert completed == answer
    assert restored == []


def test_corrects_a_mangled_phone_number_in_place_instead_of_duplicating() -> None:
    answer = "Voici le bureau approuve.\n\nTelephone: +99 123 456 0000"
    fields = {"Telephone": "+99 123 456 7890"}

    completed, restored = restore_missing_directory_contacts(answer, [fields])

    assert "+99 123 456 7890" in completed
    assert "+99 123 456 0000" not in completed
    assert completed.count("Telephone:") == 1
    assert restored == ["Telephone"]


def test_corrects_a_placeholder_value_the_model_wrote_instead_of_the_real_one() -> None:
    answer = "Office Email: not available"
    fields = {"Office Email": "support@example.test"}

    completed, restored = restore_missing_directory_contacts(answer, [fields])

    assert completed == "Office Email: support@example.test"
    assert restored == ["Office Email"]


def test_corrects_markdown_bold_labeled_line_without_breaking_formatting() -> None:
    answer = "**Office Phone:** +99 000 000 0000"
    fields = {"Office Phone": "+99 123 456 7890"}

    completed, restored = restore_missing_directory_contacts(answer, [fields])

    assert completed == "**Office Phone:** +99 123 456 7890"
    assert restored == ["Office Phone"]


def test_never_mixes_contacts_from_secondary_directory_records() -> None:
    answer = "Italy office\nAddress: Via Example 10, Rome"
    italy = {
        "Address": "Via Example 10, Rome",
        "Office Phone": "+39 06 1234 5678",
    }
    mexico = {
        "Office Phone": "+52 55 3300 9400",
        "General Mailbox": "support-mx@example.test",
    }

    completed, restored = restore_missing_directory_contacts(answer, [italy, mexico])

    assert "Office Phone: +39 06 1234 5678" in completed
    assert "+52 55 3300 9400" not in completed
    assert "support-mx@example.test" not in completed
    assert restored == ["Office Phone"]


def test_restores_requested_business_hours_when_model_leaves_value_blank() -> None:
    answer = "Here are the business hours for the Kenya office.\n\nOffice Hours:"
    fields = {
        "Country": "Kenya",
        "Business Hours Office": "09:00 - 17:00 (Mon - Fri); 10:00 - 14:00 (Sat)",
        "Telephone Office": "+254 712 434 328",
    }

    completed, restored = restore_missing_requested_directory_fields(
        answer,
        [fields],
        "what are the business hours for Kenya",
    )

    assert "Business Hours Office: 09:00 - 17:00 (Mon - Fri); 10:00 - 14:00 (Sat)" in completed
    assert restored == ["Business Hours Office"]


def test_preserves_fbo_minimum_order_label_when_answer_shortens_it() -> None:
    answer = "The minimum order size is $100 worth of products when joining."
    source = "Minimum order size FBO: $100 worth of products when joining."

    corrected, changed = preserve_directory_role_labels(answer, [source])

    assert corrected == "The FBO minimum order size is $100 worth of products when joining."
    assert changed is True


def test_removes_unrequested_directory_fields_from_phone_answer() -> None:
    answer = (
        "The office telephone is +223 44 90 05 41.\n"
        "Telephone for Orders: (see above) Email: contact@example.test\n"
        "Website: www.example.com"
    )

    focused, changed = remove_unrequested_directory_fields(
        answer,
        "what is the telephone number for Mali",
    )

    assert focused == "The office telephone is +223 44 90 05 41."
    assert changed is True


def test_corrects_directory_values_that_contradict_explicit_source() -> None:
    answer = (
        "For Morocco, the minimum order is 0.200 CC (approximately 600 MAD).\n\n"
        "After sponsorship: 500 DH minimum."
    )
    source = (
        "Minimum order size FBO: sponsorship, the first order must be equal or greater than "
        "0.200 CC (around 750 MAD). After sponsorship: we don't have a minimum order."
    )

    corrected, changed = correct_directory_source_contradictions(answer, [source])

    assert "approximately 750 MAD" in corrected
    assert "After sponsorship: there is no minimum order." in corrected
    assert "600 MAD" not in corrected
    assert "500 DH minimum" not in corrected
    assert changed is True


def test_restores_minimum_order_size_when_model_answers_nearby_faq() -> None:
    answer = "Payment methods accepted are Bank Transfer, Cash, and there is no delivery charge."
    source = "Minimum order size FBO: €81. Payment methods accepted: Bank Transfer, Cash."

    corrected, changed = restore_missing_requested_order_size(
        answer,
        [source],
        "what is the minimum ordering size for Niger",
    )

    assert "Minimum order size FBO: €81." in corrected
    assert changed is True


def test_focus_minimum_order_answer_removes_payment_and_delivery_claims() -> None:
    answer = "Payment methods accepted are Bank Transfer, Cash, and there is no delivery charge."

    focused, changed = remove_unrequested_directory_fields(
        answer,
        "what is the minimum order size for Niger",
    )

    assert focused == ""
    assert changed is True


def test_does_not_append_record_prose_as_a_minimum_order_value() -> None:
    """The value capture runs to the next period, and can run into prose.

    Appending that prose as a sentence ends the answer mid-phrase. The output
    validator then discards the entire answer as structurally incomplete and
    the reader is told the approved documents do not cover their question -
    which is how a correct Algeria answer became a refusal.
    """
    answer = "A new FBO in Algeria places a first order through the local office."
    source = (
        "Minimum order size FBO: 0,200CC (7 800DZD) and all first orders must be "
        "placed with the sponsoring office named in the"
    )

    corrected, changed = restore_missing_requested_order_size(
        answer,
        [source],
        "What is the minimum first order size for a new FBO in Algeria?",
    )

    assert changed is False
    assert corrected == answer
    assert not corrected.rstrip().endswith("the.")


def test_still_restores_an_ordinary_short_order_value() -> None:
    """The bound must not stop the restoration this function exists for."""
    answer = "Payment methods accepted are Bank Transfer and Cash."
    source = "Minimum order size FBO: 0,200CC (7 800DZD). Payment methods accepted: Cash."

    corrected, changed = restore_missing_requested_order_size(
        answer,
        [source],
        "what is the minimum order size for Algeria",
    )

    assert changed is True
    assert "Minimum order size FBO: 0,200CC (7 800DZD)." in corrected


def test_contacts_are_not_restored_into_an_answer_about_opening_hours() -> None:
    """Reported by the release gate on 2026-09-08, after a citation fix.

    Contact restoration is gated on the response having citations. Belgium's
    office-hours answer previously had none - the same citation bug seen on
    Algeria - so restoration never ran. Once citations were attached, an answer
    about opening hours gained a street address and a phone number, both
    verbatim from the record, and both then had to survive subject-aware
    grounding inside a sentence about hours. They did not: repair removed 16
    and 3743, took their sentences with them, and the canary rolled the deploy
    back.

    Restoration exists to correct a mangled contact value in an answer about
    contacts. Nothing asked for a phone number here.
    """
    fields = [{
        "Business Hours Office": "09.00 am - 17.00 pm (Mon - Fri)",
        "Telephone Office": "+32 2 3743 000",
        "Office & Product Center Address": "Bijenstraat 16",
    }]
    answer = "The office hours for the Forever Belgium office are 09.00 am - 17.00 pm (Mon - Fri)."

    corrected, restored = restore_missing_directory_contacts(
        answer, fields, "What are the office hours for the Forever Belgium office?"
    )

    assert restored == []
    assert corrected == answer
    assert "3743" not in corrected and "Bijenstraat" not in corrected


def test_contacts_are_still_restored_when_a_contact_was_asked_for() -> None:
    """The guard must not disable the correction this function exists for."""
    fields = [{"Telephone Office": "+32 2 3743 000"}]
    answer = "Telephone Office: +32 2 0000 000"

    corrected, restored = restore_missing_directory_contacts(
        answer, fields, "What is the telephone number for the Forever Belgium office?"
    )

    assert restored
    assert "+32 2 3743 000" in corrected


def test_a_question_asking_for_hours_and_an_address_still_restores() -> None:
    """Only a question naming no contact field at all skips restoration."""
    fields = [{"Office & Product Center Address": "Bijenstraat 16"}]
    answer = "Office & Product Center Address: Somewhere else"

    _corrected, restored = restore_missing_directory_contacts(
        answer, fields, "What is the office address and the opening hours?"
    )

    assert restored


# --- the France pilot defect, reproduced from the real record ---------------


FRANCE_RECORD_WRAP = (
    "Minimum order size FBO: We do not have a minimum order in France, yet a newly sponsored\n"
    "Preferred Customer will have to order 150\u20ac minimum of products within 72 hours in order "
    "to validate his\nsponsorship.\n"
)

ORDER_QUESTION = "What is the minimum order size for an FBO in France?"


def test_a_field_that_wraps_mid_sentence_is_not_appended_as_a_fragment() -> None:
    """The defect a reader actually received, on 2026-09-08.

    The capture stopped at the newline where the PDF wraps, so the answer was
    given "...yet a newly sponsored" with a period bolted on and delivered it.
    The value now runs to the end of the sentence, which makes it prose, which
    the length guard declines - so nothing is appended rather than half of it.
    """
    answer = "For an FBO in France, there is no minimum order requirement."

    restored, changed = restore_missing_requested_order_size(
        answer, [FRANCE_RECORD_WRAP], ORDER_QUESTION
    )

    assert changed is False
    assert restored == answer
    assert "yet a newly sponsored." not in restored


def test_the_old_truncation_point_is_no_longer_reachable() -> None:
    """Pinned to the exact fragment, so a regression is unmistakable."""
    restored, _ = restore_missing_requested_order_size(
        "An answer.", [FRANCE_RECORD_WRAP], ORDER_QUESTION
    )

    assert not restored.rstrip().endswith("yet a newly sponsored.")


def test_a_short_field_that_wraps_is_restored_whole() -> None:
    """Preserving the field across line breaks, not merely refusing more often.

    A wrapped value that is genuinely a value still gets restored, joined into
    one line.
    """
    wrapped = "Minimum order size FBO: 2 CC per\norder for all FBOs."

    restored, changed = restore_missing_requested_order_size(
        "An answer.", [wrapped], ORDER_QUESTION
    )

    assert changed is True
    assert restored.endswith("Minimum order size FBO: 2 CC per order for all FBOs.")


def test_a_short_single_line_field_still_restores() -> None:
    """The behaviour this function exists for must survive the fix."""
    restored, changed = restore_missing_requested_order_size(
        "An answer.", ["Minimum order size FBO: 0,200CC (7 800DZD)."], ORDER_QUESTION
    )

    assert changed is True
    assert restored.endswith("Minimum order size FBO: 0,200CC (7 800DZD).")


def test_a_prose_field_is_declined_rather_than_truncated() -> None:
    """Algeria writes this field as a sentence too, and gets the same treatment."""
    algeria = (
        "Minimum order size FBO: 0,200CC as a first order for Preferred Customers, "
        "7 800DZD ($60) and the equivalent of 5 000 DZD ($43) after the first purchase "
        "for all FBOs.\n"
    )

    _, changed = restore_missing_requested_order_size("An answer.", [algeria], ORDER_QUESTION)

    assert changed is False


# --- where a field value ends ----------------------------------------------
#
# "Stop at the sentence end" is only safe if it knows what a sentence end is.
# A first attempt stopped at the first period of any kind, which truncated
# inside the number it was restoring - worse than the newline bug it replaced.


def _restored_tail(source: str) -> str:
    restored, changed = restore_missing_requested_order_size(
        "An answer.", [source], ORDER_QUESTION
    )
    assert changed is True
    return restored[len("An answer."):].strip()


def test_a_decimal_point_does_not_end_the_field() -> None:
    """The regression this check exists for: truncating inside 1.612."""
    assert _restored_tail("Minimum order size FBO: 1.612CC per order.").endswith(
        "Minimum order size FBO: 1.612CC per order."
    )


def test_an_abbreviation_does_not_end_the_field() -> None:
    assert _restored_tail("Minimum order size FBO: 2 CC (Ref. 830) per order.").endswith(
        "Minimum order size FBO: 2 CC (Ref. 830) per order."
    )


def test_the_next_field_heading_ends_the_field() -> None:
    """A value must never run into the next bullet - that is a different field."""
    tail = _restored_tail("Minimum order size FBO: 2 CC\n\u2022 Grouped order possible?: No.")

    assert tail.endswith("Minimum order size FBO: 2 CC.")
    assert "Grouped order" not in tail


def test_a_sentence_end_ends_the_field() -> None:
    source = "Minimum order size FBO: 2 CC per order. The Preferred may order any products."

    tail = _restored_tail(source)

    assert tail.endswith("Minimum order size FBO: 2 CC per order.")
    assert "Preferred may order" not in tail


def test_a_thousands_separator_survives() -> None:
    assert _restored_tail("Minimum order size FBO: 1,612CC per order.").endswith("1,612CC per order.")


def test_the_field_value_helper_is_directly_exercised() -> None:
    """The boundary rule itself, without the surrounding restoration."""
    from utils.directory_fields import _directory_field_value

    assert _directory_field_value("1.612CC per order.") == "1.612CC per order"
    assert _directory_field_value("2 CC\n\u2022 Grouped order?: No.") == "2 CC"
    assert _directory_field_value("2 CC per\norder. Next sentence.") == "2 CC per order"
    assert _directory_field_value("2 CC (Ref. 830).") == "2 CC (Ref. 830)"
