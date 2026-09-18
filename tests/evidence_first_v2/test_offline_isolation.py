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
ALLOWED_RELATIVE_IMPORTS = {"context", "contracts", "scope", "standalone"}


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
