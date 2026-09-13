"""Unit tests for the response pipeline."""

from app.models.responses import ModelResponse
from app.response import ResponseBuilder
from app.retrieval import RetrievedDocument, RetrievalResult


def test_explicit_approved_non_numeric_rule_is_not_dropped_for_numeric_answer():
    documents = [
        RetrievedDocument(id='activity', title='Activity', content='You need 4 Active Case Credits.',
                          source='s3://kb/activity', page='1'),
        RetrievedDocument(id='rank', title='Rank', content='Rank is retained unless terminated.',
                          source='s3://kb/rank', page='2'),
        RetrievedDocument(id='noise', title='Noise', content='Unrelated bonus rules.', source='s3://kb/noise'),
    ]
    result = RetrievalResult(documents, [], 0.9, metadata={'evidence_decision': {'approved': True}})
    answer = 'You need 4 Active Case Credits [Source 1]. Rank is retained unless terminated [rank].'
    citations = ResponseBuilder()._supporting_citations(answer, result)
    assert [citation['uri'] for citation in citations] == ['s3://kb/activity', 's3://kb/rank']


def test_unknown_or_linked_markers_do_not_invent_citation_sources():
    doc = RetrievedDocument(id='rank', title='Rank', content='Retained rank.', source='s3://kb/rank')
    result = RetrievalResult([doc], [], 0.9, metadata={'evidence_decision': {'approved': True}})
    answer = 'Unsupported unrelated 999 [Source 99] [missing] [rank](https://outside.example).'
    assert ResponseBuilder()._supporting_citations(answer, result) == []


def test_response_builder_preserves_existing_api_shape() -> None:
    """ChatResponse converts back to the current widget payload."""
    retrieval_result = RetrievalResult(
        documents=[
            RetrievedDocument(
                id="doc",
                title="Policy",
                content="Policy content",
                source="s3://kb/policy.pdf",
                excerpt="Policy content",
                score=0.91,
            )
        ],
        citations=[],
        confidence=0.91,
    )
    model_response = ModelResponse(
        text="Policy content",
        citations=retrieval_result.sources,
        confidence=0.91,
        provider="claude",
        model_name="model",
        latency_ms=123,
        metadata={"prompt_version": "v1"},
    )

    chat_response = ResponseBuilder().build(
        model_response=model_response,
        retrieval_result=retrieval_result,
        correlation_id="cid",
        session_metadata={"cache": "miss"},
    )

    assert chat_response.to_api_result() == {
        "response": "Policy content",
        "sources": retrieval_result.sources,
        "confidence": 0.91,
        "correlationId": "cid",
        "metadata": {"cacheSource": "fresh"},
    }
    assert chat_response.metadata["provider"] == "claude"
    assert chat_response.metadata["retrieved_document_count"] == 1
    assert chat_response.metadata["cache"] == "miss"


def test_cached_response_exposes_safe_cache_source() -> None:
    """QA can distinguish exact and semantic hits without seeing cache internals."""
    chat_response = ResponseBuilder().from_cached(
        {"response": "Approved answer", "sources": [], "confidence": 0.9},
        "cid",
    )
    chat_response = type(chat_response)(
        **{**chat_response.__dict__, "metadata": {**chat_response.metadata, "cache": "semantic"}}
    )

    assert chat_response.to_api_result()["metadata"]["cacheSource"] == "semantic"


def test_response_builder_prefers_answer_supporting_references() -> None:
    """References shown to users should be supporting evidence, not raw search dumps."""
    retrieval_result = RetrievalResult(
        documents=[
            RetrievedDocument(
                id="relevant",
                title="CA-EN-Company-Policy.pdf",
                content=(
                    "Assistant Supervisor is achieved by generating a total of "
                    "2 Open Group Case Credits in any single Operating Company "
                    "within any 2 consecutive Months."
                ),
                source="s3://kb/policy.pdf",
                excerpt="Assistant Supervisor is achieved by generating 2 Open Group Case Credits.",
                page="6",
                score=0.72,
            ),
            RetrievedDocument(
                id="noise",
                title="CA-EN-Company-Policy.pdf",
                content="Leadership Bonus requirements for unrelated incentives are listed in this section.",
                source="s3://kb/policy.pdf",
                excerpt="Leadership Bonus requirements for unrelated incentives.",
                page="26",
                score=0.9,
            ),
        ],
        citations=[],
        confidence=0.72,
    )
    model_response = ModelResponse(
        text="To become an Assistant Supervisor, you need 2 Open Group Case Credits within any 2 consecutive months.",
        citations=retrieval_result.sources,
        confidence=0.72,
        provider="claude",
        model_name="model",
    )

    chat_response = ResponseBuilder().build(
        model_response=model_response,
        retrieval_result=retrieval_result,
        correlation_id="cid",
    )

    assert chat_response.citations[0]["page"] == "6"
    assert "2 Open Group Case Credits" in chat_response.citations[0]["excerpt"]


def test_response_builder_filters_numeric_references_without_matching_values() -> None:
    """Numeric answers should not show unrelated references with different numbers."""
    retrieval_result = RetrievalResult(
        documents=[
            RetrievedDocument(
                id="relevant",
                title="CA-EN-Company-Policy.pdf",
                content=(
                    "An FBO reaches the level of Assistant Supervisor by generating a total of "
                    "2 Open Group Case Credits in any single Operating Company within any "
                    "2 consecutive Months."
                ),
                source="s3://kb/policy.pdf",
                excerpt="Assistant Supervisor requirement",
                page="6",
                score=0.72,
            ),
            RetrievedDocument(
                id="noise",
                title="CA-EN-Company-Policy.pdf",
                content="Chairman's Bonus Manager qualification requires 700 Open Group Case Credits.",
                source="s3://kb/policy.pdf",
                excerpt="Chairman's Bonus Manager qualification",
                page="26",
                score=0.93,
            ),
        ],
        citations=[],
        confidence=0.72,
    )
    model_response = ModelResponse(
        text="To become an Assistant Supervisor, you need 2 Open Group Case Credits within any 2 consecutive months.",
        citations=retrieval_result.sources,
        confidence=0.72,
        provider="claude",
        model_name="model",
    )

    chat_response = ResponseBuilder().build(
        model_response=model_response,
        retrieval_result=retrieval_result,
        correlation_id="cid",
    )

    assert [citation["page"] for citation in chat_response.citations] == ["6"]


def test_response_builder_does_not_attach_policy_sources_to_guardrail_copy() -> None:
    """Safety interventions must not make unrelated retrieval look like evidence."""
    document = RetrievedDocument(
        id="unrelated-policy",
        title="Policy - Sec 8.08: Sapphire Manager",
        content="Sapphire Manager qualification requirements.",
        source="s3://kb/policy.pdf",
        score=0.9,
    )
    response = ResponseBuilder().build(
        model_response=ModelResponse(
            text="I cannot provide medical advice.",
            citations=[document.to_source()],
            confidence=0.9,
            provider="claude",
            model_name="model",
            finish_reason="guardrail_intervened",
        ),
        retrieval_result=RetrievalResult(documents=[document], citations=[], confidence=0.9),
        correlation_id="cid",
    )

    assert response.citations == []
    assert response.metadata["failure_layer"] == "aws_guardrail"
    assert response.metadata["response_source"] == "guardrail"


def test_response_builder_does_not_attach_an_unrelated_source() -> None:
    """No reference is safer than displaying a policy section that does not support the reply."""
    document = RetrievedDocument(
        id="unrelated",
        title="Policy - Sec 8.08: Sapphire Manager",
        content="Sapphire Manager recognition requirements.",
        source="s3://kb/policy.pdf",
        score=0.9,
    )
    response = ResponseBuilder().build(
        model_response=ModelResponse(
            text="Please contact support for help with your account.",
            citations=[document.to_source()],
            confidence=0.9,
            provider="claude",
            model_name="model",
        ),
        retrieval_result=RetrievalResult(documents=[document], citations=[], confidence=0.9),
        correlation_id="cid",
    )

    assert response.citations == []


def _section_doc(doc_id, country, section, content, score, parent=""):
    return RetrievedDocument(
        id=doc_id, title=f"{country} {section}", content=content, source=f"s3://kb/{doc_id}",
        country=country, score=score, metadata={"section_id": section, "parent_section_id": parent},
    )


_GERMANY_DIRECTORY = (
    "Welcome to Forever Germany!\nTelephone for Orders +49 6131 8999 0\n"
    "Email service@example.de\nMinimum order size FBO: 50,00 in products.\n"
    "Delivery Cost: 5,00 per order."
)


def test_numeric_answer_cites_policy_figure_alongside_directory_contact() -> None:
    """A phone number must not crowd out the passage carrying the requested figure.

    Every digit group of "+49 6131 8999 0" counts as a figure, so the directory
    record outranked the policy passage and the single numeric citation dropped it.
    """
    policy = _section_doc("DE:9.02-b", "DE", "9.02-b",
                          "Section 9.02: b) Incentive trips must be completed within 18 months of qualifying.",
                          0.93, parent="9.02")
    directory = _section_doc("GLOBAL:sponsoring-de", "GLOBAL", "sponsoring-de", _GERMANY_DIRECTORY, 0.81)
    answer = ("Incentive trips must be completed within 18 months of qualifying. For booking questions, "
              "call Forever Germany on +49 6131 8999 0 or email service@example.de.")
    citations = ResponseBuilder()._supporting_citations(answer, RetrievalResult([policy, directory], [], 0.9))
    assert {citation["section"] for citation in citations} == {"9.02", "sponsoring-de"}


def test_non_english_numeric_answer_keeps_policy_citation_next_to_contact() -> None:
    policy = _section_doc("NL:6.04-a", "NL", "6.04-a",
                          "Sectie 6.04: a) Een reis moet binnen 12 maanden na kwalificatie worden gemaakt.",
                          0.9, parent="6.04")
    directory = _section_doc("GLOBAL:sponsoring-nl", "GLOBAL", "sponsoring-nl",
                             "Welcome to Forever Netherlands!\nTelephone Office +31 55 123 4567", 0.85)
    answer = "Je reis moet binnen 12 maanden na kwalificatie worden gemaakt. Bel gerust +31 55 123 4567."
    citations = ResponseBuilder()._supporting_citations(answer, RetrievalResult([directory, policy], [], 0.9))
    # Whichever source ranks second used to be dropped; both figures need their own.
    assert sorted(citation["section"] for citation in citations) == ["6.04", "sponsoring-nl"]


def test_directory_fact_answer_still_cites_only_the_directory_record() -> None:
    policy = _section_doc("DE:3.01", "DE", "3.01",
                          "Section 3.01: An FBO needs 4 Active Case Credits and orders of 50 products.", 0.9)
    directory = _section_doc("GLOBAL:sponsoring-de", "GLOBAL", "sponsoring-de", _GERMANY_DIRECTORY, 0.8)
    answer = ("Forever Germany's FBO minimum order is 50,00 in products and delivery costs 5,00 per order. "
              "Orders: +49 6131 8999 0.")
    citations = ResponseBuilder()._supporting_citations(answer, RetrievalResult([policy, directory], [], 0.9))
    assert [citation["section"] for citation in citations] == ["sponsoring-de"]


def test_single_source_numeric_answer_keeps_one_citation() -> None:
    governing = _section_doc("DE:9.02-b", "DE", "9.02-b",
                             "Section 9.02: b) Incentive trips must be completed within 18 months of qualifying.",
                             0.9, parent="9.02")
    nearby = _section_doc("DE:9.03", "DE", "9.03",
                          "Section 9.03: Guests on incentive trips must be 18 or older.", 0.95)
    answer = "Incentive trips must be completed within 18 months of qualifying."
    citations = ResponseBuilder()._supporting_citations(answer, RetrievalResult([nearby, governing], [], 0.9))
    assert [citation["section"] for citation in citations] == ["9.02"]


def test_second_numeric_citation_never_reaches_another_markets_policy() -> None:
    own = _section_doc("DE:4.01", "DE", "4.01", "Section 4.01: Bonuses are paid monthly by bank transfer.", 0.9)
    foreign = _section_doc("AT:9.02-b", "AT", "9.02-b",
                           "Section 9.02: b) Incentive trips must be completed within 18 months of qualifying.",
                           0.7, parent="9.02")
    directory = _section_doc("GLOBAL:sponsoring-de", "GLOBAL", "sponsoring-de", _GERMANY_DIRECTORY, 0.8)
    answer = ("Incentive trips must be completed within 18 months of qualifying. "
              "Call Forever Germany on +49 6131 8999 0.")
    citations = ResponseBuilder()._supporting_citations(
        answer, RetrievalResult([own, foreign, directory], [], 0.9)
    )
    assert "AT" not in {citation["country"] for citation in citations}
    assert [citation["section"] for citation in citations] == ["sponsoring-de"]


def test_verified_evidence_citation_survives_cross_language_answer() -> None:
    """Claim-verified evidence must not be dropped by language-sensitive token overlap."""
    document = RetrievedDocument(
        id="manager-requalification",
        title="Company Policy - Sec 4.02: Manager Requalification",
        content="A Manager may requalify under the conditions stated in this section.",
        source="s3://kb/policy.pdf",
        page="19",
        metadata={"section_id": "4.02", "section_title": "Manager Requalification"},
    )
    retrieval_result = RetrievalResult(
        documents=[document],
        citations=[document.to_source()],
        confidence=0.9,
        metadata={
            "evidence_contract": {
                "status": "accepted",
                "evidence_ids": ["manager-requalification"],
            }
        },
    )
    response = ResponseBuilder().build(
        model_response=ModelResponse(
            text="Een Manager kan zich opnieuw kwalificeren volgens de voorwaarden in dit onderdeel.",
            citations=[],
            confidence=0.9,
            provider="claude",
            model_name="model",
        ),
        retrieval_result=retrieval_result,
        correlation_id="cid",
    )
    assert len(response.citations) == 1
    assert response.citations[0]["section"] == "4.02"
    assert response.citations[0]["page"] == "19"
