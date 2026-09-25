"""Tests for generic structured directory response completion."""

from utils.directory_fields import (
    build_support_contact_supplement,
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


def test_directory_fields_preserve_comma_decimal_delivery_amounts() -> None:
    content = """Welcome to Forever Exampleland!
    Delivery Cost
    €2,50-€6,00 (excluding VAT)
    """

    fields = parse_directory_fields(content)

    assert fields["Delivery Cost"] == "€2,50-€6,00 (excluding VAT)"


def test_parses_fbo_minimum_from_content_without_structured_metadata() -> None:
    fields = parse_directory_fields(
        "Welcome to Forever Singapore!\nMinimum order size FBO\nEach order must be a minimum of SGD25."
    )

    assert fields["Minimum order size FBO"] == "Each order must be a minimum of SGD25."


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


# --- build_support_contact_supplement guards --------------------------
#
# The "phone" field parsed straight off a directory record is not always a
# phone number - real corpus records carry free-text caveats and
# placeholders in it - and build_support_contact_supplement used to copy
# that value into the supplement unvalidated. These tests apply the SAME
# reviewed guards the directory contact route already uses
# (_directory_contact_route_phone_is_safe / _directory_contact_route_email_is_safe
# / _is_self_referential_value, now shared through
# utils.directory_fields._value_passes_contact_guards) so an unsafe value is
# treated as absent instead of rendered. Content strings below are copied
# verbatim, byte for byte, from the real International Sponsoring Directory
# corpus (via parse_directory_fields, the same as production).

_IRAQ_RECORD_CONTENT = (
    "Welcome to Forever Iraq!\n"
    "+964 750 820 8001\n"
    "FREQUENTLY ASKED QUESTIONS\n"
    "SIGNING UP\n"
    "\u2022 Sign up with a form\n"
    "Phone order is not available in Iraq. FBO\u2019s have to come or send somebody else to Arbil office in order to\n"
    "place an order, make payment and pick up the products.\n"
    "\u2022 Sign up online\n"
    "N/A\n"
    "ORDERING PRODUCTS\n"
    "\u2022 Minimum order size FBO: The minimum order for new FBO\u2019s is $100 and for FBO\u2019s is $50.\n"
    "\u2022 Delivery Cost: There is no delivery option in Iraq. Products must be picked up at the Erbil office.\n"
    "\u2022 Average lead time for orders to arrive: N/A\n"
    "\u2022 Payment methods accepted: Bank transfer is the only payment option. No cash or Credit Card payments.\n"
    "\u2022 Local Product Centers available: Yes at the head office in Erbil.\n"
    "\u2022 Online purchase by foreign FBO\u2019s available: Via this link you can register and order, only payment\n"
    "method in e-shop is to debt money to bank.\n"
    "\u2022 First order required while signing up as Preferred Customer?: Yes. To be a FBO, prospects have to\n"
    "provide an original and signed application form and copy of photo ID. Also first order has to be ordered.\n"
    "\u2022 Grouped order possible?: N/A\n"
    "\u2022 Online shop +website available for foreign FBO\u2019s?: Via this link you can register and order, only\n"
    "payment method in e-shop is to debt money to bank.\n"
    "GENERAL INFORMATION\n"
    "Forever Living Products Iraq\n"
    "Office & Product Center Address\n"
    "Building number 6 Street number\n"
    "16, District Wazeeran (Next to\n"
    "the TBI Bank) Erbil, Iraq\n"
    "Business Hours Office 09.00 am \u2013 17.00 pm (Sun \u2013 Thurs)\n"
    "Telephone Office +964 750 820 8001\n"
    "Telephone for Orders +964 750 820 8002\n"
    "Email flpiraq@ymail.com\n"
    "Websites www.foreverliving.com\n"
    "BONUS PAYMENT\n"
    "\u2022 To local FBO\u2019s\n"
    "Domestic bonuses are paid by bank transfer or cheques.\n"
    "\u2022 To foreign FBO\u2019s\n"
    "Bonus payment is made by bank transfer to foreign FBOs. Bonus amount has to be $100 USD and up.\n"
    "The below information should be sent to the office in order to get paid.\n"
    "USD BANK ACCOUNT DETAILS\n"
    "FLP ID:\n"
    "Account Holder\u2019s Name:\n"
    "Bank Name:\n"
    "Bank Address:\n"
    "Account Number:\n"
    "IBAN:\n"
    "Swift Code:\n"
    "\u2022 Country:\n"
    "LEGAL REQUIREMENTS AS FBO, OTHER THAN NORMAL INCOME TAXATION\n"
    "\u2022 VAT Registration:\n"
    "\u2022 Social security registration:\n"
    "\u2022 Other registrations:\n"
    "LOCAL TRAININGS\n"
    "All trainings or business meetings are held by sponsors in Iraq."
)

_BURUNDI_RECORD_CONTENT = (
    "Welcome to Forever Burundi!\n"
    "GENERAL INFORMATION\n"
    "FREQUENTLY ASKED QUESTIONS\n"
    "SIGNING UP\n"
    "\u2022 Sign up with a form:\n"
    "Yes.\n"
    "\u2022 Sign up online:\n"
    "Yes.\n"
    "ORDERING PRODUCTS\n"
    "\u2022 Minimum order size FBO: $100 worth of products when joining. $50 worth of products after joining.\n"
    "\u2022 Delivery Cost: $3.00 within the country.\n"
    "\u2022 Average lead time for orders to arrive: 12 - 24 hours.\n"
    "\u2022 Payment methods accepted: Bank deposit, Credit Card, Mobile money transfer (Mpesacam).\n"
    "\u2022 Local Product Centers available: Yes.\n"
    "\u2022 Online purchase by foreign FBO\u2019s available: No.\n"
    "\u2022 First order required while signing up as Preferred Customer?: Yes.\n"
    "\u2022 Grouped order possible?: Not available.\n"
    "\u2022 Online shop +website available for foreign FBO\u2019s?: No.\n"
    "Forever Living Products Burundi\n"
    "Office & Product Center Address\n"
    "Gatogato Building no. 15\n"
    "(KCB Bank Compound)\n"
    "1st Floor Boulevard Patrice Lumumba\n"
    "Burundi\n"
    "Business Hours Office 08.00 am \u2013 17.00 pm (Mon \u2013 Fri)\n"
    "Telephone Office Not available\n"
    "Telephone for Orders Not available\n"
    "Fax Not available\n"
    "Email info@foreverea.com\n"
    "Website www.foreverliving.com\n"
    "BONUS PAYMENT\n"
    "\u2022 To local FBO\u2019s\n"
    "Bonus paid via bank transfer ONLY when it accumulated to $5 and above. Bonus less than $5 will only be\n"
    "paid after accumulating to that level.\n"
    "\u2022 To foreign FBO\u2019s\n"
    "Bonus paid via bank transfer ONLY when it accumulated to $100 and above. Bonus less than $100 will\n"
    "only be paid after accumulating to that level.\n"
    "LEGAL REQUIREMENTS AS FBO, OTHER THAN NORMAL INCOME TAXATION\n"
    "\u2022 VAT Registration: No.\n"
    "\u2022 Social security registration: No.\n"
    "\u2022 Other registrations: No.\n"
    "LOCAL TRAININGS\n"
    "New FBO orientation at the FLP Training Center."
)

_GABON_RECORD_CONTENT = (
    "Welcome to Forever Gabon!\n"
    "+241 07 46 36 77\n"
    "GENERAL INFORMATION\n"
    "FREQUENTLY ASKED QUESTIONS\n"
    "SIGNING UP\n"
    "\u2022 Sign up with a form:\n"
    "Please click here for the Forever Business Owner application form. Printouts are accepted.\n"
    "\u2022 Sign up online is not offered.\n"
    "ORDERING PRODUCTS\n"
    "\u2022 Minimum order size FBO: First order requirement can be any CC above 0.4CC. However, we\n"
    "recommend 2CC at first order. There is no designated form required.\n"
    "\u2022 Delivery Cost: We do not deliver products to FBO\u2019s yet. FBO\u2019s pick up their products directly from the\n"
    "office.\n"
    "\u2022 Average lead time for orders to arrive: N/A\n"
    "\u2022 Payment methods accepted: Bank deposit.\n"
    "\u2022 Local Product Centers available: No.\n"
    "\u2022 Online purchase by foreign FBO\u2019s available: No.\n"
    "\u2022 First order required while signing up as Preferred Customer?: Yes.\n"
    "\u2022 Grouped order possible?: No.\n"
    "\u2022 Online shop +website available for foreign FBO\u2019s?: No.\n"
    "Forever Living Products Gabon (Gabon)\n"
    "Office & Product Center Address Aca\u00e9, Nomba Domaine\n"
    "1386 Libreville \u2013 Gabon\n"
    "Business Hours Office 09.00 am \u2013 17.00 pm (Mon \u2013 Fri)\n"
    "Business Hours Product Centre 09.00 am \u2013 17.00 pm (Mon \u2013 Fri)\n"
    "09.00 am \u2013 13.00 pm (Sat)\n"
    "Telephone Office +241 07 46 36 77 / 01 70 41 38\n"
    "Telephone for Orders No orders on the phone\n"
    "Mobile +241 02 17 02 73\n"
    "Email info@flpcameroon.com; forevergabon@gmail.com\n"
    "Website www.foreverliving.com\n"
    "BONUS PAYMENT\n"
    "\u2022 To local FBO\u2019s\n"
    "Monthly bank transfers if bonus amount is greater than XAF 2000 (Local currency).\n"
    "\u2022 To foreign FBO\u2019s\n"
    "Monthly bank transfers if bonus amount is greater than XAF 250000 (Local currency).\n"
    "LEGAL REQUIREMENTS AS FBO, OTHER THAN NORMAL INCOME TAXATION\n"
    "\u2022 VAT Registration: No.\n"
    "\u2022 Social security registration: No.\n"
    "\u2022 Other registrations: No.\n"
    "LOCAL TRAININGS\n"
    "Forever Business opportunity presentation, How to start correctly, First steps to Manager, Product launch/\n"
    "Product trainings."
)

_CAMEROON_RECORD_CONTENT = (
    "Welcome to Forever Cameroon!\n"
    "+237 233 472 448\n"
    "GENERAL INFORMATION\n"
    "FREQUENTLY ASKED QUESTIONS\n"
    "SIGNING UP\n"
    "\u2022 Sign up with a form:\n"
    "Please click here for the Forever Business Owner application form. Printouts are accepted.\n"
    "\u2022 Sign up online is not offered.\n"
    "ORDERING PRODUCTS\n"
    "\u2022 Minimum order size FBO: First order requirement can be any CC above 0.4CC. However, we\n"
    "recommend 2CC at first order. There is no designated form required.\n"
    "\u2022 Delivery Cost: We do not deliver products to FBO\u2019s yet. FBO\u2019s pick up their products directly\n"
    "from the office.\n"
    "\u2022 Average lead time for orders to arrive: N/A\n"
    "\u2022 Payment methods accepted: MTN Mobile Money and Bank deposit.\n"
    "\u2022 Local Product Centers available: No.\n"
    "\u2022 Online purchase by foreign FBO\u2019s available: No.\n"
    "\u2022 First order required while signing up as Preferred Customer?: Yes.\n"
    "\u2022 Grouped order possible?: No.\n"
    "\u2022 Online shop +website available for foreign FBO\u2019s?: No.\n"
    "Forever Living Products Cameroon S.A.R.L.\n"
    "Office & Product Center Address Santa Barbara, Route Bonamousaddi\n"
    "B.P . 18246, Douala - Cameroon\n"
    "Business Hours Office 08.30 am \u2013 17.30 pm (Mon \u2013 Fri)\n"
    "Business Hours Product Centre 08.30 am \u2013 17.30 pm (Mon \u2013 Fri)\n"
    "09.00 am \u2013 13.00 pm (Sat)\n"
    "Telephone Office +237 233 472 448\n"
    "Telephone for Orders (see above)\n"
    "Mobile +237 677 747 555\n"
    "Email info@flpcameroon.com\n"
    "Website www.foreverliving.com\n"
    "Gabon\n"
    "BONUS PAYMENT\n"
    "\u2022 To local FBO\u2019s\n"
    "Monthly bank transfers if bonus amount is greater than XAF 2000 (Local currency).\n"
    "\u2022 To foreign FBO\u2019s\n"
    "By cheque.\n"
    "LEGAL REQUIREMENTS AS FBO, OTHER THAN NORMAL INCOME TAXATION\n"
    "\u2022 VAT Registration: No.\n"
    "\u2022 Social security registration: No.\n"
    "\u2022 Other registrations: No.\n"
    "LOCAL TRAININGS\n"
    "Forever Business opportunity presentation, How to start correctly, First steps to Manager, Product launch/\n"
    "Product trainings."
)


def test_support_contact_supplement_never_renders_the_iraq_order_caveat_as_a_phone() -> None:
    """Real Iraq record: the "Phone" field parsed off the FAQ bullet holds a
    free-text caveat ("Phone order is not available in Iraq...") rather than
    a phone number. The record also carries a real "Telephone Office" value
    later in the same content, so once the caveat is guarded out the
    supplement falls through to that real number - it does not simply drop
    the phone line, because a genuinely safe one is still available."""
    fields = parse_directory_fields(_IRAQ_RECORD_CONTENT)

    supplement = build_support_contact_supplement("", fields, True, language="en")

    assert supplement is not None
    block, _labels = supplement
    assert "order is not available in iraq" not in block.lower()
    assert "- Telephone Office: +964 750 820 8001" in block
    assert "- Email: flpiraq@ymail.com" in block


def test_support_contact_supplement_never_renders_burundi_not_available_as_a_phone() -> None:
    """Real Burundi record: "Telephone Office" is literally "Not available" -
    a placeholder, not a number. Unlike Iraq, Burundi has no other "phone"
    canonical field to fall through to, so the supplement simply omits the
    phone line rather than inventing one, and still renders the valid email."""
    fields = parse_directory_fields(_BURUNDI_RECORD_CONTENT)

    supplement = build_support_contact_supplement("", fields, True, language="en")

    assert supplement is not None
    block, labels = supplement
    assert "not available" not in block.lower()
    assert not any("Telephone" in label or "Phone" in label for label in labels)
    assert block == "Email: info@foreverea.com"


def test_support_contact_supplement_never_renders_the_gabon_order_caveat() -> None:
    """Real Gabon record: "Telephone for Orders" holds the caveat "No orders
    on the phone", and a parser quirk (out of scope for this guard fix -
    parse_directory_fields swallows the following "Mobile" line into that
    same field's value) means the caveat's own label also does not cleanly
    read "Telephone for Orders" once parsed. Either way, the supplement
    already only ever considers the canonical "phone" field
    ("Telephone Office"), never "order_phone" ("Telephone for Orders"), so
    this caveat was never rendered by build_support_contact_supplement even
    before this fix - this test locks in that existing, correct behavior."""
    fields = parse_directory_fields(_GABON_RECORD_CONTENT)

    supplement = build_support_contact_supplement("", fields, True, language="en")

    assert supplement is not None
    block, _labels = supplement
    assert "no orders on the phone" not in block.lower()
    assert "- Telephone Office: +241 07 46 36 77 / 01 70 41 38" in block


def test_support_contact_supplement_treats_a_see_above_phone_as_absent() -> None:
    """"(see above)" is a real, verbatim corpus value (e.g. Cameroon's
    "Telephone for Orders" field, see
    test_support_contact_supplement_keeps_the_cameroon_output_byte_identical
    below) - here applied to the canonical "phone" field itself (no real
    record in the reviewed corpus happens to carry it on that exact field)
    to prove the existing self-referential guard
    (_is_self_referential_value) already applies inside
    build_support_contact_supplement, and keeps doing so once combined with
    the new phone/email guards."""
    fields = {
        "Telephone Office": "(see above)",
        "Email": "info@foreverea.com",
    }

    supplement = build_support_contact_supplement("", fields, True, language="en")

    assert supplement is not None
    block, labels = supplement
    assert "see above" not in block.lower()
    assert not any("Telephone" in label or "Phone" in label for label in labels)
    assert "info@foreverea.com" in block


def test_support_contact_supplement_keeps_the_cameroon_output_byte_identical() -> None:
    """Regression proof: a clean record - real phone, real email, no
    caveats - must render exactly as before this guard was added. Cameroon's
    "Telephone for Orders" is itself "(see above)", canonical "order_phone",
    already excluded from the supplement regardless of this fix."""
    fields = parse_directory_fields(_CAMEROON_RECORD_CONTENT)

    supplement = build_support_contact_supplement("", fields, True, language="en")

    assert supplement == (
        "- Telephone Office: +237 233 472 448\n- Email: info@flpcameroon.com",
        ["Telephone Office", "Email"],
    )


def test_support_contact_supplement_keeps_a_trailing_comma_multi_email_byte_identical() -> None:
    """Regression proof for the real Nigeria/Tanzania email shape: a value
    such as "flphelpdesk@yahoo.com, info@flpng.com," carries a trailing
    separator with nothing after it. The email guard strips that trailing
    separator only for the SAFETY CHECK (matching
    build_directory_contact_route's existing, reviewed behavior) - the
    RENDERED value is untouched, so this must keep rendering with its
    trailing comma exactly as it did before the guard was added."""
    fields = {
        "Telephone Office": "+234 1 2711795",
        "Email": "flphelpdesk@yahoo.com, info@flpng.com,",
    }

    supplement = build_support_contact_supplement("", fields, True, language="en")

    assert supplement == (
        "- Telephone Office: +234 1 2711795\n- Email: flphelpdesk@yahoo.com, info@flpng.com,",
        ["Telephone Office", "Email"],
    )


# Verbatim records for the four email values the guard now drops (generated
# byte for byte from current_extractor.jsonl, one source line per string).
_THAILAND_RECORD_CONTENT = (
    "Welcome to Forever Thailand!\n"
    "+662 258 0842-3\n"
    "FREQUENTLY ASKED QUESTIONS\n"
    "SIGNING UP\n"
    "Sign up with a form or online\n"
    "\u2022 Please register on website to access the Download area on https://shop.foreverliving.co.th to download\n"
    "the FBO application form in English and Thai. Printouts are accepted. Applicant need to sign.\n"
    "\u2022 Sign up online at this link https://shop.foreverliving.co.th/en/register\n"
    "ORDERING PRODUCTS\n"
    "Order online on web store; https://shop.foreverliving.co.th/\n"
    "or via LINE application; https://line.me/R/ti/p/@foreverthailand\n"
    "\u2022 Minimum order size FBO: There is no first order minimum requirement. A designated order form is not\n"
    "generally required but may be asked by staff under certain circumstances. Access the download area for\n"
    "latest price list, product brochure and other marketing tools.\n"
    "\u2022 Delivery Cost: Depends on the size of the order by weight. Free domestic delivery for orders above\n"
    "2,000 Thai Baht.\n"
    "\u2022 Average lead time for orders to arrive: Orders typically take 1 to 2 working days outside of Bangkok.\n"
    "GENERAL INFORMATION\n"
    "Forever Living Products Thailand Co., Ltd.\n"
    "Office & Product Center Address\n"
    "Bangkok Product Centre\n"
    "Unit 3923, 9th Floor, BB Building\n"
    "54 Sukhumvit Soi (Asoke) Road, Bangkok, 10110\n"
    "Thailand\n"
    "Business Hours Office 10:00 am \u2013 18:00 pm (Mon \u2013 Fri)\n"
    "Closed weekends and Bank Holidays\n"
    "Telephone Office +662 258 0842-3\n"
    "Telephone for orders +662 258 0842-3\n"
    "+669 4216 9648 (WhatsApp)\n"
    "Fax +662 258 0843\n"
    "Email\n"
    "info@foreverliving.co.th (General inquiries)\n"
    "orders@foreverliving.co.th (Orders)\n"
    "support@foreverliving.co.th (FBO support)\n"
    "Websites www.foreverliving.co.th\n"
    "In Bangkok next day delivery is generally offered depending on area and if order is placed before 2pm.\n"
    "Same day delivery is offered at extra charge.\n"
    "\u2022 Payment methods accepted: Cash and credit cards if ordering at the product center. Credit cards, bank\n"
    "transfer and cash payment at local convenience store are accepted when placing an order on web store.\n"
    "\u2022 Local Product Centers available: Bangkok Product center and any of our meeting venues.\n"
    "\u2022 Online purchase by foreign FBO\u2019s available: Yes, foreign and local FBO\u2019s can purchase online at\n"
    "https://shop.foreverliving.co.th once they have registered as users on Web Store. In order to do this FBOs\n"
    "need to be internationally sponsored into Thailand.\n"
    "\u2022 First order required while signing up as Preferred Customer?: No.\n"
    "\u2022 Grouped order possible?: No, each FBO gets a separate invoice per transaction under their name and\n"
    "their corresponding ID number.\n"
    "\u2022 Online shop +website available for foreign FBO\u2019s?: Yes.\n"
    "BONUS PAYMENT\n"
    "\u2022 Bank transfer. The costs of payment via International Bank transfer is deducted from commissions.\n"
    "Costs varies according to the amount transferred and the recipient\u2019s country.\n"
    "LEGAL REQUIREMENTS AS FBO, OTHER THAN NORMAL INCOME TAXATION\n"
    "\u2022 VAT Registration: In Thailand only companies can be VAT registered unless an individual\u2019s annual\n"
    "turnover exceeds the 1.8 million Baht threshold (approx. 58k US$). Thai domestic distributors cannot\n"
    "register as an FBO business entity, we do however honor foreign FBO\u2019s registered as a business entity.\n"
    "Link to the Thai Revenue Dept.: www.rd.go.th/publish/6043.0.html\n"
    "\u2022 Social security registration: The 13 digit Thai National ID card is required when Thai nationals apply for\n"
    "a FBOship. For foreigners passport info is needed. Thailand requires for withholding tax to be withheld by\n"
    "the payer and paid to the Revenue Department on their behalf. National and foreign residents are taxed\n"
    "different rates according to double taxation treaties in existence with their country of residence.\n"
    "\u2022 Other registrations: No other known.\n"
    "LOCAL TRAININGS\n"
    "Follow our social media channels for business meeting announcements, which can be physical, hybrid or\n"
    "online only meetings.\n"
    "Facebook: https://www.facebook.com/foreverthailandhq\n"
    "Instagram: https://www.instagram.com/foreverlivingth/\n"
    "YouTube: https://www.youtube.com/c/foreverlivingthailandhq"
)

_BOSNIA_HERZEGOVINA_RECORD_CONTENT = (
    "Welcome to Forever Bosnia & Herzegovina!\n"
    "+387 55 211 784\n"
    "GENERAL INFORMATION\n"
    "FREQUENTLY ASKED QUESTIONS\n"
    "SIGNING UP\n"
    "\u2022 Sign up with a form:\n"
    "Printed forms are available in our Product Center.\n"
    "\u2022 Sign up online:\n"
    "On-going introduction\n"
    "ORDERING PRODUCTS\n"
    "\u2022 Minimum order size FBO: \u20ac55,00 +17% VAT\n"
    "\u2022 Delivery Cost: This is determined by the weight of the order and the location it needs to be delivered to.\n"
    "\u2022 Average lead time for orders to arrive: Normal delivery time is 24 to 48 hours.\n"
    "\u2022 Payment methods accepted: Credit Card and wire transfer to our bank accounts.\n"
    "\u2022 Local Product Centers available: Yes: FLP Bosnia & Herzegovina, FLP Sarajevo Dzemala Bijedica\n"
    "166A, 71000 Sarajevo.\n"
    "\u2022 Online purchase by foreign FBO\u2019s available: -\n"
    "\u2022 First order required while signing up as Preferred Customer?: Yes, first order goes with an application\n"
    "form.\n"
    "\u2022 Grouped order possible?: Yes.\n"
    "\u2022 Online shop +website available for foreign FBO\u2019s?: In setup process at the moment\n"
    "BONUS PAYMENT\n"
    "Forever Living Products Hungary (Bosnia &\n"
    "Herzegovina)\n"
    "Office & Product Center Address Trg Djenerala Draze 3\n"
    "763000 Bijeljina, Bosnia & Herzegovina\n"
    "Business Hours Office 09.00 am \u2013 17.00 pm (Mon \u2013 Fri)\n"
    "Telephone Office +387 55 211 784\n"
    "Telephone for Orders +387 55 211 784\n"
    "Email\n"
    "flpbos@teol.net\n"
    "forever.flpbos@gmail.com\n"
    "flpbosniacustomercare@gmail.com\n"
    "Websites www.flpshop.ba\n"
    "\u2022 To local FBO\u2019s\n"
    "Domestic bonuses are paid by bank transfer. Income tax and contribution for pension security are\n"
    "deducted. FBO\u2019s registered as companies send their companies invoices.\n"
    "\u2022 To foreign FBO\u2019s\n"
    "Head office, Forever Living Products Hungary pays foreign FBO\u2019s, we have mutual compensation bonus\n"
    "agreement in our group.\n"
    "LEGAL REQUIREMENTS AS FBO, OTHER THAN NORMAL INCOME TAXATION\n"
    "\u2022 VAT Registration: Not necessary for private persons, for entrepreneurships above certain level\n"
    "\u2022 Social security registration: -\n"
    "\u2022 Other registrations: Personal Identification number\n"
    "LOCAL TRAININGS\n"
    "Yes, the training is given by managers in the business. OTS (online training system), free access to Webinar\n"
    "platform, public presentations."
)

_PHILIPPINES_RECORD_CONTENT = (
    "Welcome to Forever Philippines!\n"
    "+632 8 367 3837\n"
    "FREQUENTLY ASKED QUESTIONS\n"
    "SIGNING UP\n"
    "\u2022 Sign up with a form\n"
    "Please click here to download the FBO application form. Printouts are accepted.\n"
    "Both sponsor and applicant need to sign.\n"
    "\u2022 Sign up online\n"
    "Residents of the Philippines can register online at www.foreverliving.com.\n"
    "ORDERING PRODUCTS\n"
    "\u2022 Minimum order size FBO: No minimum purchase.\n"
    "\u2022 Delivery Cost: Logistikus Delivery Rates 1st 3kg - P100 excess P50 per kilo Metro Manila, JRS Express\n"
    "Rates : 1st 3kg - P170 excess P80 per kilo Luzon, Visayas & Mindanao LBC Rate: 1st 3kg - P190\n"
    "excess P80 per kilo Luzon, Visayas & Mindanao.\n"
    "\u2022 Average lead time for orders to arrive: Orders for delivery NATIONWIDE will take 5 days to 1 week to\n"
    "arrive.\n"
    "\u2022 Payment methods accepted: Cash, Bank Deposit through Bank of the Philippine Island or Banco De\n"
    "Oro, Debit Card, Credit Card using VISA or MasterCard, Bank Transfer & Gcash Payment.\n"
    "\u2022 Local Product Centers available: Yes, we have Five Business Centers in the Philippines:\n"
    "1. HEAD OFFICE Quezon City Address : Ground Level, Hexagon Corporate Center, 1471 Quezon Ave.\n"
    "West Triangle, Quezon City Trunklines No. (02) 367-3837 to 31, Toll Free No. 1-800-10-3673837,\n"
    "Email address: forevercss@foreverlivingph.com\n"
    "2. DAVAO BUSINESS CENTER, Address : Unit 1-81 ICOHNS Center Bldg. Quirino Ave., cor. Mt. Mayon\n"
    "GENERAL INFORMATION\n"
    "Forever Living Products Philippines\n"
    "Office & Product Center Address\n"
    "Ground Level, Hexagon Corporate Center\n"
    "1471 Quezon Ave., West Triangle\n"
    "Quezon City\n"
    "Business Hours Office 10:00 am \u2013 16:00 pm (Mon \u2013 Fri)\n"
    "10:00 am \u2013 16:00 pm (Sat)\n"
    "Telephone Office +632 8 367 3837\n"
    "Toll-Free +1 800 10 83673837\n"
    "Fax +632 8 374-8948\n"
    "Email forevercss@foreverlivingph.com\n"
    "mis@foreverlivingph.com\n"
    "Websites www.foreverliving.com\n"
    "St., Davao City\n"
    "Telephone No. (082) 226-3048\n"
    "Mobile No. 0917-533-0970\n"
    "Email address: davao@foreverlivingph.com\n"
    "3. CAGAYAN DE ORO BUSINESS CENTER, Address : Sky Hi Bldg. J.R. Borja St., Cor. Rizal St. Brgy. 11\n"
    "Cagayan De Oro City\n"
    "Telephone No. (082) 852-1727\n"
    "Mobile No. 0917-533-0976\n"
    "Email address: cdo@foreverlivingph.com\n"
    "4. CEBU BUSINESS CENTER, Unit 207 & 209 Jesa I.T Center, # 90 Gen. Maxilom Avenue, Cebu City,\n"
    "Telephone No. (032) 266-3576\n"
    "Mobile No. 0917-533-0973\n"
    "Email address: cebu@foreverlivingph.com\n"
    "5. CALAMBA BUSINESS CENTER, Address: D \u2019Verde Bldg. Brgy. Halang, National Hi-way, Calamba\n"
    "Laguna,\n"
    "Tel. No. (049) 3060-065\n"
    "Mobile No. 09178255759\n"
    "Email address: calamba@foreverlivingph.com\n"
    "6. LEGAZPI BUSINESS CENTER, Address : Air 21 Building Lakandula Drive, Brgy. Cruzada, Legazpi\n"
    "City, Albay\n"
    "Mobile No. 0977-826-3624\n"
    "Email address: legazpi@foreverlivingph.com\n"
    "7. CAVITE PRODUCT CENTER, Unit No. 27 Millenium Commercial Center,\n"
    "Aguinaldo Highway, Palico 3, Imus, Cavite TEL. NO. (046) 5376557\n"
    "Email address: cavite@foreverlivingph.com\n"
    "\u2022 Online purchase by foreign FBO\u2019s available: : Yes, as long as the foreign FBO is Internationally\n"
    "sponsored into FLP Philippines.\n"
    "\u2022 First order required while signing up as Preferred Customer?: No minimum purchase.\n"
    "\u2022 Grouped order possible?: No.\n"
    "\u2022 Online shop +website available for foreign FBO\u2019s?: Yes, the website is www.foreverliving.com; just\n"
    "choose Philippines under location.\n"
    "BONUS PAYMENT\n"
    "\u2022 To local FBO\u2019s.\n"
    "a. Cheque\n"
    "b. Bank Transfer and direct deposit to FBO account\n"
    "\u2022 To foreign FBO\u2019s\n"
    "Demand Draft or Wire Transfer with form to be filled up by the FBO and must include Tax Identification\n"
    "Number (TIN).\n"
    "LEGAL REQUIREMENTS AS FBO, OTHER THAN NORMAL INCOME TAXATION\n"
    "\u2022 VAT Registration: Tax Identification Number (TIN) or Certificate of Business Registration from BIR if\n"
    "available any government issued ID\n"
    "\u2022 Social security registration: -\n"
    "\u2022 Other registrations: -\n"
    "LOCAL TRAININGS\n"
    "\u2022 Business Opportunity Meeting, New Forever Business Owner Orientation, Product Training, Special\n"
    "Trainings."
)

_TURKEY_RECORD_CONTENT = (
    "Welcome to Forever Turkey!\n"
    "+90 212 347 7126\n"
    "FREQUENTLY ASKED QUESTIONS\n"
    "SIGNING UP\n"
    "\u2022 Sign up with a form\n"
    "The FBO application form needs to be used with copies and pre-filled FBO number, so you need to ask\n"
    "for the printed original either at your home office or at the Turkish office. This signed form needs to be sent\n"
    "by post or courier as original to Head Office. The application form requires a national id card copy (for\n"
    "residents) or passport copy for foreign FBO. Our prices are in Euro. We use fix monthly currency exchange\n"
    "rate and charge Turkish Lira. Fax orders are accepted, after payment is completed, we invoice the order\n"
    "and deliver to the address.\n"
    "\u2022 Sign up online\n"
    "On this link an FBO can register online. After the registration the application form plus national id card or\n"
    "passport copy needs to follow. We will start new system for online registration that id numbers can receive\n"
    "from online registration site automatically. FBO can print application form, from web site and fill the id\n"
    "number and other information.\n"
    "ORDERING PRODUCTS\n"
    "\u2022 Minimum order size FBO: First order minimum is \u20ac100 and requires the designated order form you can\n"
    "download here, minimum orders for existing FBO\u2019s is \u20ac50. If you wish to pay by credit card, a copy of the\n"
    "credit card needs to be included. Also Delivery is available in Turkey. There is no delivery outside of the\n"
    "country.\n"
    "GENERAL INFORMATION\n"
    "Forever Living Saglik ve Guzellik Urunleri\n"
    "Dagitim Ltd. Sti.\n"
    "Azerbaijan, Georgia, Iraq, Kazakhstan,\n"
    "Kyrgyzstan and Turkey\n"
    "Office & Product Center Address Gazeteciler Sitesi Yazarlar No: 8\n"
    "34394 Esentepe-Istanbul\n"
    "Business Hours Office 09.00 am \u2013 19.00 pm (Mon \u2013 Fri)\n"
    "Telephone Office +90 212 347 7126\n"
    "Telephone for Orders +90 212 347 7126\n"
    "Fax +90 212 347 8130\n"
    "Email flpturkey@yahoo.com\n"
    "Websites www.flptr.com\n"
    "Azerbaijan, Georgia, Iraq, Kazakhstan, Kyrgyzstan and Turkey\n"
    "\u2022 Delivery Cost: Delivery fee is 20-25 Turkish Lira.\n"
    "\u2022 Average lead time for orders to arrive: Delivery takes maximum 48 hours to Istanbul and 72 hours to\n"
    "any other address in Turkey.\n"
    "\u2022 Payment methods accepted: Payments can be made by bank transfer or credit card. Cash payment is\n"
    "available only at head office store in Istanbul for first order.\n"
    "\u2022 Local Product Centers available: Yes, FLP Izmir Office,: Address: Akdeniz Mh. Sehit Fethi Bey Cd.\n"
    "No:49 Penpar Is Merkezi Cankaya-Konak/Izmir\n"
    "Email: flpizmir@flptr.com Telephone: +90 232 445 6344.\n"
    "\u2022 Online purchase by foreign FBO\u2019s available: N/A\n"
    "\u2022 First order required while signing up as Preferred Customer?: Yes. To be a FBO, prospects have to\n"
    "provide an original and signed application form with a copy of photo ID and a first order. After that, the FBO-\n"
    "ship is valid. Faxed applications are not accepted.\n"
    "\u2022 Grouped order possible?: N/A\n"
    "\u2022 Online shop +website available for foreign FBO\u2019s?: Yes, it is available.\n"
    "BONUS PAYMENT\n"
    "\u2022 To local FBO\u2019s\n"
    "Turkey pays bonuses by bank transfer domestic FBO\u2019s.\n"
    "\u2022 To foreign FBO\u2019s\n"
    "We pay bonuses by bank transfer to foreigner FBO\u2019s. Bonus amount has to be 200 EURO/USD/POUND\n"
    "or up whichever s/he gives us as a bank account type.\n"
    "BANK ACCOUNT DETAILS\n"
    "FLP ID:\n"
    "Currency Type: (EURO/USD/POUND)\n"
    "Account Holder\u2019s Name:\n"
    "Bank Name:\n"
    "Bank Address:\n"
    "Account Number:\n"
    "IBAN:\n"
    "Swift Code:\n"
    "LEGAL REQUIREMENTS AS FBO, OTHER THAN NORMAL INCOME TAXATION\n"
    "\u2022 VAT Registration: -\n"
    "\u2022 Social security registration: -\n"
    "\u2022 Other registrations: -\n"
    "LOCAL TRAININGS\n"
    "There are business presentations and product trainings all year round in our head office and the training and\n"
    "product center in Izmir. We send monthly meeting list at the beginning of every month to our FBO\u2019s and we\n"
    "announce the list on our e-shop website too.\n"
    "ADDRESS\n"
    "FLP Turkey head office is in Istanbul and there is a training and product center in Izmir. We have business\n"
    "presentations and trainings all year round and sell products at these two offices.\n"
    "FLP Izmir Office Address:\n"
    "Akdeniz Mh. Sehit Fethi Bey Cd. No:49 Penpar Is Merkezi Cankaya-Konak/Izmir\n"
    "Phone: +90 232 445 63 44 Fax: +90 232 445 67 29 Email: flpizmir@flptr.com"
)


def test_support_contact_supplement_drops_the_thailand_email_run_on_prose() -> None:
    """Real Thailand record: "Email" sits on its own line, followed by one
    address per line and then a plural "Websites" line the parser does not
    treat as a label, so the parsed email value runs on through the FAQ and
    legal prose. The email guard rejects the whole value, so the supplement
    keeps only hours and the office phone, and none of that prose appears."""
    fields = parse_directory_fields(_THAILAND_RECORD_CONTENT)

    supplement = build_support_contact_supplement("", fields, True, hours_requested=True, language="en")

    assert supplement == (
        "- Business Hours Office: 10:00 am \u2013 18:00 pm (Mon \u2013 Fri)\n"
        "- Telephone Office: +662 258 0842-3",
        ["Business Hours Office", "Telephone Office"],
    )
    block = supplement[0]
    for prose in ("Websites", "next day delivery", "Payment methods", "VAT Registration",
                  "LOCAL TRAININGS", "https://", "www.", "@"):
        assert prose not in block


def test_support_contact_supplement_drops_the_bosnia_herzegovina_email_run_on_prose() -> None:
    """Real Bosnia & Herzegovina record: the same "Email" / one address per
    line / "Websites" shape as Thailand, so the parsed email value swallows
    the bonus and legal prose. The guard rejects it; none of it appears."""
    fields = parse_directory_fields(_BOSNIA_HERZEGOVINA_RECORD_CONTENT)

    supplement = build_support_contact_supplement("", fields, True, hours_requested=True, language="en")

    assert supplement == (
        "- Business Hours Office: 09.00 am \u2013 17.00 pm (Mon \u2013 Fri)\n"
        "- Telephone Office: +387 55 211 784",
        ["Business Hours Office", "Telephone Office"],
    )
    block = supplement[0]
    for prose in ("Websites", "Domestic bonuses", "Hungary", "VAT Registration",
                  "LOCAL TRAININGS", "www.", "@"):
        assert prose not in block


def test_support_contact_supplement_drops_the_philippines_branch_email_line() -> None:
    """Real Philippines record. The parsed "Email" value is
    "address: cavite@foreverlivingph.com", which fails the email guard, so
    the email line is dropped and hours plus the office phone remain.

    Pre-existing parser defect, left for a follow-up: parse_directory_fields
    keeps the LAST "Email address:" line in the record, which belongs to
    the Cavite branch office, so the head-office email
    (forevercss@foreverlivingph.com) was never shown, before or after this
    guard."""
    fields = parse_directory_fields(_PHILIPPINES_RECORD_CONTENT)

    supplement = build_support_contact_supplement("", fields, True, hours_requested=True, language="en")

    assert supplement == (
        "- Business Hours Office: 10:00 am \u2013 16:00 pm (Mon \u2013 Fri)\n"
        "- Telephone Office: +632 8 367 3837",
        ["Business Hours Office", "Telephone Office"],
    )
    assert "address: cavite@" not in supplement[0]
    assert "Email" not in supplement[1]


def test_support_contact_supplement_drops_the_turkey_branch_email_line() -> None:
    """Real Turkey record. The parsed "Email" value is
    "flpizmir@flptr.com Telephone: +90 232 445 6344.", which fails the email
    guard, so the email line is dropped and hours plus the office phone
    remain.

    Pre-existing parser defect, left for a follow-up: parse_directory_fields
    keeps the LAST "Email" line in the record ("Email: flpizmir@flptr.com
    Telephone: ..."), which belongs to the Izmir branch office, so the
    head-office email (flpturkey@yahoo.com) was never shown, before or
    after this guard."""
    fields = parse_directory_fields(_TURKEY_RECORD_CONTENT)

    supplement = build_support_contact_supplement("", fields, True, hours_requested=True, language="en")

    assert supplement == (
        "- Business Hours Office: 09.00 am \u2013 19.00 pm (Mon \u2013 Fri)\n"
        "- Telephone Office: +90 212 347 7126",
        ["Business Hours Office", "Telephone Office"],
    )
    assert "flpizmir@flptr.com" not in supplement[0]
    assert "+90 232 445 6344" not in supplement[0]
    assert "Email" not in supplement[1]
