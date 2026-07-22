from types import SimpleNamespace

import pytest

from services import support
from utils.exceptions import SupportRouteUnavailableError, SupportUnavailableError
from utils.validators import SupportRequest


class FakeSes:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def send_email(self, **kwargs):
        self.calls.append(kwargs)
        return {"MessageId": "ses-message"}


def request() -> SupportRequest:
    return SupportRequest(
        sessionId="session-1",
        messageId="answer-1",
        firstName="Taylor",
        email="Taylor@example.com",
        question="I need help with my account.",
        country="GB",
        language="en",
    )


def test_support_request_validates_and_normalizes_contact_fields():
    body = request()
    assert body.country == "GB"
    assert body.email == "taylor@example.com"

    with pytest.raises(ValueError):
        request().model_copy(update={"email": "not-an-email"}) if False else SupportRequest(
            sessionId="session-1",
            firstName="Taylor",
            email="not-an-email",
            question="Help",
            country="GB",
            language="en",
        )


def test_support_delivery_routes_server_side_and_uses_reply_to(monkeypatch):
    ses = FakeSes()
    monkeypatch.setattr(support.settings, "SUPPORT_EMAIL_ENABLED", True)
    monkeypatch.setattr(support.settings, "SUPPORT_EMAIL_FROM", "askvera@example.com")
    monkeypatch.setattr(support.settings, "SUPPORT_EMAIL_SUBJECT_PREFIX", "AskVera support")
    monkeypatch.setattr(
        support.settings,
        "SUPPORT_ROUTES_JSON",
        {"GB": {"department": "Customer Services", "email": "tickets@example.com"}},
    )
    monkeypatch.setattr(support.settings, "SUPPORT_DEFAULT_ROUTE_JSON", {})
    monkeypatch.setattr(support, "get_aws_clients", lambda: SimpleNamespace(ses=ses))

    delivery = support.send_support_request(request(), "12345678-abcd")

    assert delivery.route_name == "Customer Services"
    assert delivery.ticket_id.startswith("ASKVERA-")
    assert ses.calls[0]["Destination"] == {"ToAddresses": ["tickets@example.com"]}
    assert ses.calls[0]["ReplyToAddresses"] == ["taylor@example.com"]
    assert "I need help with my account." in ses.calls[0]["Message"]["Body"]["Text"]["Data"]


def test_support_delivery_rejects_unconfigured_market(monkeypatch):
    monkeypatch.setattr(support.settings, "SUPPORT_EMAIL_ENABLED", True)
    monkeypatch.setattr(support.settings, "SUPPORT_EMAIL_FROM", "askvera@example.com")
    monkeypatch.setattr(support.settings, "SUPPORT_ROUTES_JSON", {})
    monkeypatch.setattr(support.settings, "SUPPORT_DEFAULT_ROUTE_JSON", {})
    with pytest.raises(SupportRouteUnavailableError):
        support.send_support_request(request(), "cid")


def test_support_delivery_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(support.settings, "SUPPORT_EMAIL_ENABLED", False)
    with pytest.raises(SupportUnavailableError):
        support.send_support_request(request(), "cid")


def test_support_question_rejects_sensitive_credentials(monkeypatch):
    body = request().model_copy(update={"question": "My password is secret-value"})
    monkeypatch.setattr(support, "scrub_pii", lambda *_args, **_kwargs: "My password is [PASSWORD]")

    with pytest.raises(SupportUnavailableError, match="Remove passwords"):
        support.sanitize_support_question(body, "cid")


def test_support_question_uses_scrubbed_non_sensitive_text(monkeypatch):
    body = request().model_copy(update={"question": "Call me at 555-123-4567"})
    monkeypatch.setattr(support, "scrub_pii", lambda *_args, **_kwargs: "Call me at [PHONE]")

    safe_body = support.sanitize_support_question(body, "cid")

    assert safe_body.question == "Call me at [PHONE]"


def test_support_country_codes_expose_availability_not_destinations(monkeypatch):
    monkeypatch.setattr(support.settings, "SUPPORT_EMAIL_ENABLED", True)
    monkeypatch.setattr(
        support.settings,
        "SUPPORT_ROUTES_JSON",
        {
            "GB": {"department": "Customer Services", "email": "tickets@example.com"},
            "DE": {"department": "Germany", "email": "de@example.com"},
            "XX": {"department": "", "email": "missing@example.com"},
        },
    )
    monkeypatch.setattr(support.settings, "SUPPORT_DEFAULT_ROUTE_JSON", {})
    assert support.support_country_codes() == ["DE", "GB"]


def test_default_route_supports_every_published_market(monkeypatch):
    ses = FakeSes()
    monkeypatch.setattr(support.settings, "SUPPORT_EMAIL_ENABLED", True)
    monkeypatch.setattr(support.settings, "SUPPORT_EMAIL_FROM", "askvera@example.com")
    monkeypatch.setattr(support.settings, "SUPPORT_EMAIL_SUBJECT_PREFIX", "AskVera support")
    monkeypatch.setattr(support.settings, "SUPPORT_ROUTES_JSON", {})
    monkeypatch.setattr(
        support.settings,
        "SUPPORT_DEFAULT_ROUTE_JSON",
        {"department": "Global Support", "email": "global@example.com"},
    )
    monkeypatch.setattr(support, "get_country_codes", lambda: {"CA", "GB", "US"})
    monkeypatch.setattr(support, "get_aws_clients", lambda: SimpleNamespace(ses=ses))

    assert support.support_country_codes() == ["CA", "GB", "US"]
    delivery = support.send_support_request(request(), "cid")
    assert delivery.route_name == "Global Support"
    assert ses.calls[0]["Destination"] == {"ToAddresses": ["global@example.com"]}


def test_country_route_overrides_default_route(monkeypatch):
    monkeypatch.setattr(
        support.settings,
        "SUPPORT_ROUTES_JSON",
        {"GB": {"department": "UK Support", "email": "uk@example.com"}},
    )
    monkeypatch.setattr(
        support.settings,
        "SUPPORT_DEFAULT_ROUTE_JSON",
        {"department": "Global Support", "email": "global@example.com"},
    )

    assert support._route_for("GB") == ("UK Support", "uk@example.com")
