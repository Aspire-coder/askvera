"""The retrieval classifier calls must be deterministic.

The query planner, both evidence selectors, the support/income-claim routers and
query translation all return JSON or a single rewritten string. Sampling variety
there buys nothing and costs reproducibility: the same question can retrieve
different evidence on two consecutive asks.

This is asserted structurally rather than by exercising each function, because
the regression worth catching is a *new* Converse call added to these modules
without a temperature -- which a per-function test would not see at all.
"""

import ast
from pathlib import Path

import pytest

from config import settings

# Modules whose every Converse call is a classifier. Answer-writing calls live
# in app/models/bedrock_provider.py and app/orchestrator/chat_orchestrator.py,
# which are deliberately absent: those produce prose for a reader, where some
# variation is acceptable.
CLASSIFIER_MODULES = [
    "app/retrieval/providers.py",
    "app/retrieval/opensearch_sections.py",
]

REPO_ROOT = Path(__file__).resolve().parents[2]


def _converse_calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "converse"
    ]


def _inference_config(call: ast.Call) -> ast.Dict | None:
    for keyword in call.keywords:
        if keyword.arg == "inferenceConfig" and isinstance(keyword.value, ast.Dict):
            return keyword.value
    return None


@pytest.mark.parametrize("module", CLASSIFIER_MODULES)
def test_every_classifier_converse_call_sets_a_temperature(module):
    path = REPO_ROOT / module
    calls = _converse_calls(path)
    assert calls, f"expected at least one Converse call in {module}"

    for call in calls:
        config = _inference_config(call)
        assert config is not None, f"{module}:{call.lineno} passes no inferenceConfig"
        keys = {key.value for key in config.keys if isinstance(key, ast.Constant)}
        assert "temperature" in keys, (
            f"{module}:{call.lineno} is a classifier call with no temperature set. "
            "Add \"temperature\": settings.BEDROCK_CLASSIFIER_TEMPERATURE, or move the "
            "call out of this module if it writes prose for a reader."
        )


def test_classifier_temperature_default_is_deterministic():
    assert settings.BEDROCK_CLASSIFIER_TEMPERATURE == 0.0


def test_classifier_temperature_is_code_owned():
    """SSM must not be able to reintroduce sampling into retrieval.

    PROMPT_VERSION pinned in SSM silently defeated a code change once already;
    the same failure here would make retrieval non-reproducible with nothing in
    the codebase to show why.
    """
    assert "BEDROCK_CLASSIFIER_TEMPERATURE" in settings._CODE_OWNED_SETTINGS
