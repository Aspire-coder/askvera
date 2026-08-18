from app.retrieval.models import RetrievedDocument
from app.retrieval.vnext_quality import (
    parse_vnext_evidence_contract,
    vnext_unsupported_numeric_claims,
)


def _document(identifier: str, content: str) -> RetrievedDocument:
    return RetrievedDocument(
        id=identifier,
        title="Policy",
        content=content,
        excerpt=content,
        source="policy.pdf",
        score=1.0,
    )


def test_vnext_numeric_check_accepts_exact_number_in_cited_evidence() -> None:
    documents = [_document("source-1", "Customers receive a 100% satisfaction guarantee.")]

    assert vnext_unsupported_numeric_claims(
        "Customers receive a 100% satisfaction guarantee.",
        "What is the return policy?",
        documents,
        ("source-1",),
    ) == []


def test_vnext_numeric_check_accepts_number_supplied_by_user() -> None:
    documents = [_document("source-1", "At least one personal Case Credit is required.")]

    assert vnext_unsupported_numeric_claims(
        "Your stated 0.5 CC does not meet the requirement.",
        "I have 0.5 CC. Am I active?",
        documents,
        ("source-1",),
    ) == []


def test_vnext_numeric_check_keeps_number_absent_from_cited_evidence() -> None:
    documents = [_document("source-1", "A minimum product order is required.")]

    unsupported = vnext_unsupported_numeric_claims(
        "The minimum order is 100 EUR.",
        "What is the minimum order?",
        documents,
        ("source-1",),
    )

    assert [claim.number for claim in unsupported] == ["100"]


def test_vnext_numeric_check_accepts_cited_time_separator_variant() -> None:
    documents = [_document("source-1", "Orders must arrive by 23.59 on the final day.")]

    assert vnext_unsupported_numeric_claims(
        "Orders must arrive by 23:59 on the final day.",
        "When is the deadline?",
        documents,
        ("source-1",),
    ) == []


def test_vnext_contract_repairs_german_smart_quote_pair_only() -> None:
    document = _document("source-1", "A manager must be active.")
    response = """{
      "status":"approved",
      "answer":"Ein Manager muss „aktiv\" sein.",
      "evidence_ids":["source-1"],
      "claims":[{"text":"Ein Manager muss „aktiv\" sein.","evidence_ids":["source-1"]}],
      "coverage":{"complete":true,"omitted_material_facts":[]}
    }"""

    result = parse_vnext_evidence_contract(response, [document])

    assert result.valid is True
