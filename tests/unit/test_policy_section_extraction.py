"""Regression coverage for generic policy-heading formats."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "ingestion"
    / "extract_policy_sections.py"
)
SPEC = importlib.util.spec_from_file_location("policy_section_extractor", SCRIPT_PATH)
assert SPEC and SPEC.loader
extractor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = extractor
SPEC.loader.exec_module(extractor)


def test_section_match_supports_common_numbering_layouts() -> None:
    text = "\n".join(
        [
            "1 Introduction",
            "1.3. Customer definitions",
            "11.01 General policy",
            "2 3",
        ]
    )

    matches = list(extractor._iter_section_matches(text))

    assert [match.group("section") for match in matches] == ["1", "1.3", "11.01"]


def test_contents_page_heuristic_ignores_dense_numbered_lists() -> None:
    contents = "\n".join(
        [
            "1 Introduction",
            "2 Definitions",
            "3 Preferred Customer",
            "4 Marketing Plan",
            "5 Manager Status",
            "6 Leadership Bonus",
        ]
    )

    assert extractor._looks_like_contents_page(contents) is True
