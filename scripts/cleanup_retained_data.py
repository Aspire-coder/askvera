"""Apply configured retention policies to operational PostgreSQL data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Direct execution needs the repository root before application imports resolve.
from config import settings  # noqa: E402
from scripts.validate_config import validate  # noqa: E402
from services.aws_clients import init_aws_clients  # noqa: E402
from services.db import close_db, init_db  # noqa: E402
from services.retention import cleanup_retained_data, preview_retained_data  # noqa: E402
from utils.exceptions import ConfigurationError  # noqa: E402
from utils.logging import configure_logging  # noqa: E402


def main() -> int:
    """Preview retention by default and delete only with explicit --apply."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--category")
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()
    configure_logging()
    settings.load_ssm_config()
    missing = validate()
    if missing:
        raise ConfigurationError(f"Missing required config values: {', '.join(missing)}")
    init_aws_clients()
    init_db("retention-cleanup")
    try:
        result = (
            cleanup_retained_data(category=args.category, batch_size=args.batch_size)
            if args.apply
            else preview_retained_data(category=args.category)
        )
    finally:
        close_db("retention-cleanup")
    print("Retention cleanup complete" if args.apply else "Retention dry run complete")
    for table, count in sorted(result.items()):
        print(f"- {table}: {count}")
    if not args.apply:
        print("No records were deleted. Re-run with --apply after review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
