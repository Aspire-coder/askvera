"""Source-supported figures that numeric repair removed, and the controls that keep it strict.

Every source text below is copied verbatim from a local extraction row (the
pack's ``source_extractions``) and every title uses the production format
``<source file> - Sec <id>: <title>``. The answer sentences are development
wording written for these tests; the held-out pack is not used.

Defects, each reproduced offline against the recorded frozen-comparison evidence:

1. Inline label. "**Standard Delivery:** ... HK$500 ... HK$50" made {standard,
   delivery} the subject, and the Hong Kong record never says "standard".
2. Unit abbreviation and document name. "2 Case Credits ... 2 mesi" and
   "Secondo la Company Policy italiana ... 2 mesi" required "case credits" or
   "company policy" beside a figure the Italian clause writes as "2CC".
3. Sentence-initial word plus acronym. "Suomessa FBO ... 36" and "Kun FBO ...
   36" required "suomessa"/"kun" beside 36 in the Finnish 4.05(a) clause.
4. No unit or period check. "36 viikkoon" (weeks) against a months clause was
   removed only by accident of defect 3, and "25 Case Credits in any calendar
   week", "25 dollars" and "18 måneder" were kept.
"""

from __future__ import annotations

import pytest

from app.response.models import ChatResponse
from app.retrieval.models import RetrievalResult, RetrievedDocument
from app.validation.models import ValidationContext, ValidationResult
from app.validation.validators.numeric_grounding_validator import (
    NumericGroundingValidator,
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


# --- Verbatim extraction lines ---------------------------------------------------------

HONG_KONG = _document(
    "GLOBAL:sponsoring-030-hong-kong",
    "International_Sponsoring_Directory.pdf",
    "Forever Hong Kong",
    "• Minimum order size FBO: The minimum requirement is HKD 500 (after discount).\n"
    "• Delivery Cost: (A1) Delivery service is available available for purchase of HK$500 (after personal discount)\n"
    "with a handling fee of HK$50.\n"
    "(A2) Free delivery service is rendered for minimum purchase of HK$3,000.00 and above (after personal\n"
    "discount; in a single receipt).\n"
    "• Average lead time for orders to arrive: Products are usually delivered within 3 working days.\n"
    "The Company will deposit FBO’s bonus payment into their bank account held outside Hong Kong every\n"
    "time the bonus accumulates to HK$2,000 or above. The banking fee for this service is HK$115, which will\n"
    "be deducted from the bonus payment. Please also note that some banks may charge additional fees to\n"
    "receive payments.",
    "GLOBAL",
)
ITALY_DIRECTORY = _document(
    "GLOBAL:sponsoring-071-italy",
    "International_Sponsoring_Directory.pdf",
    "Forever Italy",
    "• Delivery Cost: For Forever Business Owners: orders up to €50 the delivery charge is €7.50, from €50 to\n"
    "€200, the delivery charge is €3,00. For orders over €200 the delivery charge is Free.",
    "GLOBAL",
)
NORWAY_DIRECTORY = _document(
    "GLOBAL:sponsoring-081-norway",
    "International_Sponsoring_Directory.pdf",
    "Forever Norway",
    "• Delivery Cost: B2C/ under 2CC - €18 ex VAT/ over 2CC- €12 ex VAT.\n"
    "Office Address Kvarnbygatan 2B\n"
    "43134 Mölndal, Sweden",
    "GLOBAL",
)
ITALY_3_03 = _document(
    "IT:3.03",
    "COMPANY_POLICY_IT_IT.pdf",
    "Quando il Cliente Privilegiato acquista uno Start Your Journey Pack o 2CC di prodotti",
    "3.03 Quando il Cliente Privilegiato acquista uno Start Your Journey Pack o 2CC di prodotti\n"
    "nell’arco di 2 mesi consecutivi, ha diritto a uno sconto permanente del 30% per tutti\n"
    "gli ordini a seguire.",
    "IT",
)
ITALY_4_07_C = _document(
    "IT:4.07-c",
    "COMPANY_POLICY_IT_IT.pdf",
    "Una volta che un promoter ottiene lo sconto del 30% e aderisce diventa un FBO",
    "Section 4.07: Prezzi\n"
    "(c) Una volta che un promoter ottiene lo sconto del 30% e aderisce diventa un FBO\n"
    "con la qualifica di Assistant Supervisor e, se è attivo con i 4CC, riceverà un bonus\n"
    "aggiuntivo del 5% sugli ordini personali, a partire dall’ordine successivo.",
    "IT",
)
FINLAND_3_03 = _document(
    "FI:3.03",
    "Company_Policy_Finland - suomi.pdf",
    "Kun Preferred Customer tekee 2 CC:n arvosta ostoksia yhden tai kahden",
    "3.03 Kun Preferred Customer tekee 2 CC:n arvosta ostoksia yhden tai kahden\n"
    "peräkkäisen kalenterikuukauden aikana tai ostaa jonkin Foreverin aloituspaketin,\n"
    "hän on oikeutettu 30 %:n alennukseen tulevista tilauksista.",
    "FI",
)
BELGIUM_NL_3_03 = _document(
    "BE:3.03",
    "BE-NL-Benelux-Policy.pdf",
    "Als de Pr",
    "3.03\nAls de Pr\neferred Customer een Start Your Journey Pack of 2 CC koopt binnen een periode van\n"
    "twee opeenvolgende maanden, heeft hij/zij recht op een permanente korting van 30% op volgende\n"
    "bestellingen.",
    "BE",
)
FINLAND_4_05_A = _document(
    "FI:4.05-a",
    "Company_Policy_Finland - suomi.pdf",
    "FBO, joka ei ole tehnyt ostosta 36 peräkkäiseen kalenterikuukauteen, menettää",
    "Section 4.05: FBO:n 36 kuukauden käytäntö\n"
    "(a) FBO, joka ei ole tehnyt ostosta 36 peräkkäiseen kalenterikuukauteen, menettää\n"
    "kaikki sponsoroidut alalinjat ensimmäiselle ylälinjan FBO:lle.",
    "FI",
)
FINLAND_EN_4_05_A = _document(
    "FI:4.05-a",
    "Company_Policy_finland - english.pdf",
    "An FBO who has not made a purchase for 36 consecutive calendar months will lose all",
    "Section 4.05: FBO 36-month policy\n"
    "(a) An FBO who has not made a purchase for 36 consecutive calendar months will lose all\n"
    "sponsored downlines to their first upline FBO.\n"
    "EU Company Policies and the Code of Professional Conduct Revised 20260601",
    "FI",
)
NORWAY_4_05_A = _document(
    "NO:4.05-a",
    "Company_Policy_NOrway - norsk.pdf",
    "En FBO som ikke har foretatt et kjøp i løpet av trettiseks (36)",
    "Section 4.05: FBO 36-månedersegelen\n"
    "(a) En FBO som ikke har foretatt et kjøp i løpet av trettiseks (36)\n"
    "sammenhengende kalendermåneder, mister alle sponsede downlines til sin første\n"
    "upline FBO.",
    "NO",
)
ITALY_4_05_A = _document(
    "IT:4.05-a",
    "COMPANY_POLICY_IT_IT.pdf",
    "Un FBO che non ha effettuato un acquisto personale (acquisto per uso personale",
    "Section 4.05: Politica dei 36 mesi per un FBO\n"
    "(a) Un FBO che non ha effettuato un acquisto personale (acquisto per uso personale\n"
    "e/o di Cliente Club) per trentasei (36) Mesi di calendario consecutivi perderà tutte le\n"
    "Downlines Sponsorizzate che passeranno al suo primo FBO in Upline.",
    "IT",
)
CANADA_FR_4_05_A = _document(
    "CA:4.05-a",
    "CA-FR-Company-Policy.pdf",
    "Un FBO qui n’a pas atteint l’un des objectifs suivants au cours d’une période",
    "Section 4.05: Politique de 24 mois des FBO :\n"
    "(a) Un FBO qui n’a pas atteint l’un des objectifs suivants au cours d’une période\n"
    "consécutive de vingt-quatre (24) mois sera reclassé en tant que client\n"
    "privilégié, conservera son niveau de Remise actuel et renoncera à toutes les\n"
    "lignées descendantes parrainées au profit de son premier FBO ascendant :",
    "CA",
)
CANADA_FR_13_01_E = _document(
    "CA:13.01-e",
    "CA-FR-Company-Policy.pdf",
    "Un FBO ne peut commander plus de 25 crédits de cas par mois civil sans",
    "Section 13.01: (a) Les clients privilégiés et les FBO commandent directement leurs produits\n"
    "(e) Un FBO ne peut commander plus de 25 crédits de cas par mois civil sans\n"
    "l’accord préalable du siège social.",
    "CA",
)
CANADA_13_01_E = _document(
    "CA:13.01-e",
    "CA-EN-Company-Policy.pdf",
    "An FBO may not order more than 25 Case Credits in any calendar Month",
    "Section 13.01: (a) Preferred Customers and FBOs order directly from the Company at\n"
    "(e) An FBO may not order more than 25 Case Credits in any calendar Month\n"
    "without prior Home Office approval.",
    "CA",
)
NORWAY_17_01 = _document(
    "NO:17.01-fact-1",
    "Company_Policy_NOrway - norsk.pdf",
    "personer som er 18 år eller eldre, kan inngå avtale med FLP for å bli FBO.",
    "Section 17.01: (a) Relasjonen mellom FBO og FLP er av avtalemessig karakter. Bare voksne\n"
    "personer som er 18 år eller eldre, kan inngå avtale med FLP for å bli FBO.",
    "NO",
)


# --- 1. Inline label (case 03, Hong Kong) ------------------------------------------------

HONG_KONG_BODY = (
    "Delivery is available for purchases of HK$500 (after your personal discount), with a handling fee of HK$50."
)


@pytest.mark.parametrize("label", ["Standard Delivery", "Paid Delivery", "Regular Delivery", "Delivery Costs"])
@pytest.mark.parametrize("layout", ["**{label}:** {body}", "{label}: {body}", "- **{label}:** {body}"])
def test_an_inline_label_the_record_never_uses_does_not_detach_its_amounts(label: str, layout: str) -> None:
    answer = layout.format(label=label, body=HONG_KONG_BODY)

    assert _unsupported(answer, HONG_KONG) == []


def test_repair_keeps_both_hong_kong_delivery_figures_in_the_recorded_layout() -> None:
    answer = (
        "# Delivery Costs and Free Delivery Threshold for Forever Hong Kong\n\n"
        "According to Forever Hong Kong's policy, here's how delivery charges work:\n\n"
        f"**Standard Delivery:** {HONG_KONG_BODY}\n\n"
        "**Free Delivery:** You qualify for free delivery when you spend HK$3,000 or more "
        "(after your personal discount) in a single receipt."
    )

    assert remove_unsupported_numeric_sentences(answer, [HONG_KONG]) == (answer, [])


def test_the_validator_raises_no_issue_for_the_labelled_amounts() -> None:
    """Repair is only reached through this issue, so the verdicts must agree."""
    answer = f"**Standard Delivery:** {HONG_KONG_BODY}"
    context = ValidationContext(
        chat_response=ChatResponse(
            answer=answer, citations=[], suggestions=[], cards=[], confidence=0.9, metadata={},
            correlation_id="w3",
        ),
        correlation_id="w3",
        country="US",
        language="en",
        role="active_distributor",
        retrieval_result=RetrievalResult(documents=[HONG_KONG], citations=[], confidence=0.9),
    )
    result = ValidationResult()

    NumericGroundingValidator().validate(context, result)

    assert result.valid


@pytest.mark.parametrize("amount", ["HK$60", "HK$5,000"])
def test_an_inline_label_does_not_rescue_an_invented_amount(amount: str) -> None:
    answer = f"**Standard Delivery:** Delivery is available for purchases of HK$500, with a handling fee of {amount}."

    repaired, removed = remove_unsupported_numeric_sentences(answer, [HONG_KONG])

    assert removed and amount not in repaired


def test_a_label_naming_another_rule_of_the_same_record_still_binds() -> None:
    """"banking" is a word the record uses, for the HK$115 bonus transfer fee, so it must be beside HK$50."""
    answer = "**Banking Fee:** A handling fee of HK$50 applies to purchases of HK$500."

    assert set(_unsupported(answer, HONG_KONG)) == {"50", "500"}


def test_a_label_does_not_carry_a_dollar_amount_into_another_markets_euro_record() -> None:
    answer = "**Standard Delivery:** Forever Italy charges a handling fee of HK$50."

    assert _unsupported(answer, HONG_KONG, ITALY_DIRECTORY) == ["50"]


@pytest.mark.parametrize(
    "answer, document",
    [
        ("**Standard Delivery:** For orders up to €50, the delivery charge is €7.50.", ITALY_DIRECTORY),
        ("**Home Delivery:** Orders under 2CC cost €18 ex VAT.", NORWAY_DIRECTORY),
        ("**Adresse:** Kvarnbygatan 2B, 43134 Mölndal, Sweden", NORWAY_DIRECTORY),
    ],
)
def test_inline_labels_keep_supported_amounts_in_neighbouring_records(answer: str, document: RetrievedDocument) -> None:
    assert _unsupported(answer, document) == []


# --- 2. Unit abbreviation and document name (case 13, Italy) ----------------------------


@pytest.mark.parametrize(
    "answer",
    [
        "Per ottenere lo sconto del 30%, devi acquistare 2 Case Credits (CC) di prodotti nell'arco di 2 mesi consecutivi.",
        "Lo sconto del 30% si ottiene acquistando 2 Case Credits in 2 mesi consecutivi.",
        "Secondo la Company Policy italiana, devi acquistare 2CC di prodotti nell'arco di 2 mesi consecutivi.",
    ],
)
def test_the_italian_two_case_credit_condition_is_kept(answer: str) -> None:
    assert _unsupported(answer, ITALY_3_03, ITALY_4_07_C) == []


@pytest.mark.parametrize(
    "answer, document",
    [
        ("Saat 30 %:n alennuksen, kun ostat 2 Case Creditin arvosta tuotteita.", FINLAND_3_03),
        ("Je krijgt 30% korting als je 2 Case Credits koopt binnen twee opeenvolgende maanden.", BELGIUM_NL_3_03),
        (
            "Un FBO ne peut pas commander plus de 25 Case Credits par mois civil sans l'accord du siège social.",
            CANADA_FR_13_01_E,
        ),
    ],
)
def test_case_credits_written_out_reach_cc_in_neighbouring_languages(answer: str, document: RetrievedDocument) -> None:
    assert _unsupported(answer, document) == []


@pytest.mark.parametrize(
    "answer, expected",
    [
        # Invented amount.
        ("Per ottenere lo sconto del 30%, devi acquistare 3 Case Credits (CC) nell'arco di 2 mesi consecutivi.", ["3"]),
        # Wrong timing: the clause says two months.
        ("Per ottenere lo sconto del 30% devi acquistare 2CC di prodotti nell'arco di 4 mesi consecutivi.", ["4"]),
        # Wrong unit: the record's 5 is a percentage.
        ("Per ricevere il bonus devi essere attivo con 5 Case Credits.", ["5"]),
        # The document's own name does not cover a figure it never states.
        ("Secondo la Company Policy italiana, devi acquistare 3CC di prodotti.", ["3"]),
        # Another market's policy is not this document's name.
        (
            "Secondo la Belgium Company Policy, devi acquistare 2CC di prodotti nell'arco di 2 mesi consecutivi.",
            ["2", "2"],
        ),
    ],
)
def test_italian_controls_are_still_removed(answer: str, expected: list[str]) -> None:
    assert _unsupported(answer, ITALY_3_03, ITALY_4_07_C) == expected


def test_case_credits_in_french_per_week_is_not_the_monthly_limit() -> None:
    answer = "Un FBO ne peut pas commander plus de 25 crédits de cas par semaine sans l'accord du siège social."

    assert _unsupported(answer, CANADA_FR_13_01_E) == ["25"]


# --- 3 and 4. Sentence-initial word, acronym, unit and period (case 17 turn 1) -----------

MULTILINGUAL_PERIODS = [
    (
        "fi",
        FINLAND_4_05_A,
        "Suomessa FBO, joka ei ole tehnyt ostosta 36 peräkkäiseen kalenterikuukauteen, menettää kaikki "
        "sponsoroidut alalinjat ensimmäiselle ylälinjan FBO:lle.",
        "Suomessa FBO, joka ei ole tehnyt ostosta 36 viikkoon, menettää kaikki sponsoroidut alalinjat "
        "ensimmäiselle ylälinjan FBO:lle.",
    ),
    (
        "fi",
        FINLAND_4_05_A,
        "Kun FBO ei ole tehnyt ostosta 36 peräkkäiseen kalenterikuukauteen, hän menettää kaikki sponsoroidut alalinjat.",
        "Jos FBO ei ole ostanut mitään 36 viikkoon, hän menettää kaikki sponsoroidut alalinjansa.",
    ),
    (
        "no",
        NORWAY_4_05_A,
        "En FBO som ikke har foretatt et kjøp på 36 sammenhengende kalendermåneder, mister alle sponsede "
        "downlines til sin første upline FBO.",
        "En FBO som ikke har foretatt et kjøp på 36 sammenhengende uker, mister alle sponsede downlines til "
        "sin første upline FBO.",
    ),
    (
        "it",
        ITALY_4_05_A,
        "Un FBO che non ha effettuato un acquisto personale per 36 mesi di calendario consecutivi perderà "
        "tutte le downline sponsorizzate.",
        "Un FBO che non ha effettuato un acquisto personale per 36 settimane consecutive perderà tutte le "
        "downline sponsorizzate.",
    ),
    (
        "fr",
        CANADA_FR_4_05_A,
        "Un FBO qui n’a pas atteint l’un des objectifs suivants au cours d’une période consécutive de 24 mois "
        "sera reclassé en tant que client privilégié.",
        "Un FBO qui n’a pas atteint l’un des objectifs suivants au cours d’une période consécutive de 24 "
        "semaines sera reclassé en tant que client privilégié.",
    ),
    (
        "en",
        FINLAND_EN_4_05_A,
        "An FBO who has not made a purchase for 36 consecutive calendar months will lose all sponsored "
        "downlines to their first upline FBO.",
        "An FBO who has not made a purchase for 36 consecutive calendar weeks will lose all sponsored "
        "downlines to their first upline FBO.",
    ),
    (
        "nl",
        BELGIUM_NL_3_03,
        "Je krijgt 30% korting als je 2 Case Credits koopt binnen twee opeenvolgende maanden.",
        "Je krijgt 30% korting als je 2 Case Credits koopt binnen twee opeenvolgende weken.",
    ),
]


@pytest.mark.parametrize("language, document, kept, _removed", MULTILINGUAL_PERIODS)
def test_a_restated_clause_keeps_its_figure(
    language: str, document: RetrievedDocument, kept: str, _removed: str
) -> None:
    assert remove_unsupported_numeric_sentences(kept, [document]) == (kept, []), language


@pytest.mark.parametrize("language, document, _kept, removed", MULTILINGUAL_PERIODS)
def test_the_same_figure_with_a_different_period_is_removed(
    language: str, document: RetrievedDocument, _kept: str, removed: str
) -> None:
    repaired, figures = remove_unsupported_numeric_sentences(removed, [document])

    assert figures and repaired == "", language


def test_an_invented_inactivity_period_is_still_removed() -> None:
    answer = (
        "Suomessa FBO, joka ei ole tehnyt ostosta 24 peräkkäiseen kalenterikuukauteen, menettää kaikki "
        "sponsoroidut alalinjat."
    )

    assert _unsupported(answer, FINLAND_4_05_A) == ["24"]


def test_a_freed_acronym_must_still_stand_beside_the_figure() -> None:
    """Dropping "Un" leaves {fbo}, which the customer-discount clause does not contain."""
    answer = "Un FBO ottiene uno sconto permanente del 30% dopo 2 mesi consecutivi."

    assert _unsupported(answer, ITALY_3_03) == ["30", "2"]


def test_a_role_phrase_opening_the_sentence_is_not_freed() -> None:
    answer = "Suomessa Preferred Customer, joka ei ole tehnyt ostosta 36 peräkkäiseen kalenterikuukauteen, menettää alalinjansa."

    assert _unsupported(answer, FINLAND_4_05_A) == ["36"]


# --- Case 06 (Canada) source-bound phrasings, and case 24 (Norway) ----------------------


@pytest.mark.parametrize(
    "answer",
    [
        "Yes. In Canada, an FBO may not order more than 25 Case Credits in any calendar month without prior Home Office approval.",
        "Yes. An FBO may not order more than 25 Case Credits in any calendar Month without prior Home Office approval.",
        "Yes. **Monthly Limit:** An FBO may not order more than 25 Case Credits in any calendar month without prior Home Office approval.",
        "Yes — the limit is **25 Case Credits** per calendar month.",
    ],
)
def test_the_canadian_monthly_limit_is_kept_in_source_bound_wording(answer: str) -> None:
    assert remove_unsupported_numeric_sentences(answer, [CANADA_13_01_E]) == (answer, [])


@pytest.mark.parametrize(
    "answer, figure",
    [
        ("Yes. An FBO may not order more than 30 Case Credits in any calendar month without prior Home Office approval.", "30"),
        ("Yes. An FBO may not order more than 25 Case Credits in any calendar week without prior Home Office approval.", "25"),
        ("Yes. An FBO may not order more than 25 Case Credits in any calendar year without prior Home Office approval.", "25"),
        ("Yes. An FBO may not order more than 25 dollars of product in any calendar month.", "25"),
    ],
)
def test_the_canadian_limit_controls_are_removed(answer: str, figure: str) -> None:
    assert remove_unsupported_numeric_sentences(answer, [CANADA_13_01_E]) == ("Yes.", [figure])


@pytest.mark.parametrize(
    "answer",
    [
        "**Aldersgrense:** Bare voksne personer som er 18 år eller eldre kan bli FBO.",
        "Nei. Ifølge Company Policy for Norge må du være 18 år eller eldre for å inngå avtale med FLP og bli FBO.",
    ],
)
def test_the_norwegian_age_limit_is_kept(answer: str) -> None:
    assert remove_unsupported_numeric_sentences(answer, [NORWAY_17_01]) == (answer, [])


@pytest.mark.parametrize(
    "answer, figure",
    [
        ("Nei. Ifølge Company Policy for Norge må du være 16 år eller eldre for å bli FBO.", "16"),
        ("**Aldersgrense:** Bare voksne personer som er 21 år eller eldre kan bli FBO.", "21"),
        ("Nei, i Norge må du være 18 måneder for å bli FBO.", "18"),
    ],
)
def test_the_norwegian_age_controls_are_removed(answer: str, figure: str) -> None:
    assert _unsupported(answer, NORWAY_17_01) == [figure]
