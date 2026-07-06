"""Monitoring startup initialization."""

from __future__ import annotations

from dataclasses import dataclass, field

from config import settings
from utils.logging import get_logger

from .alarms import AlarmSetupResult, CloudWatchAlarmManager, build_alarm_definitions
from .notifications import AlarmNotificationActions, NotificationSetupResult, SNSNotificationManager

LOGGER = get_logger("app.monitoring.initializer")


@dataclass(frozen=True)
class MonitoringInitializationResult:
    """Summary of monitoring startup work."""

    enabled: bool
    alarms_created_updated: int = 0
    alarms_configured: int = 0
    alarms_failed: int = 0
    alarms_skipped: int = 0
    notification_result: NotificationSetupResult = field(
        default_factory=lambda: NotificationSetupResult(enabled=False)
    )
    failures: list[str] = field(default_factory=list)


def initialize_monitoring() -> MonitoringInitializationResult:
    """Initialize SNS notifications and CloudWatch alarms during startup."""
    if not settings.ENABLE_CLOUDWATCH_ALARMS:
        skipped = _skipped_alarm_count()
        LOGGER.info("monitoring_initialization_skipped", reason="cloudwatch_alarms_disabled")
        return MonitoringInitializationResult(enabled=False, alarms_skipped=skipped)

    LOGGER.info("monitoring_initialization_started")
    failures: list[str] = []
    notification_result = _setup_notifications(failures)
    notification_actions = _notification_actions(notification_result)
    alarm_results = _setup_alarms(notification_actions, failures)

    configured = sum(1 for result in alarm_results if result.success)
    failed = sum(1 for result in alarm_results if not result.success)
    result = MonitoringInitializationResult(
        enabled=True,
        alarms_created_updated=configured,
        alarms_configured=configured,
        alarms_failed=failed,
        alarms_skipped=0,
        notification_result=notification_result,
        failures=failures,
    )
    LOGGER.info(
        "monitoring_initialization_completed",
        alarms_created_updated=result.alarms_created_updated,
        alarms_configured=result.alarms_configured,
        alarms_failed=result.alarms_failed,
        notification_enabled=notification_result.enabled,
        subscription_count=len(notification_result.subscriptions),
        failure_count=len(result.failures),
    )
    return result


def _setup_notifications(failures: list[str]) -> NotificationSetupResult:
    try:
        manager = SNSNotificationManager()
        notification_result = manager.setup()
        if notification_result.enabled and notification_result.topic_arn:
            LOGGER.info("sns_topic_resolved", topic_arn=notification_result.topic_arn)
        if notification_result.subscriptions:
            LOGGER.info(
                "email_subscriptions_processed",
                subscription_count=len(notification_result.subscriptions),
                pending_count=sum(1 for item in notification_result.subscriptions if item.status == "pending"),
                failed_count=sum(1 for item in notification_result.subscriptions if item.status == "failed"),
            )
        failures.extend(notification_result.errors)
        return notification_result
    except Exception as exc:  # noqa: BLE001 - monitoring must not block API startup.
        LOGGER.exception("monitoring_initialization_failed", stage="notifications")
        failures.append(str(exc))
        return NotificationSetupResult(enabled=settings.ENABLE_ALARM_NOTIFICATIONS, errors=[str(exc)])


def _notification_actions(notification_result: NotificationSetupResult) -> AlarmNotificationActions:
    if not notification_result.enabled or not notification_result.topic_arn:
        return AlarmNotificationActions()
    actions = AlarmNotificationActions(
        alarm_actions=[notification_result.topic_arn],
        ok_actions=[notification_result.topic_arn] if settings.ENABLE_OK_NOTIFICATIONS else [],
        insufficient_data_actions=[
            notification_result.topic_arn
        ] if settings.ENABLE_INSUFFICIENT_DATA_NOTIFICATIONS else [],
    )
    if actions.alarm_actions:
        LOGGER.info(
            "alarm_notification_actions_ready",
            alarm_actions=len(actions.alarm_actions),
            ok_actions=len(actions.ok_actions),
            insufficient_data_actions=len(actions.insufficient_data_actions),
        )
    return actions


def _setup_alarms(
    notification_actions: AlarmNotificationActions,
    failures: list[str],
) -> list[AlarmSetupResult]:
    try:
        definitions = build_alarm_definitions()
        manager = CloudWatchAlarmManager(notification_actions=notification_actions)
        results = manager.put_alarms(definitions)
        failed = [result for result in results if not result.success]
        failures.extend(result.error for result in failed if result.error)
        LOGGER.info(
            "cloudwatch_alarms_created",
            alarm_count=len(results),
            failed_count=len(failed),
        )
        return results
    except Exception as exc:  # noqa: BLE001 - monitoring must not block API startup.
        LOGGER.exception("monitoring_initialization_failed", stage="alarms")
        failures.append(str(exc))
        return []


def _skipped_alarm_count() -> int:
    try:
        return len(build_alarm_definitions())
    except Exception:  # noqa: BLE001 - disabled monitoring should stay quiet and safe.
        return 0
