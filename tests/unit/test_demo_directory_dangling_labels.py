"""W20: bounded rendering fixes for dangling directory-answer artifacts.

Live evidence: candidate 0eb5493, journey j11 (Italy session, English),
case "demo-j11-italy-phone-hours-burkina-faso-contact", Burkina Faso record
GLOBAL sponsoring-004-burkina-faso.

1. A dangling connector word ("during") left behind when the unrequested
   field it introduced is stripped.
2. A directory label surviving with no value at all, because the actual
   record used the British "Centre" spelling that the compound "Office &
   Product Center Address" label only recognised in its American spelling,
   so the removal regex matched only the trailing "Address:" word and left
   "Office & Product Centre" dangling in front of it.
3. Localized labels for build_support_contact_supplement's language keyword.

Follow-up (same worktree/task): restore_missing_directory_contacts also
appends English labels into non-English answers. Live evidence: candidate
0eb5493, cases "demo-fixes-check-04-fr-kenya-uganda-followup" (French),
"demo-fixes-check-05-de-kenya-uganda-followup" (German),
"demo-fixes-check-06-es-mexico-guatemala-followup" (Spanish), all turn1,
from SP/demo/int6/replay_inputs.json. GLOBAL Kenya/East Africa record.
"""

from __future__ import annotations

import pytest

from utils.directory_fields import (
    _SUPPORT_CONTACT_LABEL_TRANSLATIONS,
    build_support_contact_supplement,
    parse_directory_fields,
    remove_unrequested_directory_fields,
    restore_missing_directory_contacts,
)


_KENYA_RECORD = (
    "Forever Kenya/East Africa\n"
    "Office & Product Center Address\n"
    "Kenya Reinsurance Plaza, 4th floor Taifa Rd. CBD, opp. High Court "
    "Central Business District P .O. Box 44919 - 00100\n"
    "Telephone Office\n"
    "+254 20 2026869 / +254 20 2026873\n"
    "Telephone for Orders\n"
    "+254 71 0600206\n"
    "Email\n"
    "info@foreverea.com\n"
    "Website\n"
    "www.foreverliving.com\n"
)
_KENYA_FIELDS = parse_directory_fields(_KENYA_RECORD)


# --- Item 1: dangling connector left behind by an unrequested-field removal


def test_dangling_connector_removed_with_its_unrequested_field():
    """Live-shaped turn3: "during" must not survive once its hours clause is gone."""
    question = "What is the Forever Living office address for Burkina Faso?"
    before = (
        "Based on the approved directory record for Forever Living Products Burkina Faso, "
        "the office and product centre address is:\n\n"
        "**Dapoya, Secteur 3, Dimdolodomb – 01 BP 5070 Ouaga 01, Burkina Faso**\n\n"
        "You can reach the office by telephone at **+226 25 30 62 03** during \n"
        "Business Hours Office: 08:00 am - 17:00 pm.\n"
        "Please note: This is directory information for reference only and does not "
        "grant access to Burkina Faso's local policies, as the selected policy country "
        "is Italy."
    )
    cleaned, changed = remove_unrequested_directory_fields(before, question)

    assert changed is True
    assert "during" not in cleaned
    assert "Business Hours" not in cleaned
    assert (
        "You can reach the office by telephone at **+226 25 30 62 03**\nPlease note:"
        in cleaned
    )
    # The requested address itself must still be there, untouched.
    assert "Dapoya, Secteur 3, Dimdolodomb" in cleaned


def test_requested_hours_kept_when_hours_were_asked():
    """A requested field must never be swept up by the connector/label cleanup."""
    question = "What are their business hours?"
    before = "Telephone Office: +226 25 30 62 03\nBusiness Hours Office: 08:00 am - 17:00 pm."
    cleaned, changed = remove_unrequested_directory_fields(before, question)

    assert changed is True
    assert "Business Hours Office: 08:00 am - 17:00 pm." in cleaned
    assert "Telephone Office" not in cleaned


def test_legitimate_during_sentence_untouched():
    """"...during office hours: 09.00-17.00" has an object; nothing should move."""
    question = "What are the business hours?"
    before = "You can reach the office during business hours: 09.00-17.00."
    cleaned, changed = remove_unrequested_directory_fields(before, question)

    assert changed is False
    assert cleaned == before


# --- Item 2: a label must never survive without its value


def test_bare_label_not_left_dangling_when_its_value_is_removed():
    """Live-shaped final turn: British "Centre" spelling must not strand the label.

    The record spells the compound field "Office & Product Centre Address"
    (British). Address is not one of the two requested fields ("phone and
    email"), so the whole labelled line must be removed as one unit - not
    just its trailing "Address:" word, leaving "Office & Product Centre"
    behind with no value.
    """
    question = "What's their phone and email?"
    before = (
        "I'm happy to help! To give you the right contact details, could you clarify: "
        "are you asking about **Forever Living Italy** (your selected market) or "
        "**Burkina Faso** (mentioned in our earlier conversation)?\n\n"
        "Telephone Office: +226 25 30 62 03\nEmail: mfatoued2005@yahoo.fr\n\n"
        "Office & Product Centre Address: Dapoya, Secteur 3, Dimdolodomb – 01 BP "
        "5070 Ouaga 01, Burkina Faso\n"
        "Fax: +226 25 30 62 04"
    )
    cleaned, changed = remove_unrequested_directory_fields(before, question)

    assert changed is True
    assert "Office & Product Centre" not in cleaned
    assert "Address" not in cleaned
    assert "Fax" not in cleaned
    # Both requested fields keep their exact values.
    assert "Telephone Office: +226 25 30 62 03" in cleaned
    assert "Email: mfatoued2005@yahoo.fr" in cleaned
    assert not cleaned.rstrip().endswith((":", "&"))


def test_preexisting_bare_heading_at_the_end_is_also_dropped():
    """Defense in depth: a bare label heading with nothing after it anywhere,
    not just one this pass's own removal exposed, must not be the final line.
    """
    question = "What's their phone and email?"
    before = (
        "Telephone Office: +226 25 30 62 03\nEmail: mfatoued2005@yahoo.fr\n\n"
        "Office & Product Centre\n\n"
        "Office & Product Centre Address: Dapoya, Secteur 3, Dimdolodomb – 01 BP "
        "5070 Ouaga 01, Burkina Faso\n"
        "Fax: +226 25 30 62 04"
    )
    cleaned, changed = remove_unrequested_directory_fields(before, question)

    assert changed is True
    assert "Office & Product Centre" not in cleaned
    assert cleaned == "Telephone Office: +226 25 30 62 03\nEmail: mfatoued2005@yahoo.fr"


def test_label_kept_when_its_value_remains():
    """A normal, requested "Label: value" line must be left exactly alone."""
    question = "What is their email?"
    before = "Email: someone@example.com"
    cleaned, changed = remove_unrequested_directory_fields(before, question)

    assert changed is False
    assert cleaned == before


# --- Item 3: localized support-contact labels


_APPROVED_FIELDS = {
    "Telephone Office": "+226 25 30 62 03",
    "Email": "mfatoued2005@yahoo.fr",
}


def test_language_en_output_identical_to_no_argument():
    default = build_support_contact_supplement("Some answer.", _APPROVED_FIELDS, True)
    explicit_en = build_support_contact_supplement(
        "Some answer.", _APPROVED_FIELDS, True, language="en"
    )
    assert default == explicit_en


def test_unknown_language_falls_back_to_english():
    english = build_support_contact_supplement(
        "Some answer.", _APPROVED_FIELDS, True, language="en"
    )
    unknown = build_support_contact_supplement(
        "Some answer.", _APPROVED_FIELDS, True, language="xx"
    )
    assert english == unknown


@pytest.mark.parametrize("language", ["fr", "de", "es", "it", "pt", "sv", "nl"])
def test_localized_labels_translate_only_the_label(language: str):
    english_block, english_labels = build_support_contact_supplement(
        "Some answer.", _APPROVED_FIELDS, True, language="en"
    )
    localized_block, localized_labels = build_support_contact_supplement(
        "Some answer.", _APPROVED_FIELDS, True, language=language
    )

    # Labels differ (translated) ...
    assert localized_labels != english_labels
    # ... but every value is byte-identical across languages, and never
    # translated, added to, or altered.
    english_values = [line.split(": ", 1)[1] for line in english_block.split("\n")]
    localized_values = [line.split(": ", 1)[1] for line in localized_block.split("\n")]
    assert localized_values == english_values
    for value in _APPROVED_FIELDS.values():
        assert value in localized_block


@pytest.mark.parametrize("language", ["fr", "de", "es", "it", "pt", "sv", "nl"])
def test_localized_website_label_translated(language: str):
    fields = {"Website": "https://www.foreverliving.com"}
    _, localized_labels = build_support_contact_supplement(
        "Some answer.", fields, True, language=language
    )
    expected = _SUPPORT_CONTACT_LABEL_TRANSLATIONS[language]["website"]
    assert localized_labels == [expected]


def test_values_identical_across_every_language():
    values = set(_APPROVED_FIELDS.values())
    for language in ["en", "nl", "fr", "de", "es", "it", "pt", "sv", "xx"]:
        block, _ = build_support_contact_supplement(
            "Some answer.", _APPROVED_FIELDS, True, language=language
        )
        for value in values:
            assert value in block


# --- Follow-up: restore_missing_directory_contacts's own localized labels


def test_restore_directory_contacts_french_live_shaped():
    """Live-shaped demo-fixes-check-04-fr-kenya-uganda-followup turn1.

    The model already wrote the order phone under its own French label
    ("Téléphone commandes") and the email; only address, office phone and
    website are actually missing and must be appended with French labels.
    """
    question = "Quel est le coût de livraison au Kenya ?"
    answer = (
        "Selon le répertoire international des sponsors Forever Living, "
        "**le coût de livraison au Kenya est de 3 $ dans le pays**.\n\n"
        "Ce tarif s'applique aux commandes passées auprès du centre de "
        "produits Kenya/East Africa.\n\n"
        "Pour plus de détails sur les commandes au Kenya, vous pouvez "
        "contacter :\n"
        "- **Téléphone commandes** : +254 71 0600206\n"
        "- **Email** : info@foreverea.com\n\n"
        "Veuillez noter que ces informations proviennent du répertoire des "
        "sponsors."
    )

    corrected, restored = restore_missing_directory_contacts(
        answer, [_KENYA_FIELDS], question, language="fr"
    )

    assert restored == [
        "Adresse du bureau et du centre de produits",
        "Téléphone bureau",
        "Site web",
    ]
    assert "Adresse du bureau et du centre de produits: Kenya Reinsurance" in corrected
    assert "Téléphone bureau: +254 20 2026869 / +254 20 2026873" in corrected
    assert "Site web: www.foreverliving.com" in corrected
    # Never re-labeled or duplicated: the model's own line survives as-is,
    # and no English or French "Telephone for Orders" line was appended.
    assert corrected.count("+254 71 0600206") == 1
    assert "**Téléphone commandes** : +254 71 0600206" in corrected
    assert "Telephone for Orders" not in corrected
    assert "Téléphone pour commandes" not in corrected


def test_restore_directory_contacts_german_live_shaped():
    """Live-shaped demo-fixes-check-05-de-kenya-uganda-followup turn1."""
    question = "Was kostet der Versand nach Kenia?"
    answer = (
        "# Lieferkosten in Kenia\n\n"
        "Nach dem Verzeichniseintrag für Forever Kenya/East Africa betragen "
        "die Lieferkosten **$3 innerhalb des Landes**.\n\n"
        "**Forever Kenya/East Africa**\n"
        "Tel: +254 20 2026869 / +254 20 2026873\n"
        "E-Mail: info@foreverea.com\n"
    )

    corrected, restored = restore_missing_directory_contacts(
        answer, [_KENYA_FIELDS], question, language="de"
    )

    assert "Telefon für Bestellungen: +254 71 0600206" in corrected
    assert "Adresse des Büro- und Produktcenters: Kenya Reinsurance" in corrected
    assert "Website: www.foreverliving.com" in corrected
    assert "Telephone for Orders" not in corrected
    assert "Office & Product Center Address:" not in corrected


def test_restore_directory_contacts_spanish_live_shaped():
    """Live-shaped demo-fixes-check-06-es-mexico-guatemala-followup turn1 shape.

    (Uses the Kenya record for a self-contained fixture; the same "already
    quoted under a localized label" behaviour applies.)
    """
    question = "¿Cuál es el costo de envío?"
    answer = (
        "Para obtener un costo específico de envío, te recomiendo "
        "contactar directamente con el Centro de Atención:\n\n"
        "- **Teléfono para pedidos:** +254 71 0600206\n"
        "- **Email:** info@foreverea.com\n"
    )

    corrected, restored = restore_missing_directory_contacts(
        answer, [_KENYA_FIELDS], question, language="es"
    )

    assert "Dirección de la oficina y centro de productos: Kenya Reinsurance" in corrected
    assert "Teléfono de oficina: +254 20 2026869" in corrected
    assert "Sitio web: www.foreverliving.com" in corrected
    # The model's own line survives untouched, with no duplicate appended.
    assert corrected.count("+254 71 0600206") == 1
    assert corrected.count("Teléfono para pedidos") == 1
    assert "**Teléfono para pedidos:** +254 71 0600206" in corrected
    assert "Telephone for Orders" not in corrected


def test_restore_directory_contacts_language_en_identical_to_no_argument():
    question = "What is the delivery cost for Kenya?"
    answer = "Please contact the Kenya office for details."
    default = restore_missing_directory_contacts(answer, [_KENYA_FIELDS], question)
    explicit_en = restore_missing_directory_contacts(
        answer, [_KENYA_FIELDS], question, language="en"
    )
    assert default == explicit_en


def test_restore_directory_contacts_unknown_language_falls_back_to_english():
    question = "What is the delivery cost for Kenya?"
    answer = "Please contact the Kenya office for details."
    english = restore_missing_directory_contacts(
        answer, [_KENYA_FIELDS], question, language="en"
    )
    unknown = restore_missing_directory_contacts(
        answer, [_KENYA_FIELDS], question, language="xx"
    )
    assert english == unknown


def test_restore_directory_contacts_no_duplicate_for_localized_value_already_quoted():
    """"Téléphone commandes : +254 71 0600206" must never get a second,
    English or French, "Telephone for Orders" line - regardless of which
    other fields end up restored."""
    question = "Quel est le numéro de commande pour le Kenya ?"
    answer = "Contactez-nous : Téléphone commandes : +254 71 0600206"

    for language in ["en", "fr", "de", "es"]:
        corrected, restored = restore_missing_directory_contacts(
            answer, [_KENYA_FIELDS], question, language=language
        )
        assert corrected.count("+254 71 0600206") == 1
        assert "Telephone for Orders" not in corrected
        assert "Téléphone pour commandes" not in corrected
        assert "Telephone for Orders" not in restored
        assert "Téléphone pour commandes" not in restored


@pytest.mark.parametrize("language", ["fr", "de", "es", "it", "pt", "sv", "nl"])
def test_restore_directory_contacts_values_identical_across_languages(language: str):
    question = "What is their contact information?"
    # Already states the email correctly, which is what lets restoration
    # trigger at all (see has_correct_value/has_labeled_contact_line);
    # every other contact value must then be appended, in full, regardless
    # of which language its label is rendered in.
    answer = "Email: info@foreverea.com"
    english_corrected, _ = restore_missing_directory_contacts(
        answer, [_KENYA_FIELDS], question, language="en"
    )
    localized_corrected, _ = restore_missing_directory_contacts(
        answer, [_KENYA_FIELDS], question, language=language
    )
    for value in _KENYA_FIELDS.values():
        assert value in english_corrected
        assert value in localized_corrected
