"""Phase 2, Lane G: every conversation-quality test module states what kind
of proof it is.

Per docs/conversation-quality/TASK_BOARD.md / the project brief, every test
module under tests/conversation and tests/conversation_pack must state one
of five labels in its module docstring, so a reader never has to guess how
much a passing test actually proves:

- deterministic/local proof   (real code, no model, no network)
- mocked dependency behaviour (a fake retriever/router/AWS dependency stands in)
- prompt-structure check      (the prompt text, not a live generation)
- needs-live                  (the offline mechanism cannot judge the whole case)
- source-reviewed expectation (the expected fact/behaviour is pinned to a
  reviewed source document, directory record or config file)

This check globs the CURRENT files in both directories at run time rather
than hardcoding a file list, because other lanes are concurrently adding new
files there (test_reference_*, test_multilingual_fields*, test_timing_stage*,
test_fragment_*, test_dependency_*, test_contact_completion*, per
TASK_BOARD.md's Phase 2 lane table) and editing existing ones
(test_intent_multipart_order_size_payment.py, test_order_size_field_keeping.py
are Lane B's). Whatever exists when this runs gets checked.

_KNOWN_GAPS lists files that are a different lane's Phase 2 write target
(TASK_BOARD.md) and are not editable from here (Lane G may not touch them).
A file leaves this list the moment its docstring carries a label - the
allowance is not a blanket exemption, it is scoped to the exact file and
must be removed once whoever owns that file adds the label.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

CHECKED_DIRECTORIES = ("tests/conversation", "tests/conversation_pack")

LABEL_MARKERS = (
    "deterministic",
    "local proof",
    "mocked",
    "dependency behaviour",
    "dependency behavior",
    "prompt-structure",
    "needs-live",
    "needs live",
    "source-reviewed",
)

# Files owned by another Phase 2 lane (TASK_BOARD.md's lane-ownership table)
# that currently lack a label. Lane G cannot edit these files. Kept narrow
# and named, not a directory-wide exemption, so a new unlabeled file from any
# lane still fails this check.
_KNOWN_GAPS = {
    "tests/conversation/test_intent_multipart_order_size_payment.py": (
        "Lane B Phase 2 write target (TASK_BOARD.md); Lane G may not edit it."
    ),
}


def _module_files() -> list[Path]:
    root = Path(__file__).resolve().parents[2]
    files: list[Path] = []
    for directory in CHECKED_DIRECTORIES:
        files.extend(sorted((root / directory).glob("test_*.py")))
    return files


def _relative(path: Path) -> str:
    root = Path(__file__).resolve().parents[2]
    return str(path.relative_to(root)).replace("\\", "/")


@pytest.mark.parametrize("path", _module_files(), ids=lambda p: _relative(p))
def test_module_docstring_states_a_recognized_label(path: Path) -> None:
    relative = _relative(path)
    source = path.read_text(encoding="utf-8")
    docstring = ast.get_docstring(ast.parse(source)) or ""
    normalized = docstring.lower()
    has_label = any(marker in normalized for marker in LABEL_MARKERS)

    if not has_label and relative in _KNOWN_GAPS:
        pytest.skip(f"known gap, not Lane G's to fix: {_KNOWN_GAPS[relative]}")

    assert has_label, (
        f"{relative}'s module docstring names none of the required labels "
        f"({', '.join(LABEL_MARKERS)}). Every test module under "
        f"tests/conversation and tests/conversation_pack must say what kind "
        f"of proof it is."
    )


def test_known_gaps_list_only_names_files_that_still_lack_a_label() -> None:
    """If a listed file gained a label (e.g. its owning lane fixed it), the
    entry is stale and must be removed so this check stays meaningful."""
    root = Path(__file__).resolve().parents[2]
    for relative, reason in _KNOWN_GAPS.items():
        path = root / relative
        assert path.exists(), f"known-gap entry {relative!r} no longer exists ({reason})"
        docstring = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
        normalized = docstring.lower()
        already_labeled = any(marker in normalized for marker in LABEL_MARKERS)
        assert not already_labeled, (
            f"{relative} now has a label - remove it from _KNOWN_GAPS so this "
            f"check enforces it like every other file."
        )
