"""Firehose audit sink configuration foundation."""

from app.audit.models import AuditEvent
from config import settings
from utils.logging import get_logger

LOGGER = get_logger("app.audit.sinks.firehose")


class FirehoseAuditSink:
    """Future sink for Amazon Kinesis Data Firehose delivery.

    This step only makes the backend aware of Firehose. It intentionally does
    not call PutRecord or PutRecordBatch yet.
    """

    name = "firehose"

    def __init__(self) -> None:
        self.enabled = bool(settings.AUDIT_FIREHOSE_ENABLED)
        self.stream_name = settings.AUDIT_FIREHOSE_STREAM
        self.client = None

        if not self.enabled:
            LOGGER.info("firehose_audit_sink_disabled", stream=self.stream_name)
            return

        import boto3

        self.client = boto3.client("firehose", region_name=settings.AWS_REGION)
        LOGGER.info("firehose_audit_sink_initialized", stream=self.stream_name, region=settings.AWS_REGION)

    async def write(self, _event: AuditEvent) -> None:
        """Firehose delivery is intentionally not implemented yet."""
        return None


def initialize_firehose_sink() -> FirehoseAuditSink:
    """Initialise the Firehose sink configuration during startup."""
    return FirehoseAuditSink()
