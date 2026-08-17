from types import SimpleNamespace

from botocore.exceptions import ClientError

import pytest

from services import support
from utils.exceptions import SupportRouteUnavailableError, SupportUnavailableError
from utils.validators import SupportRequest


@pytest.fixture(autouse=True)
def no_managed_support_routes(monkeypatch):
    """Keep legacy SSM-route tests independent from the operations database."""
    monkeypatch.setattr(support, "get_active_support_route", lambda _country: None)
    monkeypatch.setattr(support, "list_support_routes", lambda: [])


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
    monkeypatch.setattr(
        support,
        "get_session_history",
        lambda *_args: "User: What is a Recognized Manager?\nAssistant: A policy answer.\n"
        "User: I still need help.",
    )

    delivery = support.send_support_request(request(), "12345678-abcd")

    assert delivery.route_name == "Customer Services"
    assert delivery.ticket_id.startswith("ASKVERA-")
    assert ses.calls[0]["Destination"] == {"ToAddresses": ["tickets@example.com"]}
    assert ses.calls[0]["ReplyToAddresses"] == ["taylor@example.com"]
    email_text = ses.calls[0]["Message"]["Body"]["Text"]["Data"]
    assert "I need help with my account." in email_text
    assert "The customer asked 2 questions" in email_text
    assert "What is a Recognized Manager?" in email_text
    assert "I still need help." in email_text


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
    monkeypatch.setattr(
        support,
        "get_session_history",
        lambda *_args: "User: Please help\nAssistant: I can create a support request.",
    )

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


def test_managed_country_route_overrides_ssm_route(monkeypatch):
    monkeypatch.setattr(
        support,
        "get_active_support_route",
        lambda country: {
            "country": country,
            "department": "Managed UK Support",
            "email": "managed@example.com",
        },
    )
    monkeypatch.setattr(
        support.settings,
        "SUPPORT_ROUTES_JSON",
        {"GB": {"department": "Legacy UK Support", "email": "legacy@example.com"}},
    )

    assert support._route_for("GB") == ("Managed UK Support", "managed@example.com")


def test_managed_routes_control_available_support_markets(monkeypatch):
    monkeypatch.setattr(support.settings, "SUPPORT_EMAIL_ENABLED", True)
    monkeypatch.setattr(
        support,
        "list_support_routes",
        lambda: [
            {"country": "GB", "enabled": True},
            {"country": "DE", "enabled": False},
            {"country": "SE", "enabled": True},
        ],
    )

    assert support.support_country_codes() == ["GB", "SE"]


def test_managed_fallback_is_used_when_primary_delivery_fails(monkeypatch):
    class FailoverSes:
        def __init__(self):
            self.calls = []

        def send_email(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                raise ClientError({"Error": {"Code": "ServiceUnavailable", "Message": "retry"}}, "SendEmail")
            return {"MessageId": "fallback"}

    ses = FailoverSes()
    monkeypatch.setattr(support.settings, "SUPPORT_EMAIL_ENABLED", True)
    monkeypatch.setattr(support.settings, "SUPPORT_EMAIL_FROM", "askvera@example.com")
    monkeypatch.setattr(support, "get_session_history", lambda *_: "User: Help")
    monkeypatch.setattr(support, "get_aws_clients", lambda: SimpleNamespace(ses=ses))
    monkeypatch.setattr(support, "get_active_support_route", lambda _country: {
        "department": "Primary", "email": "primary@example.com",
        "fallback_department": "Fallback", "fallback_email": "fallback@example.com",
    })

    delivery = support.send_support_request(request(), "cid")

    assert delivery.route_name == "Fallback"
    assert ses.calls[1]["Destination"] == {"ToAddresses": ["fallback@example.com"]}
