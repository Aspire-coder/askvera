"""Secure market-routed support request delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from config import settings
from services.aws_clients import get_aws_clients
from services.market_config import get_country_codes
from services.session import get_session_history
from services.support_routes import get_active_support_route, list_support_routes
from utils.exceptions import SupportRouteUnavailableError, SupportUnavailableError
from utils.logging import get_logger
from utils.validators import SupportRequest

LOGGER = get_logger("services.support")


@dataclass(frozen=True)
class SupportDelivery:
    """Non-sensitive support delivery result returned to the API layer."""

    ticket_id: str
    route_name: str


def _routes() -> dict[str, dict[str, str]]:
    routes = settings.SUPPORT_ROUTES_JSON
    if not isinstance(routes, dict):
        raise SupportUnavailableError("Support routing is not configured.")
    return routes


def _valid_route(route: object) -> bool:
    return (
        isinstance(route, dict)
        and bool(str(route.get("department") or "").strip())
        and bool(str(route.get("email") or "").strip())
    )


def support_country_codes() -> list[str]:
    """Return configured support markets without exposing route destinations."""
    if not settings.SUPPORT_EMAIL_ENABLED:
        return []
    managed = [str(route["country"]) for route in list_support_routes() if route.get("enabled")]
    if managed:
        return sorted(set(managed))
    if not isinstance(settings.SUPPORT_ROUTES_JSON, dict):
        return []
    if _valid_route(settings.SUPPORT_DEFAULT_ROUTE_JSON):
        return sorted(get_country_codes())
    return sorted(
        str(country).upper()
        for country, route in settings.SUPPORT_ROUTES_JSON.items()
        if _valid_route(route)
    )


def _route_for(country: str) -> tuple[str, str]:
    route: Any = get_active_support_route(country)
    if route:
        return str(route["department"]), str(route["email"])
    route = _routes().get(country.upper())
    if not _valid_route(route):
        route = settings.SUPPORT_DEFAULT_ROUTE_JSON
    if not _valid_route(route):
        raise SupportRouteUnavailableError("Support requests are not yet available for this market.")
    department = str(route.get("department") or "").strip()
    recipient = str(route.get("email") or "").strip()
    if not department or not recipient:
        raise SupportRouteUnavailableError("Support requests are not yet available for this market.")
    return department, recipient


def _ticket_id(correlation_id: str) -> str:
    date = datetime.now(UTC).strftime("%Y%m%d")
    reference = "".join(character for character in correlation_id if character.isalnum())[:10].upper()
    return f"ASKVERA-{date}-{reference}"


def send_support_request(body: SupportRequest, correlation_id: str) -> SupportDelivery:
    """Submit a support email without exposing its internal destination."""
    if not settings.SUPPORT_EMAIL_ENABLED or not settings.SUPPORT_EMAIL_FROM.strip():
        raise SupportUnavailableError("Support email delivery is not configured.")

    department, recipient = _route_for(body.country)
    ticket_id = _ticket_id(correlation_id)
    subject = f"{settings.SUPPORT_EMAIL_SUBJECT_PREFIX} [{ticket_id}] - {body.country}"
    transcript = get_session_history(body.sessionId, correlation_id).strip()
    question_count = sum(1 for line in transcript.splitlines() if line.lower().startswith("user:"))
    summary = (
        f"The customer asked {question_count} question{'s' if question_count != 1 else ''} in this chat. "
        f"The support request is: {body.question}"
    )
    transcript_text = transcript or "No earlier chat transcript was available."
    plain_text = (
        f"AskVera support request\n\n"
        f"Reference: {ticket_id}\nDepartment: {department}\nMarket: {body.country}\n"
        f"Language: {body.language}\nFirst name: {body.firstName}\nEmail: {body.email}\n\n"
        f"Quick summary:\n{summary}\n\n"
        f"Question or issue:\n{body.question}\n\n"
        f"Recent AskVera conversation:\n{transcript_text}\n\n"
        f"AskVera session: {body.sessionId}\nSource message: {body.messageId or 'Not linked'}\n"
    )
    html_body = (
        "<h2>AskVera support request</h2>"
        f"<p><strong>Reference:</strong> {escape(ticket_id)}<br>"
        f"<strong>Department:</strong> {escape(department)}<br>"
        f"<strong>Market:</strong> {escape(body.country)}<br>"
        f"<strong>Language:</strong> {escape(body.language)}<br>"
        f"<strong>First name:</strong> {escape(body.firstName)}<br>"
        f"<strong>Email:</strong> {escape(body.email)}</p>"
        f"<h3>Quick summary</h3><p>{escape(summary)}</p>"
        f"<h3>Question or issue</h3><p>{escape(body.question).replace(chr(10), '<br>')}</p>"
        f"<h3>Recent AskVera conversation</h3>"
        f"<pre style=\"white-space:pre-wrap;font-family:Arial,sans-serif\">{escape(transcript_text)}</pre>"
        f"<p><small>AskVera session: {escape(body.sessionId)}<br>"
        f"Source message: {escape(body.messageId or 'Not linked')}</small></p>"
    )

    try:
        get_aws_clients().ses.send_email(
            Source=settings.SUPPORT_EMAIL_FROM,
            Destination={"ToAddresses": [recipient]},
            ReplyToAddresses=[body.email],
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": plain_text, "Charset": "UTF-8"},
                    "Html": {"Data": html_body, "Charset": "UTF-8"},
                },
            },
        )
    except (BotoCoreError, ClientError) as exc:
        LOGGER.exception("support_email_failed", correlation_id=correlation_id, country=body.country, route_name=department)
        raise SupportUnavailableError("The support request could not be sent. Please try again.") from exc

    LOGGER.info("support_email_submitted", correlation_id=correlation_id, ticket_id=ticket_id, country=body.country, route_name=department)
    return SupportDelivery(ticket_id=ticket_id, route_name=department)
