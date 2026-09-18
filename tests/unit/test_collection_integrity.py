"""Guards the default pytest collection surface (Phase 2, Lane G).

``pytest.ini``'s ``testpaths`` decides what a bare ``pytest`` invocation (no
path arguments -- the default CI/local command, and the ``make test``
target) collects. Before this project, ``testpaths = tests/unit`` alone, so
``tests/governance``, ``tests/conversation`` and ``tests/conversation_pack``
never ran unless someone remembered to pass them explicitly -- easy to
silently regress back to (a reverted edit, a merge that restores the old
ini, a typo in the path list).

This test runs a REAL ``pytest --collect-only -q`` subprocess against the
repository root with no path arguments, i.e. exactly the default collection
surface, and asserts that all four required directories still contribute
collected items to it. It deliberately does not just re-read ``testpaths``
from the ini file, because that would only prove the text says the right
thing, not that pytest actually collects those directories without a
collection error (a missing/renamed conftest, a duplicate module basename
under rootdir-based imports, or an import error in one of them would all
make the ini text true but the collection empty).

``tests/integration`` is deliberately NOT required here: it gates itself on
``INTEGRATION_TEST=true`` (tests/integration/test_chat_flow.py) because it
needs live AWS, and must stay out of the default surface.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

REQUIRED_DIRECTORIES = (
    "tests/unit",
    "tests/governance",
    "tests/conversation",
    "tests/conversation_pack",
)

# Must NOT be silently pulled into the default surface: needs live AWS/network.
EXCLUDED_DIRECTORIES = ("tests/integration",)


def _run_default_collection() -> str:
    """Run `pytest --collect-only -q` with NO path arguments (the default
    surface, exactly as `pytest` or `make test` would be invoked), and
    return combined stdout/stderr."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    output = result.stdout + "\n" + result.stderr
    assert result.returncode in (0, 1), (
        f"`pytest --collect-only -q` (default testpaths) exited "
        f"{result.returncode}, which means a collection error, not just "
        f"test failures/none-collected:\n{output[-6000:]}"
    )
    return output


@pytest.fixture(scope="module")
def default_collection_output() -> str:
    """Runs the real subprocess exactly once per test module (this is an
    expensive, whole-repo pytest invocation), shared by the tests below."""
    return _run_default_collection()


def test_default_collection_includes_every_required_directory(default_collection_output: str) -> None:
    """Each required directory must contribute at least one collected item
    to the default (no-args) collection surface."""
    normalized = default_collection_output.replace("\\", "/")
    for directory in REQUIRED_DIRECTORIES:
        assert f"{directory}/" in normalized, (
            f"{directory} produced no collected items under the default "
            f"pytest invocation (no path arguments). Check pytest.ini's "
            f"testpaths -- it must list this directory.\n---\n{default_collection_output[-6000:]}"
        )


def test_default_collection_does_not_pull_in_excluded_directories(default_collection_output: str) -> None:
    """tests/integration needs live AWS; it must stay opt-in, not default."""
    normalized = default_collection_output.replace("\\", "/")
    for directory in EXCLUDED_DIRECTORIES:
        assert f"{directory}/" not in normalized, (
            f"{directory} appeared in the default (no-args) pytest "
            f"collection. It gates on INTEGRATION_TEST=true and must not be "
            f"part of testpaths.\n---\n{default_collection_output[-6000:]}"
        )


def test_testpaths_ini_setting_names_every_required_directory() -> None:
    """A faster, complementary check straight against the ini text itself,
    so a reviewer sees exactly which line to look at if this ever regresses."""
    pytest_ini = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    testpaths_line = next(
        (line for line in pytest_ini.splitlines() if line.strip().startswith("testpaths")),
        "",
    )
    assert testpaths_line, "pytest.ini has no testpaths setting at all"
    for directory in REQUIRED_DIRECTORIES:
        assert directory in testpaths_line, (
            f"{directory} is missing from pytest.ini's testpaths line: {testpaths_line!r}"
        )
    for directory in EXCLUDED_DIRECTORIES:
        assert directory not in testpaths_line, (
            f"{directory} must not be in pytest.ini's testpaths (needs live AWS): {testpaths_line!r}"
        )
