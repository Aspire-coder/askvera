"""Unit tests for Comprehend PII scrubbing."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import services.pii as pii_module
from services.pii import (
    _pii_language_code,
    contains_sensitive_pii_placeholder,
    remove_unresolved_pii_placeholders,
    scrub_pattern_pii,
    scrub_pii,
)


def test_scrub_pii_replaces_detected_entities() -> None:
    """Detected PII spans are replaced with entity labels."""
    comprehend = MagicMock()
    comprehend.detect_pii_entities.return_value = {
        "Entities": [{"BeginOffset": 11, "EndOffset": 27, "Type": "EMAIL"}]
    }
    clients = SimpleNamespace(comprehend=comprehend)
    with patch("services.pii.get_aws_clients", return_value=clients):
        assert scrub_pii("Contact me a@example.com", "cid") == "Contact me [EMAIL]"


def test_french_uses_pattern_scrubbing_without_calling_comprehend() -> None:
    with patch("services.pii.get_aws_clients") as get_clients:
        result = scrub_pii("Écrivez-moi à private@example.com", "cid", "fr")

    assert result == "Écrivez-moi à [EMAIL]"
    get_clients.assert_not_called()
    assert _pii_language_code("fr") is None


def test_approved_directory_contact_is_preserved() -> None:
    answer = "Le contact est gvilla@foreverliving.com.mx."
    evidence = "Main Admin. Email gvilla@foreverliving.com.mx"

    assert scrub_pii(answer, "cid", "fr", allowed_texts=[evidence]) == answer


def test_approved_wrapped_office_number_is_preserved() -> None:
    answer = "Adresse : Londres No. 61, Torre A, oficina 706-709"
    evidence = "Londres No.61 Torre A oficina 706 -\n709 Colonia Juarez"

    assert scrub_pii(answer, "cid", "fr", allowed_texts=[evidence]) == answer


def test_short_location_name_is_preserved_for_retrieval_input() -> None:
    text = "Give me the address of the United Kingdom office"
    start = text.index("United Kingdom")
    comprehend = MagicMock()
    comprehend.detect_pii_entities.return_value = {
        "Entities": [{"BeginOffset": start, "EndOffset": start + len("United Kingdom"), "Type": "ADDRESS"}]
    }
    clients = SimpleNamespace(comprehend=comprehend)

    with patch("services.pii.get_aws_clients", return_value=clients):
        answer = scrub_pii(text, "cid", "en", preserve_location_names=True)

    assert answer == text


def test_private_street_address_is_still_scrubbed() -> None:
    text = "Send it to 123 Main Street, Toronto"
    start = text.index("123 Main Street, Toronto")
    comprehend = MagicMock()
    comprehend.detect_pii_entities.return_value = {
        "Entities": [{"BeginOffset": start, "EndOffset": len(text), "Type": "ADDRESS"}]
    }
    clients = SimpleNamespace(comprehend=comprehend)

    with patch("services.pii.get_aws_clients", return_value=clients):
        answer = scrub_pii(text, "cid", "en", preserve_location_names=True)

    assert answer == "Send it to [ADDRESS]"


def test_person_name_is_preserved_for_retrieval_input() -> None:
    text = "Who is Dejan?"
    start = text.index("Dejan")
    comprehend = MagicMock()
    comprehend.detect_pii_entities.return_value = {
        "Entities": [{"BeginOffset": start, "EndOffset": start + len("Dejan"), "Type": "NAME"}]
    }
    clients = SimpleNamespace(comprehend=comprehend)

    with patch("services.pii.get_aws_clients", return_value=clients):
        answer = scrub_pii(text, "cid", "en", preserve_person_names=True)

    assert answer == text


def test_person_name_is_scrubbed_by_default() -> None:
    text = "My name is Dejan"
    start = text.index("Dejan")
    comprehend = MagicMock()
    comprehend.detect_pii_entities.return_value = {
        "Entities": [{"BeginOffset": start, "EndOffset": start + len("Dejan"), "Type": "NAME"}]
    }
    clients = SimpleNamespace(comprehend=comprehend)

    with patch("services.pii.get_aws_clients", return_value=clients):
        answer = scrub_pii(text, "cid", "en")

    assert answer == "My name is [NAME]"


def test_user_supplied_name_can_be_echoed_without_allowing_other_names() -> None:
    text = "I don't have information about Dejan, but contact Alice."
    dejan_start = text.index("Dejan")
    alice_start = text.index("Alice")
    comprehend = MagicMock()
    comprehend.detect_pii_entities.return_value = {
        "Entities": [
            {"BeginOffset": dejan_start, "EndOffset": dejan_start + len("Dejan"), "Type": "NAME"},
            {"BeginOffset": alice_start, "EndOffset": alice_start + len("Alice"), "Type": "NAME"},
        ]
    }
    clients = SimpleNamespace(comprehend=comprehend)

    with patch("services.pii.get_aws_clients", return_value=clients):
        answer = scrub_pii(text, "cid", "en", allowed_name_texts=["Who is Dejan?"])

    assert answer == "I don't have information about Dejan, but contact [NAME]."


def test_grounded_address_with_formatting_variation_is_preserved() -> None:
    text = "Office: 35 Homer Road, Solihull, West Midlands, UK"
    evidence = "Physical Address 35 Homer Road Solihull West Midlands B91 3QJ United Kingdom"
    start = text.index("35 Homer Road")
    comprehend = MagicMock()
    comprehend.detect_pii_entities.return_value = {
        "Entities": [{"BeginOffset": start, "EndOffset": len(text), "Type": "ADDRESS"}]
    }
    clients = SimpleNamespace(comprehend=comprehend)

    with patch("services.pii.get_aws_clients", return_value=clients):
        answer = scrub_pii(text, "cid", "en", allowed_texts=[evidence])

    assert answer == text


def test_approved_public_assistant_name_is_not_anonymized() -> None:
    comprehend = MagicMock()
    comprehend.detect_pii_entities.return_value = {
        "Entities": [{"BeginOffset": 8, "EndOffset": 12, "Type": "NAME"}]
    }
    clients = SimpleNamespace(comprehend=comprehend)

    with patch("services.pii.get_aws_clients", return_value=clients):
        answer = scrub_pii(
            "I'm ASK Vera.",
            "cid",
            "en",
            allowed_texts=["ASK Vera"],
        )

    assert answer == "I'm ASK Vera."


def test_unresolved_contact_placeholder_line_is_removed() -> None:
    answer = "Contact Support:\n- **[ADDRESS]:** +31 88 646 0200\nOr email support@example.com"

    assert remove_unresolved_pii_placeholders(answer) == "Contact Support:\nOr email support@example.com"


def test_unresolved_placeholders_are_removed_inline() -> None:
    answer = "If you're in the Benelux region ([ADDRESS], [ADDRESS]), disputes use arbitration."

    assert remove_unresolved_pii_placeholders(answer) == "If you're in the Benelux region, disputes use arbitration."


def test_government_id_is_scrubbed_without_language_specific_service() -> None:
    scrubbed = scrub_pattern_pii("My identifier is 123-45-6789")

    assert scrubbed == "My identifier is [GOVERNMENT_ID]"
    assert contains_sensitive_pii_placeholder(scrubbed) is True


def test_government_id_shaped_number_from_approved_evidence_is_not_masked() -> None:
    """A directory phone/order-line number can coincidentally match the
    3-2-4 digit shape of a US SSN. When it is grounded in approved evidence
    (an office directory record, not user-submitted text) it is a public
    business contact value and gets the same exemption phone/email numbers
    already have, instead of being masked as a personal government ID."""
    evidence = "Orders: +595 981 234 567"

    scrubbed = scrub_pattern_pii("Orders: +595 981 234 567", allowed_texts=[evidence])

    assert scrubbed == "Orders: +595 981 234 567"
    assert "[GOVERNMENT_ID]" not in scrubbed


def test_unresolved_government_id_placeholder_line_is_removed() -> None:
    """The 2026-09-01 live finding: an unresolved [GOVERNMENT_ID] placeholder
    (or any of the other high-risk categories) must never survive to a
    user-visible response - this cleanup pass previously only knew about
    ADDRESS/EMAIL/PHONE/NAME/PII and silently missed the higher-risk set."""
    answer = "Contact Support:\n* Orders: +595 [GOVERNMENT_ID]\n* WhatsApp: +595 [GOVERNMENT_ID]\nEmail: info@example.com"

    cleaned = remove_unresolved_pii_placeholders(answer)

    assert "[GOVERNMENT_ID]" not in cleaned
    assert "Email: info@example.com" in cleaned


def test_unresolved_bank_account_and_payment_card_placeholders_are_removed() -> None:
    answer = "Bank: [BANK_ACCOUNT]\nCard on file: [PAYMENT_CARD]\nSSN: [SSN]\nID: [CREDIT_DEBIT_NUMBER]"

    cleaned = remove_unresolved_pii_placeholders(answer)

    for placeholder in ("[BANK_ACCOUNT]", "[PAYMENT_CARD]", "[SSN]", "[CREDIT_DEBIT_NUMBER]"):
        assert placeholder not in cleaned


def test_valid_payment_card_is_scrubbed_but_long_phone_is_not_misclassified() -> None:
    assert scrub_pattern_pii("Card 4111 1111 1111 1111") == "Card [PAYMENT_CARD]"
    assert "[PAYMENT_CARD]" not in scrub_pattern_pii("Office +44 1926 626 600")


def test_valid_iban_is_scrubbed_in_language_neutral_fallback() -> None:
    scrubbed = scrub_pattern_pii("Mon IBAN est GB82 WEST 1234 5698 7654 32")

    assert scrubbed == "Mon IBAN est [BANK_ACCOUNT]"
    assert contains_sensitive_pii_placeholder(scrubbed) is True


def test_invalid_iban_like_policy_reference_is_not_scrubbed() -> None:
    scrubbed = scrub_pattern_pii("Policy reference GB00 TEST 1234 5678 9012 34")

    assert "[BANK_ACCOUNT]" not in scrubbed


def test_scrub_pii_checks_content_after_first_comprehend_window() -> None:
    prefix = "x" * 4500
    text = f"{prefix} Contact late@example.com"
    comprehend = MagicMock()
    comprehend.detect_pii_entities.side_effect = [
        {"Entities": []},
        {"Entities": [{"BeginOffset": 9, "EndOffset": 25, "Type": "EMAIL"}]},
    ]
    clients = SimpleNamespace(comprehend=comprehend)

    with patch("services.pii.get_aws_clients", return_value=clients):
        scrubbed = scrub_pii(text, "cid", "en")

    assert scrubbed == f"{prefix} Contact [EMAIL]"
    assert comprehend.detect_pii_entities.call_count == 2


def test_pii_circuit_opens_after_repeated_remote_failures() -> None:
    pii_module._record_pii_success()
    for _ in range(pii_module._PII_CIRCUIT_FAILURE_LIMIT):
        pii_module._record_pii_failure()

    assert pii_module._pii_circuit_is_open() is True

    pii_module._record_pii_success()
    assert pii_module._pii_circuit_is_open() is False
