"""Unit tests for Comprehend PII scrubbing."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.pii import scrub_pii


def test_scrub_pii_replaces_detected_entities() -> None:
    """Detected PII spans are replaced with entity labels."""
    comprehend = MagicMock()
    comprehend.detect_pii_entities.return_value = {
        "Entities": [{"BeginOffset": 11, "EndOffset": 27, "Type": "EMAIL"}]
    }
    clients = SimpleNamespace(comprehend=comprehend)
    with patch("services.pii.get_aws_clients", return_value=clients):
        assert scrub_pii("Contact me a@example.com", "cid") == "Contact me [EMAIL]"
