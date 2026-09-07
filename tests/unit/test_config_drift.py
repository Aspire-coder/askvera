"""Configuration drift between SSM and the code-owned defaults.

A code-owned setting pinned in SSM breaks nothing at runtime, because the code
correctly refuses to apply it. That is exactly what makes it dangerous: the
parameter store advertises a value production does not use, and the next person
to read it is misled. A PROMPT_VERSION pinned this way cost three fixes chasing
a cache that would not invalidate.
"""

import pytest

from config import settings


@pytest.fixture(autouse=True)
def _restore_settings():
    """Undo the module-global mutation these tests perform."""
    saved = {key: getattr(settings, key) for key in settings._CODE_OWNED_SETTINGS}
    saved["BEDROCK_MAX_OUTPUT_TOKENS"] = settings.BEDROCK_MAX_OUTPUT_TOKENS
    saved_ignored = list(settings._SSM_IGNORED_OVERRIDES)
    saved_overridden = list(settings._SSM_OVERRIDDEN_KEYS)
    yield
    for key, value in saved.items():
        setattr(settings, key, value)
    settings._SSM_IGNORED_OVERRIDES = saved_ignored
    settings._SSM_OVERRIDDEN_KEYS = saved_overridden


def test_code_owned_value_is_reported_not_silently_dropped():
    settings._apply_ssm_values({"PROMPT_VERSION": "STALE-2026-01-01"})

    report = settings.config_drift_report()
    ignored = {entry["key"]: entry for entry in report["ignored_code_owned"]}
    assert "PROMPT_VERSION" in ignored
    assert ignored["PROMPT_VERSION"]["ssm_value"] == "STALE-2026-01-01"
    # The report must show both values, or a reader cannot tell what is actually
    # in force versus what SSM claims.
    assert ignored["PROMPT_VERSION"]["effective"] == settings.PROMPT_VERSION
    assert settings.PROMPT_VERSION != "STALE-2026-01-01"


def test_a_real_override_is_applied_and_reported_separately():
    settings._apply_ssm_values({"BEDROCK_MAX_OUTPUT_TOKENS": "2048"})

    report = settings.config_drift_report()
    assert "BEDROCK_MAX_OUTPUT_TOKENS" in report["overridden"]
    assert report["ignored_code_owned"] == []
    # Coerced to the existing type rather than left as a string.
    assert settings.BEDROCK_MAX_OUTPUT_TOKENS == 2048


def test_an_override_matching_the_default_is_not_reported_as_drift():
    """Only a value that actually changed something is worth reporting."""
    current = settings.BEDROCK_MAX_OUTPUT_TOKENS
    settings._apply_ssm_values({"BEDROCK_MAX_OUTPUT_TOKENS": str(current)})

    assert "BEDROCK_MAX_OUTPUT_TOKENS" not in settings.config_drift_report()["overridden"]


def test_report_is_replaced_not_accumulated_across_loads():
    settings._apply_ssm_values({"PROMPT_VERSION": "STALE"})
    settings._apply_ssm_values({"BEDROCK_MAX_OUTPUT_TOKENS": "2048"})

    report = settings.config_drift_report()
    assert report["ignored_code_owned"] == [], "a resolved drift must stop being reported"


def test_every_code_owned_setting_is_listed_in_the_report():
    report = settings.config_drift_report()
    assert set(report["code_owned_settings"]) == set(settings._CODE_OWNED_SETTINGS)


def test_drift_report_is_available_before_any_ssm_load():
    """Local and test runs never call load_ssm_config; the report must still work."""
    report = settings.config_drift_report()
    assert isinstance(report["overridden"], list)
    assert isinstance(report["ignored_code_owned"], list)
