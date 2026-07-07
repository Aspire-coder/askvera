"""DynamoDB-backed widget registry provider."""

from __future__ import annotations

from typing import Any

from config import settings
from .models import WidgetRegistration


class DynamoDbWidgetRegistryProvider:
    """Read widget registrations from the AskVeraWidgets DynamoDB table."""

    name = "dynamodb"

    def __init__(self) -> None:
        self._table = None

    def reload(self) -> None:
        """Drop the cached table handle so settings changes are picked up."""
        self._table = None

    def get_widget(self, widget_id: str) -> WidgetRegistration | None:
        """Return one registration by widget ID."""
        if not widget_id:
            return None

        response = self._get_table().get_item(Key={"widgetId": widget_id})
        item = response.get("Item")
        if not item:
            return None
        return WidgetRegistration.model_validate(self._normalize_item(item))

    def list_widgets(self) -> list[WidgetRegistration]:
        """Return all registrations. Avoid using this in the request path."""
        response = self._get_table().scan()
        items = response.get("Items", [])
        while "LastEvaluatedKey" in response:
            response = self._get_table().scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response.get("Items", []))
        return [WidgetRegistration.model_validate(self._normalize_item(item)) for item in items]

    def _get_table(self) -> Any:
        if self._table is None:
            import boto3

            dynamodb = boto3.resource("dynamodb", region_name=settings.AWS_REGION)
            self._table = dynamodb.Table(settings.WIDGET_REGISTRY_TABLE)
        return self._table

    def _normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Normalize DynamoDB-decoded values before Pydantic validation."""
        normalized = dict(item)
        if "version" in normalized:
            normalized["version"] = int(normalized["version"])
        return normalized
