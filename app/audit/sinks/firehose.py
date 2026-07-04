"""Firehose audit sink configuration foundation."""

from app.audit.models import AuditEvent
from config import settings
from utils.logging import get_logger

LOGGER = get_logger("app.audit.sinks.firehose")


class FirehoseAuditSink:
    """Send audit events to Amazon Kinesis Data Firehose when enabled."""

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

    async def write(self, event: AuditEvent) -> None:
        """Send one audit event to Firehose as newline-delimited JSON."""
        if not self.enabled or self.client is None:
            return None

        payload = event.model_dump_json() + "\n"
        try:
            self.client.put_record(
                DeliveryStreamName=self.stream_name,
                Record={"Data": payload.encode("utf-8")},
            )
        except Exception:
            LOGGER.exception(
                "firehose_audit_write_failed",
                correlation_id=event.correlation_id,
                stream=self.stream_name,
                event_type=event.event_type.value,
            )
        return None


def initialize_firehose_sink() -> FirehoseAuditSink:
    """Initialise the Firehose sink configuration during startup."""
    return FirehoseAuditSink()
