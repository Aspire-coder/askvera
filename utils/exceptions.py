"""Typed application exceptions and stable error codes."""


class AskVeraError(Exception):
    """Base class for all expected ASK Vera errors."""

    error_code = "ASK_VERA_ERROR"
    status_code = 500

    def __init__(self, message: str) -> None:
        """Create an exception with a human-readable message."""
        super().__init__(message)
        self.message = message


class ConfigurationError(AskVeraError):
    """Raised when required startup configuration is missing."""

    error_code = "CONFIGURATION_ERROR"
    status_code = 500


class BedrockTimeoutError(AskVeraError):
    """Raised when Bedrock times out."""

    error_code = "BEDROCK_TIMEOUT"
    status_code = 504


class BedrockServiceError(AskVeraError):
    """Raised when Bedrock returns an unexpected error."""

    error_code = "BEDROCK_ERROR"
    status_code = 502


class CacheConnectionError(AskVeraError):
    """Raised when Redis cannot be reached."""

    error_code = "CACHE_CONNECTION_ERROR"
    status_code = 503


class GuardrailBlockedError(AskVeraError):
    """Raised when input or output is blocked by guardrails."""

    error_code = "GUARDRAIL_BLOCKED"
    status_code = 400


class LowConfidenceError(AskVeraError):
    """Raised when retrieved knowledge does not meet the confidence threshold."""

    error_code = "LOW_CONFIDENCE"
    status_code = 200


class RetrievalMissError(LowConfidenceError):
    """Raised when retrieval returns no usable sources."""

    error_code = "RETRIEVAL_MISS"
    status_code = 200


class LowConfidenceThresholdError(LowConfidenceError):
    """Raised when retrieval returns sources below the configured threshold."""

    error_code = "LOW_CONFIDENCE"
    status_code = 200


class AwsServiceError(AskVeraError):
    """Raised when an AWS dependency other than Bedrock fails."""

    error_code = "AWS_SERVICE_ERROR"
    status_code = 502


class SupportUnavailableError(AskVeraError):
    """Raised when support delivery is not configured or temporarily fails."""

    error_code = "SUPPORT_UNAVAILABLE"
    status_code = 503


class SupportRouteUnavailableError(AskVeraError):
    """Raised when the selected market has no support destination."""

    error_code = "SUPPORT_ROUTE_UNAVAILABLE"
    status_code = 422


class SessionExpiredError(AskVeraError):
    """Raised when a closed or inactive conversation receives a new message."""

    error_code = "SESSION_EXPIRED"
    status_code = 409

    def __init__(self, message: str = "This chat has ended. Please start a new chat.") -> None:
        super().__init__(message)
