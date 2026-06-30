"""Integration tests for the real AWS chat flow.

These tests are skipped unless INTEGRATION_TEST=true.
"""

import os

import pytest


@pytest.mark.skipif(os.getenv("INTEGRATION_TEST") != "true", reason="Real AWS integration tests are opt-in.")
def test_real_chat_flow_placeholder() -> None:
    """Placeholder for real AWS chat flow validation after resource IDs are configured."""
    assert os.getenv("INTEGRATION_TEST") == "true"
