"""Settings the deployed code owns must not be overridable from SSM.

On 2026-09-07 the SSM parameter /askverachat/prod/PROMPT_VERSION held
"2026-07-17.1" while the code default had moved on twice. The prompt text
deployed fine, but the version label did not, so cache keys never rotated and
answers generated under older instructions kept being served. Three code fixes
were written chasing what turned out to be a cache artifact.

The guard already existed for three sibling versions and PROMPT_VERSION was
simply missing from it.
"""

import pytest

from config import settings


def test_prompt_version_is_code_owned():
    """The value describes deployed prompt behaviour and feeds cache keys."""
    assert "PROMPT_VERSION" in settings._CODE_OWNED_SETTINGS


@pytest.mark.parametrize("name", [
    "PROMPT_VERSION",
    "RETRIEVAL_PIPELINE_VERSION",
    "CONVERSATION_ROUTING_VERSION",
    "MODEL_ROUTING_VERSION",
])
def test_ssm_cannot_override_a_code_owned_version(monkeypatch, name):
    """Applying an older SSM payload must leave these untouched."""
    monkeypatch.setattr(settings, name, "code-value", raising=False)
    settings._apply_ssm_values({name: "stale-ssm-value"})

    assert getattr(settings, name) == "code-value"


def test_kb_version_stays_runtime_owned(monkeypatch):
    """KB_VERSION is deliberately rotatable by ingestion without a deploy.

    Protecting it too would stop published content from invalidating answers.
    """
    assert "KB_VERSION" not in settings._CODE_OWNED_SETTINGS

    monkeypatch.setattr(settings, "KB_VERSION", "old", raising=False)
    settings._apply_ssm_values({"KB_VERSION": "2026-09-07-new-publication"})

    assert settings.KB_VERSION == "2026-09-07-new-publication"
