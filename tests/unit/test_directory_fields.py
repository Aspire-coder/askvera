"""Tests for generic structured directory response completion."""

from utils.directory_fields import parse_directory_fields, restore_missing_directory_contacts


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
