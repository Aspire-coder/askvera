"""Origin allowlist validation for embedded widgets."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from config import settings


LOCALHOST_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass(frozen=True)
class OriginValidation:
    """Result of checking a request origin against a widget allowlist."""

    allowed: bool
    normalized_origin: str = ""
    reason: str = ""


def normalize_origin(origin: str | None) -> str:
    """Return a canonical origin string or an empty string when invalid."""
    if not origin:
        return ""
    raw_origin = origin.strip().rstrip("/")
    parsed = urlparse(raw_origin)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    hostname = parsed.hostname.lower()
    if parsed.port:
        return f"{parsed.scheme}://{hostname}:{parsed.port}"
    return f"{parsed.scheme}://{hostname}"


def _hostname(origin: str) -> str:
    parsed = urlparse(origin)
    return (parsed.hostname or "").lower()


def _origin_scheme(origin: str) -> str:
    return urlparse(origin).scheme.lower()


def _is_localhost(origin: str) -> bool:
    return _hostname(origin) in LOCALHOST_HOSTS


def _wildcard_matches(pattern: str, origin: str) -> bool:
    normalized_pattern = pattern.strip().rstrip("/")
    scheme = ""
    wildcard_host = normalized_pattern
    if "://" in normalized_pattern:
        parsed_pattern = urlparse(normalized_pattern)
        scheme = parsed_pattern.scheme.lower()
        wildcard_host = parsed_pattern.hostname or ""

    wildcard_host = wildcard_host.lower()
    if not wildcard_host.startswith("*."):
        return False

    if scheme and scheme != _origin_scheme(origin):
        return False

    suffix = wildcard_host[2:]
    host = _hostname(origin)
    return host.endswith(f".{suffix}") and host != suffix


def is_origin_allowed(origin: str | None, allowed_origins: list[str]) -> OriginValidation:
    """Validate an origin against exact, wildcard, and local development rules."""
    normalized_origin = normalize_origin(origin)
    if not normalized_origin:
        return OriginValidation(False, reason="missing_or_invalid_origin")

    if _is_localhost(normalized_origin) and not settings.WIDGET_ALLOW_LOCALHOST_ORIGINS:
        return OriginValidation(False, normalized_origin, "localhost_not_allowed")

    normalized_allowed = {normalize_origin(value) for value in allowed_origins if not value.strip().startswith("*.")}
    if normalized_origin in normalized_allowed:
        return OriginValidation(True, normalized_origin)

    for allowed_origin in allowed_origins:
        if _wildcard_matches(allowed_origin, normalized_origin):
            return OriginValidation(True, normalized_origin)

    return OriginValidation(False, normalized_origin, "origin_not_allowed")
