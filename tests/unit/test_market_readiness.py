from services.market_readiness import (
    CHECK_NOT_CONFIGURED,
    CHECK_NOT_VERIFIED,
    CHECK_PASS,
    CHECK_WARNING,
    build_market_readiness,
)


def _market():
    return {
        "code": "ZZ",
        "name": "Zeta",
        "enabled": True,
        "defaultLanguage": "en",
        "privacyVersion": "2026.1",
        "languages": [
            {"code": "en", "name": "English", "enabled": True},
            {"code": "fr", "name": "French", "enabled": True},
        ],
    }


def test_market_readiness_reports_complete_setup_without_touching_retrieval():
    result = build_market_readiness(
        markets=[_market()],
        policy_locales={"ZZ": {"languages": {"en", "fr"}}},
        support_routes=[
            {
                "country": "ZZ",
                "department": "Customer Care",
                "email": "care@example.com",
                "enabled": True,
            }
        ],
        widget_configs=[{"status": "active", "markets": '["ZZ"]'}],
        checked_at="2026-08-13T00:00:00+00:00",
    )

    assert result["summary"] == {
        "total": 1,
        "ready": 1,
        "needs_review": 0,
        "not_configured": 0,
    }
    assert result["markets"][0]["overall"] == CHECK_PASS
    checks = {check["key"]: check for check in result["markets"][0]["checks"]}
    assert checks["retrieval"]["status"] == CHECK_NOT_VERIFIED
    assert all(language["policy_published"] for language in result["markets"][0]["languages"])


def test_market_readiness_flags_partial_policy_and_optional_setup():
    result = build_market_readiness(
        markets=[_market()],
        policy_locales={"ZZ": {"languages": {"en"}}},
        support_routes=[],
        widget_configs=[],
        checked_at="2026-08-13T00:00:00+00:00",
    )

    assert result["summary"]["needs_review"] == 1
    checks = {check["key"]: check for check in result["markets"][0]["checks"]}
    assert checks["policy_locales"]["status"] == CHECK_WARNING
    assert checks["support"]["status"] == CHECK_NOT_CONFIGURED
    assert checks["widget"]["status"] == CHECK_NOT_CONFIGURED
    assert checks["retrieval"]["status"] == CHECK_NOT_VERIFIED


def test_market_readiness_flags_missing_required_setup():
    market = _market()
    market["privacyVersion"] = ""
    result = build_market_readiness(
        markets=[market],
        policy_locales={},
        support_routes=[],
        widget_configs=[],
        checked_at="2026-08-13T00:00:00+00:00",
    )

    assert result["summary"]["not_configured"] == 1
    checks = {check["key"]: check for check in result["markets"][0]["checks"]}
    assert checks["market_config"]["status"] == CHECK_PASS
    assert checks["policy_locales"]["status"] == CHECK_NOT_CONFIGURED
    assert checks["legal"]["status"] == CHECK_NOT_CONFIGURED
