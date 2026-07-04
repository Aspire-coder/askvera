"""Firehose audit sink configuration foundation."""

import asyncio
from time import monotonic
from typing import Any

from app.audit.models import AuditEvent
from config import settings
from utils.logging import get_logger

LOGGER = get_logger("app.audit.sinks.firehose")


class FirehoseAuditSink:
    """Send audit events to Amazon Kinesis Data Firehose when enabled."""

    name = "firehose"
    RETRYABLE_ERROR_CODES = {
        "ThrottlingException",
        "ProvisionedThroughputExceededException",
    }
    RETRYABLE_HTTP_STATUS = {500, 502, 503, 504}

    def __init__(self) -> None:
        self.enabled = bool(settings.AUDIT_FIREHOSE_ENABLED)
        self.stream_name = settings.AUDIT_FIREHOSE_STREAM
        self.client = None
        self._batch: list[dict[str, bytes]] = []
        self._batch_lock = asyncio.Lock()
        self._batch_size = settings.AUDIT_BATCH_SIZE
        self._batch_timeout = settings.AUDIT_BATCH_TIMEOUT_SECONDS
        self._retry_attempts = settings.AUDIT_RETRY_MAX_ATTEMPTS
        self._retry_base_delay = settings.AUDIT_RETRY_BASE_DELAY_SECONDS
        self._retry_max_delay = settings.AUDIT_RETRY_MAX_DELAY_SECONDS
        self._last_flush = monotonic()
        self._flush_task: asyncio.Task[None] | None = None
        self._flush_interval_seconds = 1.0

        if not self.enabled:
            LOGGER.info("firehose_audit_sink_disabled", stream=self.stream_name)
            return

        import boto3

        self.client = boto3.client("firehose", region_name=settings.AWS_REGION)
        LOGGER.info("firehose_audit_sink_initialized", stream=self.stream_name, region=settings.AWS_REGION)

    async def start(self) -> None:
        """Start the periodic partial-batch flush loop."""
        if not self.enabled or self.client is None:
            return
        if self._flush_task and not self._flush_task.done():
            return
        self._flush_task = asyncio.create_task(self._periodic_flush_loop())
        LOGGER.info("firehose_audit_flush_timer_started", stream=self.stream_name, timeout_seconds=self._batch_timeout)

    async def stop(self) -> None:
        """Stop the periodic flush loop and send any remaining records."""
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                LOGGER.info("firehose_audit_flush_timer_stopped", stream=self.stream_name)
        self._flush_task = None
        await self._flush()

    async def write(self, event: AuditEvent) -> None:
        """Buffer one audit event as a Firehose-ready record."""
        if not self.enabled or self.client is None:
            return None

        await self._add_to_batch(event)
        return None

    async def _add_to_batch(self, event: AuditEvent) -> None:
        """Serialize and append one event to the in-memory batch."""
        payload = event.model_dump_json() + "\n"
        record = {"Data": payload.encode("utf-8")}
        needs_flush = False
        async with self._batch_lock:
            self._batch.append(record)
            needs_flush = len(self._batch) >= self._batch_size

        if needs_flush:
            await self._flush()

    async def _periodic_flush_loop(self) -> None:
        """Flush partial batches when the configured timeout elapses."""
        while True:
            await asyncio.sleep(self._flush_interval_seconds)
            try:
                if await self._should_flush_for_timeout():
                    await self._flush()
            except Exception:
                LOGGER.exception("firehose_audit_flush_timer_failed", stream=self.stream_name)

    async def _should_flush_for_timeout(self) -> bool:
        """Return True when a partial batch has exceeded its timeout."""
        async with self._batch_lock:
            if not self._batch:
                return False
            return monotonic() - self._last_flush >= self._batch_timeout

    async def _flush(self) -> None:
        """Flush the current batch with one Firehose PutRecordBatch call."""
        if not self.enabled or self.client is None:
            return None

        async with self._batch_lock:
            if not self._batch:
                return None
            records = self._batch
            self._batch = []
            self._last_flush = monotonic()

        total_count = len(records)
        if await self._put_record_batch_with_retries(records):
            LOGGER.info("firehose_audit_batch_written", stream=self.stream_name, batch_size=total_count, failed_count=0)
        return None

    async def _put_record_batch_with_retries(self, records: list[dict[str, bytes]]) -> bool:
        """Send a batch to Firehose with deterministic exponential backoff."""
        records_to_send = records
        original_batch_size = len(records)
        max_attempts = max(1, self._retry_attempts)
        for attempt in range(max_attempts):
            batch_size = len(records_to_send)
            try:
                response = await self._send_batch(records_to_send)
            except Exception as exc:
                error_code, http_status = self._error_details(exc)
                if not self._should_retry(exc):
                    LOGGER.exception(
                        "firehose_non_retryable_error",
                        stream=self.stream_name,
                        batch_size=batch_size,
                        error_code=error_code,
                        http_status=http_status,
                    )
                    return False

                if attempt == max_attempts - 1:
                    LOGGER.exception(
                        "firehose_batch_failed_after_retries",
                        stream=self.stream_name,
                        batch_size=batch_size,
                        attempt=attempt + 1,
                        max_attempts=max_attempts,
                        error_code=error_code,
                        http_status=http_status,
                    )
                    return False

                delay = self._retry_delay(attempt)
                LOGGER.warning(
                    "firehose_retry_scheduled",
                    stream=self.stream_name,
                    batch_size=batch_size,
                    attempt=attempt + 1,
                    max_attempts=max_attempts,
                    delay_seconds=delay,
                    error_code=error_code,
                    http_status=http_status,
                )
                await asyncio.sleep(delay)
                continue

            failed_records = self._failed_records(records_to_send, response)
            failed_count = len(failed_records)
            if not failed_count:
                return True

            if attempt == max_attempts - 1:
                LOGGER.warning(
                    "firehose_partial_batch_failed",
                    stream=self.stream_name,
                    batch_size=batch_size,
                    original_batch_size=original_batch_size,
                    remaining_failed_records=failed_count,
                    attempt=attempt + 1,
                    max_attempts=max_attempts,
                )
                return False

            delay = self._retry_delay(attempt)
            LOGGER.warning(
                "firehose_partial_batch_retry",
                stream=self.stream_name,
                batch_size=batch_size,
                original_batch_size=original_batch_size,
                failed_count=failed_count,
                retry_batch_size=failed_count,
                attempt=attempt + 1,
                max_attempts=max_attempts,
                delay_seconds=delay,
            )
            records_to_send = failed_records
            await asyncio.sleep(delay)
        return False

    async def _send_batch(self, records: list[dict[str, bytes]]) -> dict[str, Any]:
        """Send one Firehose PutRecordBatch request."""
        return self.client.put_record_batch(
            DeliveryStreamName=self.stream_name,
            Records=records,
        )

    def _failed_records(self, records: list[dict[str, bytes]], response: dict[str, Any]) -> list[dict[str, bytes]]:
        """Return only the records Firehose reported as failed."""
        request_responses = response.get("RequestResponses", [])
        failed_records: list[dict[str, bytes]] = []
        for original_record, result in zip(records, request_responses):
            if isinstance(result, dict) and result.get("ErrorCode"):
                failed_records.append(original_record)
        return failed_records

    def _should_retry(self, exc: Exception) -> bool:
        """Return True when a Firehose failure is likely transient."""
        error_code, http_status = self._error_details(exc)
        if error_code in self.RETRYABLE_ERROR_CODES:
            return True
        if http_status in self.RETRYABLE_HTTP_STATUS:
            return True
        return False

    def _error_details(self, exc: Exception) -> tuple[str | None, int | None]:
        """Extract AWS-style error code and HTTP status from an exception."""
        response = getattr(exc, "response", None)
        if not isinstance(response, dict):
            return None, None

        error = response.get("Error", {})
        metadata = response.get("ResponseMetadata", {})
        error_code = error.get("Code") if isinstance(error, dict) else None
        http_status = metadata.get("HTTPStatusCode") if isinstance(metadata, dict) else None
        return error_code, http_status if isinstance(http_status, int) else None

    def _retry_delay(self, attempt: int) -> float:
        """Return deterministic exponential retry delay for one attempt."""
        delay = self._retry_base_delay * (2**attempt)
        return min(delay, self._retry_max_delay)

    def batch_size(self) -> int:
        """Return the current number of buffered records."""
        return len(self._batch)

    def batch_config(self) -> dict[str, Any]:
        """Return the active batch configuration."""
        return {
            "batch_size": self._batch_size,
            "batch_timeout_seconds": self._batch_timeout,
            "last_flush": self._last_flush,
        }


def initialize_firehose_sink() -> FirehoseAuditSink:
    """Initialise the Firehose sink configuration during startup."""
    return FirehoseAuditSink()
