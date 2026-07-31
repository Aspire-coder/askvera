"""Process durable AskVera document-ingestion commands from SQS."""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import sys
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.exc import SQLAlchemyError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402
from services.aws_clients import get_aws_clients, init_aws_clients  # noqa: E402
from services.db import close_db, init_db  # noqa: E402
from services.knowledge_ingestion import (  # noqa: E402
    ACCESS_SCOPES,
    DOCUMENT_TYPES,
    claim_ingestion_job,
    process_ingestion_job,
    release_ingestion_claim,
    safe_filename,
    validate_document_content,
    validate_upload,
)
from services.market_config import (  # noqa: E402
    get_country_codes,
    get_language_codes_for_country,
)
from utils.logging import configure_logging, get_logger  # noqa: E402

LOGGER = get_logger("scripts.run_ingestion_worker")
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
REQUIRED_FIELDS = {
    "jobId",
    "uploadUri",
    "filename",
    "country",
    "language",
    "documentType",
    "accessScope",
    "contentHash",
}


class RetryableIngestionError(RuntimeError):
    """A temporary condition that should return to SQS for another attempt."""


def _parse_command(body: str) -> dict[str, str]:
    if len(body) > 16_384:
        raise ValueError("Ingestion command exceeds the maximum size.")
    payload = json.loads(body)
    if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
        raise ValueError("Unsupported ingestion command schema.")
    missing = REQUIRED_FIELDS.difference(payload)
    if missing:
        raise ValueError(f"Ingestion command is missing: {', '.join(sorted(missing))}")
    return {key: str(value) for key, value in payload.items()}


def _s3_location(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.lstrip("/"):
        raise ValueError("Ingestion upload URI must be a valid S3 URI.")
    return parsed.netloc, parsed.path.lstrip("/")


def _validate_command(command: dict[str, str]) -> tuple[str, str]:
    bucket, key = _s3_location(command["uploadUri"])
    expected_prefix = settings.ADMIN_INGESTION_QUARANTINE_PREFIX.strip("/")
    if bucket != settings.KNOWLEDGE_UPLOAD_BUCKET or not key.startswith(f"{expected_prefix}/"):
        raise ValueError("Ingestion upload is outside the approved quarantine location.")
    if command["filename"] != safe_filename(command["filename"]):
        raise ValueError("Ingestion filename is not storage-safe.")
    country = command["country"].upper()
    language = command["language"].lower()
    if country not in get_country_codes():
        raise ValueError("Ingestion command has an unsupported country.")
    if language not in get_language_codes_for_country(country):
        raise ValueError("Ingestion command has an unsupported language.")
    if command["documentType"] not in DOCUMENT_TYPES:
        raise ValueError("Ingestion command has an unsupported document type.")
    if command["accessScope"] not in ACCESS_SCOPES:
        raise ValueError("Ingestion command has an unsupported access scope.")
    if not re.fullmatch(r"[a-f0-9]{64}", command["contentHash"].lower()):
        raise ValueError("Ingestion command has an invalid content hash.")
    return bucket, key


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def process_message(message: dict[str, str]) -> bool:
    command = _parse_command(message["Body"])
    bucket, key = _validate_command(command)
    job_id = command["jobId"]
    filename = Path(command["filename"]).name
    claim = claim_ingestion_job(
        job_id,
        WORKER_ID,
        settings.ADMIN_INGESTION_WORKER_VISIBILITY_SECONDS,
    )
    if claim == "completed":
        LOGGER.info("ingestion_duplicate_completed", job_id=job_id)
        return True
    if claim == "terminal":
        LOGGER.warning("ingestion_terminal_message_removed", job_id=job_id)
        return True
    if claim != "claimed":
        LOGGER.info("ingestion_claim_skipped", job_id=job_id, claim=claim)
        return False
    try:
        if settings.ADMIN_INGESTION_MALWARE_SCAN_REQUIRED:
            tags = get_aws_clients().s3.get_object_tagging(Bucket=bucket, Key=key)
            tag_map = {item["Key"].lower(): item["Value"].upper() for item in tags.get("TagSet", [])}
            if tag_map.get("malware-scan-status") != "CLEAN":
                raise RetryableIngestionError(
                    "Ingestion upload has not passed malware scanning."
                )
        with TemporaryDirectory(prefix=f"askvera-{job_id[:10]}-") as directory:
            local_path = Path(directory) / filename
            get_aws_clients().s3.download_file(bucket, key, str(local_path))
            validate_upload(filename, local_path.stat().st_size)
            validate_document_content(local_path)
            if _file_hash(local_path) != command["contentHash"].lower():
                raise ValueError("Ingestion upload hash does not match the accepted document.")
            return process_ingestion_job(
                job_id,
                str(local_path),
                filename=filename,
                country=command["country"],
                language=command["language"],
                document_type=command["documentType"],
                access_scope=command["accessScope"],
                version=command.get("version", ""),
                effective_date=command.get("effectiveDate", ""),
                upload_uri=command["uploadUri"],
                accepted_by=command.get("acceptedBy", ""),
                logical_document_id=command.get("logicalDocumentId", ""),
                document_owner=command.get("documentOwner", ""),
                approval_reference=command.get("approvalReference", ""),
            )
    except RetryableIngestionError as exc:
        release_ingestion_claim(job_id, str(exc), retryable=True)
        raise
    except ValueError as exc:
        release_ingestion_claim(job_id, str(exc), retryable=False)
        raise
    except (BotoCoreError, ClientError, SQLAlchemyError, OSError) as exc:
        release_ingestion_claim(job_id, str(exc), retryable=True)
        raise


def _extend_message_visibility(
    stop_event: threading.Event,
    *,
    receipt_handle: str,
) -> None:
    """Keep a long-running ingestion command owned by this worker."""
    visibility_seconds = max(30, settings.ADMIN_INGESTION_WORKER_VISIBILITY_SECONDS)
    heartbeat_seconds = max(10, min(visibility_seconds // 2, 300))
    clients = get_aws_clients()
    while not stop_event.wait(heartbeat_seconds):
        try:
            clients.sqs.change_message_visibility(
                QueueUrl=settings.ADMIN_INGESTION_QUEUE_URL,
                ReceiptHandle=receipt_handle,
                VisibilityTimeout=visibility_seconds,
            )
        except (BotoCoreError, ClientError):
            LOGGER.exception("ingestion_visibility_extension_failed")


def run_forever() -> None:
    """Long-poll until terminated by the service manager."""
    if not settings.ADMIN_INGESTION_QUEUE_URL:
        raise RuntimeError("ADMIN_INGESTION_QUEUE_URL is required.")
    clients = get_aws_clients()
    while True:
        response = clients.sqs.receive_message(
            QueueUrl=settings.ADMIN_INGESTION_QUEUE_URL,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=max(1, min(settings.ADMIN_INGESTION_WORKER_WAIT_SECONDS, 20)),
            VisibilityTimeout=max(30, settings.ADMIN_INGESTION_WORKER_VISIBILITY_SECONDS),
            AttributeNames=["ApproximateReceiveCount"],
        )
        for message in response.get("Messages", []):
            stop_heartbeat = threading.Event()
            heartbeat = threading.Thread(
                target=_extend_message_visibility,
                kwargs={
                    "stop_event": stop_heartbeat,
                    "receipt_handle": message["ReceiptHandle"],
                },
                name="ingestion-visibility-heartbeat",
                daemon=True,
            )
            heartbeat.start()
            try:
                if process_message(message):
                    clients.sqs.delete_message(
                        QueueUrl=settings.ADMIN_INGESTION_QUEUE_URL,
                        ReceiptHandle=message["ReceiptHandle"],
                    )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                LOGGER.exception("invalid_ingestion_command")
            except RetryableIngestionError:
                LOGGER.info("ingestion_message_retry_scheduled")
            except (BotoCoreError, ClientError, SQLAlchemyError, OSError):
                LOGGER.exception("ingestion_message_retry_scheduled")
            finally:
                stop_heartbeat.set()
                heartbeat.join(timeout=1)


def main() -> int:
    """Initialise standalone dependencies and run until the service stops."""
    configure_logging()
    settings.load_ssm_config()
    if not settings.ADMIN_INGESTION_QUEUE_ENABLED:
        raise RuntimeError("ADMIN_INGESTION_QUEUE_ENABLED must be true for the worker.")
    init_aws_clients()
    init_db("ingestion-worker")
    try:
        run_forever()
    finally:
        close_db("ingestion-worker")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
