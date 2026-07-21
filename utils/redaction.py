"""Dependency-free redaction helpers for operational telemetry."""

import re

EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])", re.UNICODE)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{5,}\d)(?!\w)", re.UNICODE)
GOVERNMENT_ID_RE = re.compile(r"(?<!\d)\d{3}[- ]?\d{2}[- ]?\d{4}(?!\d)", re.UNICODE)
PAYMENT_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)", re.UNICODE)


def _valid_payment_card(candidate: str) -> bool:
    digits = [int(character) for character in candidate if character.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def redact_payment_cards(text: str, replacement: str = "[PAYMENT_CARD]") -> str:
    """Redact card-like numbers that pass the Luhn checksum."""
    return PAYMENT_CARD_RE.sub(
        lambda match: replacement if _valid_payment_card(match.group(0)) else match.group(0),
        text,
    )


def redact_common_pii(text: str) -> str:
    """Mask common language-neutral email and phone values for telemetry."""
    redacted = GOVERNMENT_ID_RE.sub("[GOVERNMENT_ID]", text or "")
    redacted = redact_payment_cards(redacted)
    return PHONE_RE.sub("[PHONE]", EMAIL_RE.sub("[EMAIL]", redacted))
