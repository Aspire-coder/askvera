"""Header authentication for operational admin endpoints."""

from hmac import compare_digest

from fastapi import Header, HTTPException

from config import settings


def require_admin_key(x_admin_key: str = Header(default="")) -> None:
    """Require the separately managed admin API key."""
    configured = str(settings.ADMIN_API_KEY or "")
    if not configured or not x_admin_key or not compare_digest(configured, x_admin_key):
        raise HTTPException(status_code=401, detail="A valid admin key is required.")
