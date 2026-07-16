"""Dependency-free redaction helpers for operational telemetry."""

import re

EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])", re.UNICODE)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{5,}\d)(?!\w)", re.UNICODE)


def redact_common_pii(text: str) -> str:
    """Mask common language-neutral email and phone values for telemetry."""
    return PHONE_RE.sub("[PHONE]", EMAIL_RE.sub("[EMAIL]", text or ""))
