"""Unit tests for monitoring startup initialization."""

from app.monitoring.alarms import AlarmDefinition, AlarmSetupResult
from app.monitoring.notifications import NotificationSetupResult, SubscriptionResult
from config import settings


def _set_setting(name: str, value):
    original = getattr(settings, name)
    setattr(settings, name, value)
    return original


def _restore_setting(name: str, value) -> None:
    setattr(settings, name, value)


def test_initialize_monitoring_skips_when_cloudwatch_alarms_disabled() -> None:
    from app.monitoring import initializer

    original = _set_setting("ENABLE_CLOUDWATCH_ALARMS", False)
    try:
        result = initializer.initialize_monitoring()
    finally:
        _restore_setting("ENABLE_CLOUDWATCH_ALARMS", original)

    assert result.enabled is False
    assert result.alarms_created_updated == 0
    assert result.alarms_failed == 0
    assert result.alarms_skipped >= 0


def test_initialize_monitoring_configures_notifications_and_alarms() -> None:
    from app.monitoring import initializer

    class FakeSNSManager:
        def setup(self):
            return NotificationSetupResult(
                enabled=True,
                topic_arn="arn:topic",
                subscriptions=[
                    SubscriptionResult(endpoint="ops@example.com", status="pending"),
                ],
            )

    class FakeAlarmManager:
        def __init__(self, notification_actions):
            self.notification_actions = notification_actions

        def put_alarms(self, definitions):
            assert self.notification_actions.alarm_actions == ["arn:topic"]
            assert self.notification_actions.ok_actions == ["arn:topic"]
            return [AlarmSetupResult(name=definition.name, success=True) for definition in definitions]

    original_alarms = _set_setting("ENABLE_CLOUDWATCH_ALARMS", True)
    original_ok = _set_setting("ENABLE_OK_NOTIFICATIONS", True)
    original_insufficient = _set_setting("ENABLE_INSUFFICIENT_DATA_NOTIFICATIONS", False)
    original_sns_manager = initializer.SNSNotificationManager
    original_alarm_manager = initializer.CloudWatchAlarmManager
    original_build = initializer.build_alarm_definitions
    try:
        initializer.SNSNotificationManager = FakeSNSManager
        initializer.CloudWatchAlarmManager = FakeAlarmManager
        initializer.build_alarm_definitions = lambda: [
            AlarmDefinition(name="AskVera-Test", description="Test", metric_name="TotalRequests")
        ]
        result = initializer.initialize_monitoring()
    finally:
        initializer.SNSNotificationManager = original_sns_manager
        initializer.CloudWatchAlarmManager = original_alarm_manager
        initializer.build_alarm_definitions = original_build
        _restore_setting("ENABLE_CLOUDWATCH_ALARMS", original_alarms)
        _restore_setting("ENABLE_OK_NOTIFICATIONS", original_ok)
        _restore_setting("ENABLE_INSUFFICIENT_DATA_NOTIFICATIONS", original_insufficient)

    assert result.enabled is True
    assert result.alarms_created_updated == 1
    assert result.alarms_configured == 1
    assert result.alarms_failed == 0
    assert result.notification_result.topic_arn == "arn:topic"
    assert len(result.notification_result.subscriptions) == 1


def test_initialize_monitoring_collects_alarm_failures() -> None:
    from app.monitoring import initializer

    class FakeSNSManager:
        def setup(self):
            return NotificationSetupResult(enabled=False)

    class FakeAlarmManager:
        def __init__(self, notification_actions):
            self.notification_actions = notification_actions

        def put_alarms(self, definitions):
            return [
                AlarmSetupResult(name="AskVera-Good", success=True),
                AlarmSetupResult(name="AskVera-Bad", success=False, error="cloudwatch failed"),
            ]

    original_alarms = _set_setting("ENABLE_CLOUDWATCH_ALARMS", True)
    original_sns_manager = initializer.SNSNotificationManager
    original_alarm_manager = initializer.CloudWatchAlarmManager
    original_build = initializer.build_alarm_definitions
    try:
        initializer.SNSNotificationManager = FakeSNSManager
        initializer.CloudWatchAlarmManager = FakeAlarmManager
        initializer.build_alarm_definitions = lambda: [
            AlarmDefinition(name="AskVera-Good", description="Test", metric_name="TotalRequests"),
            AlarmDefinition(name="AskVera-Bad", description="Test", metric_name="TotalRequests"),
        ]
        result = initializer.initialize_monitoring()
    finally:
        initializer.SNSNotificationManager = original_sns_manager
        initializer.CloudWatchAlarmManager = original_alarm_manager
        initializer.build_alarm_definitions = original_build
        _restore_setting("ENABLE_CLOUDWATCH_ALARMS", original_alarms)

    assert result.alarms_created_updated == 1
    assert result.alarms_failed == 1
    assert result.failures == ["cloudwatch failed"]


def test_initialize_monitoring_continues_when_notifications_fail() -> None:
    from app.monitoring import initializer

    class FakeSNSManager:
        def setup(self):
            raise RuntimeError("sns failed")

    class FakeAlarmManager:
        def __init__(self, notification_actions):
            self.notification_actions = notification_actions

        def put_alarms(self, definitions):
            return [AlarmSetupResult(name=definition.name, success=True) for definition in definitions]

    original_alarms = _set_setting("ENABLE_CLOUDWATCH_ALARMS", True)
    original_notifications = _set_setting("ENABLE_ALARM_NOTIFICATIONS", True)
    original_sns_manager = initializer.SNSNotificationManager
    original_alarm_manager = initializer.CloudWatchAlarmManager
    original_build = initializer.build_alarm_definitions
    try:
        initializer.SNSNotificationManager = FakeSNSManager
        initializer.CloudWatchAlarmManager = FakeAlarmManager
        initializer.build_alarm_definitions = lambda: [
            AlarmDefinition(name="AskVera-Test", description="Test", metric_name="TotalRequests")
        ]
        result = initializer.initialize_monitoring()
    finally:
        initializer.SNSNotificationManager = original_sns_manager
        initializer.CloudWatchAlarmManager = original_alarm_manager
        initializer.build_alarm_definitions = original_build
        _restore_setting("ENABLE_CLOUDWATCH_ALARMS", original_alarms)
        _restore_setting("ENABLE_ALARM_NOTIFICATIONS", original_notifications)

    assert result.enabled is True
    assert result.alarms_created_updated == 1
    assert result.notification_result.enabled is True
    assert "sns failed" in result.failures
