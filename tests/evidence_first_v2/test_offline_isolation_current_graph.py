"""V2 import isolation for the CURRENT package graph. Deterministic/local proof.

tests/evidence_first_v2/test_offline_isolation.py is pinned by the V2 audit
ledger at its accepted V2-02 milestone hash (app/experimental/evidence_first_v2/
audit.py). It is left byte-for-byte unchanged. Its frozen relative-import
allowlist predates V2-09/V2-10, so `test_package_imports_use_a_narrow_allowlist`
still fails on the later `from .capture_provenance import ...` in
scope_aware_fusion.py. That remains a known, visible failure awaiting a
reviewed V2-boundary decision (PROGRAMME_LEDGER N7). It is not hidden here.

This file checks two things that test could not:
1. N7: six modules load siblings through `__import__(__package__ + ".x")`,
   which an ImportFrom-only walk never sees. Each dynamic import must resolve
   statically to an existing sibling on an explicit list. Anything it cannot
   resolve fails.
2. The graph as it stands now, with capture_provenance allowed on the R08
   recommendation. The boundary itself, meaning no provider, network or
   production module loaded, is still proven by the pinned file's subprocess
   test.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).parents[2] / "app" / "experimental" / "evidence_first_v2"
ALLOWED_ABSOLUTE_IMPORTS = {"__future__", "dataclasses", "enum", "hashlib", "re", "typing", "unicodedata"}
ALLOWED_RELATIVE_IMPORTS = {"context", "contracts", "scope", "standalone", "capture_provenance"}
ALLOWED_DYNAMIC_SIBLING_IMPORTS = {
    "comparison",
    "comparison_exposure",
    "comparison_fixture",
    "evidence",
    "ranking",
    "ranking_fixture",
    "ranking_ledger",
}


def _dynamic_sibling_target(call: ast.Call) -> str | None:
    """Return X for __import__(__package__ + ".X", ...), or None for any other shape."""
    if not call.args:
        return None
    argument = call.args[0]
    if (
        isinstance(argument, ast.BinOp)
        and isinstance(argument.op, ast.Add)
        and isinstance(argument.left, ast.Name)
        and argument.left.id == "__package__"
        and isinstance(argument.right, ast.Constant)
        and isinstance(argument.right.value, str)
        and argument.right.value.startswith(".")
    ):
        return argument.right.value[1:]
    return None


def _calls_named(tree: ast.AST, names: set[str]) -> list[ast.Call]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            function = node.func
            name = function.id if isinstance(function, ast.Name) else getattr(function, "attr", "")
            if name in names:
                found.append(node)
    return found


def test_every_import_statement_is_on_the_current_allowlist() -> None:
    for source_path in PACKAGE.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] in ALLOWED_ABSOLUTE_IMPORTS, source_path
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0:
                    assert (node.module or "").split(".")[0] in ALLOWED_ABSOLUTE_IMPORTS, source_path
                else:
                    assert node.level == 1, source_path
                    assert node.module in ALLOWED_RELATIVE_IMPORTS, source_path


def test_every_dynamic_import_resolves_to_an_allowed_sibling() -> None:
    for source_path in PACKAGE.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for call in _calls_named(tree, {"__import__", "import_module"}):
            target = _dynamic_sibling_target(call)
            assert target is not None, f"{source_path}: dynamic import that cannot be resolved statically"
            assert target in ALLOWED_DYNAMIC_SIBLING_IMPORTS, source_path
            assert (PACKAGE / f"{target}.py").is_file(), f"{source_path}: {target} is not a sibling"


def test_the_dynamic_import_check_is_not_vacuous() -> None:
    """It must actually see the dynamic imports that exist today."""
    seen = set()
    for source_path in PACKAGE.glob("*.py"):
        for call in _calls_named(ast.parse(source_path.read_text(encoding="utf-8")), {"__import__"}):
            seen.add(_dynamic_sibling_target(call) or "<unresolved>")
    assert seen == ALLOWED_DYNAMIC_SIBLING_IMPORTS


def test_the_resolver_rejects_foreign_or_unresolvable_targets() -> None:
    def call(source: str) -> ast.Call:
        return ast.parse(source).body[0].value  # type: ignore[attr-defined]

    assert _dynamic_sibling_target(call('__import__(__package__ + ".evidence")')) == "evidence"
    assert _dynamic_sibling_target(call('__import__("boto3")')) is None
    assert _dynamic_sibling_target(call("__import__(name)")) is None
    assert _dynamic_sibling_target(call('__import__("app" + ".retrieval")')) is None
