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

Fable's re-review of that fix (2026-09-19, findings F2/F3) added two more
blocks: F2 (should-fix) -- "What is my volume requirement to stay active?"
still matched the current-value shape because that shape didn't care what
came after the noun; see ``test_fable_f2_requirement_purpose_probes_are_not_personal_account``
for every reproduction. F3 (low) -- the S1 narrowing dropped real lookups
that pair commission/bonus/earnings with an explicit time marker ("What is
my commission this month?", "Did my bonus get paid this month?"); see
``test_fable_f3_commission_bonus_with_time_marker_is_personal_account``.
Both are covered in all 12 languages, and every S1 negative above is
re-asserted in ``test_fable_s1_rate_and_need_probes_are_not_personal_account``
to confirm F2/F3 did not reopen S1.

Fable's re-review of the F2/F3 fix (2026-09-19, all confirmed) found two
more low-priority gaps in the veto lists, both low priority: F2-A --
"What is my volume and how is it calculated under the policy?" and "What is
my points quota to keep my status?" still matched the current-value shape
(the veto word list lacked "quota"/"to keep", and had no role/conditional/
general/policy/calculated veto at all), and the new F3 time-marker shape had
no trailing veto, so "What is my commission this month if I reach Manager?"
and "How much is my bonus this month as a Supervisor in general?" wrongly
got the note. See
``test_fable_f2a_extended_veto_probes_are_not_personal_account`` for every
reproduction, in every language where the corresponding shape exists. F2-B
-- the "for the ..." veto was too broad and wrongly excluded a genuine
time-scoped lookup, "What is my volume for the month?"; see
``test_fable_f2b_for_the_month_or_week_is_a_time_marker_not_purpose``.
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
        ("sv", "Vad är mitt saldo?"),  # grammatical Swedish (Fable re-review)
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


# --- Fable CX review finding F2 (2026-09-19, should-fix): a requirement/
# rule/purpose clause after the current-value shape must still not match,
# in all 12 languages. ------------------------------------------------------


@pytest.mark.parametrize(
    "language,question",
    [
        ("en", "What is my volume requirement to stay active?"),
        ("en", "What is my balance requirement for the 2CC rule?"),
        ("de", "Wie hoch ist mein Guthaben, um aktiv zu bleiben?"),
        ("de", "Wie hoch ist mein Kontostand Anforderung für die 2CC-Regel?"),
        ("es", "¿Cuál es mi requisito de puntos para permanecer activo?"),
        ("es", "¿Cuál es mi saldo requisito para la regla del 2CC?"),
        ("fr", "Quel est mon solde exigence pour rester actif?"),
        ("fr", "Quel est mon nombre de points exigence pour la règle du 2CC?"),
        ("it", "Qual è il mio saldo requisito per rimanere attivo?"),
        ("it", "Qual è il mio numero di punti requisito per la regola del 2CC?"),
        ("nl", "Wat is mijn saldo vereiste om actief te blijven?"),
        ("nl", "Wat is mijn aantal punten vereiste voor de 2CC-regel?"),
        ("sv", "Vad är mitt saldo krav för att förbli aktiv?"),
        ("sv", "Vad är min poäng krav för regeln 2CC?"),
        ("da", "Hvad er min saldo krav for at forblive aktiv?"),
        ("da", "Hvad er min pointsum krav for reglen 2CC?"),
        ("no", "Hva er min saldo krav for å forbli aktiv?"),
        ("no", "Hva er min poengsum krav for regelen 2CC?"),
        ("fi", "Mikä on saldoni vaatimus pysyäkseni aktiivisena?"),
        ("fi", "Mikä on pisteideni määrä vaatimus säännön mukaan?"),
        ("ru", "Какой мой баланс требование, чтобы остаться активным?"),
        ("ru", "Какой мой остаток баллов требование для правила 2CC?"),
        ("sr", "Колико је моје стање услов да останем активан?"),
        ("sr", "Колико је мој број поена услов за правило 2CC?"),
    ],
)
def test_fable_f2_requirement_purpose_probes_are_not_personal_account(language: str, question: str) -> None:
    assert detect_personal_account_request(question, language) is False


# --- Fable CX review finding F3 (2026-09-19, low): commission/bonus/
# earnings paired with an explicit time marker IS a real lookup, in all 12
# languages -- the S1 narrowing must not have dropped this shape. ----------


@pytest.mark.parametrize(
    "language,question",
    [
        ("en", "What is my commission this month?"),
        ("en", "What is my bonus last month?"),
        ("en", "How much is my earnings so far?"),
        ("en", "Did my bonus get paid this month?"),
        ("de", "Wie hoch ist meine Provision diesen Monat?"),
        ("de", "Wurde mein Bonus ausgezahlt?"),
        ("es", "¿Cuál es mi comisión este mes?"),
        ("fr", "Quel est mon bonus ce mois-ci ?"),
        ("it", "Qual è la mia commissione questo mese?"),
        ("nl", "Wat is mijn commissie deze maand?"),
        ("sv", "Vad är min provision denna månad?"),
        ("da", "Hvad er min provision denne måned?"),
        ("no", "Hva er min provisjon denne måneden?"),
        ("fi", "Mikä on palkkioni tässä kuussa?"),
        ("ru", "Какая моя комиссия в этом месяце?"),
        ("sr", "Колика је моја провизија овог месеца?"),
    ],
)
def test_fable_f3_commission_bonus_with_time_marker_is_personal_account(language: str, question: str) -> None:
    assert detect_personal_account_request(question, language) is True


# --- Fable CX review finding F2-A (2026-09-19, low): the veto list needed
# "quota"/"to keep" on the current-value shape, and a role/conditional/
# general/policy/calculated veto on the F3 time-marker shape too. Covered
# in every language where each shape exists (Finnish and the Slavic
# languages have no F3-shaped positive for "if I..."/"as a role", so those
# are omitted rather than forced). --------------------------------------


@pytest.mark.parametrize(
    "language,question",
    [
        # Current-value shape: "quota" / "to keep" additions.
        ("en", "What is my volume and how is it calculated under the policy?"),
        ("en", "What is my points quota to keep my status?"),
        ("de", "Wie hoch ist mein Guthaben, wenn ich Supervisor werde?"),
        ("de", "Wie hoch ist mein Punktestand Quote, um meinen Status zu behalten?"),
        ("es", "¿Cuál es mi saldo y cómo se calcula según la política?"),
        ("es", "¿Cuál es mi cuota de puntos para mantener mi estado?"),
        ("fr", "Quel est mon solde et comment est-il calculé selon la politique?"),
        ("fr", "Quel est mon quota de points pour garder mon statut?"),
        ("it", "Qual è il mio saldo e come viene calcolato secondo la politica?"),
        ("it", "Qual è la mia quota di punti per mantenere il mio stato?"),
        ("nl", "Wat is mijn saldo en hoe wordt het berekend volgens het beleid?"),
        ("nl", "Wat is mijn quotum aan punten om mijn status te behouden?"),
        ("sv", "Vad är mitt saldo och hur beräknas det enligt policyn?"),
        ("sv", "Vad är min poäng kvot för att behålla min status?"),
        ("da", "Hvad er min saldo, og hvordan beregnes det ifølge politikken?"),
        ("da", "Hvad er min pointsum kvote for at beholde min status?"),
        ("no", "Hva er min saldo, og hvordan beregnes det ifølge policyen?"),
        ("no", "Hva er min poengsum kvote for å beholde min status?"),
        ("fi", "Mikä on saldoni ja miten se lasketaan käytännön mukaan?"),
        ("fi", "Mikä on pisteideni määrä kiintiö säilyttääkseni asemani?"),
        ("ru", "Какой мой баланс и как это рассчитывается согласно политике?"),
        ("ru", "Какой мой остаток баллов квота, чтобы сохранить мой статус?"),
        ("sr", "Колико је моје стање и како се то израчунава према политици?"),
        ("sr", "Колико је мој број поена квота да задржим свој статус?"),
        # F3 time-marker shape: role/conditional/general veto.
        ("en", "What is my commission this month if I reach Manager?"),
        ("en", "How much is my bonus this month as a Supervisor in general?"),
        ("de", "Wie hoch ist meine Provision diesen Monat, wenn ich Manager werde?"),
        ("de", "Wie hoch ist mein Bonus diesen Monat als Supervisor im Allgemeinen?"),
        ("es", "¿Cuál es mi comisión este mes si llego a Gerente?"),
        ("es", "¿Cuánto es mi bono este mes como Supervisor en general?"),
        ("fr", "Quel est mon bonus ce mois-ci si je deviens Manager?"),
        ("fr", "Combien est ma commission ce mois-ci en tant que Superviseur en général?"),
        ("it", "Qual è la mia commissione questo mese se divento Manager?"),
        ("it", "Quanto è il mio bonus questo mese come Supervisore in generale?"),
        ("nl", "Wat is mijn commissie deze maand als ik Manager word?"),
        ("nl", "Hoeveel is mijn bonus deze maand als Supervisor in het algemeen?"),
        ("sv", "Vad är min provision denna månad om jag blir chef?"),
        ("sv", "Hur mycket är min bonus denna månad som chef i allmänhet?"),
        ("da", "Hvad er min provision denne måned, hvis jeg bliver leder?"),
        ("da", "Hvor meget er min bonus denne måned som leder generelt?"),
        ("no", "Hva er min provisjon denne måneden hvis jeg blir leder?"),
        ("no", "Hvor mye er min bonus denne måneden som leder generelt?"),
        ("fi", "Mikä on palkkioni tässä kuussa, jos minusta tulee esimies?"),
        ("ru", "Какая моя комиссия в этом месяце, если я стану менеджером?"),
        ("sr", "Колика је моја провизија овог месеца ако постанем менаџер?"),
    ],
)
def test_fable_f2a_extended_veto_probes_are_not_personal_account(language: str, question: str) -> None:
    assert detect_personal_account_request(question, language) is False


# --- Fable CX review finding F2-B (2026-09-19, low): "for the month/week"
# (or "for this month") is a time marker, not a purpose clause -- it must
# NOT be vetoed by the requirement/rule exclusion. Only the languages whose
# veto phrase is a generic preposition+determiner (en/de/es/fr/it/nl) can
# clash with this; the others (sv/da/no/fi/ru/sr) use a rule-specific
# phrase ("för regeln", "säännön mukaan", ...) that never overlaps with
# "for the month/week" in the first place. ---------------------------------


@pytest.mark.parametrize(
    "language,question",
    [
        ("en", "What is my volume for the month?"),
        ("en", "What is my balance for the week?"),
        ("en", "What is my points for this month?"),
        ("de", "Wie hoch ist mein Guthaben für die Woche?"),
        ("es", "¿Cuál es mi saldo para la semana?"),
        ("fr", "Quel est mon solde pour la semaine?"),
        ("it", "Qual è il mio saldo per la settimana?"),
        ("nl", "Wat is mijn saldo voor de maand?"),
        ("nl", "Wat is mijn saldo voor de week?"),
    ],
)
def test_fable_f2b_for_the_month_or_week_is_a_time_marker_not_purpose(language: str, question: str) -> None:
    assert detect_personal_account_request(question, language) is True


def test_unrecognised_language_never_matches() -> None:
    assert detect_personal_account_request("Where is my order?", "xx") is False


def test_empty_question_never_matches() -> None:
    assert detect_personal_account_request("", "en") is False
    assert detect_personal_account_request(None, "en") is False  # type: ignore[arg-type]


def test_region_tagged_language_code_normalizes_like_contact_completion() -> None:
    assert detect_personal_account_request("Où est ma commande?", "fr-FR") is True
