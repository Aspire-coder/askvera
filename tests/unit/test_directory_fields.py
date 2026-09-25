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
    "Welcome to Forever Iraq!\n+964 750 820 8001\nFREQUENTLY ASKED QUESTIONS\nSIGNING UP\n"
    "� Sign up with a form\n"
    "Phone order is not available in Iraq. FBO�s have to come or send somebody else to Arbil office in order to\n"
    "place an order, make payment and pick up the products.\n� Sign up online\nN/A\nORDERING PRODUCTS\n"
    "� Minimum order size FBO: The minimum order for new FBO�s is $100 and for FBO�s is $50.\n"
    "� Delivery Cost: There is no delivery option in Iraq. Products must be picked up at the Erbil office.\n"
    "� Average lead time for orders to arrive: N/A\n"
    "� Payment methods accepted: Bank transfer is the only payment option. No cash or Credit Card payments.\n"
    "� Local Product Centers available: Yes at the head office in Erbil.\n"
    "� Online purchase by foreign FBO�s available: Via this link you can register and order, only payment\n"
    "method in e-shop is to debt money to bank.\n"
    "� First order required while signing up as Preferred Customer?: Yes. To be a FBO, prospects have to\n"
    "provide an original and signed application form and copy of photo ID. Also first order has to be ordered.\n"
    "� Grouped order possible?: N/A\n"
    "� Online shop +website available for foreign FBO�s?: Via this link you can register and order, only\n"
    "payment method in e-shop is to debt money to bank.\nGENERAL INFORMATION\nForever Living Products Iraq\n"
    "Office & Product Center Address\nBuilding number 6 Street number\n16, District Wazeeran (Next to\n"
    "the TBI Bank) Erbil, Iraq\nBusiness Hours Office 09.00 am � 17.00 pm (Sun � Thurs)\n"
    "Telephone Office +964 750 820 8001\nTelephone for Orders +964 750 820 8002\nEmail flpiraq@ymail.com\n"
    "Websites www.foreverliving.com\nBONUS PAYMENT\n� To local FBO�s\n"
    "Domestic bonuses are paid by bank transfer or cheques.\n� To foreign FBO�s\n"
    "Bonus payment is made by bank transfer to foreign FBOs. Bonus amount has to be $100 USD and up.\n"
    "The below information should be sent to the office in order to get paid.\nUSD BANK ACCOUNT DETAILS\n"
    "FLP ID:\nAccount Holder�s Name:\nBank Name:\nBank Address:\nAccount Number:\nIBAN:\nSwift Code:\n"
    "� Country:\nLEGAL REQUIREMENTS AS FBO, OTHER THAN NORMAL INCOME TAXATION\n� VAT Registration:\n"
    "� Social security registration:\n� Other registrations:\nLOCAL TRAININGS\n"
    "All trainings or business meetings are held by sponsors in Iraq."
)

_BURUNDI_RECORD_CONTENT = (
    "Welcome to Forever Burundi!\nGENERAL INFORMATION\nFREQUENTLY ASKED QUESTIONS\nSIGNING UP\n"
    "� Sign up with a form:\nYes.\n� Sign up online:\nYes.\nORDERING PRODUCTS\n"
    "� Minimum order size FBO: $100 worth of products when joining. $50 worth of products after joining.\n"
    "� Delivery Cost: $3.00 within the country.\n� Average lead time for orders to arrive: 12 - 24 hours.\n"
    "� Payment methods accepted: Bank deposit, Credit Card, Mobile money transfer (Mpesacam).\n"
    "� Local Product Centers available: Yes.\n� Online purchase by foreign FBO�s available: No.\n"
    "� First order required while signing up as Preferred Customer?: Yes.\n"
    "� Grouped order possible?: Not available.\n� Online shop +website available for foreign FBO�s?: No.\n"
    "Forever Living Products Burundi\nOffice & Product Center Address\nGatogato Building no. 15\n"
    "(KCB Bank Compound)\n1st Floor Boulevard Patrice Lumumba\nBurundi\n"
    "Business Hours Office 08.00 am � 17.00 pm (Mon � Fri)\nTelephone Office Not available\n"
    "Telephone for Orders Not available\nFax Not available\nEmail info@foreverea.com\n"
    "Website www.foreverliving.com\nBONUS PAYMENT\n� To local FBO�s\n"
    "Bonus paid via bank transfer ONLY when it accumulated to $5 and above. Bonus less than $5 will only be\n"
    "paid after accumulating to that level.\n� To foreign FBO�s\n"
    "Bonus paid via bank transfer ONLY when it accumulated to $100 and above. Bonus less than $100 will\n"
    "only be paid after accumulating to that level.\nLEGAL REQUIREMENTS AS FBO, OTHER THAN NORMAL INCOME TAXATION\n"
    "� VAT Registration: No.\n� Social security registration: No.\n� Other registrations: No.\n"
    "LOCAL TRAININGS\nNew FBO orientation at the FLP Training Center."
)

_GABON_RECORD_CONTENT = (
    "Welcome to Forever Gabon!\n+241 07 46 36 77\nGENERAL INFORMATION\nFREQUENTLY ASKED QUESTIONS\nSIGNING UP\n"
    "� Sign up with a form:\nPlease click here for the Forever Business Owner application form. Printouts are accepted.\n"
    "� Sign up online is not offered.\nORDERING PRODUCTS\n"
    "� Minimum order size FBO: First order requirement can be any CC above 0.4CC. However, we\n"
    "recommend 2CC at first order. There is no designated form required.\n"
    "� Delivery Cost: We do not deliver products to FBO�s yet. FBO�s pick up their products directly from the\n"
    "office.\n� Average lead time for orders to arrive: N/A\n� Payment methods accepted: Bank deposit.\n"
    "� Local Product Centers available: No.\n� Online purchase by foreign FBO�s available: No.\n"
    "� First order required while signing up as Preferred Customer?: Yes.\n� Grouped order possible?: No.\n"
    "� Online shop +website available for foreign FBO�s?: No.\n"
    "Forever Living Products Gabon (Gabon)\nOffice & Product Center Address Aca�, Nomba Domaine\n"
    "1386 Libreville � Gabon\nBusiness Hours Office 09.00 am � 17.00 pm (Mon � Fri)\n"
    "Business Hours Product Centre 09.00 am � 17.00 pm (Mon � Fri)\n09.00 am � 13.00 pm (Sat)\n"
    "Telephone Office +241 07 46 36 77 / 01 70 41 38\nTelephone for Orders No orders on the phone\n"
    "Mobile +241 02 17 02 73\nEmail info@flpcameroon.com; forevergabon@gmail.com\nWebsite www.foreverliving.com\n"
    "BONUS PAYMENT\n� To local FBO�s\nMonthly bank transfers if bonus amount is greater than XAF 2000 (Local currency).\n"
    "� To foreign FBO�s\nMonthly bank transfers if bonus amount is greater than XAF 250000 (Local currency).\n"
    "LEGAL REQUIREMENTS AS FBO, OTHER THAN NORMAL INCOME TAXATION\n� VAT Registration: No.\n"
    "� Social security registration: No.\n� Other registrations: No.\nLOCAL TRAININGS\n"
    "Forever Business opportunity presentation, How to start correctly, First steps to Manager, Product launch/\n"
    "Product trainings."
)

_CAMEROON_RECORD_CONTENT = (
    "Welcome to Forever Cameroon!\n+237 233 472 448\nGENERAL INFORMATION\nFREQUENTLY ASKED QUESTIONS\nSIGNING UP\n"
    "� Sign up with a form:\nPlease click here for the Forever Business Owner application form. Printouts are accepted.\n"
    "� Sign up online is not offered.\nORDERING PRODUCTS\n"
    "� Minimum order size FBO: First order requirement can be any CC above 0.4CC. However, we\n"
    "recommend 2CC at first order. There is no designated form required.\n"
    "� Delivery Cost: We do not deliver products to FBO�s yet. FBO�s pick up their products directly\n"
    "from the office.\n� Average lead time for orders to arrive: N/A\n"
    "� Payment methods accepted: MTN Mobile Money and Bank deposit.\n"
    "� Local Product Centers available: No.\n� Online purchase by foreign FBO�s available: No.\n"
    "� First order required while signing up as Preferred Customer?: Yes.\n� Grouped order possible?: No.\n"
    "� Online shop +website available for foreign FBO�s?: No.\n"
    "Forever Living Products Cameroon S.A.R.L.\nOffice & Product Center Address Santa Barbara, Route Bonamousaddi\n"
    "B.P . 18246, Douala - Cameroon\nBusiness Hours Office 08.30 am � 17.30 pm (Mon � Fri)\n"
    "Business Hours Product Centre 08.30 am � 17.30 pm (Mon � Fri)\n09.00 am � 13.00 pm (Sat)\n"
    "Telephone Office +237 233 472 448\nTelephone for Orders (see above)\nMobile +237 677 747 555\n"
    "Email info@flpcameroon.com\nWebsite www.foreverliving.com\nGabon\nBONUS PAYMENT\n� To local FBO�s\n"
    "Monthly bank transfers if bonus amount is greater than XAF 2000 (Local currency).\n� To foreign FBO�s\n"
    "By cheque.\nLEGAL REQUIREMENTS AS FBO, OTHER THAN NORMAL INCOME TAXATION\n� VAT Registration: No.\n"
    "� Social security registration: No.\n� Other registrations: No.\nLOCAL TRAININGS\n"
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
