"""Fail CI when production code reintroduces known credential or storage risks."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPES = (
    "api",
    "app",
    "config",
    "deployment",
    "services",
    "utils",
    "widget-wrapper/src",
    "admin-portal/src",
)
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".json", ".yaml", ".yml", ".md", ".env", ".example"}
SECRET_PATTERNS = {
    "AWS account-bearing ARN": re.compile(r"arn:aws(?:-[a-z]+)?:[^:\s]+:[^:\s]*:\d{12}:"),
    "SQS URL with account ID": re.compile(r"https://sqs\.[^\s/]+\.amazonaws\.com/\d{12}/"),
    "presigned AWS credential": re.compile(r"X-Amz-(?:Credential|Signature|Security-Token)=", re.I),
}


def _files():
    for scope in SCOPES:
        base = ROOT / scope
        if base.is_file():
            yield base
            continue
        if base.exists():
            yield from (path for path in base.rglob("*") if path.is_file() and path.suffix in TEXT_SUFFIXES)


def main() -> int:
    failures: list[str] = []
    for path in _files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        relative = path.relative_to(ROOT).as_posix()
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                failures.append(f"{relative}: {label}")
        if relative.startswith("widget-wrapper/src/") and "/storage/" not in relative:
            if re.search(r"\b(?:window\.)?(?:localStorage|sessionStorage)\b", text):
                failures.append(f"{relative}: bypasses the widget storage adapter")
    if failures:
        print("Security regression checks failed:")
        for failure in sorted(set(failures)):
            print(f"- {failure}")
        return 1
    print("Security regression checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
