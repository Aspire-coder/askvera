"""RDS-backed widget registry provider for managed widget configurations."""

from __future__ import annotations

from app.widget_registry.models import WidgetRegistration
from services.widget_configs import get_widget_config, list_widget_configs


class RdsWidgetRegistryProvider:
    name = "rds"

    def reload(self) -> None:
        return None

    def get_widget(self, widget_id: str) -> WidgetRegistration | None:
        config = get_widget_config(widget_id, public=True)
        return self._registration(config) if config else None

    def list_widgets(self) -> list[WidgetRegistration]:
        return [self._registration(config) for config in list_widget_configs()]

    @staticmethod
    def _registration(config: dict) -> WidgetRegistration:
        return WidgetRegistration(
            widgetId=config["public_key"],
            organizationId=config["id"],
            companyName=config["display_name"],
            allowedOrigins=config["allowed_origins"],
            status=config["status"],
            legalVersion=config["legal_version"],
            createdBy=config["created_by"],
            metadata={
                "primaryColor": config["accent_color"],
                "greeting": config["greeting"],
                "logo": config.get("logo_url", ""),
                "position": config["position"],
                "markets": config["markets"],
                "languages": config["languages"],
                "defaultMarket": config["default_market"],
                "defaultLanguage": config["default_language"],
                "rateLimitTier": config["rate_limit_tier"],
                "usageCap": config["usage_cap"],
                "keyVersion": config["key_version"],
            },
        )
