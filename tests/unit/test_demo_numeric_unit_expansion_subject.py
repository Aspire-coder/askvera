"""Demo E2: a parenthetical that expands the unit beside a figure is not the claim's subject.

Reproduced cause. Letters glued to a figure are not words for subject binding,
so in "... 2CC (Crediti Caso) in 2 mesi consecutivi" the Title-Case expansion
alone became the subject of the months figure. It is absent from the Italian
3.03 clause, the figure was reported unsupported, and repair deleted the whole
sentence, grounded "2 mesi consecutivi" included (live: IT:3.03 citation lost in
6/6 runs). The spaced "2 CC (...)" was kept only because "CC" joined the phrase.

The source is the approved Italian Company Policy 3.03 extract; the answer
sentences are paraphrases written for this test, and the English pair is synthetic.
"""

from __future__ import annotations

import pytest

from app.retrieval.models import RetrievedDocument
from app.validation.validators.numeric_grounding_validator import (
    _without_unit_expansions,
    remove_unsupported_numeric_sentences,
)

IT_CLAUSE = (
    "Quando il Cliente Privilegiato acquista uno Start Your Journey Pack o 2CC di prodotti\n"
    "nell’arco di 2 mesi consecutivi, ha diritto a uno sconto permanente del 30% per tutti\n"
    "gli ordini a seguire."
)
EN_CLAUSE = (
    "A Loyal Customer who buys 2 CC of products, or one starter pack, within 2 consecutive months "
    "receives a permanent 30% discount on all following orders."
)


def _document(content: str, country: str, language: str) -> RetrievedDocument:
    return RetrievedDocument(
        id=f"{country}:3.03", title=f"COMPANY_POLICY_{country}_{language.upper()}.pdf - Sec 3.03",
        content=content, source="s3://approved/policy.pdf", country=country, language=language, score=0.9,
    )


ITALY = _document(IT_CLAUSE, "IT", "it")
ENGLISH = _document(EN_CLAUSE, "GB", "en")
IT_LEAD = "Il Cliente Privilegiato ottiene lo sconto permanente del 30% acquistando "
EN_LEAD = "A Loyal Customer gets a permanent 30% discount after buying "

KEPT = [
    (ITALY, IT_LEAD + "2CC (Crediti Caso) nell'arco di 2 mesi consecutivi."),
    (ITALY, IT_LEAD + "**2CC (Crediti Caso)** nell'arco di 2 mesi consecutivi."),
    (ITALY, IT_LEAD + "**2CC** (Crediti Caso) nell'arco di 2 mesi consecutivi."),
    (ITALY, IT_LEAD + "l'equivalente di 2CC (Credit Certificati) in 2 mesi consecutivi."),
    (ITALY, IT_LEAD + "2 CC (Crediti Caso) nell'arco di 2 mesi consecutivi."),
    (ITALY, IT_LEAD + "2CC di prodotti nell'arco di 2 mesi consecutivi."),
    (ENGLISH, EN_LEAD + "2CC (Credit Certificates) within 2 consecutive months."),
    (ENGLISH, EN_LEAD + "the equivalent of **2CC (Credit Certificates)** within 2 consecutive months."),
    (ENGLISH, EN_LEAD + "2 CC (Credit Certificates) within 2 consecutive months."),
]

REMOVED = [
    # Invented subject, not a unit expansion.
    (ITALY, IT_LEAD + "2CC di Aloe Vera Gel nell'arco di 2 mesi consecutivi.", "2"),
    (ENGLISH, EN_LEAD + "2 CC of Aloe Products within 2 consecutive months.", "2"),
    # A parenthetical whose words do not spell the unit is still a subject.
    (ITALY, IT_LEAD + "2CC (Aloe Vera) nell'arco di 2 mesi consecutivi.", "2"),
    (ENGLISH, EN_LEAD + "2CC (Aloe Products) within 2 consecutive months.", "2"),
    # Wrong period beside the grounded unit.
    (ITALY, IT_LEAD + "2CC (Crediti Caso) nell'arco di 2 settimane consecutive.", "2"),
    (ENGLISH, EN_LEAD + "2CC (Credit Certificates) within 2 consecutive weeks.", "2"),
    # Wrong figure beside the expansion.
    (ITALY, IT_LEAD + "4CC (Crediti Caso) nell'arco di 2 mesi consecutivi.", "4"),
    (ENGLISH, EN_LEAD + "2CC (Credit Certificates) within 3 consecutive months.", "3"),
]


@pytest.mark.parametrize("document, answer", KEPT)
def test_unit_expansion_keeps_the_grounded_sentence(document, answer) -> None:
    assert remove_unsupported_numeric_sentences(answer, [document]) == (answer, [])


@pytest.mark.parametrize("document, answer, figure", REMOVED)
def test_unsupported_subject_period_or_figure_is_still_removed(document, answer, figure) -> None:
    repaired, removed = remove_unsupported_numeric_sentences(answer, [document])
    assert figure in removed
    assert repaired != answer


@pytest.mark.parametrize("text, expected", [
    ("acquistando 2CC (Crediti Caso) in ", "acquistando 2CC  in "),
    ("buying 2 CC (Credit Certificates) within ", "buying 2 CC  within "),
    ("buying **2CC** (Case Credits) within ", "buying **2CC**  within "),
    # Left alone: not a known unit, initials that do not spell it, lowercase, or no figure.
    ("sponsor 2 FBO (Forever Business Owners) in ", "sponsor 2 FBO (Forever Business Owners) in "),
    ("buying 2CC (Aloe Vera) within ", "buying 2CC (Aloe Vera) within "),
    ("buying 2cc (credit certificates) within ", "buying 2cc (credit certificates) within "),
    ("the CC (Credit Certificates) within ", "the CC (Credit Certificates) within "),
])
def test_only_an_expansion_of_the_unit_beside_a_figure_is_dropped(text, expected) -> None:
    assert _without_unit_expansions(text) == expected
