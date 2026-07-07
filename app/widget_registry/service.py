"""Cached widget registry facade."""

from __future__ import annotations

from time import monotonic

from config import settings
from utils.logging import get_logger

from .dynamodb_provider import DynamoDbWidgetRegistryProvider
from .json_provider import JsonWidgetRegistryProvider
from .models import WidgetRegistration
from .provider import WidgetRegistryProvider

LOGGER = get_logger("app.widget_registry.service")


class WidgetRegistryService:
    """Provider-backed widget registry with a small in-memory cache."""

    def __init__(self, provider: WidgetRegistryProvider | None = None) -> None:
        self._provider = provider or self._build_provider()
        self._cache: dict[str, tuple[float, WidgetRegistration | None]] = {}

    @property
    def provider_name(self) -> str:
        """Return the active provider name."""
        return self._provider.name

    def reload(self) -> None:
        """Reload the provider and clear cached registrations."""
        self._provider = self._build_provider()
        self._provider.reload()
        self._cache.clear()
        LOGGER.info("widget_registry_reloaded", provider=self.provider_name)

    def get_widget(self, widget_id: str) -> WidgetRegistration | None:
        """Return a widget registration by ID."""
        if not widget_id:
            return None

        ttl = max(int(settings.WIDGET_REGISTRY_CACHE_SECONDS), 0)
        now = monotonic()
        cached = self._cache.get(widget_id)
        if cached and ttl and cached[0] > now:
            return cached[1]

        widget = self._provider.get_widget(widget_id)
        if ttl:
            self._cache[widget_id] = (now + ttl, widget)
        return widget

    def list_active_widgets(self) -> list[WidgetRegistration]:
        """Return active widgets. Do not use this for normal request authorization."""
        return [widget for widget in self._provider.list_widgets() if widget.status == "active"]

    def get_all_allowed_origins(self) -> set[str]:
        """Return allowed origins for active widgets."""
        origins: set[str] = set()
        for widget in self.list_active_widgets():
            origins.update(widget.allowedOrigins)
        return origins

    def _build_provider(self) -> WidgetRegistryProvider:
        provider_name = str(settings.WIDGET_REGISTRY_PROVIDER).lower()
        if provider_name == "json":
            return JsonWidgetRegistryProvider()
        if provider_name == "dynamodb":
            return DynamoDbWidgetRegistryProvider()
        raise RuntimeError(f"Unsupported WIDGET_REGISTRY_PROVIDER: {settings.WIDGET_REGISTRY_PROVIDER}")


widget_registry_service = WidgetRegistryService()
