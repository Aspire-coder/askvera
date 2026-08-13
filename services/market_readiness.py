"""Read-only readiness checks for onboarding and operating a market."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable

from services.market_config import load_market_config, load_policy_locales
from services.support_routes import list_support_routes
from services.widget_configs import list_widget_configs

CHECK_PASS = "pass"
CHECK_WARNING = "warning"
CHECK_NOT_CONFIGURED = "not_configured"
CHECK_NOT_VERIFIED = "not_verified"


def _normalise_codes(values: Any) -> set[str]:
    if isinstance(values, str):
        try:
            values = json.loads(values)
        except json.JSONDecodeError:
            values = [values]
    if not isinstance(values, (list, tuple, set)):
        return set()
    return {str(value).upper().strip() for value in values if str(value).strip()}


def _check(key: str, label: str, status: str, detail: str) -> dict[str, str]:
    return {"key": key, "label": label, "status": status, "detail": detail}


def _route_by_market(routes: Iterable[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    return {
        str(route.get("country") or "").upper(): route
        for route in routes or []
        if str(route.get("country") or "").strip()
    }


def _widgets_by_market(widgets: Iterable[dict[str, Any]] | None) -> dict[str, bool]:
    coverage: dict[str, bool] = {}
    for widget in widgets or []:
        if str(widget.get("status") or "active").lower() not in {"active", "enabled"}:
            continue
        for market in _normalise_codes(widget.get("markets")):
            coverage[market] = True
    return coverage


def _enabled_language_codes(market: dict[str, Any]) -> set[str]:
    return {
        str(language.get("code") or "").lower()
        for language in market.get("languages", [])
        if isinstance(language, dict) and language.get("enabled", True)
    }


def _published_languages(
    policy_locales: dict[str, dict[str, Any]], code: str
) -> set[str]:
    locale = policy_locales.get(code) or policy_locales.get(code.lower()) or {}
    languages = locale.get("languages", set())
    if isinstance(languages, str):
        languages = [languages]
    return {str(language).lower() for language in languages}


def _language_view(market: dict[str, Any], published: set[str]) -> list[dict[str, Any]]:
    return [
        {
            "code": str(language.get("code") or "").lower(),
            "name": str(language.get("name") or language.get("code") or ""),
            "policy_published": str(language.get("code") or "").lower() in published,
        }
        for language in market.get("languages", [])
        if isinstance(language, dict) and language.get("enabled", True)
    ]


def build_market_readiness(
    *,
    markets: list[dict[str, Any]] | None = None,
    policy_locales: dict[str, dict[str, Any]] | None = None,
    support_routes: list[dict[str, Any]] | None = None,
    widget_configs: list[dict[str, Any]] | None = None,
    checked_at: str | None = None,
) -> dict[str, Any]:
    """Build a truthful onboarding checklist without probing the retrieval path."""
    if markets is None:
        markets = [
            market
            for market in load_market_config().get("markets", [])
            if market.get("enabled", True)
        ]
    if policy_locales is None:
        policy_locales = load_policy_locales()

    try:
        routes = _route_by_market(
            list_support_routes() if support_routes is None else support_routes
        )
    except Exception:
        routes = {}
    try:
        widgets = _widgets_by_market(
            list_widget_configs() if widget_configs is None else widget_configs
        )
    except Exception:
        widgets = {}

    results: list[dict[str, Any]] = []
    for market in markets:
        code = str(market.get("code") or "").upper()
        name = str(market.get("name") or code)
        configured_languages = _enabled_language_codes(market)
        published_languages = _published_languages(policy_locales, code)
        route = routes.get(code, {})
        route_ready = bool(
            route.get("enabled")
            and route.get("department")
            and route.get("email")
        )
        policy_status = (
            CHECK_PASS
            if configured_languages and configured_languages <= published_languages
            else CHECK_WARNING
            if published_languages
            else CHECK_NOT_CONFIGURED
        )
        policy_detail = (
            "All configured languages have published policy content."
            if configured_languages and configured_languages <= published_languages
            else "Some configured languages do not have published policy content."
            if published_languages
            else "Upload and publish the market policy before enabling it."
        )
        checks = [
            _check(
                "market_config",
                "Market configuration",
                CHECK_PASS if configured_languages else CHECK_NOT_CONFIGURED,
                "Market and enabled languages are defined."
                if configured_languages
                else "Add at least one enabled language.",
            ),
            _check(
                "policy_locales",
                "Policy locales",
                policy_status,
                policy_detail,
            ),
            _check(
                "legal",
                "Legal version",
                CHECK_PASS
                if str(market.get("privacyVersion") or "").strip()
                else CHECK_NOT_CONFIGURED,
                "Consent version is configured."
                if market.get("privacyVersion")
                else "Add the current consent version.",
            ),
            _check(
                "support",
                "Support routing",
                CHECK_PASS if route_ready else CHECK_NOT_CONFIGURED,
                "An enabled department and destination email are configured."
                if route_ready
                else "Configure a support route if this market needs handoff.",
            ),
            _check(
                "widget",
                "Widget coverage",
                CHECK_PASS if widgets.get(code) else CHECK_NOT_CONFIGURED,
                "At least one active widget includes this market."
                if widgets.get(code)
                else "Add this market to an active widget when the website is ready.",
            ),
            _check(
                "retrieval",
                "Retrieval validation",
                CHECK_NOT_VERIFIED,
                "Run the market's retrieval evaluation before production use.",
            ),
        ]
        required = {
            check["key"]: check
            for check in checks
            if check["key"] in {"market_config", "policy_locales", "legal"}
        }
        if not configured_languages or required["policy_locales"]["status"] == CHECK_NOT_CONFIGURED:
            overall = CHECK_NOT_CONFIGURED
        elif any(
            check["status"] in {CHECK_WARNING, CHECK_NOT_CONFIGURED}
            for check in required.values()
        ):
            overall = CHECK_WARNING
        else:
            overall = CHECK_PASS
        results.append(
            {
                "code": code,
                "name": name,
                "overall": overall,
                "languages": _language_view(market, published_languages),
                "checks": checks,
            }
        )

    summary = {
        "total": len(results),
        "ready": sum(result["overall"] == CHECK_PASS for result in results),
        "needs_review": sum(result["overall"] == CHECK_WARNING for result in results),
        "not_configured": sum(result["overall"] == CHECK_NOT_CONFIGURED for result in results),
    }
    return {
        "checked_at": checked_at or datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "markets": results,
    }
