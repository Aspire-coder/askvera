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
    with pytest.raises(SupportRouteUnavailableError):
        support.send_support_request(request(), "cid")


def test_support_delivery_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(support.settings, "SUPPORT_EMAIL_ENABLED", False)
    with pytest.raises(SupportUnavailableError):
        support.send_support_request(request(), "cid")


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
    assert support.support_country_codes() == ["DE", "GB"]
