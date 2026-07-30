"""Apply ordered SQL migrations with checksums and a PostgreSQL advisory lock."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402
from scripts.validate_config import validate  # noqa: E402
from services.aws_clients import init_aws_clients  # noqa: E402
from services.db import close_db, init_db  # noqa: E402
from utils.exceptions import ConfigurationError  # noqa: E402
from utils.logging import configure_logging  # noqa: E402

MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
LOCK_ID = 8_922_026_073_000_001


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _migration_sql(path: Path) -> str:
    """Return migration SQL without file-level transaction wrappers."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(
        line for line in lines
        if line.strip().upper() not in {"BEGIN;", "COMMIT;"}
    )


def apply_migrations(*, dry_run: bool) -> list[str]:
    """Validate and optionally apply every pending ordered migration."""
    engine = init_db("db-migrations")
    pending: list[str] = []
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": LOCK_ID})
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    checksum TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        applied = {
            row["version"]: row["checksum"]
            for row in connection.execute(
                text("SELECT version, checksum FROM schema_migrations")
            ).mappings()
        }
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            checksum = _checksum(path)
            existing = applied.get(path.name)
            if existing and existing != checksum:
                raise RuntimeError(f"Applied migration checksum changed: {path.name}")
            if existing:
                continue
            pending.append(path.name)
            if dry_run:
                continue
            connection.exec_driver_sql(_migration_sql(path))
            connection.execute(
                text(
                    """
                    INSERT INTO schema_migrations (version, checksum)
                    VALUES (:version, :checksum)
                    """
                ),
                {"version": path.name, "checksum": checksum},
            )
    return pending


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply pending migrations.")
    parser.add_argument("--load-ssm", action="store_true", help="Load deployment configuration from SSM.")
    args = parser.parse_args()

    configure_logging()
    if args.load_ssm:
        settings.load_ssm_config()
    missing = validate()
    if missing:
        raise ConfigurationError(f"Missing required config values: {', '.join(missing)}")
    init_aws_clients()
    try:
        pending = apply_migrations(dry_run=not args.apply)
    finally:
        close_db("db-migrations")

    mode = "Applied" if args.apply else "Pending"
    print(f"{mode} migrations: {len(pending)}")
    for version in pending:
        print(f"- {version}")
    if pending and not args.apply:
        print("Dry run only. Re-run with --apply after review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
