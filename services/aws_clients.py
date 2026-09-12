"""Application-scoped AWS client container."""

import contextvars
from contextlib import contextmanager
from typing import Any, Iterator

import boto3
from botocore.config import Config

from config import settings

# --- Capture-gated Bedrock Converse token-usage accumulator --------------------
#
# The benchmark runner records only the final generation call's token usage
# (from the orchestrator's own response metadata). Planner and evidence-selector
# Bedrock calls use the same bedrock-runtime client and the same Converse API,
# but their usage was never counted, so measured cost understated real spend.
#
# This accumulator is default off: outside ``capture_bedrock_usage()`` the
# context var below is ``None`` and the event handler records nothing. It never
# changes a response, never raises into the call path, and records no prompt or
# response text -- only token counts, the model id and a coarse, structural
# call label (derived from the request's tool name, never from message text).

_bedrock_usage_records: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar(
    "_bedrock_usage_records", default=None
)


@contextmanager
def capture_bedrock_usage() -> Iterator[list[dict[str, Any]]]:
    """Record token usage from every Bedrock Converse call made in this block.

    Yields the list that usage records are appended to as they happen; the
    caller reads it after the block exits. Nesting is safe: each call gets its
    own list via ``contextvars``, so concurrent or nested captures never mix
    records.
    """
    records: list[dict[str, Any]] = []
    token = _bedrock_usage_records.set(records)
    try:
        yield records
    finally:
        _bedrock_usage_records.reset(token)


def _coarse_bedrock_call_label(params: dict[str, Any]) -> str:
    """A structural, best-effort label for one Converse call -- never prompt text.

    Only the request's declared tool name is used, when present: a schema
    element, not free text. Calls without a distinguishing tool (most
    generation calls) fall back to the generic label.
    """
    try:
        tool_config = params.get("toolConfig") if isinstance(params, dict) else None
        tools = tool_config.get("tools") if isinstance(tool_config, dict) else None
        if isinstance(tools, list) and tools:
            spec = tools[0].get("toolSpec") if isinstance(tools[0], dict) else None
            name = spec.get("name") if isinstance(spec, dict) else None
            if isinstance(name, str) and name:
                return name
    except Exception:
        pass
    return "converse"


def _record_bedrock_converse_usage(parsed: Any = None, params: Any = None, **_kwargs: Any) -> None:
    """Botocore ``after-call`` handler: append one usage record when capture is on.

    Registered on the shared bedrock-runtime client so every caller through
    that client is covered without each call site changing. Swallows every
    exception: a bug here must never fail, delay or alter a real call.
    """
    try:
        sink = _bedrock_usage_records.get()
        if sink is None:
            return
        usage = (parsed or {}).get("usage") or {}
        input_tokens = usage.get("inputTokens")
        output_tokens = usage.get("outputTokens")
        if input_tokens is None and output_tokens is None:
            return
        model_id = params.get("modelId") if isinstance(params, dict) else None
        sink.append(
            {
                "model_id": model_id if isinstance(model_id, str) else None,
                "input_tokens": int(input_tokens or 0),
                "output_tokens": int(output_tokens or 0),
                "call_label": _coarse_bedrock_call_label(params if isinstance(params, dict) else {}),
            }
        )
    except Exception:
        return


def _client_config(*, read_timeout: int, max_attempts: int) -> Config:
    """Build a bounded client budget using total request attempts."""
    return Config(
        connect_timeout=settings.AWS_CONNECT_TIMEOUT_SECONDS,
        read_timeout=read_timeout,
        retries={"total_max_attempts": max_attempts, "mode": "standard"},
    )


class AwsClients:
    """Creates boto3 clients once using the EC2 IAM instance role."""

    def __init__(self) -> None:
        """Initialise reusable clients without explicit credentials."""
        background_config = _client_config(
            read_timeout=settings.AWS_READ_TIMEOUT_SECONDS,
            max_attempts=settings.AWS_MAX_ATTEMPTS,
        )
        interactive_config = _client_config(
            read_timeout=settings.AWS_INTERACTIVE_READ_TIMEOUT_SECONDS,
            max_attempts=settings.AWS_INTERACTIVE_MAX_ATTEMPTS,
        )
        pii_config = _client_config(
            read_timeout=settings.AWS_PII_READ_TIMEOUT_SECONDS,
            max_attempts=settings.AWS_PII_MAX_ATTEMPTS,
        )
        self.bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=settings.AWS_REGION, config=background_config)
        self.bedrock_runtime = boto3.client("bedrock-runtime", region_name=settings.AWS_REGION, config=interactive_config)
        self.bedrock_runtime.meta.events.register("after-call.bedrock-runtime.Converse", _record_bedrock_converse_usage)
        self.bedrock_embedding_runtime = boto3.client(
            "bedrock-runtime", region_name=settings.AWS_REGION, config=background_config
        )
        self.comprehend = boto3.client("comprehend", region_name=settings.AWS_REGION, config=pii_config)
        self.cognito_idp = boto3.client(
            "cognito-idp",
            region_name=settings.ADMIN_COGNITO_REGION or settings.AWS_REGION,
            config=background_config,
        )
        self.firehose = boto3.client("firehose", region_name=settings.AWS_REGION, config=background_config)
        self.secretsmanager = boto3.client("secretsmanager", region_name=settings.AWS_REGION, config=background_config)
        self.s3 = boto3.client("s3", region_name=settings.AWS_REGION, config=background_config)
        self.ses = boto3.client("ses", region_name=settings.AWS_REGION, config=background_config)
        self.sqs = boto3.client("sqs", region_name=settings.AWS_REGION, config=background_config)
        self.textract = boto3.client("textract", region_name=settings.AWS_REGION, config=background_config)


aws_clients: AwsClients | None = None


def init_aws_clients() -> AwsClients:
    """Create and store application-scoped AWS clients."""
    global aws_clients
    aws_clients = AwsClients()
    return aws_clients


def get_aws_clients() -> AwsClients:
    """Return initialized AWS clients."""
    if aws_clients is None:
        return init_aws_clients()
    return aws_clients
