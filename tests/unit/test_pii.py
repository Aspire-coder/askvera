"""Unit tests for Comprehend PII scrubbing."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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


def test_value_placeholder_does_not_leave_an_empty_field_label() -> None:
    answer = "Office details:\n**Physical Address:** [ADDRESS]\n**Phone:** [PHONE]\nWebsite: example.com"

    assert remove_unresolved_pii_placeholders(answer) == "Office details:\nWebsite: example.com"


def test_government_id_is_scrubbed_without_language_specific_service() -> None:
    scrubbed = scrub_pattern_pii("My identifier is 123-45-6789")

    assert scrubbed == "My identifier is [GOVERNMENT_ID]"
    assert contains_sensitive_pii_placeholder(scrubbed) is True


def test_valid_payment_card_is_scrubbed_but_long_phone_is_not_misclassified() -> None:
    assert scrub_pattern_pii("Card 4111 1111 1111 1111") == "Card [PAYMENT_CARD]"
    assert "[PAYMENT_CARD]" not in scrub_pattern_pii("Office +44 1926 626 600")
