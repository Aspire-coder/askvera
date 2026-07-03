"""Backward-compatible exports for consent service functions."""

from services.consent_service import has_valid_consent, record_consent

__all__ = ["has_valid_consent", "record_consent"]
