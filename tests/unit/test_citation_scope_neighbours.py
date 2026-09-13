"""Neighbour checks for citation scope.

Covers market isolation, directory answers, refusals, unsupported answers and
parent/child passages. The tests report citation *presence* separately from
*governing support*: whether a cited source actually states the answer's figure
with its unit.
"""

from app.evidence import approve_evidence
from app.response import ResponseBuilder
from app.retrieval import RetrievedDocument, RetrievalResult
from app.validation.validators.numeric_grounding_validator import remove_unsupported_numeric_sentences


def _doc(doc_id, country, section, content, score, parent="", directory=False, language="en", **metadata):
    fields = {"section_id": section, "parent_section_id": parent, **metadata}
    if directory:
        fields.update({"directory_section": "sponsoring", "directory_kind": "international_sponsoring"})
    return RetrievedDocument(
        id=doc_id, title=f"{country} {section}", content=content, source=f"s3://kb/{doc_id}",
        country=country, language=language, score=score, metadata=fields,
    )


def _cited(answer, documents, country):
    """(presence, documents): the citations shown, and the retrieved documents behind them."""
    citations = ResponseBuilder()._supporting_citations(
        answer, RetrievalResult(documents, [], 0.9), session_country=country
    )
    by_uri = {document.source: document for document in documents}
    return [(c.get("country"), c.get("section")) for c in citations], [by_uri[c["uri"]] for c in citations]


def _governing_support(answer, cited_documents):
    """For each figure the answer states with a unit (outside contact details), whether a cited source states it."""
    builder = ResponseBuilder()
    figures = [figure for figure in builder._figure_occurrences(answer, skip_contacts=True) if figure[1] or figure[2]]
    return [
        any(builder._covers_figure(builder._figure_occurrences(document.content), figure) for document in cited_documents)
        for figure in figures
    ]


_LU_DIRECTORY = (
    "Welcome to Forever Luxemburg!\n+352 2 786 1452\nBusiness Hours Office 09.00 am – 17.00 pm (Mon – Fri)\n"
    "Telephone Office +31 88 646 0200 (Reception, Netherlands)\nTelephone for Orders +352 2 786 1452 (Luxemburg for orders)\n"
    "Email support@example.nl\nWebsite example.com"
)
_LU_CLAUSE = (
    "Section 7.03: a) Dans le cas où le partenaire d’un FBO ne peut pas participer à un voyage attribué, le FBO peut\n"
    "c) Les voyages Sapphire à Platinum Centurion doivent être effectués dans les 24 mois suivant la\nqualification."
)
_LU_PARENT = (
    "7.03 a) Un invité doit avoir 14 ans ou plus.\n"
    "c) Les voyages Sapphire à Platinum Centurion doivent être effectués dans les 24 mois suivant la\nqualification."
)
_LU_ANSWER = (
    "Selon la politique Luxembourg, **les voyages Sapphire doivent être effectués dans les 24 mois suivant la "
    "qualification**.\n\nCela signifie que vous avez deux ans à compter de votre date de qualification pour organiser "
    "et réaliser votre voyage Sapphire.\n\nSi vous avez des questions sur les détails spécifiques de votre voyage ou "
    "sur les modalités de réservation, je vous recommande de contacter directement le bureau Forever Luxembourg :\n\n"
    "**Téléphone pour les commandes :** +352 2 786 1452 (Luxembourg)  \n**Email :** support@example.nl  \n"
    "**Site web :** example.com\n\nIls pourront vous aider à finaliser les arrangements de votre voyage."
)


def _lu_directory():
    return _doc("GLOBAL:sponsoring-lu", "GLOBAL", "sponsoring-lu", _LU_DIRECTORY, 0.75, directory=True)


def _lu_clause():
    return _doc("LU:7.03-c", "LU", "7.03-c", _LU_CLAUSE, 0.85, parent="7.03", language="fr")


_DK_DIRECTORY = (
    "Welcome to Forever Denmark!\n+45 70 20 30 40\nDelivery Cost: under 2CC - €18 ex VAT per order.\n"
    "Business Hours Office 09.00 am - 16.00 pm (Mon - Fri)\nTelephone Office +45 70 20 30 40\nEmail service@example.dk"
)
_DK_AGE_PARENT = (
    "Section 5.01: a) The relationship between the FBO and FLP is contractual. Only adult persons who are "
    "18 years or older may sign an agreement with FLP to register as an FBO. b) A registered FBO is an "
    "independent entrepreneur and must follow the Company Policy and Code of Conduct."
)
_DK_AGE_ANSWER = (
    "No, you cannot register as an FBO in Denmark yet. Only adult persons who are 18 years or older may sign "
    "an agreement to register as an FBO. You can contact Forever Denmark when you turn 18 years old.\n"
    "Phone: +45 70 20 30 40\nEmail: service@example.dk\nOpening hours: Mon-Fri 09.00-16.00"
)


def _dk_directory():
    return _doc("GLOBAL:sponsoring-dk", "GLOBAL", "sponsoring-dk", _DK_DIRECTORY, 0.8, directory=True)


def test_mixed_policy_and_directory_answer_cites_both_and_the_policy_governs_the_figure() -> None:
    policy = _doc("DK:5.01", "DK", "5.01", _DK_AGE_PARENT, 0.85)
    presence, documents = _cited(_DK_AGE_ANSWER, [policy, _dk_directory()], "DK")
    assert presence == [("GLOBAL", "sponsoring-dk"), ("DK", "5.01")]
    assert all(_governing_support(_DK_AGE_ANSWER, documents))
    # The directory alone is present but does not govern "18 years" (it prints "€18" as a fee).
    assert not any(_governing_support(_DK_AGE_ANSWER, [_dk_directory()]))


def test_case_19_shape_shows_presence_without_governing_support() -> None:
    """Known gap, reported as a measurement: the directory is cited, the deadline clause is not."""
    presence, documents = _cited(_LU_ANSWER, [_lu_clause(), _lu_directory()], "LU")
    assert presence == [("GLOBAL", "sponsoring-lu")]
    assert _governing_support(_LU_ANSWER, documents) == [False]


def test_a_directory_citation_is_not_governing_support_for_a_policy_figure() -> None:
    """The Denmark directory prints "€18" as a delivery fee; it does not state an age limit of 18 years."""
    directory = _doc("GLOBAL:sponsoring-dk", "GLOBAL", "sponsoring-dk",
                     "Welcome to Forever Denmark!\n+45 70 20 30 40\nDelivery Cost: under 2CC - €18 ex VAT per order.\n"
                     "Telephone Office +45 70 20 30 40\nEmail service@example.dk", 0.8, directory=True)
    termination = _doc("DK:16.02-fact-9", "DK", "16.02-fact-9",
                       "Section 16.02: Prohibited activities giving grounds for termination ... registered as FBO "
                       "and is over 18 years. That means it is not", 0.7, parent="16.02")
    answer = ("No, you cannot sign up as an FBO yet. You can contact Forever Denmark when you turn 18 years old.\n"
              "Phone: +45 70 20 30 40\nEmail: service@example.dk")
    presence, documents = _cited(answer, [termination, directory], "DK")
    assert presence == [("GLOBAL", "sponsoring-dk")]
    assert _governing_support(answer, documents) == [False]


def test_another_markets_policy_answer_is_not_cited_in_a_different_session() -> None:
    for session in ("NO", "BE", ""):
        presence, _documents = _cited(_LU_ANSWER, [_lu_clause(), _lu_directory()], session)
        assert presence == [("GLOBAL", "sponsoring-lu")], session


def test_cross_market_company_policy_request_is_refused_before_generation() -> None:
    italy = _doc("IT:4.01", "IT", "4.01", "Sezione 4.01: La commissione del promotore è del 5%.", 0.9, status="active")
    austria = _doc("AT:4.01", "AT", "4.01", "Section 4.01: The sponsor bonus is 5%.", 0.8, status="active")
    decision = approve_evidence(
        "What does the Italy company policy say about promoter commission?",
        RetrievalResult([italy, austria], [], 0.9), "AT", "en",
    )
    assert (decision.approved, decision.reason, decision.evidence) == (False, "cross_market_policy_request", [])


def test_a_refusal_with_foreign_policy_retrieved_cites_nothing() -> None:
    italy = _doc("IT:4.01", "IT", "4.01", "Section 4.01: The promoter commission in Italy is 5% of sales.", 0.9)
    refusal = ("I can only answer from the company policy for Austria. The Italian promoter commission is not part "
               "of the Austrian company policy.")
    numeric = "The promoter commission in Italy is 5% of sales."
    assert _cited(refusal, [italy], "AT")[0] == []
    assert _cited(numeric, [italy], "AT")[0] == []


def test_an_unsupported_answer_gets_no_policy_citation() -> None:
    policy = _doc("DK:6.02-c", "DK", "6.02-c",
                  "Section 6.02: c) Incentive trips must be taken within 24 months of qualifying.", 0.9, parent="6.02")
    assert _cited("Incentive trips must be taken within 36 months of qualifying.", [policy], "DK")[0] == []
    assert _cited("Our product catalogue is refreshed every spring with new flavours.", [policy], "DK")[0] == []


def test_a_parent_passage_stating_the_figure_is_not_joined_by_its_child() -> None:
    parent = _doc("LU:7.03", "LU", "7.03", _LU_PARENT, 0.9, language="fr")
    answer = "Les voyages Sapphire à Platinum Centurion doivent être effectués dans les 24 mois suivant la qualification."
    presence, documents = _cited(answer, [parent, _lu_clause()], "LU")
    assert [document.id for document in documents] == ["LU:7.03"]
    assert presence == [("LU", "7.03")]
    assert _governing_support(answer, documents) == [True]


def test_parent_and_child_are_never_both_cited_next_to_the_directory() -> None:
    parent = _doc("DK:5.01", "DK", "5.01", _DK_AGE_PARENT, 0.85)
    child = _doc("DK:5.01-a", "DK", "5.01-a",
                 "Section 5.01: a) The relationship between the FBO and FLP is contractual. Only adult persons who "
                 "are 18 years or older may sign an agreement with FLP to register as an FBO.", 0.84, parent="5.01")
    presence, documents = _cited(_DK_AGE_ANSWER, [parent, child, _dk_directory()], "DK")
    assert len(documents) == 2
    assert {document.id for document in documents} != {"DK:5.01", "DK:5.01-a"}
    assert presence == [("GLOBAL", "sponsoring-dk"), ("DK", "5.01")]
    assert all(_governing_support(_DK_AGE_ANSWER, documents))


def test_directory_contact_digits_do_not_crowd_out_a_supported_policy_citation_in_a_known_session() -> None:
    policy = _doc("DE:9.02-b", "DE", "9.02-b",
                  "Section 9.02: b) Incentive trips must be completed within 18 months of qualifying.", 0.7,
                  parent="9.02")
    directory = _doc("GLOBAL:sponsoring-de", "GLOBAL", "sponsoring-de",
                     "Welcome to Forever Germany!\nTelephone for Orders +49 6131 8999 0\nEmail service@example.de\n"
                     "Delivery Cost: 5,00 per order.", 0.9, directory=True)
    answer = ("Incentive trips must be completed within 18 months of qualifying. For booking questions, "
              "call Forever Germany on +49 6131 8999 0 or email service@example.de.")
    presence, documents = _cited(answer, [directory, policy], "DE")
    assert set(presence) == {("DE", "9.02"), ("GLOBAL", "sponsoring-de")}
    assert _governing_support(answer, documents) == [True]


def test_sponsoring_directory_answer_keeps_its_citation_after_repair_in_another_session() -> None:
    """A Norwegian reader asking about Germany: repair removes an invented figure, the directory stays cited."""
    local = _doc("NO:3.01", "NO", "3.01", "Section 3.01: A new FBO must place an order of 50 products within 2 months.", 0.9)
    directory = _doc("GLOBAL:sponsoring-de", "GLOBAL", "sponsoring-de",
                     "Welcome to Forever Germany!\nTelephone for Orders +49 6131 8999 0\nEmail service@example.de\n"
                     "Minimum order size FBO: 50,00 in products.\nDelivery Cost: 5,00 per order.", 0.8, directory=True)
    built_answer = ("Forever Germany's minimum order for an FBO is 50,00 in products and delivery costs 5,00 per order. "
                    "Orders: +49 6131 8999 0.\nExpress delivery costs 17,50 extra.")
    documents = [local, directory]
    delivered = remove_unsupported_numeric_sentences(built_answer, documents)[0]
    assert "17,50" not in delivered

    builder = ResponseBuilder()
    result = RetrievalResult(documents, [], 0.9)
    built = builder._supporting_citations(built_answer, result, session_country="NO")
    reconciled = builder.reconcile_citations(
        built_answer=built_answer, delivered_answer=delivered, citations=built,
        retrieval_result=result, session_country="NO",
    )
    assert [(c["country"], c["section"]) for c in reconciled] == [("GLOBAL", "sponsoring-de")]
