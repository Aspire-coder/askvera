"""Tests for managed widget configuration safety and compatibility."""

from pathlib import Path

import pytest

from app.widget_registry.rds_provider import RdsWidgetRegistryProvider
from app.widget_registry import rds_provider
from app.widget_registry.service import WIDGET_REGISTRY_VERSION_KEY, WidgetRegistryService
from config import settings
from services import widget_configs


def _config(**updates) -> dict:
    values = {
        "name": "Customer portal",
        "customer": "Example",
        "allowed_origins": ["https://portal.example.com"],
        "markets": ["US"],
        "languages": ["en"],
        "default_market": "US",
        "default_language": "en",
        "display_name": "AskVera",
        "greeting": "How can I help?",
        "accent_color": "#2F7D4E",
        "position": "bottom-right",
        "legal_version": "2026.1",
        "rate_limit_tier": "standard",
        "usage_cap": 1000,
    }
    values.update(updates)
    return values


def test_widget_config_accepts_exact_https_origin() -> None:
    clean = widget_configs.validate_widget_config(_config())

    assert clean["allowed_origins"] == ["https://portal.example.com"]
    assert clean["default_market"] == "US"


def test_widget_config_rejects_undeployed_legal_version(monkeypatch) -> None:
    monkeypatch.setattr(settings, "LEGAL_VERSION", "2026.1")

    with pytest.raises(ValueError, match="currently deployed"):
        widget_configs.validate_widget_config(_config(legal_version="2027.1"))


@pytest.mark.parametrize(
    "origin",
    [
        "portal.example.com",
        "https://portal.example.com/path",
        "https://portal.example.com?debug=true",
        "https://user:pass@portal.example.com",
        "*.example.com",
    ],
)
def test_widget_config_rejects_non_origin_values(origin: str) -> None:
    with pytest.raises(ValueError, match="Invalid allowed origin"):
        widget_configs.validate_widget_config(_config(allowed_origins=[origin]))


def test_embed_code_contains_public_configuration_only(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WIDGET_LOADER_URL", "https://cdn.example.com/widget.js")
    monkeypatch.setattr(settings, "WIDGET_STYLES_URL", "https://cdn.example.com/widget.css")

    snippet = widget_configs.widget_embed_code("wgt_public", "bottom-left")

    assert 'widgetId: "wgt_public"' in snippet
    assert 'position: "bottom-left"' in snippet
    assert "widget.js" in snippet
    assert not any(word in snippet.lower() for word in ("secret", "password", "private_key"))


def test_runtime_provider_remains_legacy_when_flag_is_off(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WIDGET_CONFIG_RUNTIME_ENABLED", False)
    monkeypatch.setattr(settings, "WIDGET_REGISTRY_PROVIDER", "json")
    monkeypatch.setattr(settings, "WIDGET_REGISTRY_JSON", "[]")

    service = WidgetRegistryService()

    assert service.provider_name == "json"


def test_runtime_provider_uses_rds_only_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WIDGET_CONFIG_RUNTIME_ENABLED", True)

    service = WidgetRegistryService()

    assert isinstance(service._provider, RdsWidgetRegistryProvider)


def test_distributed_invalidation_refreshes_another_process(monkeypatch) -> None:
    class SharedCache:
        def __init__(self):
            self.version = 0

        def get(self, key):
            assert key == WIDGET_REGISTRY_VERSION_KEY
            return str(self.version)

        def incr(self, key):
            assert key == WIDGET_REGISTRY_VERSION_KEY
            self.version += 1
            return self.version

    class Provider:
        name = "test"

        def __init__(self):
            self.value = None

        def reload(self):
            return None

        def get_widget(self, _widget_id):
            return self.value

        def list_widgets(self):
            return []

    shared_cache = SharedCache()
    provider_a = Provider()
    provider_b = Provider()
    service_a = WidgetRegistryService(provider_a)
    service_b = WidgetRegistryService(provider_b)
    monkeypatch.setattr(
        "app.widget_registry.service.get_cache_client",
        lambda: shared_cache,
    )
    monkeypatch.setattr(settings, "WIDGET_CONFIG_RUNTIME_ENABLED", True)
    monkeypatch.setattr(settings, "WIDGET_REGISTRY_CACHE_SECONDS", 300)
    monkeypatch.setattr(service_a, "_build_provider", lambda: provider_a)

    provider_b.value = "old"
    assert service_b.get_widget("widget") == "old"
    provider_b.value = "new"
    assert service_b.get_widget("widget") == "old"

    service_a.invalidate()

    assert service_b.get_widget("widget") == "new"


def test_rotated_public_key_makes_old_key_unresolvable(monkeypatch) -> None:
    config = {
        "id": "widget-1",
        "public_key": "wgt_new",
        "display_name": "AskVera",
        "allowed_origins": ["https://portal.example.com"],
        "status": "active",
        "legal_version": "2026.1",
        "created_by": "admin",
        "accent_color": "#2F7D4E",
        "greeting": "Hello",
        "position": "bottom-right",
        "markets": ["US"],
        "languages": ["en"],
        "default_market": "US",
        "default_language": "en",
        "rate_limit_tier": "standard",
        "usage_cap": None,
        "key_version": 2,
    }
    monkeypatch.setattr(
        rds_provider,
        "get_widget_config",
        lambda identifier, public=False: config if public and identifier == "wgt_new" else None,
    )
    provider = RdsWidgetRegistryProvider()

    assert provider.get_widget("wgt_old") is None
    assert provider.get_widget("wgt_new").widgetId == "wgt_new"


def test_feature_flags_default_to_disabled() -> None:
    assert settings.FEEDBACK_EXPECTED_ANSWER_ENABLED is False
    assert settings.ADMIN_RBAC_ENABLED is False
    assert settings.ADMIN_USER_MANAGEMENT_ENABLED is False
    assert settings.WIDGET_CONFIG_ADMIN_ENABLED is False
    assert settings.WIDGET_CONFIG_RUNTIME_ENABLED is False


def test_forward_only_migrations_define_required_schema() -> None:
    migrations = Path(__file__).resolve().parents[2] / "migrations"
    feedback = (migrations / "20260728_01_feedback_expected_answer.sql").read_text(encoding="utf-8")
    admin = (migrations / "20260728_02_admin_rbac.sql").read_text(encoding="utf-8")
    widgets = (migrations / "20260728_03_widget_configs.sql").read_text(encoding="utf-8")

    assert "expected_answer_present BOOLEAN NOT NULL DEFAULT false" in feedback
    assert "CREATE TABLE IF NOT EXISTS admin_users" in admin
    assert "CREATE TABLE IF NOT EXISTS admin_user_scopes" in admin
    assert "CREATE TABLE IF NOT EXISTS admin_audit_log" in admin
    assert "CREATE TABLE IF NOT EXISTS widget_configs" in widgets
    assert "public_key TEXT NOT NULL UNIQUE" in widgets
