"""Delete expired chat sessions.

Run from the project root with:
python scripts/cleanup_expired_sessions.py
"""

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
from services.session import cleanup_expired_sessions  # noqa: E402
from utils.exceptions import ConfigurationError  # noqa: E402
from utils.logging import configure_logging  # noqa: E402


def main() -> int:
    """Initialise dependencies, delete expired sessions, and print a short result."""
    configure_logging()
    settings.load_ssm_config()
    missing = validate()
    if missing:
        raise ConfigurationError(f"Missing required config values: {', '.join(missing)}")
    init_aws_clients()
    init_db("session-cleanup")
    deleted = cleanup_expired_sessions()
    close_db("session-cleanup")
    print(f"Deleted expired sessions: {deleted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
