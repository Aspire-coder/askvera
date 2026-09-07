"""Tests for production SSM configuration precedence."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

from config import settings


def test_ssm_cannot_override_code_owned_pipeline_versions(monkeypatch) -> None:
    """A stale SSM cache namespace must not survive a code deployment."""
    paginator = MagicMock()
    paginator.paginate.return_value = [
        {
            "Parameters": [
                {
                    "Name": "/askverachat/prod/RETRIEVAL_PIPELINE_VERSION",
                    "Value": "stale-retrieval-version",
                },
                {
                    "Name": "/askverachat/prod/CONVERSATION_ROUTING_VERSION",
                    "Value": "stale-conversation-version",
                },
                {
                    "Name": "/askverachat/prod/BEDROCK_MIN_CONFIDENCE",
                    "Value": "0.51",
                },
            ]
        }
    ]
    client = MagicMock()
    client.get_paginator.return_value = paginator
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *_args, **_kwargs: client))
    monkeypatch.setattr(settings, "SSM_CONFIG_ENABLED", True)
    monkeypatch.setattr(settings, "RETRIEVAL_PIPELINE_VERSION", "deployed-code-version")
    monkeypatch.setattr(settings, "CONVERSATION_ROUTING_VERSION", "deployed-conversation-version")
    monkeypatch.setattr(settings, "BEDROCK_MIN_CONFIDENCE", 0.47)

    loaded = settings.load_ssm_config("/askverachat/prod/")

    assert loaded["RETRIEVAL_PIPELINE_VERSION"] == "stale-retrieval-version"
    assert settings.RETRIEVAL_PIPELINE_VERSION == "deployed-code-version"
    assert settings.CONVERSATION_ROUTING_VERSION == "deployed-conversation-version"
    assert settings.BEDROCK_MIN_CONFIDENCE == 0.51


def test_ssm_cannot_pin_prompt_version_to_an_older_build(monkeypatch) -> None:
    """A stale prompt version must not survive a code deployment.

    On 2026-09-07 /askverachat/prod/PROMPT_VERSION held "2026-07-17.1" while the
    code default had moved on twice. The prompt text deployed, the version label
    did not, so cache keys never rotated and answers written under older
    instructions kept being served. PROMPT_VERSION was simply missing from
    _CODE_OWNED_SETTINGS, which already existed for its sibling versions.

    KB_VERSION stays runtime-owned on purpose: ingestion rotates it to invalidate
    answers when content is published, without a deploy.
    """
    paginator = MagicMock()
    paginator.paginate.return_value = [
        {
            "Parameters": [
                {"Name": "/askverachat/prod/PROMPT_VERSION", "Value": "2026-07-17.1"},
                {"Name": "/askverachat/prod/KB_VERSION", "Value": "2026-09-07-new-publication"},
            ]
        }
    ]
    client = MagicMock()
    client.get_paginator.return_value = paginator
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *_args, **_kwargs: client))
    monkeypatch.setattr(settings, "SSM_CONFIG_ENABLED", True)
    monkeypatch.setattr(settings, "PROMPT_VERSION", "deployed-prompt-version")
    monkeypatch.setattr(settings, "KB_VERSION", "old-content-version")

    loaded = settings.load_ssm_config("/askverachat/prod/")

    assert loaded["PROMPT_VERSION"] == "2026-07-17.1"
    assert settings.PROMPT_VERSION == "deployed-prompt-version"
    assert settings.KB_VERSION == "2026-09-07-new-publication"
