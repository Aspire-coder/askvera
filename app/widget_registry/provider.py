"""Provider interface for widget registry backends."""

from __future__ import annotations

from typing import Protocol

from .models import WidgetRegistration


class WidgetRegistryProvider(Protocol):
    """Storage backend for widget registrations."""

    name: str

    def get_widget(self, widget_id: str) -> WidgetRegistration | None:
        """Return one widget registration by ID."""
        ...

    def list_widgets(self) -> list[WidgetRegistration]:
        """Return known widget registrations."""
        ...

    def reload(self) -> None:
        """Refresh provider state when configuration changes."""
        ...
