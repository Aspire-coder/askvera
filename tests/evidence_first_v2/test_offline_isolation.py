"""Prove V2-01 stays local and has no provider coupling."""

from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys
import unittest

from app.experimental.evidence_first_v2 import ScopeIntent, V2Request, resolve_scope


PACKAGE = Path(__file__).parents[2] / "app" / "experimental" / "evidence_first_v2"
ALLOWED_ABSOLUTE_IMPORTS = {"__future__", "dataclasses", "enum", "hashlib", "re", "typing", "unicodedata"}
ALLOWED_RELATIVE_IMPORTS = {
    "context",
    "contracts",
    "scope",
    "standalone",
    # V2-10 provenance validator: dependency-free (stdlib only) and shared by
    # scope_aware_fusion by design. Added at R11 integration on the R08
    # recommendation; the subprocess test below still proves no provider,
    # network or production module is loaded.
    "capture_provenance",
}
# Siblings reached through __import__(__package__ + ".<name>") rather than an
# import statement. Several of these modules import each other, and the dynamic
# form breaks the cycle. Before R11 this check could not see them at all (N7).
# Each one must be a sibling module, and no other dynamic import form is
# accepted.
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
    """Return X for __import__(__package__ + ".X", ...), or None if it is not that exact shape."""
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


class OfflineIsolationTests(unittest.TestCase):
    def test_scope_resolution_is_deterministic_and_has_no_cross_request_state(self) -> None:
        kenya = V2Request("one", "Sponsor in Kenya", "US", "en", "FBO", "v1", requested_directory_market="KE")
        belgium = V2Request("two", "Sponsor in Belgium", "US", "en", "FBO", "v1", requested_directory_market="BE")

        self.assertEqual(resolve_scope(kenya, ScopeIntent.INTERNATIONAL_SPONSORING).directory_market, "KE")
        self.assertEqual(resolve_scope(belgium, ScopeIntent.INTERNATIONAL_SPONSORING).directory_market, "BE")
        self.assertEqual(resolve_scope(kenya, ScopeIntent.INTERNATIONAL_SPONSORING).directory_market, "KE")

    def test_package_imports_use_a_narrow_allowlist(self) -> None:
        for source_path in PACKAGE.glob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertIn(alias.name.split(".")[0], ALLOWED_ABSOLUTE_IMPORTS, source_path)
                elif isinstance(node, ast.ImportFrom):
                    if node.level == 0:
                        self.assertIn((node.module or "").split(".")[0], ALLOWED_ABSOLUTE_IMPORTS, source_path)
                    else:
                        self.assertEqual(node.level, 1, source_path)
                        self.assertIn(node.module, ALLOWED_RELATIVE_IMPORTS, source_path)
                elif isinstance(node, ast.Call):
                    function = node.func
                    name = function.id if isinstance(function, ast.Name) else getattr(function, "attr", "")
                    if name in {"__import__", "import_module"}:
                        target = _dynamic_sibling_target(node)
                        self.assertIsNotNone(target, f"{source_path}: dynamic import that cannot be resolved statically")
                        self.assertIn(target, ALLOWED_DYNAMIC_SIBLING_IMPORTS, source_path)
                        self.assertTrue((PACKAGE / f"{target}.py").is_file(), f"{source_path}: {target} is not a sibling")

    def test_the_dynamic_import_check_is_not_vacuous(self) -> None:
        """The check above must see the dynamic imports that exist today (N7)."""
        seen: set[str] = set()
        for source_path in PACKAGE.glob("*.py"):
            for node in ast.walk(ast.parse(source_path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "__import__":
                    seen.add(_dynamic_sibling_target(node) or "<unresolved>")
        self.assertEqual(seen, ALLOWED_DYNAMIC_SIBLING_IMPORTS)

    def test_an_unresolvable_or_foreign_dynamic_import_is_rejected(self) -> None:
        """Negative controls for the resolver itself."""
        def call(source: str) -> ast.Call:
            return ast.parse(source).body[0].value  # type: ignore[attr-defined]

        self.assertEqual(_dynamic_sibling_target(call('__import__(__package__ + ".evidence")')), "evidence")
        self.assertIsNone(_dynamic_sibling_target(call('__import__("boto3")')))
        self.assertIsNone(_dynamic_sibling_target(call('__import__(name)')))
        self.assertIsNone(_dynamic_sibling_target(call('__import__("app" + ".retrieval")')))

    def test_clean_subprocess_imports_only_the_isolated_package(self) -> None:
        candidate = PACKAGE.parents[2]
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONPATH"] = str(candidate)
        smoke = (
            "import sys; import app.experimental.evidence_first_v2; "
            "forbidden = ('app.evidence', 'app.retrieval', 'app.orchestrator', 'services', 'config', "
            "'socket', 'urllib', 'httpx', 'requests', 'boto3', 'openai', 'anthropic'); "
            "raise SystemExit(any(name == prefix or name.startswith(prefix + '.') for name in sys.modules for prefix in forbidden))"
        )
        completed = subprocess.run(
            [sys.executable, "-c", smoke], cwd=candidate, env=environment, check=False, capture_output=True, text=True
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
