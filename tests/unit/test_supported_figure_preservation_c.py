"""Source-supported figures that repair removed after correct retrieval.

Two unrelated causes, each covered with a positive case and a control proving
an invented or misattributed figure in the same sentence is still removed.

1. Number variants: a whole amount written by the answer ("HK$3,000") could not
   reach a record that adds zero cents ("HK$3,000.00"), so a correctly stated
   free-delivery threshold was reported ungrounded.
2. Market identity: a policy document's market is carried by its ``country``
   field, not its title ("LU-FR-Benelux-Policy.pdf - Sec 7.03-c: ..."), so a
   sentence naming "Forever Luxembourg" had that name treated as a subject that
   the Luxembourg policy text had to repeat beside the figure.

The answer sentences are development wording written for these tests.
"""

import pytest

from app.retrieval.models import RetrievedDocument
from app.validation.validators.numeric_grounding_validator import (
    _number_variants,
    remove_unsupported_numeric_sentences,
    unsupported_numeric_claims,
)


HONG_KONG_DELIVERY = (
    "• Delivery Cost: (A1) Delivery service is available available for purchase of HK$500 "
    "(after personal discount)\nwith a handling fee of HK$50.\n"
    "(A2) Free delivery service is rendered for minimum purchase of HK$3,000.00 and above "
    "(after personal\ndiscount; in a single receipt).\n"
    "• Average lead time for orders to arrive: Products are usually delivered within 3 working days."
)

LUXEMBOURG_TRIP_DEADLINE = (
    "Section 7.03: a) Dans le cas où le partenaire d’un FBO ne peut pas participer à un voyage "
    "attribué, le FBO peut\nc) Les voyages Sapphire à Platinum Centurion doivent être effectués "
    "dans les 24 mois suivant la\nqualification."
)


def _hong_kong() -> RetrievedDocument:
    return RetrievedDocument(
        id="sponsoring-030-hong-kong",
        title="International-Sponsoring-Directory.pdf - Forever Hong Kong",
        content=HONG_KONG_DELIVERY,
        source="International_Sponsoring_Directory.pdf",
        country="GLOBAL",
        language="en",
        metadata={"directory_section": "sponsoring"},
    )


def _luxembourg_policy(country: str = "LU") -> RetrievedDocument:
    return RetrievedDocument(
        id=f"{country}:7.03-c",
        title=(
            "LU-FR-Benelux-Policy.pdf - Sec 7.03-c: Les voyages Sapphire à Platinum Centurion "
            "doivent être effectués dans les 24 mois suivant la"
        ),
        content=LUXEMBOURG_TRIP_DEADLINE,
        source="LU-FR-Benelux-Policy.pdf",
        country=country,
        language="fr",
    )


def _removed(answer: str, document: RetrievedDocument) -> list[str]:
    return [claim.text for claim in unsupported_numeric_claims(answer, [document])]


# --- 1. Whole amount against a record that adds zero cents -------------------


@pytest.mark.parametrize("amount", ["HK$3,000", "HK$3,000.00"])
def test_whole_amount_reaches_a_record_written_with_zero_cents(amount: str) -> None:
    answer = f"Free delivery is available for orders of {amount} or more in a single receipt."

    assert _removed(answer, _hong_kong()) == []


def test_repair_keeps_the_free_delivery_threshold_under_its_heading() -> None:
    answer = (
        "**Delivery Fee:**\n"
        "A handling fee of HK$50 applies to orders of HK$500 or more.\n\n"
        "**Free Delivery:**\n"
        "Free delivery is available for orders of HK$3,000 or more in a single receipt."
    )

    repaired, removed = remove_unsupported_numeric_sentences(answer, [_hong_kong()])

    assert removed == []
    assert "HK$50" in repaired and "HK$3,000" in repaired


@pytest.mark.parametrize("amount", ["HK$5,000", "HK$3,500", "HK$3,000.50"])
def test_an_invented_threshold_in_the_same_sentence_is_still_removed(amount: str) -> None:
    answer = f"Free delivery is available for orders of {amount} or more in a single receipt."

    repaired, removed = remove_unsupported_numeric_sentences(answer, [_hong_kong()])

    assert removed
    assert amount not in repaired


def test_zero_cents_never_turns_a_whole_number_into_a_thousands_group() -> None:
    """"24" may reach "24.00", never "24.000", which reads as 24 000 in continental notation."""
    variants = _number_variants("24")

    assert {"24.00", "24,00"} <= variants
    assert not variants & {"24.000", "24,000", "24.0000"}


def test_the_ambiguous_point_group_still_does_not_reach_a_comma_group_with_cents() -> None:
    """"3.000" stays ambiguous: it must not ground against "HK$3,000.00"."""
    assert "3,000.00" not in _number_variants("3.000")
    answer = "Free delivery is available for orders of HK$3.000 or more in a single receipt."

    assert _removed(answer, _hong_kong()) == ["3.000"]


# --- 2. Market named in the sentence, market carried by the document country --


@pytest.mark.parametrize(
    "answer",
    [
        "Chez Forever Luxembourg, un voyage Sapphire doit être réalisé dans les 24 mois qui suivent "
        "la qualification.",
        "Selon la politique de Forever Luxembourg, vous devez effectuer ce voyage dans les 24 mois "
        "suivant votre qualification.",
    ],
)
def test_market_named_in_the_sentence_is_established_by_the_document_country(answer: str) -> None:
    assert _removed(answer, _luxembourg_policy()) == []


def test_repair_keeps_the_trip_deadline_sentence() -> None:
    answer = (
        "Selon la politique de Forever Luxembourg, vous devez effectuer ce voyage dans les 24 mois "
        "suivant votre qualification. Planifiez votre voyage dans ce délai."
    )

    repaired, removed = remove_unsupported_numeric_sentences(answer, [_luxembourg_policy()])

    assert removed == []
    assert repaired == answer


def test_an_invented_deadline_naming_the_market_is_still_removed() -> None:
    answer = (
        "Selon la politique de Forever Luxembourg, vous devez effectuer ce voyage dans les 18 mois "
        "suivant votre qualification. Planifiez votre voyage dans ce délai."
    )

    repaired, removed = remove_unsupported_numeric_sentences(answer, [_luxembourg_policy()])

    assert removed == ["18"]
    assert repaired == "Planifiez votre voyage dans ce délai."


def test_another_market_is_not_forgiven_by_the_document_country() -> None:
    answer = (
        "Selon la politique de Forever Belgique, vous devez effectuer ce voyage dans les 24 mois "
        "suivant votre qualification."
    )

    assert _removed(answer, _luxembourg_policy()) == ["24"]


def test_the_market_is_not_forgiven_when_the_document_belongs_to_another_country() -> None:
    answer = (
        "Selon la politique de Forever Luxembourg, vous devez effectuer ce voyage dans les 24 mois "
        "suivant votre qualification."
    )

    assert _removed(answer, _luxembourg_policy(country="BE")) == ["24"]


def test_a_rank_subject_still_has_to_appear_beside_the_figure() -> None:
    """Only the market is forgiven; another named subject must still be in the source."""
    answer = (
        "Chez Forever Luxembourg, un voyage Eagle Managers doit être réalisé dans les 24 mois qui "
        "suivent la qualification."
    )

    assert _removed(answer, _luxembourg_policy()) == ["24"]
