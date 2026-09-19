"""Phase 3 Lane 3: detect_personal_account_request.

docs/conversation-quality/phase3/CX_LANES.md. Positive cases are the five
lookup shapes documented in config/personal_account_vocabulary.py; negative
cases are the general-policy questions that use "my" but must NOT trigger
the personal-account note, in several languages, per the Lane 3 brief.

Fable CX review finding S1 (2026-09-19, should-fix, all 12 languages) added
a second negative block below: 23/23 policy-shaped probes ("what is my
bonus PERCENTAGE as a <role>", "what is my commission RATE", "do I need my
order number...") wrongly matched the first shipped version of this
vocabulary. See config/personal_account_vocabulary.py's module docstring
for the fix (commission/bonus removed from the bare current-value shape;
every identifier shape anchored to an explicit lookup verb) and
``test_fable_s1_rate_and_need_probes_are_not_personal_account`` below for
every reproduction, in all 12 languages.
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
        "Track my order",
        "Has my payment been received?",
        "Did my commission arrive yet?",
        "Was my payment received?",
        "What is my balance?",
        "How many points do I have?",
        "How much did I earn this month?",
        "How much did I earn last month?",
        "Where is my bonus payment?",
        "What's my tracking number?",
    ],
)
def test_detects_personal_account_lookup_in_english(question: str) -> None:
    assert detect_personal_account_request(question, "en") is True


# --- Positives in other languages, including the new (b) commission/bonus
# state-or-time-marker shape Fable's finding requires stay covered even
# though the bare "what is my commission/bonus" match is gone. -------------


@pytest.mark.parametrize(
    "language,question",
    [
        ("es", "¿Dónde está mi pedido?"),
        ("es", "¿Cuál es mi saldo?"),
        ("es", "¿Se ha pagado mi comisión?"),
        ("fr", "Où est ma commande?"),
        ("fr", "Quel est mon solde?"),
        ("fr", "Ma commission a-t-elle été payée?"),
        ("de", "Wo ist meine Bestellung?"),
        ("de", "Wie hoch ist mein Kontostand?"),
        ("de", "Wurde mein Bonus ausgezahlt?"),
        ("de", "Ist meine Provision bezahlt?"),
        ("it", "Dov'è il mio ordine?"),
        ("it", "Qual è il mio saldo?"),
        ("it", "Il mio bonus è stato pagato?"),
        ("nl", "Waar is mijn bestelling?"),
        ("nl", "Wat is mijn saldo?"),
        ("nl", "Is mijn bonus betaald?"),
        ("fi", "Missä tilaukseni on?"),
        ("fi", "Onko bonukseni maksettu?"),
        ("sv", "Var är min order?"),
        ("sv", "Vad är min saldo?"),
        ("da", "Hvor er min ordre?"),
        ("no", "Hvor er min bestilling?"),
        ("ru", "Где мой заказ?"),
        ("ru", "Какой мой баланс?"),
        ("sr", "Где је моја поруџбина?"),
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


# --- Fable CX review finding S1 (2026-09-19): 23/23 rate/role/"need"
# probes that wrongly matched before the fix. Every one of Fable's two
# repro shapes, in all 12 route languages. ----------------------------------


@pytest.mark.parametrize(
    "language,question",
    [
        # Shape 1: rate/percentage-as-a-role questions (the bare
        # "what is my commission/bonus" match this module used to accept).
        ("en", "What is my bonus percentage as an Assistant Supervisor?"),
        ("en", "What is my commission rate?"),
        ("de", "Wie hoch ist mein Bonus als Supervisor?"),
        ("de", "Wie hoch ist meine Provision als Supervisor?"),
        ("es", "¿Cuál es mi porcentaje de bono como Supervisor Asistente?"),
        ("es", "¿Cuál es mi tasa de comisión?"),
        ("fr", "Quel est mon pourcentage de bonus en tant que Superviseur Adjoint?"),
        ("fr", "Quel est mon taux de commission?"),
        ("it", "Qual è la mia percentuale di bonus come Supervisore Assistente?"),
        ("it", "Qual è il mio tasso di commissione?"),
        ("nl", "Wat is mijn bonuspercentage als Assistent Supervisor?"),
        ("nl", "Wat is mijn commissiepercentage?"),
        ("sv", "Vad är min bonusprocent som Assisterande Supervisor?"),
        ("sv", "Vad är min provisionssats?"),
        ("da", "Hvad er min bonusprocent som Assisterende Supervisor?"),
        ("da", "Hvad er min provisionssats?"),
        ("no", "Hva er min bonusprosent som Assisterende Supervisor?"),
        ("no", "Hva er min provisjonssats?"),
        ("fi", "Mikä on bonusprosenttini apulaisvalvojana?"),
        ("fi", "Mikä on palkkioprosenttini?"),
        ("ru", "Какой у меня процент бонуса как ассистента супервайзера?"),
        ("ru", "Какая у меня комиссионная ставка?"),
        ("sr", "Колико је мој проценат бонуса као помоћника супервизора?"),
        ("sr", "Колики је мој проценат провизије?"),
        # Shape 2: "do I need my order number..." capability questions (the
        # bare, unanchored "my order/tracking/account number" match).
        ("en", "Do I need my order number to return a product?"),
        ("de", "Brauche ich meine Bestellnummer für eine Rücksendung?"),
        ("es", "¿Necesito mi número de pedido para una devolución?"),
        ("fr", "Ai-je besoin de mon numéro de commande pour un retour?"),
        ("it", "Ho bisogno del mio numero d'ordine per un reso?"),
        ("nl", "Heb ik mijn bestelnummer nodig voor een retour?"),
        ("sv", "Behöver jag mitt ordernummer för en retur?"),
        ("da", "Har jeg brug for mit ordrenummer til en retur?"),
        ("no", "Trenger jeg bestillingsnummeret mitt for en retur?"),
        ("fi", "Tarvitsenko tilausnumeroni palautusta varten?"),
        ("ru", "Нужен ли мне номер заказа для возврата?"),
        ("sr", "Да ли ми је потребан број поруџбине за повраћај?"),
    ],
)
def test_fable_s1_rate_and_need_probes_are_not_personal_account(language: str, question: str) -> None:
    assert detect_personal_account_request(question, language) is False


def test_unrecognised_language_never_matches() -> None:
    assert detect_personal_account_request("Where is my order?", "xx") is False


def test_empty_question_never_matches() -> None:
    assert detect_personal_account_request("", "en") is False
    assert detect_personal_account_request(None, "en") is False  # type: ignore[arg-type]


def test_region_tagged_language_code_normalizes_like_contact_completion() -> None:
    assert detect_personal_account_request("Où est ma commande?", "fr-FR") is True
