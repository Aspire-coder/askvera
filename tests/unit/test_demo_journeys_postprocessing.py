"""Demo journeys (L9): source-verified turns replayed through the real post-generation path.

A tuned development acceptance set, not an independent benchmark. Each test feeds
a scripted model answer and approved directory evidence into
`AIOrchestrator._secure_and_complete_response` (PII scrub stubbed, as in
test_chat_orchestrator) and checks what the reader would receive. Record text is
excerpted from the approved International Sponsoring Directory extract (worker C
manifest, DEMO_SOURCE_MANIFEST.md). Model generation, retrieval ranking and live
guardrails are not exercised here.
"""

import pytest

from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.response.models import ChatResponse
from app.retrieval.models import RetrievedDocument, RetrievalResult

KENYA = (
    "Forever Kenya/East Africa\n"
    "• Minimum order size FBO: $100 worth of products when joining, $50 of products after joining.\n"
    "• Delivery Cost: $3 within the country.\n"
    "• Payment methods accepted: Bank deposit, Credit Card, Mobile Money Transfer (Mpesa).\n"
    "Office & Product Center Address\n"
    "Kenya Reinsurance Plaza, 4th floor\n"
    "Business Hours Office 09.00 am – 19.00 pm (Mon – Fri)\n"
    "Telephone Office +254 20 2026869 / +254 20 2026873\n"
    "Telephone for Orders +254 71 0600206\n"
    "Email info@foreverea.com\n"
)
NETHERLANDS = (
    "Forever Netherlands Benelux\n"
    "Office Address Gerrit van der Veenlaan 16, 3743 DN Baarn, The Netherlands\n"
    "Business Hours Office 09.00 am – 17.00 pm (Mon – Fri)\n"
    "Telephone Office +31 88 646 0220 (Benelux)\n"
    "Email support@foreverliving.nl\n"
    "• Minimum order size FBO: €50,00 in products excl. VAT and excl. literature.\n"
    "• Delivery Cost: €5,00 excl. VAT per order. Orders above 2CC are free of charge.\n"
    "• Payment methods accepted: Credit card (Visa, MasterCard), Direct Debit, iDeal.\n"
)
BURKINA_FASO = (
    "Forever Burkina Faso\n"
    "Office & Product Centre Address\n"
    "Dapoya, Secteur 3\n"
    "Dimdolodomb – 01 BP 5070 Ouaga 01\n"
    "Business Hours Office 08.30 am – 16.30 pm (Mon – Fri)\n"
    "Telephone Office +226 25 30 62 03\n"
    "Email mfatoued2005@yahoo.fr\n"
)


@pytest.fixture(autouse=True)
def _no_comprehend(monkeypatch):
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)


def _record(slug: str, country_name: str, content: str) -> RetrievedDocument:
    return RetrievedDocument(
        id=f"GLOBAL|en|International-Sponsoring-Directory.pdf|{slug}",
        title="International-Sponsoring-Directory.pdf",
        content=content,
        source="International-Sponsoring-Directory.pdf",
        country="GLOBAL",
        language="en",
        score=0.9,
        metadata={"directory_kind": "international_sponsoring", "directory_section": "sponsoring",
                  "record_country": country_name, "section_id": slug},
    )


def _deliver(question: str, answer: str, record: RetrievedDocument, session_country: str = "US") -> str:
    retrieval = RetrievalResult(documents=[record], citations=[record.to_source()], confidence=0.9)
    response = ChatResponse(
        answer=answer, citations=[record.to_source()], suggestions=[], cards=[], confidence=0.9,
        metadata={}, correlation_id="cid",
    )
    return AIOrchestrator()._secure_and_complete_response(
        response, retrieval, "en", "cid", user_question=question, country=session_country,
    ).answer


# Journey 6: Netherlands delivery fee -> minimum order -> payment methods.
def test_j6_delivery_cost_keeps_vat_and_threshold_and_drops_unrequested_payment_line():
    record = _record("sponsoring-080-netherlands-benelux", "Netherlands Benelux", NETHERLANDS)
    answer = ("Delivery Cost: €5,00 excl. VAT per order. Orders above 2CC are free of charge.\n"
              "Payment methods accepted: Credit card, Direct Debit, iDeal.")

    delivered = _deliver("What is the delivery cost in the Netherlands?", answer, record, "NL")

    assert "€5,00 excl. VAT per order" in delivered
    assert "above 2CC" in delivered
    assert "iDeal" not in delivered


def test_j6_minimum_order_restores_the_complete_decimal_comma_value():
    record = _record("sponsoring-080-netherlands-benelux", "Netherlands Benelux", NETHERLANDS)

    delivered = _deliver("What is the minimum order size for an FBO in the Netherlands?",
                         "Orders are placed online.", record, "NL")

    assert "€50,00 in products excl. VAT and excl. literature" in delivered


# Journey 7 / 14: Kenya phone and email together; office vs order phone.
def test_j7_phone_and_email_are_both_kept_and_hours_removed():
    record = _record("sponsoring-012-kenya-east-africa", "Kenya/East Africa", KENYA)
    answer = ("Telephone Office: +254 20 2026869 / +254 20 2026873\n"
              "Email: info@foreverea.com\n"
              "Business Hours Office: 09.00 am – 19.00 pm (Mon – Fri)")

    delivered = _deliver("What is the Kenya office phone number and email?", answer, record, "KE")

    assert "+254 20 2026869" in delivered
    assert "info@foreverea.com" in delivered
    assert "09.00 am" not in delivered


def test_j14_office_phone_question_does_not_keep_the_order_phone_line():
    record = _record("sponsoring-012-kenya-east-africa", "Kenya/East Africa", KENYA)
    answer = "Telephone Office: +254 20 2026869 / +254 20 2026873\nTelephone for Orders: +254 71 0600206"

    delivered = _deliver("Is that the office phone for Kenya?", answer, record, "KE")

    assert "+254 20 2026869" in delivered
    assert "+254 71 0600206" not in delivered


# Journey 14 / 13: minimum order is restored for an FBO, never for a Preferred Customer.
def test_j14_fbo_minimum_order_restored_with_first_and_ongoing_amounts():
    record = _record("sponsoring-012-kenya-east-africa", "Kenya/East Africa", KENYA)

    delivered = _deliver("What is Kenya's minimum order size for an FBO?", "You can order at the office.", record, "KE")

    assert "$100 worth of products when joining" in delivered
    assert "Mpesa" not in delivered


def test_j13_preferred_customer_question_never_receives_the_fbo_figure():
    record = _record("sponsoring-012-kenya-east-africa", "Kenya/East Africa", KENYA)

    delivered = _deliver("Is there a minimum first order for a Preferred Customer in Kenya?",
                         "Yes, a first order is required when signing up as a Preferred Customer.", record, "KE")

    assert "$100" not in delivered


# Journey 11: Burkina Faso address with a sensitive placeholder in the contact block.
def test_j11_burkina_faso_address_has_no_empty_contact_container():
    record = _record("sponsoring-004-burkina-faso", "Burkina Faso", BURKINA_FASO)
    answer = ("The office address for Burkina Faso is:\n\nDapoya, Secteur 3, Dimdolodomb – 01 BP 5070 Ouaga 01, "
              "Burkina Faso\n\nYou can reach them at:\n- **[BANK_ACCOUNT]** - **")

    delivered = _deliver("What is the Forever Living office address for Burkina Faso?", answer, record, "NL")

    assert "Dapoya, Secteur 3" in delivered
    assert not delivered.rstrip().endswith(":")
    assert all(any(character.isalnum() for character in line) for line in delivered.splitlines() if line.strip())
