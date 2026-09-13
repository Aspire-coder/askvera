"""Review corrections to the numeric repair relaxations (Fable 5.1 review of diff 3ce4f695).

The relaxations in test_numeric_grounding_repair_defects.py keep supported
figures. These tests hold the other side: a relaxation never keeps a figure the
base validator (fb22f38) removed for a wrong row, tier, market, period or unit.
Probe sentences are the reviewer's (scratchpad fable-ovn/w3/probes_*.py); every
source text is a verbatim extraction line in the production title format.
"""

from __future__ import annotations

import pytest

from app.retrieval.models import RetrievedDocument
from app.validation.validators.numeric_grounding_validator import (
    remove_unsupported_numeric_sentences,
    unsupported_numeric_claims,
)


def _document(section_id: str, source_file: str, title: str, content: str, country: str) -> RetrievedDocument:
    if country == "GLOBAL":
        full_title = f"{source_file} - {title}"
    else:
        full_title = f"{source_file} - Sec {section_id.split(':', 1)[1]}: {title}"
    return RetrievedDocument(
        id=section_id,
        title=full_title,
        content=content,
        source=f"opensearch-section://{source_file}/{section_id}",
        country=country,
        metadata={"section_id": section_id.split(":", 1)[1]},
    )


def _unsupported(answer: str, *documents: RetrievedDocument) -> list[str]:
    return [claim.text for claim in unsupported_numeric_claims(answer, list(documents))]


DIRECTORY = "International_Sponsoring_Directory.pdf"

HONG_KONG = _document(
    "GLOBAL:sponsoring-030-hong-kong", DIRECTORY, "Forever Hong Kong",
    "• Minimum order size FBO: The minimum requirement is HKD 500 (after discount).\n"
    "• Delivery Cost: (A1) Delivery service is available available for purchase of HK$500 (after personal discount)\n"
    "with a handling fee of HK$50.\n"
    "(A2) Free delivery service is rendered for minimum purchase of HK$3,000.00 and above (after personal\n"
    "discount; in a single receipt).\n"
    "• Average lead time for orders to arrive: Products are usually delivered within 3 working days.\n"
    "• Local Product Centers available: Yes. We have 2 product centers.\n"
    "The Company will deposit FBO’s bonus payment into their bank account held outside Hong Kong every\n"
    "time the bonus accumulates to HK$2,000 or above. The banking fee for this service is HK$115, which will\n"
    "be deducted from the bonus payment. Please also note that some banks may charge additional fees to\n"
    "receive payments.",
    "GLOBAL",
)
NORWAY_DIRECTORY = _document(
    "GLOBAL:sponsoring-081-norway", DIRECTORY, "Forever Norway",
    "• Minimum order size FBO: There are no first order requirements.\n"
    "• Delivery Cost: B2C/ under 2CC - €18 ex VAT/ over 2CC- €12 ex VAT.\n"
    "B2B/ under 2CC - €21 ex VAT/ over 2CC - €15 ex VAT\n"
    "• Average lead time for orders to arrive: within 4-6 days\n"
    "Office Address Kvarnbygatan 2B\n"
    "43134 Mölndal, Sweden\n"
    "• First order required while signing up as Preferred Customer?: You do not have to place an order to\n"
    "become Preferred Customer, this has to be done within 3 months.",
    "GLOBAL",
)
ALGERIA = _document(
    "GLOBAL:sponsoring-001-algeria", DIRECTORY, "Forever Algeria",
    "• Minimum order size FBO: 0,200CC as a first order for Preferred Customers, 7 800DZD ($60) and the\n"
    "equivalent of 5 000 DZD ($43) after the first purchase for all FBOs.\n"
    "• Delivery Cost: 900 DZD ($7.5)",
    "GLOBAL",
)
POLAND = _document(
    "GLOBAL:sponsoring-082-poland", DIRECTORY, "Forever Poland",
    "Note: you are required to submit the signed original Application Form within 30 days.\n"
    "• Minimum order size FBO: First order requirement is 250 PLN (≈€65). No designated first order form\n"
    "required.\n• Delivery Cost: 16 PLN (≈€4)\n• Average lead time for orders to arrive: Up to 3 working days.",
    "GLOBAL",
)
LUXEMBOURG_DIRECTORY = _document(
    "GLOBAL:sponsoring-075-luxemburg", DIRECTORY, "Forever Luxemburg",
    "• Delivery Cost: €5,00 excl. VAT per order. Orders above 2CC are free of charge.\n"
    "Business Hours Office 09.00 am – 17.00 pm (Mon – Fri)",
    "GLOBAL",
)
US_MANAGER = _document(
    "US:4.01-definition-7", "US-EN-Company-Policy.pdf", "The Active Assistant Manager also receives",
    "Section 4.01: The FBO has the right to sell FLP products. The combined sales volume\n"
    "The Active Assistant Manager also receives:\n"
    "• 5% Volume Bonus on the Personal Accredited Sales of previously\n"
    "personally sponsored Supervisors and their Downlines.\n"
    "• 8% Volume Bonus on the Personal Accredited Sales of previously\n"
    "personally sponsored Assistant Supervisors and their Downlines.\n"
    "(d) Manager is achieved as soon as 120 Open Group Case Credits are generated\n"
    "within 1 or 2 consecutive Months, or 150 Open Group Case Credits within 3",
    "US",
)
CANADA_13_01_E = _document(
    "CA:13.01-e", "CA-EN-Company-Policy.pdf", "An FBO may not order more than 25 Case Credits in any calendar Month",
    "Section 13.01: (a) Preferred Customers and FBOs order directly from the Company at\n"
    "(e) An FBO may not order more than 25 Case Credits in any calendar Month\n"
    "without prior Home Office approval.",
    "CA",
)
CANADA_FR_13_01_E = _document(
    "CA:13.01-e", "CA-FR-Company-Policy.pdf", "Un FBO ne peut commander plus de 25 crédits de cas par mois civil sans",
    "Section 13.01: (a) Les clients privilégiés et les FBO commandent directement leurs produits\n"
    "(e) Un FBO ne peut commander plus de 25 crédits de cas par mois civil sans\n"
    "l’accord préalable du siège social.",
    "CA",
)
NORWAY_17_01 = _document(
    "NO:17.01-fact-1", "Company_Policy_NOrway - norsk.pdf",
    "personer som er 18 år eller eldre, kan inngå avtale med FLP for å bli FBO.",
    "Section 17.01: (a) Relasjonen mellom FBO og FLP er av avtalemessig karakter. Bare voksne\n"
    "personer som er 18 år eller eldre, kan inngå avtale med FLP for å bli FBO.",
    "NO",
)
ITALY_3_03 = _document(
    "IT:3.03", "COMPANY_POLICY_IT_IT.pdf",
    "Quando il Cliente Privilegiato acquista uno Start Your Journey Pack o 2CC di prodotti",
    "3.03 Quando il Cliente Privilegiato acquista uno Start Your Journey Pack o 2CC di prodotti\n"
    "nell’arco di 2 mesi consecutivi, ha diritto a uno sconto permanente del 30% per tutti\n"
    "gli ordini a seguire.",
    "IT",
)
ITALY_4_07_C = _document(
    "IT:4.07-c", "COMPANY_POLICY_IT_IT.pdf",
    "Una volta che un promoter ottiene lo sconto del 30% e aderisce diventa un FBO",
    "Section 4.07: Prezzi\n"
    "(c) Una volta che un promoter ottiene lo sconto del 30% e aderisce diventa un FBO\n"
    "con la qualifica di Assistant Supervisor e, se è attivo con i 4CC, riceverà un bonus\n"
    "aggiuntivo del 5% sugli ordini personali, a partire dall’ordine successivo.",
    "IT",
)
ITALY_4_05_A = _document(
    "IT:4.05-a", "COMPANY_POLICY_IT_IT.pdf",
    "Un FBO che non ha effettuato un acquisto personale (acquisto per uso personale",
    "Section 4.05: Politica dei 36 mesi per un FBO\n"
    "(a) Un FBO che non ha effettuato un acquisto personale (acquisto per uso personale\n"
    "e/o di Cliente Club) per trentasei (36) Mesi di calendario consecutivi perderà tutte le\n"
    "Downlines Sponsorizzate che passeranno al suo primo FBO in Upline.",
    "IT",
)
FINLAND_3_03 = _document(
    "FI:3.03", "Company_Policy_Finland - suomi.pdf",
    "Kun Preferred Customer tekee 2 CC:n arvosta ostoksia yhden tai kahden",
    "3.03 Kun Preferred Customer tekee 2 CC:n arvosta ostoksia yhden tai kahden\n"
    "peräkkäisen kalenterikuukauden aikana tai ostaa jonkin Foreverin aloituspaketin,\n"
    "hän on oikeutettu 30 %:n alennukseen tulevista tilauksista.",
    "FI",
)
FINLAND_4_05_A = _document(
    "FI:4.05-a", "Company_Policy_Finland - suomi.pdf",
    "FBO, joka ei ole tehnyt ostosta 36 peräkkäiseen kalenterikuukauteen, menettää",
    "Section 4.05: FBO:n 36 kuukauden käytäntö\n"
    "(a) FBO, joka ei ole tehnyt ostosta 36 peräkkäiseen kalenterikuukauteen, menettää\n"
    "kaikki sponsoroidut alalinjat ensimmäiselle ylälinjan FBO:lle.",
    "FI",
)
BELGIUM_NL_3_03 = _document(
    "BE:3.03", "BE-NL-Benelux-Policy.pdf", "Als de Pr",
    "3.03\nAls de Pr\neferred Customer een Start Your Journey Pack of 2 CC koopt binnen een periode van\n"
    "twee opeenvolgende maanden, heeft hij/zij recht op een permanente korting van 30% op volgende\n"
    "bestellingen.",
    "BE",
)
BELGIUM_FR_3_03 = _document(
    "BE:3.03", "BE-FR-Benelux-Policy.pdf",
    "Lorsque le Preferred Customer achète un Start Your Journey Pack ou 2 CC de produits en l’espace",
    "3.03 Lorsque le Preferred Customer achète un Start Your Journey Pack ou 2 CC de produits en l’espace\n"
    "de deux mois consécutifs, il/elle a droit à une remise permanente de 30 % sur toutes ses prochaines\n"
    "commandes.",
    "BE",
)
NORWAY_3_03 = _document(
    "NO:3.03", "Company_Policy_NOrway - norsk.pdf", "Når en Preferred Customer handler for 2 CC i løpet av en til to påfølgende",
    "3.03 Når en Preferred Customer handler for 2 CC i løpet av en til to påfølgende\n"
    "kalendermåneder eller kjøper en av Forevers startpakker, har vedkommende rett til\n"
    "en permanent rabatt på 30 % på fremtidige bestillinger.",
    "NO",
)
SWEDEN_3_03 = _document(
    "SE:3.03", "sweden company policy svenska.pdf", "När en Preferred Customer handlar för 2 CC inom en till två på varandra följande",
    "3.03 När en Preferred Customer handlar för 2 CC inom en till två på varandra följande\n"
    "kalendermånader alternativt köper någon av Forevers startboxar har hen rätt till en\n"
    "permanent 30 % rabatt på framtida order.",
    "SE",
)
DENMARK_3_03 = _document(
    "DK:3.03", "Company_Policy - denmark - dank.pdf", "Når en Preferred Customer handler for 2 CC inden for en til to på hinanden",
    "3.03 Når en Preferred Customer handler for 2 CC inden for en til to på hinanden\n"
    "følgende kalendermåneder eller køber en af Forever's startpakker, har\n"
    "vedkommende ret til en permanent rabat på 30 % på fremtidige ordrer.",
    "DK",
)
GERMANY_3_03 = _document(
    "DE:3.03", "DE-DE-Company-Policy.pdf",
    "Ein Preferred-Customer der 2 Case-Credits innerhalb eines Zeitraums von 2 aufeinanderfolgenden Monaten kauft",
    "3.03 Ein Preferred-Customer der 2 Case-Credits innerhalb eines Zeitraums von 2 aufeinanderfolgenden "
    "Monaten kauft, ist berechtig, sich als Forever Business Owner (FBO) auf der Ebene eines Assistant "
    "Supervisors für den Marketing-Plan zu registrieren.",
    "DE",
)


# --- Finding 1 and 7: inline labels never bind less than the unlabelled sentence -------

LABEL_MISATTRIBUTIONS = [
    # (answer, document, the wrong figure that must go)
    ("**Shipping Fee:** A handling fee of HK$115 applies.", HONG_KONG, "115"),
    ("**Express Courier:** The courier fee is HK$115 per parcel.", HONG_KONG, "115"),
    ("**Kurier Express:** The threshold is HK$2,000 for this.", HONG_KONG, "2,000"),
    ("**Postage Rate:** The rate is HK$2 per product for this service.", HONG_KONG, "2"),
    ("**Delivery Cost:** 2", HONG_KONG, "2"),
    (
        "**Senior Manager:** You qualify with 120 Open Group Case Credits within 1 or 2 consecutive Months.",
        US_MANAGER, "120",
    ),
    ("**Levering B2C:** Under 2CC koster det €12 ex VAT.", NORWAY_DIRECTORY, "12"),
    ("**Frakt B2B:** Under 2CC koster det €15 ex VAT.", NORWAY_DIRECTORY, "15"),
    ("**Delivery B2B:** Under 2CC the charge is €18 ex VAT.", NORWAY_DIRECTORY, "18"),
    # One-word and role labels.
    ("**Supervisor:** You qualify with 120 Open Group Case Credits within 1 or 2 consecutive Months.", US_MANAGER, "120"),
    ("**FBO:** You must place your first order within 3 months.", NORWAY_DIRECTORY, "3"),
    ("**Preferred Customer:** The minimum requirement is HKD 500 (after discount).", HONG_KONG, "500"),
    ("**Adresse:** Kvarnbygatan 4B, 43134 Mölndal", NORWAY_DIRECTORY, "4"),
]


@pytest.mark.parametrize("answer, document, figure", LABEL_MISATTRIBUTIONS)
def test_a_label_does_not_keep_a_figure_from_another_row_or_tier(
    answer: str, document: RetrievedDocument, figure: str
) -> None:
    repaired, removed = remove_unsupported_numeric_sentences(answer, [document])

    assert figure in removed and repaired == ""


@pytest.mark.parametrize("answer, document, _figure", LABEL_MISATTRIBUTIONS)
def test_a_label_never_binds_less_than_the_sentence_without_it(
    answer: str, document: RetrievedDocument, _figure: str
) -> None:
    unlabelled = answer.split(":**", 1)[1].strip()

    assert set(_unsupported(unlabelled, document)) <= set(_unsupported(answer, document))


GHANA = _document(
    "GLOBAL:sponsoring-010-ghana", DIRECTORY, "Forever Ghana",
    "Welcome to Forever Ghana!\n"
    "• Minimum order size FBO: First order requirements is US$100 +3% VAT +3% Handling charge. No\n"
    "designated order form required.\n"
    "• Delivery Cost: Not in place yet.\n"
    "BONUS PAYMENT\n• To local FBO’s\n"
    "Bonuses equal or above US$10 are paid by bank transfer or mobile money. FBOs without bank account\n"
    "or mobile money details are paid by cheque when their bonuses are up to US$50 or above.\n"
    "• To foreign FBO’s\nBonuses equal or above US$100 are paid by bank transfer.",
    "GLOBAL",
)
CANADA_13_01 = _document(
    "CA:13.01", "CA-EN-Company-Policy.pdf", "(a) Preferred Customers and FBOs order directly from the Company at",
    "13.01 (a) Preferred Customers and FBOs order directly from the Company at\n"
    "discounted prices.\n"
    "(b) All orders with appropriate payment must be submitted to an authorized FLP\n"
    "product center, Customer Care at (888) 440-ALOE (2563), or via the Internet\n"
    "at www.foreverliving.com, by 11:59 p.m.(AZ time) on the last calendar day of\n"
    "the applicable Month to qualify for a bonus generated for that Month.",
    "CA",
)


@pytest.mark.parametrize(
    "answer, document",
    [
        # Recorded delivered answers (cases 12 and 07) and a sentence-case label: base never
        # bound the words of a label that is not Title Case, and neither does the label reading.
        (
            "**Bonus payment threshold:** Bonuses equal to or above **US$100** are paid by bank transfer "
            "to foreign FBOs.",
            GHANA,
        ),
        ("- **Téléphone** : (888) 440-ALOE (2563)", CANADA_13_01),
        ("- **Delivery charge:** HK$50 handling fee for purchases of HK$500 (after personal discount)", HONG_KONG),
    ],
)
def test_sentence_case_and_short_value_labels_keep_what_base_kept(answer: str, document: RetrievedDocument) -> None:
    assert _unsupported(answer, document) == []


@pytest.mark.parametrize(
    "answer, document",
    [
        ("**Delivery Cost:** 900 DZD ($7.5)", ALGERIA),
        ("**Levering B2C:** Under 2CC koster det €18 ex VAT.", NORWAY_DIRECTORY),
        ("**Adresse:** Kvarnbygatan 2B, 43134 Mölndal, Sweden", NORWAY_DIRECTORY),
        ("**FBO:** The minimum requirement is HKD 500 (after discount).", HONG_KONG),
        ("**Manager:** You qualify with 120 Open Group Case Credits within 1 or 2 consecutive Months.", US_MANAGER),
    ],
)
def test_a_label_that_matches_its_row_keeps_the_figure(answer: str, document: RetrievedDocument) -> None:
    assert remove_unsupported_numeric_sentences(answer, [document]) == (answer, [])


# --- Finding 2: the document name is not dropped when another market is named --------


@pytest.mark.parametrize(
    "answer, document, figure",
    [
        ("Ifølge Company Policy for Sverige må du være 18 år eller eldre for å bli FBO.", NORWAY_17_01, "18"),
        (
            "Secondo la Company Policy per la Spagna, devi acquistare 2CC di prodotti nell'arco di 2 mesi consecutivi.",
            ITALY_3_03, "2",
        ),
        (
            "Selon la Company Policy du Luxembourg, un FBO ne peut commander plus de 25 crédits de cas par mois civil.",
            CANADA_FR_13_01_E, "25",
        ),
        (
            "According to the Company Policy for Mexico, an FBO may not order more than 25 Case Credits in any "
            "calendar month.",
            CANADA_13_01_E, "25",
        ),
        (
            "According to the Company Policy for the United Kingdom, an FBO may not order more than 25 Case Credits "
            "in any calendar month.",
            CANADA_13_01_E, "25",
        ),
    ],
)
def test_a_market_named_after_the_document_name_keeps_the_full_subject(
    answer: str, document: RetrievedDocument, figure: str
) -> None:
    assert figure in _unsupported(answer, document)


@pytest.mark.parametrize(
    "answer, document",
    [
        ("Ifølge Company Policy for Norge må du være 18 år eller eldre for å bli FBO.", NORWAY_17_01),
        (
            "Secondo la Company Policy per l'Italia, devi acquistare 2CC di prodotti nell'arco di 2 mesi consecutivi.",
            ITALY_3_03,
        ),
    ],
)
def test_naming_the_documents_own_market_still_drops_the_document_name(
    answer: str, document: RetrievedDocument
) -> None:
    assert _unsupported(answer, document) == []


# --- Fable re-review finding 1: a market modifier inside the document-name phrase --------
#
# "According to the US Company Policy ... 25 Case Credits" against the Canadian
# record names a market the document is not about, exactly as a trailing "for
# Sverige" does, but the modifier sits INSIDE the run that _without_document_name
# drops. Once "Company Policy" is gone, only "US" is left, too short to be a
# subject on its own, and the claim fell through to the lexical fallback, which
# wrongly grounded the Canadian 25 against the American/Belgian/Swedish/Benelux/
# Scandinavian-labelled sentence. Base removes every one of these; so must W3.

CROSS_MARKET_MODIFIER_ROWS = [
    # (answer, document, the wrong figure that must go)
    (
        "According to the US Company Policy, an FBO may not order more than 25 Case Credits in any "
        "calendar month.",
        CANADA_13_01_E, "25",
    ),
    (
        "According to the Belgian Company Policy, an FBO may not order more than 25 Case Credits in any "
        "calendar month.",
        CANADA_13_01_E, "25",
    ),
    (
        "According to the American Company Policy, an FBO may not order more than 25 Case Credits in any "
        "calendar month.",
        CANADA_13_01_E, "25",
    ),
    (
        "According to the Swedish Company Policy you must be 18 år eller eldre for å bli FBO.",
        NORWAY_17_01, "18",
    ),
    (
        "Secondo la Benelux Company Policy, devi acquistare 2CC di prodotti nell'arco di 2 mesi consecutivi.",
        ITALY_3_03, "2",
    ),
    (
        "Secondo la Scandinavian Company Policy, devi acquistare 2CC di prodotti nell'arco di 2 mesi "
        "consecutivi.",
        ITALY_3_03, "2",
    ),
]


@pytest.mark.parametrize("answer, document, figure", CROSS_MARKET_MODIFIER_ROWS)
def test_an_unrecognised_market_modifier_inside_the_document_name_keeps_the_full_subject(
    answer: str, document: RetrievedDocument, figure: str
) -> None:
    assert figure in _unsupported(answer, document)


@pytest.mark.parametrize(
    "answer, document",
    [
        (
            "According to the Canadian Company Policy, an FBO may not order more than 25 Case Credits in any "
            "calendar month.",
            CANADA_13_01_E,
        ),
    ],
)
def test_an_own_market_adjective_inside_the_document_name_still_drops_it(
    answer: str, document: RetrievedDocument
) -> None:
    assert _unsupported(answer, document) == []


# --- Finding 3: a time word beside one figure, a count beside the other -----------------

SPELLED_PERIODS = [
    # (language, source row, restatement kept, same figure with weeks removed)
    (
        "nl", BELGIUM_NL_3_03,
        "Je krijgt 30% korting als je 2 CC koopt binnen 2 maanden.",
        "Je krijgt 30% korting als je 2 CC koopt binnen 2 weken.",
    ),
    (
        "no", NORWAY_3_03,
        "En Preferred Customer som handler for 2 CC i løpet av 2 påfølgende kalendermåneder får 30 % rabatt.",
        "En Preferred Customer som handler for 2 CC i løpet av 2 påfølgende uker får 30 % rabatt.",
    ),
    (
        "fi", FINLAND_3_03,
        "Preferred Customer saa 30 %:n alennuksen, kun hän ostaa 2 CC:n arvosta tuotteita 2 peräkkäisen "
        "kalenterikuukauden aikana.",
        "Preferred Customer saa 30 %:n alennuksen, kun hän ostaa 2 CC:n arvosta tuotteita 2 peräkkäisen "
        "viikon aikana.",
    ),
    (
        "da", DENMARK_3_03,
        "En Preferred Customer, der handler for 2 CC inden for 2 på hinanden følgende kalendermåneder, får 30 % rabat.",
        "En Preferred Customer, der handler for 2 CC inden for 2 på hinanden følgende uger, får 30 % rabat.",
    ),
    (
        "sv", SWEDEN_3_03,
        "En Preferred Customer som handlar för 2 CC inom 2 på varandra följande kalendermånader får 30 % rabatt.",
        "En Preferred Customer som handlar för 2 CC inom 2 på varandra följande veckor får 30 % rabatt.",
    ),
    (
        "fr", BELGIUM_FR_3_03,
        "Lorsque le Preferred Customer achète 2 CC de produits en l'espace de 2 mois consécutifs, il a droit à "
        "une remise permanente de 30 %.",
        "Lorsque le Preferred Customer achète 2 CC de produits en l'espace de 2 semaines consécutives, il a droit "
        "à une remise permanente de 30 %.",
    ),
    (
        # The German row writes the period with a digit; kept as the same-shape control.
        "de", GERMANY_3_03,
        "Ein Preferred-Customer, der 2 Case-Credits innerhalb von 2 aufeinanderfolgenden Monaten kauft, kann "
        "sich als FBO registrieren.",
        "Ein Preferred-Customer, der 2 Case-Credits innerhalb von 2 aufeinanderfolgenden Wochen kauft, kann "
        "sich als FBO registrieren.",
    ),
    (
        # The Italian row spells the period and repeats it as a bracketed digit.
        "it", ITALY_4_05_A,
        "Un FBO che non acquista per 36 mesi consecutivi perde le downline sponsorizzate.",
        "Un FBO che non acquista per 36 settimane consecutive perde le downline sponsorizzate.",
    ),
]


@pytest.mark.parametrize("language, document, kept, _removed", SPELLED_PERIODS)
def test_a_period_beside_one_figure_matches_the_period_of_the_count(
    language: str, document: RetrievedDocument, kept: str, _removed: str
) -> None:
    assert _unsupported(kept, document) == [], language


@pytest.mark.parametrize("language, document, _kept, removed", SPELLED_PERIODS)
def test_a_different_period_beside_one_figure_is_still_removed(
    language: str, document: RetrievedDocument, _kept: str, removed: str
) -> None:
    repaired, figures = remove_unsupported_numeric_sentences(removed, [document])

    assert figures and repaired == "", language


def test_the_month_figure_is_not_removed_where_the_extraction_splits_the_role_name() -> None:
    """The BE-NL row reads "Pr\\neferred Customer", so {preferred, customer} cannot match it and the
    base validator already removed one 2. The period rule must not add the second, "2 opeenvolgende maanden"."""
    answer = "Als een Preferred Customer 2 CC koopt binnen 2 opeenvolgende maanden, krijgt hij 30% korting."
    month_figure = answer.index("2 opeenvolgende")

    removed = unsupported_numeric_claims(answer, [BELGIUM_NL_3_03])

    assert len(removed) <= 1
    assert all(claim.start != month_figure for claim in removed)


def test_a_time_word_in_a_later_clause_is_not_the_figures_period() -> None:
    answer = (
        "You may order at most 25 Case Credits, and Home Office approval, which takes days, "
        "is needed for more in a month."
    )

    assert _unsupported(answer, CANADA_13_01_E) == []


@pytest.mark.parametrize(
    "answer, document, figure",
    [
        ("FBO, joka ei ole tehnyt ostosta 36 viikkoon, menettää alalinjansa.", FINLAND_4_05_A, "36"),
        (
            "An FBO may not order more than 25 Case Credits in any calendar week without prior Home Office approval.",
            CANADA_13_01_E, "25",
        ),
        ("An FBO may not order more than 25 dollars of product in any calendar month.", CANADA_13_01_E, "25"),
        ("Nei, i Norge må du være 18 måneder for å bli FBO.", NORWAY_17_01, "18"),
        ("Products are usually delivered within 3 working weeks.", HONG_KONG, "3"),
        ("You must submit the signed original Application Form within 30 months.", POLAND, "30"),
        ("The minimum order is 500 CC after discount.", HONG_KONG, "500"),
        ("Manager is achieved with $120 of Open Group sales within 1 or 2 consecutive Months.", US_MANAGER, "120"),
        ("Per ottenere lo sconto del 30% devi acquistare 2CC di prodotti nell'arco di 4 mesi consecutivi.", ITALY_4_07_C, "4"),
    ],
)
def test_the_guard_still_removes_a_different_unit_or_period(
    answer: str, document: RetrievedDocument, figure: str
) -> None:
    assert figure in _unsupported(answer, document)


# --- Finding 6: Case Credits equivalence is for subjects only; accepted leniency ---------


def test_case_credits_written_out_does_not_borrow_another_rules_cc() -> None:
    answer = "Per restare attivo devi acquistare 2 Case Credits al mese."

    assert _unsupported(answer, ITALY_3_03, ITALY_4_07_C) == ["2"]


@pytest.mark.xfail(
    strict=True,
    reason="Accepted leniency: a freed acronym ('Every FBO') binds only {fbo}, and 'first order' against a "
    "monthly cap is a condition the validator does not read; the base removed it only because 'every' "
    "was part of the subject.",
)
@pytest.mark.parametrize(
    "answer, document",
    [
        ("Every FBO must place a first order of 25 Case Credits.", CANADA_13_01_E),
        ("Chaque FBO doit passer une première commande de 25 crédits de cas.", CANADA_FR_13_01_E),
    ],
)
def test_a_freed_acronym_with_a_wrong_condition_is_removed(answer: str, document: RetrievedDocument) -> None:
    assert "25" in _unsupported(answer, document)


# --- Fable re-review: accepted leniencies, pinned rather than left implicit -------------
#
# In each row below, base removed the figure only because an unrecognised label
# word ("standard", "kurier") is absent from the record, exactly the defect that
# deleted case 03's correct HK$50/HK$500. The unlabelled twin sentence is kept by
# base too, so the label is never made to bind less than that plain twin. These
# are accepted, not fixed: condition semantics (fee vs. threshold, which figure a
# swapped sentence order actually names) are not read (residual risk R1).


@pytest.mark.parametrize(
    "answer",
    [
        # The record's own order is "purchases of HK$500 ... handling fee of HK$50";
        # this answer swaps which figure follows which label word.
        "**Standard Delivery:** Delivery is available for purchases of HK$50 with a handling fee of HK$500.",
        # The record's free-delivery threshold is HK$3,000, not HK$500 -- HK$500 is
        # the paid-delivery purchase amount. The unlabelled twin is kept by base too.
        "**Standard Delivery:** Delivery is free for purchases of HK$500 or more.",
    ],
)
def test_a_swapped_standard_delivery_condition_is_an_accepted_leniency(answer: str) -> None:
    assert _unsupported(answer, HONG_KONG) == []


def test_a_misnamed_courier_label_restating_the_banking_fee_is_an_accepted_leniency() -> None:
    answer = "**Kurier Express:** The fee for this service is HK$115."

    assert _unsupported(answer, HONG_KONG) == []


# --- Case 19: a clock time supports only a figure written as a time ---------------------


@pytest.mark.parametrize(
    "answer",
    [
        "Business Hours Office: from 09 to 17 (Mon – Fri).",
        "Business Hours Office: 9 am to 5 pm (Mon – Fri).",
        "Delivery Cost: €5,00 excl. VAT per order.",
    ],
)
def test_a_clock_time_still_supports_times_and_amounts_still_match(answer: str) -> None:
    assert _unsupported(answer, LUXEMBOURG_DIRECTORY) == []


@pytest.mark.parametrize(
    "answer, figure",
    [
        ("Business Hours Office: you have 17 business days (Mon – Fri) to book.", "17"),
        ("Business Hours Office accepts 09 orders per day (Mon – Fri).", "09"),
    ],
)
def test_a_clock_time_does_not_support_a_count(answer: str, figure: str) -> None:
    assert _unsupported(answer, LUXEMBOURG_DIRECTORY) == [figure]
