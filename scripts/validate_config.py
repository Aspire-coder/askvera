"""Fail-fast startup configuration validator."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings

PLACEHOLDER_PREFIX = "REPLACE_WITH"


def validate() -> list[str]:
    """Return missing or placeholder required setting names."""
    missing: list[str] = []
    for name in settings.REQUIRED_VALUES:
        value = getattr(settings, name, "")
        if value in (None, "") or (isinstance(value, str) and value.startswith(PLACEHOLDER_PREFIX)):
            missing.append(name)
    return missing


def main() -> int:
    """Print validation result and return a process exit code."""
    missing = validate()
    if missing:
        print("ASK Vera configuration is incomplete. Fill these values in config/settings.py:")
        for name in missing:
            print(f"- {name}")
        return 1
    print("ASK Vera configuration is complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
