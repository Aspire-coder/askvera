"""SQS feedback queue logic."""

import json

from botocore.exceptions import BotoCoreError, ClientError

from config import settings
from services.aws_clients import get_aws_clients
from utils.exceptions import AwsServiceError
from utils.logging import get_logger
from utils.validators import FeedbackRequest

LOGGER = get_logger("services.feedback")


def enqueue_feedback(feedback: FeedbackRequest, correlation_id: str) -> None:
    """Send user feedback to SQS for KB review workflows."""
    if settings.SQS_FEEDBACK_QUEUE_URL.startswith("REPLACE_WITH"):
        LOGGER.warning("feedback_queue_not_configured", correlation_id=correlation_id, session_id=feedback.sessionId)
        return
    try:
        get_aws_clients().sqs.send_message(
            QueueUrl=settings.SQS_FEEDBACK_QUEUE_URL,
            MessageBody=json.dumps({"correlationId": correlation_id, **feedback.model_dump()}, ensure_ascii=True),
        )
    except (BotoCoreError, ClientError) as exc:
        LOGGER.exception("feedback_enqueue_failed", correlation_id=correlation_id)
        raise AwsServiceError("Feedback queue write failed.") from exc
    LOGGER.info("feedback_enqueued", correlation_id=correlation_id, session_id=feedback.sessionId, rating=feedback.rating)
