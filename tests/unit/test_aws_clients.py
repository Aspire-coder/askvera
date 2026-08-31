"""Tests for application-scoped AWS client configuration."""

from services import aws_clients


def test_optional_bedrock_client_has_bounded_timeout_and_no_retries(monkeypatch) -> None:
    created: list[tuple[str, object]] = []

    def fake_client(service_name: str, **kwargs):
        created.append((service_name, kwargs["config"]))
        return object()

    monkeypatch.setattr(aws_clients.boto3, "client", fake_client)
    clients = aws_clients.AwsClients()

    optional_config = next(
        config
        for service_name, config in created
        if service_name == "bedrock-runtime"
        and config.read_timeout == aws_clients.settings.AWS_OPTIONAL_BEDROCK_READ_TIMEOUT_SECONDS
    )
    assert clients.bedrock_optional_runtime is not clients.bedrock_runtime
    assert optional_config.connect_timeout == 2
    assert optional_config.read_timeout == 8
    assert optional_config.retries["total_max_attempts"] == 1


def test_optional_bedrock_runtime_falls_back_for_legacy_test_clients(monkeypatch) -> None:
    runtime = object()
    monkeypatch.setattr(
        aws_clients,
        "get_aws_clients",
        lambda: type("Clients", (), {"bedrock_runtime": runtime})(),
    )

    assert aws_clients.get_optional_bedrock_runtime() is runtime
