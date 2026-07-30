"""Dependency-free redaction helpers for operational telemetry."""

import re

EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])", re.UNICODE)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{5,}\d)(?!\w)", re.UNICODE)
GOVERNMENT_ID_RE = re.compile(r"(?<!\d)\d{3}[- ]?\d{2}[- ]?\d{4}(?!\d)", re.UNICODE)
PAYMENT_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)", re.UNICODE)
IBAN_RE = re.compile(
    r"(?<![A-Z0-9])(?:[A-Z]{2}\d{2}(?:[ -]?[A-Z0-9]){11,30})(?![A-Z0-9])",
    re.IGNORECASE | re.UNICODE,
)


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


def _valid_iban(candidate: str) -> bool:
    compact = re.sub(r"[\s-]+", "", candidate).upper()
    if not 15 <= len(compact) <= 34:
        return False
    if not compact[:2].isalpha() or not compact[2:4].isdigit() or not compact.isalnum():
        return False
    rearranged = compact[4:] + compact[:4]
    remainder = 0
    for character in rearranged:
        digits = character if character.isdigit() else str(ord(character) - ord("A") + 10)
        for digit in digits:
            remainder = (remainder * 10 + int(digit)) % 97
    return remainder == 1


def redact_ibans(text: str, replacement: str = "[BANK_ACCOUNT]") -> str:
    """Redact international bank account numbers that pass ISO 13616 mod-97."""
    return IBAN_RE.sub(
        lambda match: replacement if _valid_iban(match.group(0)) else match.group(0),
        text,
    )


def redact_common_pii(text: str) -> str:
    """Mask common language-neutral email and phone values for telemetry."""
    redacted = GOVERNMENT_ID_RE.sub("[GOVERNMENT_ID]", text or "")
    redacted = redact_payment_cards(redacted)
    redacted = redact_ibans(redacted)
    return PHONE_RE.sub("[PHONE]", EMAIL_RE.sub("[EMAIL]", redacted))
