"""Multilingual directory-field-request detection. Deterministic/local: pure
regex post-processing in utils/directory_fields.py, no model or network call.

Phase 2 / Lane B (2026-09-18). Reproduced-before: every ``language=...`` case
below fails on the pre-fix code with ``TypeError: remove_unrequested_directory_fields()
got an unexpected keyword argument 'language'`` (recorded in the handoff),
since that parameter did not exist at all before this change.

Per language this exercises:
  - a positive multipart case (minimum order + payment methods): both halves
    survive, mirroring MULTIPART-001 for English
    (tests/conversation/test_intent_multipart_order_size_payment.py);
  - a negative case: an order-size-only question still sheds an unrequested
    field (business hours), proving the detector is not just "never strip
    anything for this language";
  - a duration-vs-business-hours control: a bare duration ("48 <hours-word>")
    is never read as a business-hours request, so it is stripped alongside
    payment when only the order size was asked for.

The answer text in every case stays the record's own canonical English
labels ("Minimum order size FBO:", "Payment methods accepted:", "Business
Hours:") - see config/directory_field_vocabulary.py's docstring for why the
localization only needs to interpret the QUESTION, not relabel the answer.
"""

from __future__ import annotations

import pytest

from utils.directory_fields import remove_unrequested_directory_fields

ANSWER = (
    "Minimum order size FBO: $100 worth of products when joining, $50 of products after joining.\n"
    "Business Hours: 08:00 am - 17:00 pm.\n"
    "Payment methods accepted: Bank deposit, Credit Card, Mobile Money Transfer (Mpesa)."
)
# Two-field answer (no business hours line) for the multipart positive case,
# so requesting only order size + payment methods leaves nothing else to
# strip and ``changed`` is genuinely False - mirrors KENYA_ANSWER in
# test_intent_multipart_order_size_payment.py.
TWO_FIELD_ANSWER = (
    "Minimum order size FBO: $100 worth of products when joining, $50 of products after joining.\n"
    "Payment methods accepted: Bank deposit, Credit Card, Mobile Money Transfer (Mpesa)."
)

# (language, multipart question, order-size-only question, duration-only question)
CASES = {
    "fr": (
        "Quelle est la commande minimum pour un FBO au Kenya, "
        "et quels moyens de paiement acceptent-ils ?",
        "Quelle est la commande minimum pour un FBO au Kenya ?",
        "Quelle est la commande minimum si j'ai besoin des produits dans 48 heures ?",
    ),
    "de": (
        "Was ist die Mindestbestellung für einen FBO in Kenia, "
        "und welche Zahlungsmethoden akzeptieren sie?",
        "Was ist die Mindestbestellung für einen FBO in Kenia?",
        "Was ist die Mindestbestellung, wenn ich die Produkte innerhalb von 48 Stunden brauche?",
    ),
    "nl": (
        "Wat is de minimale bestelling voor een FBO in Kenia, "
        "en welke betaalmethoden accepteren ze?",
        "Wat is de minimale bestelling voor een FBO in Kenia?",
        "Wat is de minimale bestelling als ik de producten binnen 48 uur nodig heb?",
    ),
    "es": (
        "¿Cuál es el pedido mínimo para un FBO en Kenia, "
        "y qué métodos de pago aceptan?",
        "¿Cuál es el pedido mínimo para un FBO en Kenia?",
        "¿Cuál es el pedido mínimo si necesito los productos dentro de 48 horas?",
    ),
    "it": (
        "Qual è l'ordine minimo per un FBO in Kenya, "
        "e quali metodi di pagamento accettano?",
        "Qual è l'ordine minimo per un FBO in Kenya?",
        "Qual è l'ordine minimo se ho bisogno dei prodotti entro 48 ore?",
    ),
    "pt": (
        "Qual é a encomenda mínima para um FBO no Quênia, "
        "e quais métodos de pagamento eles aceitam?",
        "Qual é a encomenda mínima para um FBO no Quênia?",
        "Qual é a encomenda mínima se eu precisar dos produtos em 48 horas?",
    ),
    "fi": (
        "Mikä on vähimmäistilaus FBO:lle Keniassa, "
        "ja mitä maksutapoja he hyväksyvät?",
        "Mikä on vähimmäistilaus FBO:lle Keniassa?",
        "Mikä on vähimmäistilaus, jos tarvitsen tuotteet 48 tunnin sisällä?",
    ),
    "no": (
        "Hva er minstebestillingen for en FBO i Kenya, "
        "og hvilke betalingsmetoder godtar de?",
        "Hva er minstebestillingen for en FBO i Kenya?",
        "Hva er minstebestillingen hvis jeg trenger produktene innen 48 timer?",
    ),
    "sv": (
        "Vad är minsta beställning för en FBO i Kenya, "
        "och vilka betalningsmetoder accepterar de?",
        "Vad är minsta beställning för en FBO i Kenya?",
        "Vad är minsta beställning om jag behöver produkterna inom 48 timmar?",
    ),
}


@pytest.mark.parametrize("language", sorted(CASES))
def test_multipart_order_and_payment_both_survive(language: str) -> None:
    multipart_question, _, _ = CASES[language]
    result, changed = remove_unrequested_directory_fields(TWO_FIELD_ANSWER, multipart_question, language=language)
    assert "$100 worth of products when joining" in result
    assert "Mpesa" in result
    assert changed is False


@pytest.mark.parametrize("language", sorted(CASES))
def test_order_size_only_sheds_unrequested_business_hours(language: str) -> None:
    _, order_only_question, _ = CASES[language]
    result, changed = remove_unrequested_directory_fields(ANSWER, order_only_question, language=language)
    assert "$100 worth of products when joining" in result
    assert "08:00 am" not in result
    assert "Mpesa" not in result
    assert changed is True


@pytest.mark.parametrize("language", sorted(CASES))
def test_bare_duration_is_never_read_as_business_hours(language: str) -> None:
    """"48 hours"/"48 heures"/"48 Stunden"/"48 tuntia"/... is a duration, not
    a business-hours request - the order size survives, business hours does
    not, exactly like the English case in test_order_size_field_keeping.py."""
    _, _, duration_question = CASES[language]
    result, changed = remove_unrequested_directory_fields(ANSWER, duration_question, language=language)
    assert "$100 worth of products when joining" in result
    assert "08:00 am" not in result
    assert changed is True


@pytest.mark.parametrize("language", sorted(CASES))
def test_negation_numbers_and_names_survive_untouched(language: str) -> None:
    """A negated field request, currency figures, units and the country/role
    names in the multipart question must not be altered by this pass - only
    the answer's unrequested-field lines are ever touched, never the
    question, and the kept answer's numbers/currency must be byte-identical."""
    multipart_question, _, _ = CASES[language]
    result, _ = remove_unrequested_directory_fields(ANSWER, multipart_question, language=language)
    assert "$100" in result
    assert "$50" in result
    assert "FBO" in result
    assert multipart_question == CASES[language][0]  # the question itself is never mutated


def test_negation_not_the_email_only_the_phone_is_protected_english() -> None:
    """This module's field-request detection is deliberately not a negation
    parser: "not the email, only the phone" still names both "email" and
    "phone" as words, so both are treated as requested and neither line is
    touched - the conservative direction (never guess a field away), and the
    same behaviour as before this project (no ``language`` kwarg passed).
    What this pins is that the negated wording is not corrupted or split by
    this pass, not that the answer is edited around the negation."""
    answer = "Telephone Office: +254 700 000000.\nEmail: kenya@forever.example."
    kept, changed = remove_unrequested_directory_fields(
        answer, "Not the email, only the phone number please."
    )
    assert kept == answer
    assert changed is False


@pytest.mark.parametrize("language", ["xx", "zz", "klingon"])
def test_unknown_language_strips_nothing(language: str) -> None:
    """An unrecognised language code must fail conservatively: nothing is
    stripped or restored on a guess, per the module's contract."""
    multipart_question = CASES["fr"][0]
    result, changed = remove_unrequested_directory_fields(ANSWER, multipart_question, language=language)
    assert result == ANSWER
    assert changed is False


def test_norwegian_bokmal_tag_folds_to_the_no_vocabulary() -> None:
    """"nb" (Norwegian Bokmål, the tag markets.json-style configs may use)
    must resolve to the same vocabulary as "no"."""
    multipart_question, _, _ = CASES["no"]
    result_no, changed_no = remove_unrequested_directory_fields(ANSWER, multipart_question, language="no")
    result_nb, changed_nb = remove_unrequested_directory_fields(ANSWER, multipart_question, language="nb")
    assert result_no == result_nb
    assert changed_no == changed_nb


@pytest.mark.parametrize("language", sorted(CASES))
def test_phone_and_email_both_survive(language: str) -> None:
    """Combination: phone + email. A bare "and" between the two directory
    fields, one currency-free contact answer, no order-size branch involved
    at all - exercises the generic (non-order-size) removal path instead."""
    contact_answer = "Telephone Office: +254 700 000000.\nEmail: kenya@forever.example.\nWebsite: www.foreverliving.example."
    questions = {
        "fr": "Quel est le téléphone du bureau et l'adresse e-mail ?",
        "de": "Wie ist die Telefonnummer des Büros und die E-Mail-Adresse?",
        "nl": "Wat is de telefoon van het kantoor en het e-mailadres?",
        "es": "¿Cuál es el teléfono de la oficina y el correo electrónico?",
        "it": "Qual è il telefono dell'ufficio e l'e-mail?",
        "pt": "Qual é o telefone do escritório e o e-mail?",
        "fi": "Mikä on toimiston puhelin ja sähköposti?",
        "no": "Hva er telefonen til kontoret og e-posten?",
        "sv": "Vad är kontorets telefon och e-post?",
    }
    result, changed = remove_unrequested_directory_fields(contact_answer, questions[language], language=language)
    assert "+254 700 000000" in result
    assert "kenya@forever.example" in result
    assert "www.foreverliving.example" not in result
    assert changed is True


@pytest.mark.parametrize("language", sorted(CASES))
def test_address_and_business_hours_both_survive(language: str) -> None:
    """Combination: office address + business hours, with an unrequested
    phone number shed alongside."""
    contact_answer = (
        "Telephone Office: +254 700 000000.\n"
        "Address: PO Box 100, Nairobi, Kenya.\n"
        "Business Hours: 08:00 am - 17:00 pm."
    )
    questions = {
        "fr": "Quelle est l'adresse du bureau et les heures d'ouverture ?",
        "de": "Wie ist die Adresse des Büros und die Öffnungszeiten?",
        "nl": "Wat is het adres van het kantoor en de openingstijden?",
        "es": "¿Cuál es la dirección de la oficina y el horario de oficina?",
        "it": "Qual è l'indirizzo dell'ufficio e l'orario d'ufficio?",
        "pt": "Qual é o endereço do escritório e o horário de funcionamento?",
        "fi": "Mikä on toimiston osoite ja aukioloaika?",
        "no": "Hva er kontorets adresse og åpningstider?",
        "sv": "Vad är kontorets adress och öppettider?",
    }
    result, changed = remove_unrequested_directory_fields(contact_answer, questions[language], language=language)
    assert "PO Box 100, Nairobi, Kenya" in result
    assert "08:00 am" in result
    assert "+254 700 000000" not in result
    assert changed is True


@pytest.mark.parametrize("language", sorted(CASES))
def test_delivery_cost_survives_an_order_size_only_strip(language: str) -> None:
    """Combination: delivery fee kept alongside minimum order when both are
    asked for. The "free-delivery threshold" half of the original combination
    has no canonical field in this module (see
    config/directory_field_vocabulary.py's docstring, "out of this module's
    scope") - this exercises the delivery_cost half only."""
    answer = (
        "Minimum order size FBO: $100 worth of products when joining.\n"
        "Delivery Cost: $5 flat fee."
    )
    questions = {
        "fr": "Quelle est la commande minimum et les frais de livraison ?",
        "de": "Was ist die Mindestbestellung und die Lieferkosten?",
        "nl": "Wat is de minimale bestelling en de verzendkosten?",
        "es": "¿Cuál es el pedido mínimo y el coste de envío?",
        "it": "Qual è l'ordine minimo e i costi di spedizione?",
        "pt": "Qual é a encomenda mínima e o custo de envio?",
        "fi": "Mikä on vähimmäistilaus ja toimitusmaksu?",
        "no": "Hva er minstebestillingen og leveringskostnaden?",
        "sv": "Vad är minsta beställning och fraktkostnaden?",
    }
    result, changed = remove_unrequested_directory_fields(answer, questions[language], language=language)
    assert "$100 worth of products when joining" in result
    assert "$5 flat fee" in result
    assert changed is False
