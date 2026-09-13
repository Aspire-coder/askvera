"""Field cleanup removes unrequested labelled lines, never prose facts.

`remove_unrequested_directory_fields` runs on every answer, not only directory
answers. A sentence-level prose pass added during demo work deleted text from
the keyword to the next period: "Returns are free, but the delivery cost is not
refunded." became "Returns are free, but.", a policy sentence about refunds was
removed for an address question, and "Business hours are 09.00 am ..." was cut
at "09." into "00 am to 19.00 pm". Arm A removed only "Label: value" lines, and
that is the behaviour kept here.
"""

from utils.directory_fields import remove_unrequested_directory_fields


def test_policy_sentence_mentioning_delivery_cost_survives_an_email_question():
    answer = ("Returns are accepted within 30 days. Returns are free, but the delivery cost is not refunded. "
              "Email returns@example.com.")

    cleaned, _changed = remove_unrequested_directory_fields(answer, "What is the email address for returns?")

    assert "Returns are free, but the delivery cost is not refunded." in cleaned


def test_policy_sentence_about_charges_survives_an_address_question():
    answer = ("You can change the address before dispatch. Business hours for changes are Monday to Friday, "
              "and the delivery charge is refunded if cancelled.")

    cleaned, _changed = remove_unrequested_directory_fields(answer, "Can I change my delivery address after ordering?")

    assert "the delivery charge is refunded if cancelled." in cleaned


def test_prose_hours_with_a_decimal_time_are_never_cut_mid_value():
    answer = "The Kenya office phone is +254 20 2026869. Business hours are 09.00 am to 19.00 pm Monday to Friday."

    cleaned, _changed = remove_unrequested_directory_fields(answer, "What is the Kenya office phone number?")

    assert "00 am to 19.00 pm" not in cleaned.replace("09.00 am to 19.00 pm", "")
    assert "+254 20 2026869" in cleaned


def test_unrequested_labelled_line_is_still_removed():
    answer = "Delivery cost: €5,00 excl. VAT per order. Orders above 2CC are free of charge.\nPayment methods accepted: iDeal."

    cleaned, changed = remove_unrequested_directory_fields(answer, "What is the Netherlands delivery cost?")

    assert changed
    assert "iDeal" not in cleaned
    assert "Delivery cost: €5,00 excl. VAT per order. Orders above 2CC are free of charge." in cleaned
