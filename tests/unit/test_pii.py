"""Unit tests for Comprehend PII scrubbing."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.pii import _pii_language_code, scrub_pii


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
