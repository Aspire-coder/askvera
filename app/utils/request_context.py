"""Helpers for reading request-scoped context."""

from fastapi import Request

from app.utils.context import correlation_id_ctx


def get_correlation_id(request: Request | None = None) -> str:
    """Return the correlation ID from async context or request state."""
    correlation_id = correlation_id_ctx.get()
    if correlation_id:
        return correlation_id
    if request is None:
        return ""
    return getattr(request.state, "correlation_id", "")
