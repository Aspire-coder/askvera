"""Tests for production SSM configuration precedence."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

from config import settings


def test_ssm_cannot_override_code_owned_retrieval_version(monkeypatch) -> None:
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
    monkeypatch.setattr(settings, "BEDROCK_MIN_CONFIDENCE", 0.47)

    loaded = settings.load_ssm_config("/askverachat/prod/")

    assert loaded["RETRIEVAL_PIPELINE_VERSION"] == "stale-retrieval-version"
    assert settings.RETRIEVAL_PIPELINE_VERSION == "deployed-code-version"
    assert settings.BEDROCK_MIN_CONFIDENCE == 0.51
