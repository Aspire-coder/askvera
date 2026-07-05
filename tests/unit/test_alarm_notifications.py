"""Unit tests for alarm SNS notifications."""

from app.monitoring.alarms import AlarmDefinition, CloudWatchAlarmManager
from app.monitoring.notifications import AlarmNotificationActions, SNSNotificationManager


class FakeSNSClient:
    def __init__(self, fail_subscribe: bool = False) -> None:
        self.fail_subscribe = fail_subscribe
        self.created_topics = []
        self.subscriptions = []
        self.existing = []

    def create_topic(self, Name):
        self.created_topics.append(Name)
        return {"TopicArn": f"arn:aws:sns:us-east-1:123456789012:{Name}"}

    def list_subscriptions_by_topic(self, **kwargs):
        return {"Subscriptions": self.existing}

    def subscribe(self, **kwargs):
        if self.fail_subscribe:
            raise RuntimeError("subscribe failed")
        self.subscriptions.append(kwargs)
        return {"SubscriptionArn": "pending confirmation"}


class FakeCloudWatchClient:
    def __init__(self) -> None:
        self.calls = []

    def put_metric_alarm(self, **kwargs) -> None:
        self.calls.append(kwargs)


def _definition() -> AlarmDefinition:
    return AlarmDefinition(
        name="AskVera-Test",
        description="Test alarm",
        metric_name="TotalRequests",
        dimensions={"Environment": "test"},
    )


def test_notification_manager_parses_and_deduplicates_emails() -> None:
    manager = SNSNotificationManager(
        enabled=False,
        email_subscriptions="ops@example.com, dev@example.com, OPS@example.com",
    )

    assert manager.email_subscriptions == ["ops@example.com", "dev@example.com"]


def test_notification_manager_uses_configured_topic_arn() -> None:
    manager = SNSNotificationManager(enabled=True, topic_arn="arn:topic", email_subscriptions=[])

    result = manager.setup()

    assert result.enabled is True
    assert result.topic_arn == "arn:topic"
    assert result.errors == []


def test_notification_manager_creates_topic_when_allowed() -> None:
    client = FakeSNSClient()
    manager = SNSNotificationManager(
        client=client,
        enabled=True,
        topic_arn="",
        topic_name="askvera-alerts",
        create_topic_if_missing=True,
        email_subscriptions=[],
    )

    result = manager.setup()

    assert result.topic_arn.endswith(":askvera-alerts")
    assert client.created_topics == ["askvera-alerts"]


def test_notification_manager_subscribes_missing_emails_without_duplicates() -> None:
    client = FakeSNSClient()
    client.existing = [
        {
            "Protocol": "email",
            "Endpoint": "ops@example.com",
            "SubscriptionArn": "arn:subscription",
        }
    ]
    manager = SNSNotificationManager(
        client=client,
        enabled=True,
        topic_arn="arn:topic",
        email_subscriptions="ops@example.com,dev@example.com",
    )

    result = manager.setup()

    assert len(result.subscriptions) == 2
    assert result.subscriptions[0].status == "confirmed"
    assert result.subscriptions[1].status == "pending"
    assert len(client.subscriptions) == 1
    assert client.subscriptions[0]["Endpoint"] == "dev@example.com"


def test_notification_manager_reports_subscription_failures() -> None:
    client = FakeSNSClient(fail_subscribe=True)
    manager = SNSNotificationManager(
        client=client,
        enabled=True,
        topic_arn="arn:topic",
        email_subscriptions="ops@example.com",
    )

    result = manager.setup()

    assert result.subscriptions[0].status == "failed"
    assert "subscribe failed" in result.subscriptions[0].error


def test_alarm_actions_respect_optional_ok_and_insufficient_data_flags() -> None:
    manager = SNSNotificationManager(
        enabled=True,
        topic_arn="arn:topic",
        enable_ok_notifications=True,
        enable_insufficient_data_notifications=True,
    )

    actions = manager.alarm_actions()

    assert actions.alarm_actions == ["arn:topic"]
    assert actions.ok_actions == ["arn:topic"]
    assert actions.insufficient_data_actions == ["arn:topic"]


def test_alarm_payload_omits_actions_when_notifications_disabled() -> None:
    client = FakeCloudWatchClient()
    manager = CloudWatchAlarmManager(client=client, enabled=True)

    manager.put_alarm(_definition())

    payload = client.calls[0]
    assert "AlarmActions" not in payload
    assert "OKActions" not in payload
    assert "InsufficientDataActions" not in payload


def test_alarm_payload_includes_notification_actions_when_enabled() -> None:
    client = FakeCloudWatchClient()
    manager = CloudWatchAlarmManager(
        client=client,
        enabled=True,
        notification_actions=AlarmNotificationActions(
            alarm_actions=["arn:topic"],
            ok_actions=["arn:topic"],
            insufficient_data_actions=["arn:topic"],
        ),
    )

    manager.put_alarm(_definition())

    payload = client.calls[0]
    assert payload["AlarmActions"] == ["arn:topic"]
    assert payload["OKActions"] == ["arn:topic"]
    assert payload["InsufficientDataActions"] == ["arn:topic"]
