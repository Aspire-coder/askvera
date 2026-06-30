"""Kinesis Firehose audit logging."""

import json
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from config import settings
from services.aws_clients import get_aws_clients
from utils.exceptions import AwsServiceError
from utils.logging import get_logger

LOGGER = get_logger("services.audit")


def write_audit_event(event: dict[str, Any], correlation_id: str) -> None:
    """Send one audit event to Kinesis Firehose."""
    if settings.KINESIS_FIREHOSE_STREAM_NAME.startswith("REPLACE_WITH"):
        LOGGER.warning("audit_not_configured", correlation_id=correlation_id, event_type=event.get("type", "unknown"))
        return
    payload = {"timestamp": datetime.now(UTC).isoformat(), "correlationId": correlation_id, **event}
    try:
        get_aws_clients().firehose.put_record(
            DeliveryStreamName=settings.KINESIS_FIREHOSE_STREAM_NAME,
            Record={"Data": json.dumps(payload, ensure_ascii=True).encode("utf-8") + b"\n"},
        )
    except (BotoCoreError, ClientError) as exc:
        LOGGER.exception("audit_write_failed", correlation_id=correlation_id)
        raise AwsServiceError("Audit logging failed.") from exc
    LOGGER.info("audit_written", correlation_id=correlation_id, event_type=event.get("type", "unknown"))
