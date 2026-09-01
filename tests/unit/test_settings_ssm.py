"""Regression tests for strict, atomic SSM configuration loading."""

import sys
from types import SimpleNamespace

import pytest

from config import settings


class _ParameterPaginator:
    def __init__(self, parameters: list[dict[str, str]]) -> None:
        self._parameters = parameters

    def paginate(self, **_kwargs):
        yield {"Parameters": self._parameters}


class _SsmClient:
    def __init__(self, parameters: list[dict[str, str]]) -> None:
        self._parameters = parameters

    def get_paginator(self, name: str) -> _ParameterPaginator:
        assert name == "get_parameters_by_path"
        return _ParameterPaginator(self._parameters)


def _install_fake_boto3(monkeypatch, parameters: list[dict[str, str]]) -> None:
    fake_boto3 = SimpleNamespace(
        client=lambda service, **_kwargs: _SsmClient(parameters)
        if service == "ssm"
        else None
    )
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)


def test_boolean_parser_rejects_ambiguous_values() -> None:
    with pytest.raises(ValueError, match="Invalid boolean"):
        settings._parse_bool("enabled", "WIDGET_AUTH_REQUIRED")


def test_ssm_batch_is_not_partially_applied_when_one_value_is_invalid(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "SSM_CONFIG_ENABLED", True)
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "WIDGET_AUTH_REQUIRED", False)
    _install_fake_boto3(
        monkeypatch,
        [
            {"Name": "/test/APP_ENV", "Value": "production"},
            {"Name": "/test/WIDGET_AUTH_REQUIRED", "Value": "sometimes"},
        ],
    )

    with pytest.raises(ValueError, match="WIDGET_AUTH_REQUIRED"):
        settings.load_ssm_config("/test/")

    assert settings.APP_ENV == "development"
    assert settings.WIDGET_AUTH_REQUIRED is False


def test_hardened_ssm_rejects_unknown_parameter_names(monkeypatch) -> None:
    monkeypatch.setattr(settings, "SSM_CONFIG_ENABLED", True)
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "SECURITY_PROFILE", "standard")
    _install_fake_boto3(
        monkeypatch,
        [
            {"Name": "/test/SECURITY_PROFILE", "Value": "hardened"},
            {"Name": "/test/WIDET_AUTH_REQUIRED", "Value": "true"},
        ],
    )

    with pytest.raises(ValueError, match="WIDET_AUTH_REQUIRED"):
        settings.load_ssm_config("/test/")

    assert settings.SECURITY_PROFILE == "standard"
