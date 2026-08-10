"""Disabled-by-default webhook boundary for a future WhatsApp channel."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from config import settings

whatsapp_router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


def _require_enabled() -> None:
    if not settings.WHATSAPP_ENABLED:
        raise HTTPException(status_code=404, detail="WhatsApp channel is not enabled.")


def _verify_signature(raw_body: bytes, signature: str) -> None:
    secret = settings.WHATSAPP_APP_SECRET
    if not secret:
        return
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=403, detail="Invalid webhook signature.")


@whatsapp_router.get("/webhook")
async def verify_webhook(request: Request) -> Any:
    _require_enabled()
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode != "subscribe" or not settings.WHATSAPP_VERIFY_TOKEN or not hmac.compare_digest(
        token or "", settings.WHATSAPP_VERIFY_TOKEN
    ):
        raise HTTPException(status_code=403, detail="Webhook verification failed.")
    return int(challenge) if challenge and challenge.isdigit() else (challenge or "")


@whatsapp_router.post("/webhook")
async def receive_webhook(request: Request) -> dict[str, Any]:
    _require_enabled()
    body = await request.body()
    _verify_signature(body, request.headers.get("x-hub-signature-256", ""))
    # The channel is intentionally an acknowledgement boundary until Meta
    # credentials, message routing, consent, and outbound delivery are approved.
    return {"success": True, "data": {"accepted": True}}
