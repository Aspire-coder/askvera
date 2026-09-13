"""Numeric repair removed figures the retrieved record states (live, candidate 0eb5493).

Thirteen replayed demo turns lost figures that ``numbers_present_in_sources``
reported present in the evidence. Answers below are the live
``answer_before_validation`` text (or an excerpt of it). Record text is quoted
verbatim from the local extractions:

- International Sponsoring Directory records: release-knowledge-live-data/outputs/
  interaction_quality/r4-local-audit/r4-global-specialized/
  International-Sponsoring-Directory.directory.jsonl
- Sweden 21.02: askvera-deploy/outputs/chunk-comparison-full/current/SE/en/
  sweden company policy english.sections.jsonl
- US Spanish 21.03: askvera-deploy/outputs/chunk-comparison-full/current/US/es/
  US-ES-Company_Policy.sections.jsonl

Records marked SYNTHETIC are minimal inventions used only to build a
different-market case. They are not source text.
"""

import pytest

from app.retrieval.models import RetrievedDocument
from app.validation.validators.numeric_grounding_validator import (
    _extract_claims,
    remove_unsupported_numeric_sentences,
    unsupported_numeric_claims,
)

KENYA = (
    "Welcome to Forever Kenya/East Africa!\n"
    "+254 20 2026869\n"
    "+254 20 2026873\n"
    "ORDERING PRODUCTS\n"
    "• Minimum order size FBO: $100 worth of products when joining, $50 of products after joining.\n"
    "• Delivery Cost: $3 within the country.\n"
    "• Average lead time for orders to arrive: 12 to 24 hours.\n"
    "• Payment methods accepted: Bank deposit, Credit Card, Mobile Money Transfer (Mpesa).\n"
    "Telephone Office +254 20 2026869 / +254 20 2026873\n"
    "Telephone for Orders +254 71 0600206\n"
    "Email info@foreverea.com\n"
)
UGANDA = (
    "Welcome to Forever Uganda!\n"
    "+256 3921 77993/4\n"
    "ORDERING PRODUCTS\n"
    "• Minimum order size FBO: $100 worth of products when joining, $50 of products after joining.\n"
    "• Delivery Cost: $3 within the country.\n"
    "• Average lead time for orders to arrive: 12 to 24 hours.\n"
    "• Payment methods accepted: Bank deposit, Credit Card, Mobile Money Transfer (Mpesa).\n"
    "Forever Living Products Kenya (Uganda)\n"
    "Office & Product Center Address\n"
    "Suite B1 First Floor Park Royal Shopping Mall\n"
    "Plot 26, Buganda Road\n"
    "P .O. Box 34721 Kampala – Uganda\n"
    "Business Hours Office 09.00 am – 17.00 pm (Mon – Fri)\n"
    "10.00 am – 14.00 pm (Sat)\n"
    "Telephone Office +256 3921 77993/4\n"
    "Telephone for Orders +256 7720 43567\n"
    "Email info@foreverea.com, alubega@forerverea.com\n"
    "Website www.foreverliving.com\n"
)
# SYNTHETIC: a Uganda record whose delivery cost differs from Kenya's. The real
# Uganda record states the same "$3 within the country" as Kenya.
SYNTHETIC_UGANDA = (
    "Welcome to Forever Uganda!\n"
    "ORDERING PRODUCTS\n"
    "• Delivery Cost: $4 within the country.\n"
    "• Average lead time for orders to arrive: 48 to 72 hours.\n"
)
MEXICO = (
    "Welcome to Forever Mexico!\n"
    "800 8010 600\n"
    "ORDERING PRODUCTS\n"
    "• Minimum order size FBO: $50 USD or $1,300.00 MXN.\n"
    "• Delivery Cost: Depends on the weight of the package and distance.\n"
    "• Average lead time for orders to arrive: 2-3 business days.\n"
    "• Payment methods accepted: Visa Credit/Debit and a minimum of $600 pesos each.\n"
    "Telephone Office +55 55 3300 9400\n"
    "Telephone for Orders (800 8010 600)\n"
    "Email centrodeatencion@foreverliving.com.mx\n"
)
NETHERLANDS = (
    "Welcome to Forever Netherlands Benelux!\n"
    "ORDERING PRODUCTS\n"
    "• Minimum order size FBO: €50,00 in products excl. VAT and excl. literature.\n"
    "• Delivery Cost: €5,00 excl. VAT per order. Orders above 2CC are free of charge.\n"
    "• Average lead time for orders to arrive: Within 2 working days\n"
)
SWEDEN_21_02 = (
    "21.02 End customers/Preferred Customers (FPCs):\n"
    "(a) End customers/FPCs are guaranteed a 100% Customer Satisfaction Guarantee. Within\n"
    "ninety (90) days of the date of purchase, an end customer/FPC may:\n"
    "1) receive a new replacement product for a defective product, or\n"
    "2) cancel the purchase, return the product and receive a full refund of the purchase price,\n"
    "excluding delivery costs.\n"
)
US_ES_21_03 = (
    "21.03 (a) A los Clientes Minoristas/Preferidos se les garantiza 100% de satisfacción con\n"
    "el producto. Durante los treinta (30) días a partir de la fecha de compra, un\n"
    "Cliente Minorista/Preferido puede:\n"
    "1) Obtener un nuevo reemplazo por cualquier producto defectuoso; o\n"
    "2) Cancelar la compra, devolver el producto y obtener un reembolso total\n"
    "del precio de compra, excluyendo el costo de envío.\n"
)


def _record(slug: str, name: str, content: str) -> RetrievedDocument:
    return RetrievedDocument(
        id=f"GLOBAL|en|International-Sponsoring-Directory.pdf|{slug}",
        title=f"International-Sponsoring-Directory.pdf - Forever {name}",
        content=content,
        source="International-Sponsoring-Directory.pdf",
        country="GLOBAL",
        language="en",
        score=0.9,
        metadata={"directory_kind": "international_sponsoring", "directory_section": "sponsoring",
                  "record_country": name, "section_id": slug},
    )


def _policy(country: str, language: str, filename: str, section: str, content: str) -> RetrievedDocument:
    return RetrievedDocument(
        id=f"{country}|{language}|{filename}|{section}",
        title=f"{filename} - Sec {section}",
        content=content,
        source=filename,
        country=country,
        language=language,
        score=0.9,
        metadata={"section_id": section},
    )


def kenya() -> RetrievedDocument:
    return _record("sponsoring-012-kenya-east-africa", "Kenya/East Africa", KENYA)


def uganda() -> RetrievedDocument:
    return _record("sponsoring-025-uganda", "Uganda", UGANDA)


def mexico() -> RetrievedDocument:
    return _record("sponsoring-109-mexico", "Mexico", MEXICO)


def netherlands() -> RetrievedDocument:
    return _record("sponsoring-080-netherlands-benelux", "Netherlands Benelux", NETHERLANDS)


def _unsupported(answer: str, documents: list[RetrievedDocument]) -> list[str]:
    return [claim.text for claim in unsupported_numeric_claims(answer, documents)]


# ---------------------------------------------------------------------------
# (a) Localized field names bind a figure to the record field that states it.
# ---------------------------------------------------------------------------

def test_dutch_kenya_delivery_cost_is_kept():
    answer = ("Volgens de directorygegevens voor Forever Kenya/East Africa bedragen de bezorgkosten "
              "**$3 binnen het land**.")
    assert _unsupported(answer, [kenya()]) == []


def test_french_kenya_delivery_cost_and_lead_time_are_kept():
    answer = (
        "Selon le répertoire international des sponsors Forever Living, **le coût de livraison au Kenya est "
        "de 3 $ dans le pays**.\n\nCe tarif s'applique aux commandes passées auprès du centre de produits "
        "Kenya/East Africa. Le délai de livraison moyen est de 12 à 24 heures."
    )
    assert _unsupported(answer, [kenya()]) == []


def test_french_uganda_answer_keeps_every_field_and_no_heading_is_left_empty():
    answer = (
        "Pour l'Ouganda, voici les informations du répertoire Forever Living :\n\n"
        "**Contact :**\n"
        "- Téléphone bureau : +256 3921 77993/4\n"
        "- Téléphone commandes : +256 7720 43567\n\n"
        "**Frais de livraison :**\n"
        "$3 dans le pays, avec un délai moyen de 12 à 24 heures.\n\n"
        "**Commande minimum :**\n"
        "$100 de produits lors de l'adhésion, puis $50 après l'adhésion."
    )

    repaired, removed = remove_unsupported_numeric_sentences(answer, [uganda()])

    assert removed == []
    assert repaired == answer


@pytest.mark.parametrize("answer, record", [
    ("Nach dem Verzeichniseintrag für Forever Kenya/East Africa betragen die Lieferkosten **$3 innerhalb des "
     "Landes**.\n\nDie durchschnittliche Lieferzeit für Bestellungen beträgt 12 bis 24 Stunden.", kenya),
    ("Gemäß dem Verzeichniseintrag für Forever Uganda betragen die **Lieferkosten innerhalb des Landes $3**. "
     "Die durchschnittliche Lieferzeit für Bestellungen liegt bei **12 bis 24 Stunden**.", uganda),
])
def test_german_delivery_cost_and_lead_time_are_kept(answer, record):
    assert _unsupported(answer, [record()]) == []


def test_spanish_lead_time_written_with_words_is_kept():
    answer = ("Según el directorio de Forever Mexico, el costo de envío **depende del peso del paquete y la "
              "distancia**.\n\nEl tiempo promedio de entrega es de 2 a 3 días hábiles una vez que se procesa tu orden.")
    assert _unsupported(answer, [mexico()]) == []


@pytest.mark.parametrize("answer", [
    ("Según el directorio de Forever Mexico, los requisitos para hacer un pedido como Distribuidor Independiente "
     "(FBO) son:\n\n**Tamaño mínimo de pedido:** $50 USD o $1,300.00 MXN.\n\n"
     "**Tiempos de entrega:** El tiempo promedio de llegada de los pedidos es de 2–3 días hábiles."),
    ("Basándome en el directorio de Forever México, estos son los requisitos para hacer un pedido:\n\n"
     "**Monto mínimo de pedido:** $50 USD o $1,300.00 MXN.\n\n"
     "**Tiempo de entrega:** El promedio es de 2-3 días hábiles."),
    ("**Ordering Requirements for Mexico:**\n\n"
     "For FBOs in Mexico, the FBO minimum order size is $50 USD or $1,300.00 MXN."),
])
def test_mexico_minimum_order_and_lead_time_are_kept_in_spanish_and_english(answer):
    assert _unsupported(answer, [mexico()]) == []


# ---------------------------------------------------------------------------
# (b) A comma-grouped amount with point cents is one claim.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("$50 USD or $1,300.00 MXN.", ["50", "1,300.00"]),
    ("1.300,00 MXN", ["1.300,00"]),
    ("3,000 CC", ["3,000"]),
])
def test_mixed_separator_amount_is_a_single_claim(text, expected):
    assert [claim.text for claim in _extract_claims(text)] == expected


# ---------------------------------------------------------------------------
# (c) A phone line suffix the source writes on the same number.
# ---------------------------------------------------------------------------

def test_phone_line_suffix_stated_by_the_record_is_kept():
    answer = "**Forever Living Products Uganda**\nTelefon: +256 3921 77993/4\nTelefon für Bestellungen: +256 7720 43567"
    assert _unsupported(answer, [uganda()]) == []


# ---------------------------------------------------------------------------
# (e) The company name is not a subject; the words after the figure bind it.
# ---------------------------------------------------------------------------

def test_sweden_customer_satisfaction_guarantee_percent_is_kept():
    answer = ("Forever Living offers a **100% Customer Satisfaction Guarantee** for end customers and "
              "Preferred Customers (FPCs).")
    document = _policy("SE", "en", "SE-EN-Company-Policy.pdf", "21.02", SWEDEN_21_02)
    assert _unsupported(answer, [document]) == []


def test_spanish_satisfaction_guarantee_percent_is_kept():
    answer = ("Según la política de Forever Living Products, **se les garantiza 100% de satisfacción con el "
              "producto**. Durante los treinta (30) días a partir de la fecha de compra, un Cliente "
              "Minorista/Preferido puede:")
    document = _policy("US", "es", "US-ES-Company-Policy.pdf", "21.03", US_ES_21_03)
    assert _unsupported(answer, [document]) == []


# ---------------------------------------------------------------------------
# (f) "1)" list markers survive repair.
# ---------------------------------------------------------------------------

def test_list_markers_keep_their_parenthesis_after_repair():
    answer = (
        "Sí, existe una garantía.\n\n"
        "Durante 45 días a partir de la fecha de compra se puede devolver.\n\n"
        "1) Obtener un nuevo reemplazo por cualquier producto defectuoso; o\n"
        "2) Cancelar la compra, devolver el producto y obtener un reembolso total del precio de compra."
    )
    document = _policy("US", "es", "US-ES-Company-Policy.pdf", "21.03", US_ES_21_03)

    repaired, removed = remove_unsupported_numeric_sentences(answer, [document])

    assert removed == ["45"]
    assert "1) Obtener un nuevo reemplazo" in repaired
    assert "2) Cancelar la compra" in repaired


# ---------------------------------------------------------------------------
# Must still be removed.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("answer, invented", [
    ("Le délai de livraison moyen est de 12 à 36 heures.", "36"),
    ("Die Lieferkosten betragen $3 und die Mindestbestellung $75.", "75"),
    ("**Tamaño mínimo de pedido:** $50 USD o $1,400.00 MXN.", "1,400.00"),
])
def test_invented_figure_beside_a_supported_one_is_removed(answer, invented):
    record = mexico() if "MXN" in answer else kenya()
    assert _unsupported(answer, [record]) == [invented]


def test_figure_from_another_markets_record_does_not_ground_this_market():
    # SYNTHETIC_UGANDA is an invented record; KENYA is verbatim.
    answer = "Gemäß dem Verzeichniseintrag für Forever Uganda betragen die Lieferkosten $3."
    documents = [kenya(), _record("sponsoring-025-uganda", "Uganda", SYNTHETIC_UGANDA)]

    assert _unsupported(answer, documents) == ["3"]
    assert _unsupported("**Frais de livraison :**\n$3 dans le pays.", documents) == ["3"]


def test_record_of_another_market_alone_does_not_ground_a_named_market():
    answer = "Gemäß dem Verzeichniseintrag für Forever Uganda betragen die Lieferkosten $3."
    assert _unsupported(answer, [kenya()]) == ["3"]


@pytest.mark.parametrize("answer, record, figure", [
    ("**Frais de livraison :** $20 dans le pays.", kenya, "20"),
    ("Telefon: +256 3921 77993/5", uganda, "5"),
    ("**Commande minimum :** $4 de produits.", uganda, "4"),
])
def test_short_figure_found_only_inside_a_phone_number_is_removed(answer, record, figure):
    assert _unsupported(answer, [record()]) == [figure]


@pytest.mark.parametrize("answer, record, figure", [
    ("**Tamaño mínimo de pedido:** 1,300 CC.", mexico, "1,300"),
    ("**Minimale bestelling:** 50 Case Credits.", netherlands, "50"),
    ("The minimum order size is 50 Case Credits.", netherlands, "50"),
])
def test_same_digits_with_a_different_unit_are_removed(answer, record, figure):
    assert _unsupported(answer, [record()]) == [figure]


# SYNTHETIC: continental notation with a currency code, to pair with "1.300,00 EUR".
SYNTHETIC_MXN_CONTINENTAL = (
    "Welcome to Forever Mexico!\n"
    "ORDERING PRODUCTS\n"
    "• Minimum order size FBO: 1.300,00 MXN.\n"
)


@pytest.mark.parametrize("answer, content, figure", [
    ("In Mexico the FBO minimum order size is $1,300.00 USD.", MEXICO, "1,300.00"),
    ("**Tamaño mínimo de pedido:** $1,300.00 USD.", MEXICO, "1,300.00"),
    ("In Mexico the FBO minimum order size is $50 MXN.", MEXICO, "50"),
    ("**Tamaño mínimo de pedido:** $50 MXN.", MEXICO, "50"),
    ("In Mexico the FBO minimum order size is 1.300,00 EUR.", SYNTHETIC_MXN_CONTINENTAL, "1.300,00"),
])
def test_amount_with_a_different_currency_code_is_removed(answer, content, figure):
    record = _record("sponsoring-109-mexico", "Mexico", content)
    assert _unsupported(answer, [record]) == [figure]


@pytest.mark.parametrize("answer, content", [
    ("In Mexico the FBO minimum order size is $1,300.00 MXN.", MEXICO),
    ("**Tamaño mínimo de pedido:** $1,300.00 MXN.", MEXICO),
    ("In Mexico the FBO minimum order size is $50 USD.", MEXICO),
    ("In Mexico the FBO minimum order size is 1.300,00 MXN.", SYNTHETIC_MXN_CONTINENTAL),
])
def test_amount_with_the_same_currency_code_is_kept(answer, content):
    record = _record("sponsoring-109-mexico", "Mexico", content)
    assert _unsupported(answer, [record]) == []


@pytest.mark.parametrize("answer, figure", [
    ("Die Lieferkosten betragen $100.", "100"),
    ("**Frais de livraison :** $50 dans le pays.", "50"),
    ("Le délai de livraison moyen est de 3 jours.", "3"),
])
def test_localized_field_word_pointing_at_another_field_is_removed(answer, figure):
    assert _unsupported(answer, [kenya()]) == [figure]


def test_role_the_record_does_not_give_the_minimum_to_is_removed():
    answer = "The minimum order size for Preferred Customers is $50 USD."
    assert _unsupported(answer, [mexico()]) == ["50"]


@pytest.mark.parametrize("answer, figure", [
    ("Forever Living offers a **90% Customer Satisfaction Guarantee** for end customers.", "90"),
    ("Forever Living offers a 100% refund on all shipping costs.", "100"),
])
def test_company_named_percent_without_the_same_following_words_is_removed(answer, figure):
    document = _policy("SE", "en", "SE-EN-Company-Policy.pdf", "21.02", SWEDEN_21_02)
    assert _unsupported(answer, [document]) == [figure]


def test_non_directory_document_does_not_use_the_field_path():
    document = RetrievedDocument(
        id="SE|en|SE-EN-Company-Policy.pdf|x", title="SE-EN-Company-Policy.pdf - Sec x", content=KENYA,
        source="SE-EN-Company-Policy.pdf", country="SE", language="en", score=0.9, metadata={},
    )
    assert _unsupported("Die Lieferkosten betragen $3 innerhalb des Landes.", [document]) == ["3"]
