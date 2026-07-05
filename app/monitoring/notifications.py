"""SNS notification management for CloudWatch alarms."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import settings
from utils.logging import get_logger

LOGGER = get_logger("app.monitoring.notifications")


@dataclass(frozen=True)
class SubscriptionResult:
    """Result for one SNS email subscription."""

    endpoint: str
    status: str
    subscription_arn: str = ""
    error: str = ""


@dataclass(frozen=True)
class NotificationSetupResult:
    """Result from resolving SNS topic and subscriptions."""

    enabled: bool
    topic_arn: str = ""
    subscriptions: list[SubscriptionResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AlarmNotificationActions:
    """Alarm action ARNs for CloudWatch alarm payloads."""

    alarm_actions: list[str] = field(default_factory=list)
    ok_actions: list[str] = field(default_factory=list)
    insufficient_data_actions: list[str] = field(default_factory=list)


class SNSNotificationManager:
    """Manage SNS topic and email subscriptions for CloudWatch alarms."""

    def __init__(
        self,
        client: Any | None = None,
        enabled: bool | None = None,
        topic_arn: str | None = None,
        topic_name: str | None = None,
        email_subscriptions: str | list[str] | None = None,
        create_topic_if_missing: bool | None = None,
        enable_ok_notifications: bool | None = None,
        enable_insufficient_data_notifications: bool | None = None,
    ) -> None:
        self.enabled = settings.ENABLE_ALARM_NOTIFICATIONS if enabled is None else enabled
        self.topic_arn = topic_arn if topic_arn is not None else settings.SNS_TOPIC_ARN
        self.topic_name = topic_name or settings.SNS_TOPIC_NAME
        self.email_subscriptions = _parse_email_subscriptions(
            settings.SNS_EMAIL_SUBSCRIPTIONS if email_subscriptions is None else email_subscriptions
        )
        self.create_topic_if_missing = (
            settings.CREATE_SNS_TOPIC_IF_MISSING
            if create_topic_if_missing is None
            else create_topic_if_missing
        )
        self.enable_ok_notifications = (
            settings.ENABLE_OK_NOTIFICATIONS
            if enable_ok_notifications is None
            else enable_ok_notifications
        )
        self.enable_insufficient_data_notifications = (
            settings.ENABLE_INSUFFICIENT_DATA_NOTIFICATIONS
            if enable_insufficient_data_notifications is None
            else enable_insufficient_data_notifications
        )
        self.client = client
        if self.enabled and self.client is None:
            self.client = self._build_client()

    def validate(self) -> None:
        """Validate notification configuration before setup."""
        if not self.enabled:
            return
        if not self.topic_arn and not self.topic_name:
            raise ValueError("SNS topic ARN or topic name is required when alarm notifications are enabled.")
        if not self.topic_arn and not self.create_topic_if_missing:
            raise ValueError("SNS_TOPIC_ARN is required unless CREATE_SNS_TOPIC_IF_MISSING=true.")

    def setup(self) -> NotificationSetupResult:
        """Resolve topic and subscribe configured email recipients."""
        if not self.enabled:
            LOGGER.info("alarm_notifications_disabled")
            return NotificationSetupResult(enabled=False)
        errors: list[str] = []
        subscriptions: list[SubscriptionResult] = []
        try:
            self.validate()
            topic_arn = self.resolve_topic_arn()
            if not topic_arn:
                return NotificationSetupResult(enabled=True, errors=["SNS topic ARN could not be resolved."])
            subscriptions = self.ensure_email_subscriptions(topic_arn)
            return NotificationSetupResult(enabled=True, topic_arn=topic_arn, subscriptions=subscriptions)
        except Exception as exc:  # noqa: BLE001 - setup reports failures without breaking callers.
            LOGGER.warning("alarm_notification_setup_failed", error=str(exc))
            errors.append(str(exc))
            return NotificationSetupResult(enabled=True, topic_arn=self.topic_arn, subscriptions=subscriptions, errors=errors)

    def resolve_topic_arn(self) -> str:
        """Return configured topic ARN or create/reuse an SNS topic by name."""
        if not self.enabled:
            return ""
        if self.topic_arn:
            LOGGER.info("sns_topic_configured", topic_arn=self.topic_arn)
            return self.topic_arn
        if not self.client:
            raise RuntimeError("SNS client is unavailable.")
        if not self.create_topic_if_missing:
            raise ValueError("SNS topic creation is disabled and no topic ARN was provided.")
        response = self.client.create_topic(Name=self.topic_name)
        self.topic_arn = response["TopicArn"]
        LOGGER.info("sns_topic_created_or_reused", topic_name=self.topic_name, topic_arn=self.topic_arn)
        return self.topic_arn

    def ensure_email_subscriptions(self, topic_arn: str) -> list[SubscriptionResult]:
        """Subscribe missing email endpoints without duplicating existing subscriptions."""
        if not self.enabled or not self.email_subscriptions:
            return []
        if not self.client:
            raise RuntimeError("SNS client is unavailable.")
        existing = self._existing_email_subscriptions(topic_arn)
        results: list[SubscriptionResult] = []
        for endpoint in self.email_subscriptions:
            current = existing.get(endpoint.lower())
            if current:
                status = "pending" if current == "PendingConfirmation" else "confirmed"
                results.append(SubscriptionResult(endpoint=endpoint, status=status, subscription_arn=current))
                LOGGER.info("sns_subscription_already_present", endpoint=endpoint, status=status)
                continue
            try:
                response = self.client.subscribe(
                    TopicArn=topic_arn,
                    Protocol="email",
                    Endpoint=endpoint,
                    ReturnSubscriptionArn=True,
                )
                subscription_arn = response.get("SubscriptionArn", "")
                status = "pending" if subscription_arn == "pending confirmation" else "subscribed"
                results.append(SubscriptionResult(endpoint=endpoint, status=status, subscription_arn=subscription_arn))
                LOGGER.info("sns_subscription_added", endpoint=endpoint, status=status)
            except Exception as exc:  # noqa: BLE001 - one bad email should not stop other setup work.
                LOGGER.warning("sns_subscription_failed", endpoint=endpoint, error=str(exc))
                results.append(SubscriptionResult(endpoint=endpoint, status="failed", error=str(exc)))
        return results

    def alarm_actions(self, topic_arn: str | None = None) -> AlarmNotificationActions:
        """Return CloudWatch action lists for alarm payloads."""
        if not self.enabled:
            return AlarmNotificationActions()
        arn = topic_arn or self.topic_arn
        if not arn:
            return AlarmNotificationActions()
        actions = [arn]
        return AlarmNotificationActions(
            alarm_actions=actions,
            ok_actions=actions if self.enable_ok_notifications else [],
            insufficient_data_actions=actions if self.enable_insufficient_data_notifications else [],
        )

    def _existing_email_subscriptions(self, topic_arn: str) -> dict[str, str]:
        existing: dict[str, str] = {}
        next_token: str | None = None
        while True:
            kwargs: dict[str, Any] = {"TopicArn": topic_arn}
            if next_token:
                kwargs["NextToken"] = next_token
            response = self.client.list_subscriptions_by_topic(**kwargs)
            for subscription in response.get("Subscriptions", []):
                if subscription.get("Protocol") != "email":
                    continue
                endpoint = str(subscription.get("Endpoint", "")).lower()
                arn = str(subscription.get("SubscriptionArn", ""))
                if endpoint:
                    existing[endpoint] = arn
            next_token = response.get("NextToken")
            if not next_token:
                return existing

    @staticmethod
    def _build_client() -> Any | None:
        try:
            import boto3

            return boto3.client("sns", region_name=settings.AWS_REGION)
        except Exception as exc:  # noqa: BLE001 - notification setup can be disabled if SDK/client is unavailable.
            LOGGER.warning("sns_client_init_failed", error=str(exc))
            return None


def _parse_email_subscriptions(value: str | list[str]) -> list[str]:
    """Parse comma-separated email subscription configuration."""
    if isinstance(value, list):
        raw_values = value
    else:
        raw_values = value.split(",")
    deduped: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        email = raw.strip()
        key = email.lower()
        if not email or key in seen:
            continue
        seen.add(key)
        deduped.append(email)
    return deduped
