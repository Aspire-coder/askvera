"""Create a reviewable Markdown snapshot of the AskVera repository."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {
    ".git",
    "node_modules",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".codex-test-venv",
    ".pytest-deploy",
    ".pytest-local-clean",
    ".pytest-local-temp",
    ".pytest-urgent-final",
    ".pytest-urgent-fix",
    ".tmp-ci-fix-deps",
    ".tmp-current-test-deps",
    ".tmp-rollout-test-deps",
    ".tmp-shadow-deps",
    ".tmp-test-deps",
    ".tmp-vnext-test-deps",
    "tmp",
    "outputs",
    "exports",
}
EXCLUDED_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
}
REDACTED_NAMES = {
    ".iam-askvera-admin-users.json",
    ".ssm-activate-full-rollout.json",
    ".ssm-activation-prereqs.json",
    ".ssm-deploy-request.json",
    ".ssm-rollout-preflight.json",
    ".ssm-rollout-readiness.json",
    ".ssm-seed-full-rollout.json",
    ".ssm-verify-request.json",
}
TEXT_SUFFIXES = {
    ".css", ".csv", ".html", ".ini", ".json", ".js", ".md", ".mjs",
    ".ps1", ".py", ".scss", ".sh", ".sql", ".toml", ".ts", ".tsx", ".txt",
    ".yaml", ".yml", ".lock", ".conf", ".example", ".properties", ".service",
}
TEXT_NAMES = {".gitignore", "Dockerfile", "Makefile", "Procfile", "LICENSE"}


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    paths = []
    for raw in result.stdout.splitlines():
        path = Path(raw)
        if path.name in EXCLUDED_NAMES or any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        if path.name in REDACTED_NAMES:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in TEXT_NAMES:
            continue
        if (ROOT / path).is_file():
            paths.append(path)
    return sorted(set(paths), key=lambda item: str(item).lower())


def redact(text: str, path: Path) -> str:
    if path.name in REDACTED_NAMES:
        return "[REDACTED OPERATIONAL CONFIGURATION FILE]\n"
    text = re.sub(r"(?i)(AKIA[0-9A-Z]{16})", "[REDACTED_AWS_ACCESS_KEY]", text)
    text = re.sub(r"(?i)(aws_secret_access_key\s*[:=]\s*)[^\\s,]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)(password\s*[:=]\s*)[^\\s,]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)(api[_-]?key\s*[:=]\s*)[^\\s,]+", r"\1[REDACTED]", text)
    return text


def language_for(path: Path) -> str:
    if path.name == "Makefile":
        return "makefile"
    if path.name == "Dockerfile":
        return "dockerfile"
    if path.name in {"Makefile", "Procfile"}:
        return "makefile"
    return {
        ".py": "python", ".ts": "typescript", ".tsx": "tsx", ".js": "javascript",
        ".mjs": "javascript", ".css": "css", ".scss": "scss", ".json": "json",
        ".sql": "sql", ".ps1": "powershell", ".yaml": "yaml", ".yml": "yaml",
        ".md": "markdown", ".html": "html", ".toml": "toml",
    }.get(path.suffix.lower(), "text")


def fence_for(content: str) -> str:
    """Return a Markdown fence longer than any fence inside the file."""
    longest = max((len(match) for match in re.findall(r"`+", content)), default=0)
    return "`" * max(3, longest + 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    stamp = dt.date.today().isoformat()
    output = args.output or ROOT / "exports" / f"AskVera_Full_Code_Export_{stamp}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    files = tracked_files()
    lines = [
        f"# AskVera Full Code Export - {stamp}",
        "",
        "This snapshot was generated from the current `askvera-deploy` checkout.",
        "It includes source code, configuration contracts, migrations, tests, scripts, and documentation.",
        "Generated dependencies, build output, caches, temporary test environments, and operational secret-bearing files are excluded.",
        "",
        f"**Included text files:** {len(files)}",
        "",
        "## File Index",
        "",
    ]
    lines.extend(f"- `{path.as_posix()}`" for path in files)
    lines.append("")
    lines.append("## Source Files")
    lines.append("")
    for path in files:
        content = redact((ROOT / path).read_text(encoding="utf-8", errors="replace"), path)
        fence = fence_for(content)
        lines.extend([
            f"### `{path.as_posix()}`",
            "",
            f"{fence}{language_for(path)}",
            content.rstrip("\n"),
            fence,
            "",
        ])
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Created {output}")
    print(f"Included files: {len(files)}")


if __name__ == "__main__":
    main()
