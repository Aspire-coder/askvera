"""Phase 2 Lane F: pure-function tests for app/response/contact_completion.py.

Deterministic/local: no orchestrator, retrieval, model or network
dependency. These exercise the new module directly, so they need no
orchestrator patch and pass today.
"""

from __future__ import annotations

import pytest

from app.response.contact_completion import (
    build_contact_supplement_with_fax_fallback,
    recommends_contact_in_language,
)

# --------------------------------------------------------------------------
# recommends_contact_in_language: positive controls, one per covered
# language (fr, de, es, nl plus five more: it, pt, fi, sv, no).
# --------------------------------------------------------------------------

_POSITIVE_CASES = {
    "fr": "Vous pouvez commander directement. Veuillez contacter le service client pour plus d'aide.",
    "de": "Sie können direkt bestellen. Bitte wenden Sie sich an den Kundenservice für weitere Hilfe.",
    "es": "Puede realizar el pedido directamente. Por favor, póngase en contacto con atención al cliente.",
    "nl": "U kunt direct bestellen. Neem contact op met de klantenservice voor meer hulp.",
    "it": "Può ordinare direttamente. La preghiamo di contattare il servizio clienti per ulteriore assistenza.",
    "pt": "Você pode fazer o pedido diretamente. Entre em contato com o atendimento ao cliente para mais ajuda.",
    "fi": "Voit tilata suoraan. Ota yhteyttä asiakaspalveluun saadaksesi lisää apua.",
    "sv": "Du kan beställa direkt. Kontakta kundtjänsten för mer hjälp.",
    "no": "Du kan bestille direkte. Kontakt kundeservice for mer hjelp.",
}

# --------------------------------------------------------------------------
# Negative controls: the SAME topic, in the SAME language, with no
# recommendation to contact anyone - proves the patterns are not loose
# keyword matches that would fire on any sentence mentioning the topic.
# --------------------------------------------------------------------------

_NEGATIVE_CASES = {
    "fr": "Le montant minimum de commande est de 200 dollars par trimestre.",
    "de": "Die Mindestbestellmenge beträgt 200 US-Dollar pro Quartal.",
    "es": "El pedido mínimo es de 200 dólares por trimestre.",
    "nl": "De minimale bestelling is 200 dollar per kwartaal.",
    "it": "L'ordine minimo è di 200 dollari al trimestre.",
    "pt": "O pedido mínimo é de 200 dólares por trimestre.",
    "fi": "Vähimmäistilaus on 200 dollaria neljänneksessä.",
    "sv": "Minsta beställning är 200 dollar per kvartal.",
    "no": "Minste bestilling er 200 dollar per kvartal.",
}


@pytest.mark.parametrize("language", sorted(_POSITIVE_CASES))
def test_positive_control_detects_the_recommendation(language: str) -> None:
    assert recommends_contact_in_language(_POSITIVE_CASES[language], language) is True


@pytest.mark.parametrize("language", sorted(_NEGATIVE_CASES))
def test_negative_control_does_not_fire_on_a_plain_answer(language: str) -> None:
    assert recommends_contact_in_language(_NEGATIVE_CASES[language], language) is False


def test_unknown_language_returns_false_rather_than_guessing() -> None:
    """A language with no reviewed pattern must append nothing, even when
    the text would match a listed language's pattern by coincidence."""
    assert recommends_contact_in_language("Contactez le service client.", "xx") is False
    assert recommends_contact_in_language("Contactez le service client.", "") is False


def test_english_is_deliberately_not_handled_here() -> None:
    """English detection stays owned by the orchestrator's own
    ``_CARE_CONTACT_RECOMMENDATION_RE`` - this module must not duplicate it,
    so an English "en" lookup returns False even for a clear English
    recommendation."""
    assert recommends_contact_in_language("Please contact customer care.", "en") is False


def test_case_insensitive_and_language_code_is_case_insensitive_too() -> None:
    assert recommends_contact_in_language(_POSITIVE_CASES["fr"].upper(), "FR") is True


# --------------------------------------------------------------------------
# build_contact_supplement_with_fax_fallback
# --------------------------------------------------------------------------


def test_fax_only_record_is_surfaced_as_a_last_resort() -> None:
    fields = {"Fax": "+254 20 999999"}
    result = build_contact_supplement_with_fax_fallback(
        "Please contact customer care for help.", fields, True
    )
    assert result == ("Fax: +254 20 999999", ["Fax"])


def test_a_phone_still_wins_over_a_fax_in_the_same_record() -> None:
    """The fallback must never crowd out whatever the wrapped function
    already picks - it only fires when that function returns None."""
    fields = {"Fax": "+254 20 999999", "Telephone Office": "+254 20 1234567"}
    result = build_contact_supplement_with_fax_fallback(
        "Please contact customer care for help.", fields, True
    )
    assert result is not None
    block, labels = result
    assert "+254 20 1234567" in block
    assert "+254 20 999999" not in block
    assert labels == ["Telephone Office"]


def test_no_fields_at_all_still_returns_none_never_fabricates() -> None:
    assert build_contact_supplement_with_fax_fallback("Please contact customer care.", {}, True) is None


def test_answer_without_a_care_recommendation_gets_no_fax_fallback_either() -> None:
    fields = {"Fax": "+254 20 999999"}
    assert build_contact_supplement_with_fax_fallback("The minimum order is $200.", fields, False) is None


def test_a_fax_only_value_that_is_blank_after_stripping_still_returns_none() -> None:
    fields = {"Fax": "   "}
    assert build_contact_supplement_with_fax_fallback("Please contact customer care.", fields, True) is None
