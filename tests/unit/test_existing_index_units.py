"""What the stricter unit rule does to the index as it stands today.

Two of the changes reach production by different routes and must be judged
separately:

  carrying a heading onto continuation chunks happens at INGESTION, so it
  reaches a document only when that document is re-ingested. The 17,896
  sections in the index today keep the chunking they were ingested with.

  the unit-attribution rule is VALIDATION, so it applies to every answer from
  the next deploy, over chunks that were never shaped for it.

That second half is the one that can regress live answers, and it is stricter
than what it replaced. So these run the real corpus text - verbatim excerpts,
the same ones the notation coverage uses - and check that correct claims over
unchanged chunks still ground.
"""

from __future__ import annotations

import pytest

from app.retrieval.models import RetrievedDocument
from app.validation.validators.numeric_grounding_validator import (
    unsupported_numeric_claims,
)

# Verbatim from askvera-policy-sections, exactly as the corpus writes them.
# Reformatting them would defeat the purpose: the point is that these are the
# shapes already in the index, glued units and all.
ALGERIA = (
    "Welcome to Forever Algeria! Minimum order size FBO: 0,200CC as a first order for Preferred "
    "Customers, 7 800DZD ($60) and the equivalent of 5 000 DZD ($43) after the first purchase for "
    "all FBOs. Delivery Cost: 900 DZD ($7.5). Average lead time for orders to arrive: between 48h "
    "to 96h, exception made for the extreme southern part of the country."
)
REUNION = (
    "Forever Reunion Island. Delivery cost are at 6EUR and free for orders exceeding 1CC. "
    "The GO2FBO pack costs 352.38EUR and it represents 1.612CC."
)
FRANCE = (
    "Forever France. A newly sponsored Preferred Customer will have to order 150EUR minimum of "
    "products within 72 hours. The Discovery Pack is worth 0,540CC at 150EUR. Forever France "
    "transfers bonuses to local accounts if the bonus amount exceeds 5EUR."
)

RECORDS = {
    "algeria": (ALGERIA, "Forever Algeria", "sponsoring-001-algeria"),
    "reunion": (REUNION, "Forever Reunion Island", "sponsoring-084-r-union-island"),
    "france": (FRANCE, "Forever France", "sponsoring-063-france"),
}


def _document(record: str) -> RetrievedDocument:
    content, title, section_id = RECORDS[record]
    return RetrievedDocument(
        id=section_id,
        title=f"International-Sponsoring-Directory.pdf - {title}",
        content=content,
        source="s3://askverachat-prod-kb/approved/Global_en/directories/"
        "International-Sponsoring-Directory.pdf",
        page="5",
        metadata={
            "access_scope": "global",
            "directory_section": "sponsoring",
            "section_id": section_id,
        },
    )


def _removed(answer: str, record: str) -> list[str]:
    return [
        claim.number
        for claim in unsupported_numeric_claims(answer, [_document(record)])
    ]


# --- correct claims over unchanged chunks ---------------------------------


@pytest.mark.parametrize(
    "record,answer",
    [
        ("algeria", "Delivery in Algeria costs 900 DZD."),
        ("algeria", "The minimum order after the first purchase is 5 000 DZD."),
        ("algeria", "A first order for Preferred Customers is 0,200CC."),
        ("reunion", "Delivery on Reunion Island costs 6EUR."),
        ("reunion", "The GO2FBO pack costs 352.38EUR."),
        ("reunion", "The GO2FBO pack represents 1.612CC."),
        ("france", "A newly sponsored Preferred Customer must order 150EUR of products."),
        ("france", "The Discovery Pack is worth 0,540CC."),
        ("france", "Bonuses are transferred when the amount exceeds 5EUR."),
    ],
)
def test_a_correct_claim_over_an_unchanged_chunk_still_grounds(record, answer) -> None:
    """The regression that would matter most: deleting figures from good answers.

    Every one of these is denominated by a unit written beside it, which is how
    this corpus writes charges. The stricter rule changes what happens when a
    unit is NOT beside the figure, and these show it does not disturb the case
    that dominates the real text.
    """
    assert _removed(answer, record) == []


# --- wrong claims over the same chunks ------------------------------------


@pytest.mark.parametrize(
    "record,answer,number",
    [
        ("algeria", "Delivery in Algeria costs 900 EUR.", "900"),
        ("reunion", "Delivery on Reunion Island costs 6 DZD.", "6"),
        ("france", "The Discovery Pack costs 150 DZD.", "150"),
    ],
)
def test_a_wrong_currency_over_an_unchanged_chunk_is_removed(record, answer, number) -> None:
    assert _removed(answer, record) == [number]


def test_a_unit_borrowed_from_a_neighbouring_sentence_is_removed() -> None:
    """The behaviour change operators should expect on the existing index.

    Algeria's record names CC and DZD in adjacent sentences. Attaching CC to a
    DZD figure was previously accepted whenever CC appeared anywhere in the
    document; it no longer is. This is stricter, and it is the direction that
    prevents a wrong unit reaching a reader.
    """
    assert _removed("Delivery in Algeria costs 900CC.", "algeria") == ["900"]


def test_the_dollar_conversions_in_the_corpus_do_not_license_a_dollar_claim() -> None:
    """Algeria writes ($60) beside 7 800DZD. That parenthetical is adjacent to
    its own figure and says nothing about the delivery charge."""
    assert _removed("Delivery in Algeria costs 900 USD.", "algeria") == ["900"]


# --- what re-ingestion changes, and what it does not ----------------------


def test_a_legacy_chunk_gains_nothing_from_the_ingestion_side_fix() -> None:
    """Stated as a test so the limit is not mistaken for a fix.

    Carrying a heading happens at ingestion. A chunk already in the index that
    lost its table heading to an old split still has no currency in it, and no
    claim naming one can be grounded against it until it is re-ingested.
    """
    orphaned = _document("algeria")
    orphaned = RetrievedDocument(
        id=orphaned.id,
        title=orphaned.title,
        content="Standard delivery to the Algiers office: 900\n",
        source=orphaned.source,
        page=orphaned.page,
        metadata=orphaned.metadata,
    )

    claims = unsupported_numeric_claims(
        "Standard delivery to the Algiers office costs 900 DZD.", [orphaned]
    )

    assert [claim.number for claim in claims] == ["900"]
