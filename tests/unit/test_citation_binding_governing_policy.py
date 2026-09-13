"""Citation binding between a market's governing policy and a directory record.

A numeric answer that states a policy figure and then lists contact details
used to be cited to the directory record alone: phone digit groups counted as
matched figures, and a directory that happened to repeat the policy figure in
an unrelated sentence looked as if it covered it.
"""

import pytest

from app.models.responses import ModelResponse
from app.response import ResponseBuilder
from app.retrieval import RetrievedDocument, RetrievalResult


def _doc(doc_id, country, section, content, score, parent="", directory=False):
    metadata = {"section_id": section, "parent_section_id": parent}
    if directory:
        metadata.update({"directory_section": "sponsoring", "directory_kind": "international_sponsoring"})
    return RetrievedDocument(
        id=doc_id, title=f"{country} {section}", content=content, source=f"s3://kb/{doc_id}",
        country=country, score=score, metadata=metadata,
    )


def _citations(answer, documents, country):
    response = ResponseBuilder().build(
        model_response=ModelResponse(text=answer, citations=[], confidence=0.9, provider="claude", model_name="model"),
        retrieval_result=RetrievalResult(documents, [], 0.9),
        correlation_id="cid",
        session_metadata={"country": country},
    )
    return [(citation.get("country"), citation.get("section")) for citation in response.citations]


_DENMARK_DIRECTORY = (
    "Welcome to Forever Denmark!\n+45 70 20 30 40\n"
    "Delivery Cost: under 2CC - €18 ex VAT per order.\n"
    "Business Hours Office 09.00 am - 16.00 pm (Mon - Fri)\n"
    "Telephone Office +45 70 20 30 40\nEmail service@example.dk"
)
_DENMARK_AGE_POLICY = "Section 5.01: a) Only persons who are 18 years or older may sign an FBO agreement."
_AGE_ANSWER_WITH_CONTACTS = (
    "No, you cannot sign up as an FBO yet. You can contact Forever Denmark when you turn 18 years old.\n"
    "Phone: +45 70 20 30 40\nEmail: service@example.dk\nOpening hours: Mon-Fri 09.00-16.00"
)

_GERMANY_DIRECTORY = (
    "Welcome to Forever Germany!\nTelephone for Orders +49 6131 8999 0\n"
    "Email service@example.de\nMinimum order size FBO: 50,00 in products.\n"
    "Delivery Cost: 5,00 per order. Orders above 12 cases ship free."
)


# KNOWN GAP, NOT COVERAGE. The three xfail tests below state outcomes the product
# needs but the builder does not deliver. Do not count them as passing coverage.
#
# Each governing passage scores below the unchanged 0.35 full-answer support gate
# (its measured score is in the reason), because the answer's contact digits
# dilute it. No other path adds a governing passage.
#
# Scoring the contact-blanked answer instead would pass all three. That gate was
# measured UNSAFE on 2026-09-11 (Fable, handoff 2026-09-11_1530): it added false
# second citations on 4 of 9 new adversarial shapes (N1, N4b, N5b, N7b), and it
# must not be adopted to close this gap. A figure-sentence window gate was also
# measured and rejected (handoff 2026-09-11_1625_ovn-w4-citation).
#
# strict=True: an unexpected pass fails the run, so closing the gap has to be a
# deliberate, reviewed change rather than a side effect.
_BELOW_FULL_ANSWER_GATE = (
    "KNOWN GAP (not coverage): governing passage scores below the unchanged 0.35 full-answer gate; "
    "the contact-blanked gate that would pass it was measured unsafe (N1, N4b, N5b, N7b)"
)


@pytest.mark.xfail(strict=True, reason=f"{_BELOW_FULL_ANSWER_GATE} (DK:5.01-a 0.2254)")
def test_policy_figure_is_cited_when_directory_repeats_the_digits_elsewhere() -> None:
    """The directory charges 18 for delivery; that does not make it the source of an age limit."""
    policy = _doc("DK:5.01-a", "DK", "5.01-a", _DENMARK_AGE_POLICY, 0.9, parent="5.01")
    directory = _doc("GLOBAL:sponsoring-dk", "GLOBAL", "sponsoring-dk", _DENMARK_DIRECTORY, 0.8, directory=True)
    cited = _citations(_AGE_ANSWER_WITH_CONTACTS, [policy, directory], "DK")
    assert set(cited) == {("DK", "5.01"), ("GLOBAL", "sponsoring-dk")}


@pytest.mark.xfail(strict=True, reason=f"{_BELOW_FULL_ANSWER_GATE} (BE:6.02-c 0.1982; held-out case 19 shape)")
def test_contact_digits_do_not_push_the_policy_deadline_below_the_support_threshold() -> None:
    policy = _doc("BE:6.02-c", "BE", "6.02-c",
                  "Section 6.02: c) Incentive trips must be taken within 24 months of qualifying.", 0.9, parent="6.02")
    directory = _doc("GLOBAL:sponsoring-be", "GLOBAL", "sponsoring-be",
                     "Welcome to Forever Belgium!\nTelephone for Orders +32 2 345 6789\nEmail support@example.be",
                     0.8, directory=True)
    answer = (
        "According to the Belgian rules, your incentive trip has to happen within 24 months. That gives you "
        "roughly two years from your qualification date to organise and enjoy everything calmly.\n"
        "If you still have questions about bookings or practical arrangements, please reach the Forever "
        "Belgium office directly.\nOrders telephone: +32 2 345 6789\nEmail: support@example.be"
    )
    cited = _citations(answer, [policy, directory], "BE")
    assert ("BE", "6.02") in cited
    assert ("GLOBAL", "sponsoring-be") in cited


def test_only_the_session_markets_policy_is_cited_when_another_market_ranks_higher() -> None:
    own = _doc("DE:9.02-b", "DE", "9.02-b",
               "Section 9.02: b) Incentive trips must be completed within 18 months of qualifying.", 0.7, parent="9.02")
    foreign = _doc("AT:9.02-b", "AT", "9.02-b",
                   "Section 9.02: b) Incentive trips must be completed within 18 months of qualifying.", 0.95,
                   parent="9.02")
    answer = "Incentive trips must be completed within 18 months of qualifying."
    cited = _citations(answer, [foreign, own], "DE")
    assert cited == [("DE", "9.02")]


def test_foreign_policy_is_never_cited_even_when_it_alone_states_the_figure() -> None:
    foreign = _doc("SE:5.01-a", "SE", "5.01-a", _DENMARK_AGE_POLICY, 0.95, parent="5.01")
    directory = _doc("GLOBAL:sponsoring-dk", "GLOBAL", "sponsoring-dk", _DENMARK_DIRECTORY, 0.8, directory=True)

    policy_only_answer = "Only persons who are 18 years or older may sign an FBO agreement."
    assert "SE" not in {country for country, _section in _citations(policy_only_answer, [foreign, directory], "DK")}

    cited = _citations(_AGE_ANSWER_WITH_CONTACTS, [foreign, directory], "DK")
    assert cited == [("GLOBAL", "sponsoring-dk")]


def test_requested_sponsoring_directory_answer_still_cites_the_directory() -> None:
    """A Norwegian reader asking about Germany is answered from Germany's directory record."""
    local = _doc("NO:3.01", "NO", "3.01",
                 "Section 3.01: A new FBO must place an order of 50 products within 2 months.", 0.9)
    directory = _doc("GLOBAL:sponsoring-de", "GLOBAL", "sponsoring-de", _GERMANY_DIRECTORY, 0.8, directory=True)
    answer = ("Forever Germany's minimum order for an FBO is 50,00 in products and delivery costs 5,00 per order. "
              "Orders: +49 6131 8999 0.")
    assert _citations(answer, [local, directory], "NO") == [("GLOBAL", "sponsoring-de")]


@pytest.mark.xfail(strict=True, reason=f"{_BELOW_FULL_ANSWER_GATE} (DE:9.02-b 0.2119)")
def test_multi_part_answer_cites_policy_and_directory_for_their_own_facts() -> None:
    policy = _doc("DE:9.02-b", "DE", "9.02-b",
                  "Section 9.02: b) Incentive trips must be completed within 12 months of qualifying.", 0.8,
                  parent="9.02")
    directory = _doc("GLOBAL:sponsoring-de", "GLOBAL", "sponsoring-de", _GERMANY_DIRECTORY, 0.9, directory=True)
    answer = ("Your trip has to be taken within 12 months. Forever Germany charges delivery of 5,00 per order; "
              "call +49 6131 8999 0 or email service@example.de.")
    cited = _citations(answer, [directory, policy], "DE")
    assert set(cited) == {("DE", "9.02"), ("GLOBAL", "sponsoring-de")}


def test_single_source_numeric_answer_keeps_its_one_citation() -> None:
    governing = _doc("DE:9.02-b", "DE", "9.02-b",
                     "Section 9.02: b) Incentive trips must be completed within 18 months of qualifying.", 0.9,
                     parent="9.02")
    nearby = _doc("DE:9.03", "DE", "9.03", "Section 9.03: Guests on incentive trips must be 18 or older.", 0.95)
    answer = "Incentive trips must be completed within 18 months of qualifying."
    assert _citations(answer, [nearby, governing], "DE") == [("DE", "9.02")]


def test_contact_only_answer_is_still_cited_to_the_directory_alone() -> None:
    policy = _doc("DE:2.01", "DE", "2.01", "Section 2.01: Sponsors must answer within 30 days on 49 topics.", 0.9)
    directory = _doc("GLOBAL:sponsoring-de", "GLOBAL", "sponsoring-de", _GERMANY_DIRECTORY, 0.8, directory=True)
    answer = "You can reach Forever Germany on +49 6131 8999 0 or by email at service@example.de."
    assert _citations(answer, [policy, directory], "DE") == [("GLOBAL", "sponsoring-de")]


# A shared figure is not a shared fact. Each answer below states a figure that
# an unrelated same-market passage also happens to print, next to a word that
# is not a unit (a year, "or", "per", a month) or in a clause about something
# else. fb22f38 cited the directory alone for every one of them; the policy
# addition must not invent a second citation.
_DENMARK_CONTACTS = "\nPhone: +45 70 20 30 40\nEmail: service@example.dk\nOpening hours: Mon-Fri 09.00-16.00"


def _denmark_directory():
    return _doc("GLOBAL:sponsoring-dk", "GLOBAL", "sponsoring-dk", _DENMARK_DIRECTORY, 0.8, directory=True)


def test_a_year_followed_by_a_short_word_does_not_bind_an_unrelated_section() -> None:
    unrelated = _doc("DK:1.02", "DK", "1.02",
                     "Section 1.02: In 2024 the company updated its code of conduct for every FBO.", 0.9)
    answer = "Since 2024 the delivery charge has been €18 per order." + _DENMARK_CONTACTS
    assert _citations(answer, [unrelated, _denmark_directory()], "DK") == [("GLOBAL", "sponsoring-dk")]


def test_or_after_the_figure_is_not_a_unit() -> None:
    unrelated = _doc("DK:9.03", "DK", "9.03",
                     "Section 9.03: Guests travelling on incentive trips must be 18 or more years old.", 0.9)
    answer = "The trip has to be taken within 18 or fewer months of qualifying." + _DENMARK_CONTACTS
    assert _citations(answer, [unrelated, _denmark_directory()], "DK") == [("GLOBAL", "sponsoring-dk")]


def test_per_after_the_figure_is_not_a_unit() -> None:
    unrelated = _doc("DK:4.01", "DK", "4.01",
                     "Section 4.01: Bonuses are paid at 18 per cent of personal case credits.", 0.9)
    answer = "Delivery is €18 per order below 2CC." + _DENMARK_CONTACTS
    assert _citations(answer, [unrelated, _denmark_directory()], "DK") == [("GLOBAL", "sponsoring-dk")]


def test_a_day_of_the_month_does_not_bind_an_unrelated_section() -> None:
    unrelated = _doc("DK:3.01", "DK", "3.01",
                     "Section 3.01: Bonus statements are issued on 1 January each year.", 0.9)
    answer = "Registration for the new period opens on 1 January; delivery is €18 per order." + _DENMARK_CONTACTS
    assert _citations(answer, [unrelated, _denmark_directory()], "DK") == [("GLOBAL", "sponsoring-dk")]


def test_the_same_figure_and_unit_in_an_unrelated_clause_is_not_cited() -> None:
    """The Norway termination clause says "over 18 år" too; it does not govern who may join."""
    termination = _doc("DK:16.02-fact-9", "DK", "16.02-fact-9",
                       "Section 16.02: Prohibited activities giving grounds for termination ... registered as FBO "
                       "and is over 18 years. That means it is not", 0.7, parent="16.02")
    cited = _citations(_AGE_ANSWER_WITH_CONTACTS, [termination, _denmark_directory()], "DK")
    assert cited == [("GLOBAL", "sponsoring-dk")]


def test_supported_policy_is_added_when_the_directory_repeats_its_figure_as_a_fee() -> None:
    """Held-out case 24 shape: the directory ranks first on contacts and prints "€18" as a delivery fee.

    fb22f38 saw every answer figure in the directory and cited it alone. The
    policy passage restating the joining age clears the full-answer gate here.
    """
    policy = _doc(
        "DK:5.01", "DK", "5.01",
        "Section 5.01: a) The relationship between the FBO and FLP is contractual. Only adult persons who are "
        "18 years or older may sign an agreement with FLP to register as an FBO. b) A registered FBO is an "
        "independent entrepreneur and must follow the Company Policy and Code of Conduct.", 0.85)
    answer = (
        "No, you cannot register as an FBO in Denmark yet. Only adult persons who are 18 years or older may sign "
        "an agreement to register as an FBO. You can contact Forever Denmark when you turn 18 years old."
        + _DENMARK_CONTACTS
    )
    assert _citations(answer, [policy, _denmark_directory()], "DK") == [("GLOBAL", "sponsoring-dk"), ("DK", "5.01")]


_LUXEMBOURG_DIRECTORY = (
    "Welcome to Forever Luxemburg!\n+352 2 786 1452\nBusiness Hours Office 09.00 am – 17.00 pm (Mon – Fri)\n"
    "Telephone Office +31 88 646 0200 (Reception, Netherlands)\nTelephone for Orders +352 2 786 1452 (Luxemburg for orders)\n"
    "Email support@example.nl\nWebsite example.com"
)
# The extraction wraps the clause mid-sentence, as the real LU:7.03-c row does.
_LUXEMBOURG_TRIP_CLAUSE = (
    "Section 7.03: a) Dans le cas où le partenaire d’un FBO ne peut pas participer à un voyage attribué, le FBO peut\n"
    "c) Les voyages Sapphire à Platinum Centurion doivent être effectués dans les 24 mois suivant la\nqualification."
)
_LUXEMBOURG_TRIP_ANSWER = (
    "Selon la politique Luxembourg, **les voyages Sapphire doivent être effectués dans les 24 mois suivant la "
    "qualification**.\n\nCela signifie que vous avez deux ans à compter de votre date de qualification pour organiser "
    "et réaliser votre voyage Sapphire.\n\nSi vous avez des questions sur les détails spécifiques de votre voyage ou "
    "sur les modalités de réservation, je vous recommande de contacter directement le bureau Forever Luxembourg :\n\n"
    "**Téléphone pour les commandes :** +352 2 786 1452 (Luxembourg)  \n**Email :** support@example.nl  \n"
    "**Site web :** example.com\n\nIls pourront vous aider à finaliser les arrangements de votre voyage."
)


def _luxembourg_documents():
    return [
        _doc("LU:7.03-c", "LU", "7.03-c", _LUXEMBOURG_TRIP_CLAUSE, 0.85, parent="7.03"),
        _doc("GLOBAL:sponsoring-lu", "GLOBAL", "sponsoring-lu", _LUXEMBOURG_DIRECTORY, 0.75, directory=True),
    ]


@pytest.mark.xfail(strict=True, reason=(
    "KNOWN GAP (not coverage): held-out case 19, LU:7.03-c 0.3322 below the 0.35 full-answer gate. "
    "Neither the contact-blanked gate nor a figure-sentence window gate is safe (measured 2026-09-11, "
    "handoff 2026-09-11_1625_ovn-w4-citation)"
))
def test_clause_restating_the_answers_figure_sentence_is_cited_below_the_full_answer_gate() -> None:
    """Held-out case 19 shape: the answer restates LU 7.03(c), then quotes the orders telephone.

    The phone number's digit groups hold the clause below the full-answer gate
    (0.3322 < 0.35), so the builder cites the directory alone. A gate scoring
    the sentence around "24 mois" would cite it, but on real extraction rows the
    same gate cited clauses about a different subject, so none is shipped.
    """
    builder = ResponseBuilder()
    clause = _luxembourg_documents()[0]
    assert builder._support_score(_LUXEMBOURG_TRIP_ANSWER, clause.content) < 0.35
    cited = _citations(_LUXEMBOURG_TRIP_ANSWER, _luxembourg_documents(), "LU")
    assert cited == [("GLOBAL", "sponsoring-lu"), ("LU", "7.03")]


@pytest.mark.parametrize("country", ["NO", "BE", "", "GLOBAL"])
def test_case_19_clause_is_never_cited_for_another_or_an_unknown_market(country) -> None:
    assert _citations(_LUXEMBOURG_TRIP_ANSWER, _luxembourg_documents(), country) == [("GLOBAL", "sponsoring-lu")]


# Shapes on which the contact-blanked gate added a false second citation
# (Fable, 2026-09-11). Each shares the figure, its unit and one or two topic
# words with an unrelated clause. They pin that no looser gate is in use.
_BLANKED_GATE_UNSAFE_SHAPES = {
    "N1 18 days notice": (
        "Section 16.03: Returns. Products may be returned for a refund. An FBO who resigns must give 18 days notice "
        "before the returns of products are processed by the office.",
        "Returns are refunded within 18 days of receipt of the products.",
    ),
    "N4b 24 months warranty": (
        "Section 7.02: Product warranty is 24 months from the qualification of the trip supplier.",
        "Your incentive trip must be completed within 18–24 months of qualification.",
    ),
    "N5b 30% restocking": (
        "Section 4.04: Returned product orders are refunded less a 30% restocking charge for customers.",
        "Preferred Customers receive a 30% discount on all product orders.",
    ),
    "N7b 4 CC orders": (
        "Section 5.04: Orders of 4 CC ship free; 2 months of statements are kept.",
        "To qualify you need 4 CC within 2 consecutive months of orders.",
    ),
    "N14 short sentence": (
        "Section 12.01: Sponsors of new FBOs receive 24 months of training material.",
        "FBOs must take the trip within 24 months.",
    ),
}


@pytest.mark.parametrize("shape", sorted(_BLANKED_GATE_UNSAFE_SHAPES))
def test_no_looser_gate_admits_the_shapes_the_blanked_gate_admitted(shape) -> None:
    clause, answer = _BLANKED_GATE_UNSAFE_SHAPES[shape]
    unrelated = _doc("DK:9.99", "DK", "9.99", clause, 0.9)
    assert _citations(answer + _DENMARK_CONTACTS, [unrelated, _denmark_directory()], "DK") == [
        ("GLOBAL", "sponsoring-dk")
    ]


@pytest.mark.parametrize("country", ["", "GLOBAL", None])
def test_no_policy_is_added_when_the_reader_market_is_unknown(country) -> None:
    """Without a known market the own-market filter is off, so nothing may be added on top of fb22f38."""
    policy = _doc("DK:5.01-a", "DK", "5.01-a", _DENMARK_AGE_POLICY, 0.9, parent="5.01")
    cited = _citations(_AGE_ANSWER_WITH_CONTACTS, [policy, _denmark_directory()], country)
    assert cited == [("GLOBAL", "sponsoring-dk")]
