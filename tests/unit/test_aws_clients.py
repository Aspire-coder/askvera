"""Unit tests for AWS client request budgets."""

from services.aws_clients import _client_config


def test_client_config_uses_total_attempt_budget() -> None:
    config = _client_config(read_timeout=5, max_attempts=1)

    assert config.connect_timeout == 3
    assert config.read_timeout == 5
    assert config.retries["total_max_attempts"] == 1
    assert config.retries["mode"] == "standard"


def test_long_poll_sqs_client_outwaits_the_longest_sqs_wait(monkeypatch) -> None:
    """SQS holds a long poll open for up to 20 s; a shorter read timeout fails every empty poll."""
    from unittest.mock import MagicMock

    import services.aws_clients as aws_clients
    from config import settings

    created = {}

    def fake_client(service, **kwargs):
        created.setdefault(service, []).append(kwargs["config"])
        return MagicMock()

    monkeypatch.setattr(aws_clients.boto3, "client", fake_client)
    clients = aws_clients.AwsClients()

    assert settings.AWS_SQS_LONG_POLL_READ_TIMEOUT_SECONDS > 20
    sqs_timeouts = sorted(config.read_timeout for config in created["sqs"])
    assert sqs_timeouts == [settings.AWS_READ_TIMEOUT_SECONDS, settings.AWS_SQS_LONG_POLL_READ_TIMEOUT_SECONDS]
    assert clients.sqs is not clients.sqs_long_poll
