"""The primary citation of a contract-verified answer is the passage that supports it.

Tracker row 24 (Sweden, screenshot image11): "If I stop being an FBO, will the
company buy back my leftover stock?" was answered with the 12-month buy-back
rule of section 21.05, but the widget's PRIMARY SOURCE card was section 1.01,
the company introduction. When the evidence contract is accepted, the builder
cited the model's listed Source IDs in retrieval order, so whichever listed
passage ranked first led the cards. Contract-verified citations are still all
kept; only their order follows support. Section texts are short excerpts of the
approved SE-EN Company Policy extract.
"""

from app.models import ModelResponse
from app.response.builder import ResponseBuilder
from app.retrieval.models import RetrievedDocument, RetrievalResult

_INTRO = RetrievedDocument(
    id="SE|en|SE-EN-Company-Policy.pdf|1.01",
    title="SE-EN-Company-Policy.pdf",
    content="1.01 (a) Forever Living Products (FLP) is an international company that produces and markets "
            "exclusive health and beauty products worldwide through its unique concept that encourages and "
            "supports the use and sale of the products by independent Forever Business Owners (FBOs).",
    source="SE-EN-Company-Policy.pdf", page="3", country="SE", language="en", score=0.91,
    metadata={"section_id": "1.01"},
)
_BUYBACK = RetrievedDocument(
    id="SE|en|SE-EN-Company-Policy.pdf|21.05",
    title="SE-EN-Company-Policy.pdf",
    content="21.05 (a) FLP shall repurchase all unsold saleable FLP products with CC value, except literature, "
            "purchased directly from FLP during the previous twelve (12) months from the date of purchase by the "
            "FBO terminating its FBO activities. Repurchase shall be effected by the FBO terminating their "
            "activities first notifying the FLP in writing of their intention to terminate the FLP activities.",
    source="SE-EN-Company-Policy.pdf", page="50", country="SE", language="en", score=0.84,
    metadata={"section_id": "21.05"},
)
_PURPOSE = RetrievedDocument(
    id="SE|en|SE-EN-Company-Policy.pdf|21.06",
    title="SE-EN-Company-Policy.pdf",
    content="21.06 The purpose of the buy-back rule is to impose an obligation on the sponsor and the company to "
            "ensure that an FBO purchases products in the correct manner.",
    source="SE-EN-Company-Policy.pdf", page="50", country="SE", language="en", score=0.80,
    metadata={"section_id": "21.06"},
)
_ANSWER = (
    "Yes. If you stop being an FBO, FLP will repurchase all unsold saleable FLP products with CC value that you "
    "purchased directly from FLP during the previous twelve (12) months, except literature. You need to notify "
    "FLP in writing of your intention to terminate your FLP activities first."
)


def _cited_sections(documents, answer=_ANSWER, evidence_ids=None):
    ids = [document.id for document in documents] if evidence_ids is None else evidence_ids
    retrieval = RetrievalResult(
        documents=documents,
        citations=[document.to_source() for document in documents],
        confidence=0.9,
        metadata={"evidence_contract": {"status": "accepted", "evidence_ids": ids}},
    )
    response = ResponseBuilder().build(
        model_response=ModelResponse(text=answer, citations=[], confidence=0.9, provider="claude", model_name="model"),
        retrieval_result=retrieval,
        correlation_id="cid",
    )
    return [citation["section"] for citation in response.citations]


def test_governing_passage_is_primary_even_when_the_introduction_ranked_first():
    cited = _cited_sections([_INTRO, _BUYBACK, _PURPOSE])

    assert cited[0] == "21.05"


def test_every_contract_verified_citation_is_still_kept():
    assert sorted(_cited_sections([_INTRO, _BUYBACK, _PURPOSE])) == ["1.01", "21.05", "21.06"]


def test_order_is_unchanged_when_retrieval_already_ranked_the_governing_passage_first():
    assert _cited_sections([_BUYBACK, _PURPOSE, _INTRO])[0] == "21.05"


def test_a_single_verified_citation_in_another_language_is_kept():
    dutch = "Als je stopt als FBO, koopt FLP onverkochte producten terug die je in de afgelopen twaalf maanden kocht."

    assert _cited_sections([_BUYBACK], answer=dutch) == ["21.05"]
