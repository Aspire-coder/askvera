from config import settings

from app.risk.models import PolicyAction, RiskContext
from app.risk.policies.input_length_policy import InputLengthPolicy


def _context(message: str) -> RiskContext:
    return RiskContext(
        user_message=message,
        country="US",
        language="en",
        role="new-prospect",
        correlation_id="test-correlation",
    )


def test_input_length_policy_allows_ordinary_messages() -> None:
    policy = InputLengthPolicy()

    assert policy.evaluate(_context("What is the minimum order size?")) == []


def test_input_length_policy_flags_oversized_messages() -> None:
    policy = InputLengthPolicy()

    issues = policy.evaluate(_context("a" * (settings.RISK_INPUT_MAX_CHARS + 1)))

    assert len(issues) == 1
    assert issues[0].code == "INPUT_TOO_LONG"
    assert issues[0].action == PolicyAction.REFUSE


def test_input_length_policy_limit_is_read_from_settings(monkeypatch) -> None:
    """The limit must be a live settings read, not a fixed constant."""
    monkeypatch.setattr(settings, "RISK_INPUT_MAX_CHARS", 10)
    policy = InputLengthPolicy()

    assert policy.evaluate(_context("short")) == []
    issues = policy.evaluate(_context("this message is over the limit"))

    assert len(issues) == 1
    assert issues[0].code == "INPUT_TOO_LONG"
