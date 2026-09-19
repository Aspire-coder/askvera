"""Phase 3 Lane 3: detect_personal_account_request.

docs/conversation-quality/phase3/CX_LANES.md. Positive cases are the five
lookup shapes documented in config/personal_account_vocabulary.py; negative
cases are the general-policy questions that use "my" but must NOT trigger
the personal-account note, in several languages, per the Lane 3 brief.
"""

from __future__ import annotations

import pytest

from app.response.personal_account import detect_personal_account_request
from config.personal_account_vocabulary import supported_languages


def test_supported_languages_cover_the_twelve_route_locales() -> None:
    # da de en es fi fr it nl no ru sr sv - the CX route-copy language set
    # named in the Lane 3 brief.
    assert supported_languages() == frozenset(
        {"da", "de", "en", "es", "fi", "fr", "it", "nl", "no", "ru", "sr", "sv"}
    )


# --- Positives: one per lookup shape, in English -------------------------


@pytest.mark.parametrize(
    "question",
    [
        "Where is my order?",
        "What is the status of my shipment?",
        "My order status, please",
        "Has my payment been received?",
        "Did my commission arrive yet?",
        "What is my balance?",
        "How many points do I have?",
        "How much did I earn this month?",
        "What's my tracking number?",
    ],
)
def test_detects_personal_account_lookup_in_english(question: str) -> None:
    assert detect_personal_account_request(question, "en") is True


# --- Positives in other languages -----------------------------------------


@pytest.mark.parametrize(
    "language,question",
    [
        ("es", "¿Dónde está mi pedido?"),
        ("es", "¿Cuál es mi saldo?"),
        ("fr", "Où est ma commande?"),
        ("fr", "Quel est mon solde?"),
        ("de", "Wo ist meine Bestellung?"),
        ("de", "Wie hoch ist mein Kontostand?"),
        ("fi", "Missä tilaukseni on?"),
        ("sv", "Var är min order?"),
        ("sv", "Vad är min bonus?"),
        ("ru", "Где мой заказ?"),
        ("sr", "Где је моја поруџбина?"),
        ("it", "Dov'è il mio ordine?"),
        ("nl", "Waar is mijn bestelling?"),
        ("no", "Hvor er min bestilling?"),
        ("da", "Hvor er min ordre?"),
    ],
)
def test_detects_personal_account_lookup_multilingual(language: str, question: str) -> None:
    assert detect_personal_account_request(question, language) is True


# --- Negatives: general policy questions using "my" -----------------------
# Exactly the four shapes the Lane 3 brief calls out as must-not-match,
# translated into several languages.


@pytest.mark.parametrize(
    "language,question",
    [
        ("en", "How is my bonus calculated?"),
        ("en", "When will my commission be paid?"),
        ("en", "Can I return my order?"),
        ("en", "What are the payment methods for my order?"),
        ("es", "¿Cómo se calcula mi bono?"),
        ("es", "¿Cuándo se pagará mi comisión?"),
        ("es", "¿Puedo devolver mi pedido?"),
        ("fr", "Comment est calculée ma commission?"),
        ("fr", "Quand ma commission sera-t-elle payée?"),
        ("fr", "Puis-je retourner ma commande?"),
        ("de", "Wie wird mein Bonus berechnet?"),
        ("de", "Wann wird meine Provision bezahlt?"),
        ("de", "Kann ich meine Bestellung zurückgeben?"),
        ("fi", "Miten bonukseni lasketaan?"),
        ("sv", "Hur beräknas min bonus?"),
        ("ru", "Как рассчитывается мой бонус?"),
        ("ru", "Где заказ?"),  # no possessive at all - must fail conservatively
        ("sr", "Како се израчунава моја провизија?"),
    ],
)
def test_general_policy_question_with_possessive_is_not_personal_account(language: str, question: str) -> None:
    assert detect_personal_account_request(question, language) is False


def test_unrecognised_language_never_matches() -> None:
    assert detect_personal_account_request("Where is my order?", "xx") is False


def test_empty_question_never_matches() -> None:
    assert detect_personal_account_request("", "en") is False
    assert detect_personal_account_request(None, "en") is False  # type: ignore[arg-type]


def test_region_tagged_language_code_normalizes_like_contact_completion() -> None:
    assert detect_personal_account_request("Où est ma commande?", "fr-FR") is True
