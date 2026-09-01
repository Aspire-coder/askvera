"""Unit tests for AWS client request budgets."""

from services.aws_clients import _client_config


def test_client_config_uses_total_attempt_budget() -> None:
    config = _client_config(read_timeout=5, max_attempts=1)

    assert config.connect_timeout == 3
    assert config.read_timeout == 5
    assert config.retries["total_max_attempts"] == 1
    assert config.retries["mode"] == "standard"
