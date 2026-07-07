"""JSON-backed widget registry provider."""

from __future__ import annotations

import json

from config import settings
from .models import WidgetRegistration


class JsonWidgetRegistryProvider:
    """Read widget registrations from WIDGET_REGISTRY_JSON."""

    name = "json"

    def __init__(self) -> None:
        self._widgets = self._load_widgets()

    def reload(self) -> None:
        """Reload registrations from current settings."""
        self._widgets = self._load_widgets()

    def get_widget(self, widget_id: str) -> WidgetRegistration | None:
        """Return one registration by widget ID."""
        return self._widgets.get(widget_id)

    def list_widgets(self) -> list[WidgetRegistration]:
        """Return all configured registrations."""
        return list(self._widgets.values())

    def _load_widgets(self) -> dict[str, WidgetRegistration]:
        try:
            raw_registrations = json.loads(settings.WIDGET_REGISTRY_JSON or "[]")
        except json.JSONDecodeError as exc:
            raise RuntimeError("WIDGET_REGISTRY_JSON must be valid JSON.") from exc

        registrations = [WidgetRegistration.model_validate(item) for item in raw_registrations]
        return {registration.widgetId: registration for registration in registrations}
