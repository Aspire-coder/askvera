"""Configuration package for ASK Vera."""

from config.settings import get, load_ssm_config as load_config

__all__ = ["get", "load_config"]
