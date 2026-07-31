"""Preview or reconcile terminal ingestion commands from the SQS dead-letter queue."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402
from services.aws_clients import get_aws_clients, init_aws_clients  # noqa: E402
from services.db import close_db, get_engine, init_db  # noqa: E402
from utils.logging import configure_logging  # noqa: E402


def receive_dlq_messages(limit: int) -> list[dict[str, str]]:
    """Receive a bounded DLQ sample without deleting it."""
    messages: list[dict[str, str]] = []
    clients = get_aws_clients()
    while len(messages) < limit:
        response = clients.sqs.receive_message(
            QueueUrl=settings.ADMIN_INGESTION_DLQ_URL,
            MaxNumberOfMessages=min(10, limit - len(messages)),
            WaitTimeSeconds=1,
            VisibilityTimeout=30,
        )
        batch = response.get("Messages", [])
        if not batch:
            break
        messages.extend(batch)
    return messages


def job_id_from_message(message: dict[str, str]) -> str:
    """Return the job identifier from a supported ingestion command."""
    payload = json.loads(message.get("Body", ""))
    if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
        raise ValueError("Unsupported ingestion command schema.")
    job_id = str(payload.get("jobId") or "").strip()
    if not job_id:
        raise ValueError("Ingestion command has no jobId.")
    return job_id


def reconcile_message(message: dict[str, str]) -> str:
    """Mark one job dead-lettered and remove the matching DLQ command."""
    job_id = job_id_from_message(message)
    with get_engine().begin() as connection:
        result = connection.execute(
            text(
                """
                UPDATE ingestion_jobs
                SET status = 'dead_lettered',
                    progress = 100,
                    lease_owner = '',
                    lease_expires_at = NULL,
                    updated_at = now()
                WHERE job_id = :job_id
                  AND status NOT IN ('ready', 'completed', 'cancelled')
                """
            ),
            {"job_id": job_id},
        )
        if result.rowcount != 1:
            raise RuntimeError(
                f"DLQ command references a missing or completed job: {job_id}"
            )
    get_aws_clients().sqs.delete_message(
        QueueUrl=settings.ADMIN_INGESTION_DLQ_URL,
        ReceiptHandle=message["ReceiptHandle"],
    )
    return job_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Update job states and delete matched DLQ commands. Default is dry-run.",
    )
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--load-ssm", action="store_true")
    args = parser.parse_args()

    configure_logging()
    if args.load_ssm:
        settings.load_ssm_config()
    if not settings.ADMIN_INGESTION_DLQ_URL:
        print("ADMIN_INGESTION_DLQ_URL is required.", file=sys.stderr)
        return 1

    init_aws_clients()
    init_db("ingestion-dlq-reconciliation")
    try:
        messages = receive_dlq_messages(max(1, min(args.limit, 1000)))
        job_ids = [job_id_from_message(message) for message in messages]
        print(f"Dead-letter commands visible: {len(messages)}")
        for job_id in job_ids:
            print(f"- {job_id}")
        if not args.apply:
            print("Dry run only. Re-run with --apply after reviewing the jobs.")
            return 0
        reconciled = [reconcile_message(message) for message in messages]
        print(f"Reconciled dead-letter jobs: {len(reconciled)}")
        return 0
    except (
        BotoCoreError,
        ClientError,
        SQLAlchemyError,
        RuntimeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(f"DLQ reconciliation failed: {exc}", file=sys.stderr)
        return 1
    finally:
        close_db("ingestion-dlq-reconciliation")


if __name__ == "__main__":
    raise SystemExit(main())
