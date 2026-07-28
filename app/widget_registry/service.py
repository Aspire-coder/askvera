"""Cached widget registry facade."""

from __future__ import annotations

from time import monotonic

import redis

from config import settings
from services.cache import get_cache_client
from utils.logging import get_logger

from .dynamodb_provider import DynamoDbWidgetRegistryProvider
from .json_provider import JsonWidgetRegistryProvider
from .models import WidgetRegistration
from .provider import WidgetRegistryProvider
from .rds_provider import RdsWidgetRegistryProvider

LOGGER = get_logger("app.widget_registry.service")
WIDGET_REGISTRY_VERSION_KEY = "ask-vera:widget-registry:version"


class WidgetRegistryService:
    """Provider-backed widget registry with a small in-memory cache."""

    def __init__(self, provider: WidgetRegistryProvider | None = None) -> None:
        self._provider = provider or self._build_provider()
        self._cache: dict[str, tuple[float, WidgetRegistration | None]] = {}
        self._origins_cache: tuple[float, set[str]] | None = None
        self._distributed_version: int | None = None

    @property
    def provider_name(self) -> str:
        """Return the active provider name."""
        return self._provider.name

    def reload(self) -> None:
        """Reload the provider and clear cached registrations."""
        self._provider = self._build_provider()
        self._provider.reload()
        self._clear_local_cache()
        LOGGER.info("widget_registry_reloaded", provider=self.provider_name)

    def invalidate(self) -> None:
        """Invalidate this process and notify other processes through Valkey."""
        self.reload()
        client = get_cache_client()
        if client is None:
            return
        try:
            self._distributed_version = int(client.incr(WIDGET_REGISTRY_VERSION_KEY))
        except (redis.RedisError, TypeError, ValueError):
            LOGGER.exception("widget_registry_invalidation_publish_failed")

    def _clear_local_cache(self) -> None:
        self._cache.clear()
        self._origins_cache = None

    def _sync_distributed_invalidation(self) -> None:
        client = get_cache_client()
        if client is None:
            return
        try:
            raw_version = client.get(WIDGET_REGISTRY_VERSION_KEY)
            version = int(raw_version or 0)
        except (redis.RedisError, TypeError, ValueError):
            LOGGER.warning("widget_registry_invalidation_check_failed")
            return
        if self._distributed_version is None:
            self._distributed_version = version
        elif version != self._distributed_version:
            self._distributed_version = version
            self._clear_local_cache()
            LOGGER.info("widget_registry_distributed_invalidation_applied")

    def _cache_ttl(self) -> int:
        ttl = max(int(settings.WIDGET_REGISTRY_CACHE_SECONDS), 0)
        return min(ttl, 30) if settings.WIDGET_CONFIG_RUNTIME_ENABLED else ttl

    def get_widget(self, widget_id: str) -> WidgetRegistration | None:
        """Return a widget registration by ID."""
        if not widget_id:
            return None

        self._sync_distributed_invalidation()
        ttl = self._cache_ttl()
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
        self._sync_distributed_invalidation()
        ttl = self._cache_ttl()
        now = monotonic()
        if self._origins_cache and ttl and self._origins_cache[0] > now:
            return set(self._origins_cache[1])

        origins: set[str] = set()
        for widget in self.list_active_widgets():
            origins.update(widget.allowedOrigins)

        if ttl:
            self._origins_cache = (now + ttl, set(origins))
        return origins

    def _build_provider(self) -> WidgetRegistryProvider:
        if settings.WIDGET_CONFIG_RUNTIME_ENABLED:
            return RdsWidgetRegistryProvider()
        provider_name = str(settings.WIDGET_REGISTRY_PROVIDER).lower()
        if provider_name == "json":
            return JsonWidgetRegistryProvider()
        if provider_name == "dynamodb":
            return DynamoDbWidgetRegistryProvider()
        raise RuntimeError(f"Unsupported WIDGET_REGISTRY_PROVIDER: {settings.WIDGET_REGISTRY_PROVIDER}")


widget_registry_service = WidgetRegistryService()
