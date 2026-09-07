from dataclasses import replace
import hashlib

import pytest

from app.retrieval.models import RetrievedDocument
from app.retrieval.structural_selection import document_sources, select_bound_documents


def document(country="CA", **metadata):
    content = "To be considered Active, an FBO must qualify monthly."
    return RetrievedDocument(id="section-id", title="Policy", content=content, source="s3://approved/policy.pdf",
                             country=country, language="en", score=0.35, metadata={
                                 "logical_document_id": "canada-policy", "ingestion_id": "published-1",
                                 "section_id": "4.03", "section_title": "Activity Qualification",
                                 "content_hash": hashlib.sha256(content.encode()).hexdigest(), "status": "active",
                                 "access_scope": "country", "document_type": "policy", **metadata})


def payload(documents):
    sources = document_sources(documents, country="CA", active_ingestion_ids={"published-1"})
    return {"decision": "ANSWER_FACT", "draft_answer": "Qualify monthly.", "missing_facts": [], "confidence": 0.95,
            "support": [{"source_id": source.binding_id, "quote": source.content} for source in sources]}


def test_bridge_preserves_scores_and_does_not_mark_answer_approved():
    doc = document(evidence_selector_directly_answers=False)
    selected = select_bound_documents(payload([doc]), [doc], question="How do I become Active?", country="CA",
                                      language="en", active_ingestion_ids={"published-1"})
    assert selected.documents == (doc,)
    assert selected.documents[0] is doc
    assert selected.documents[0].score == 0.35
    assert selected.documents[0].metadata["evidence_selector_directly_answers"] is False
    assert "approved" not in selected.documents[0].metadata


@pytest.mark.parametrize("metadata", [
    {"ingestion_id": "old"}, {"ingestion_id": None}, {"logical_document_id": 12},
    {"content_hash": "wrong"}, {"content_hash": None}, {"status": "retired"},
    {"section_id": ""}, {"access_scope": "unknown"}, {"document_type": "unknown"},
])
def test_invalid_provenance_rejected(metadata):
    with pytest.raises(ValueError):
        document_sources([document(**metadata)], country="CA", active_ingestion_ids={"published-1"})


def test_foreign_policy_cannot_be_authorized_by_model_or_global_flag():
    with pytest.raises(ValueError, match="Foreign"):
        document_sources([document(country="BE")], country="US", active_ingestion_ids={"published-1"},
                         allow_global_sponsoring=True)


def test_global_sponsoring_allowed_across_selected_markets_only_when_authorized():
    doc = document(country="GLOBAL", access_scope="global", document_type="office_directory",
                   directory_kind="international_sponsoring", record_country="Belgium")
    assert document_sources([doc], country="US", active_ingestion_ids={"published-1"}, allow_global_sponsoring=True)
    with pytest.raises(ValueError):
        document_sources([doc], country="US", active_ingestion_ids={"published-1"})
    wrong = replace(doc, metadata={**doc.metadata, "directory_kind": "office"})
    with pytest.raises(ValueError):
        document_sources([wrong], country="US", active_ingestion_ids={"published-1"}, allow_global_sponsoring=True)


def test_changed_generation_cannot_reuse_old_support():
    doc = document()
    old = payload([doc])
    updated = replace(doc, metadata={**doc.metadata, "ingestion_id": "published-2"})
    with pytest.raises(ValueError, match="Unknown or stale"):
        select_bound_documents(old, [updated], question="Active?", country="CA", language="en",
                               active_ingestion_ids={"published-2"})


def test_abstention_returns_no_documents_even_if_candidates_exist():
    abstention = {"decision": "INSUFFICIENT_EVIDENCE", "draft_answer": "", "missing_facts": ["rule"],
                  "support": [], "confidence": 0.9}
    assert not select_bound_documents(abstention, [document()], question="Unknown?", country="CA", language="en",
                                      active_ingestion_ids={"published-1"}).documents


def test_duplicate_document_identity_rejected():
    doc = document()
    with pytest.raises(ValueError, match="duplicate"):
        document_sources([doc, doc], country="CA", active_ingestion_ids={"published-1"})


def test_canonical_s3_identity_fallback_still_binds_generation_and_content():
    doc = document(logical_document_id="")
    source = document_sources([doc], country="CA", active_ingestion_ids={"published-1"})[0]
    assert source.document_id == doc.source
    assert source.generation_id == "published-1"
    assert source.content == doc.content


@pytest.mark.parametrize("uri", ["", "opensearch-section://file/section", "s3://bucket/", "s3://bucket/a?token=x"])
def test_temporary_or_missing_document_identity_rejected(uri):
    doc = replace(document(logical_document_id=""), source=uri)
    with pytest.raises(ValueError, match="stable document identity"):
        document_sources([doc], country="CA", active_ingestion_ids={"published-1"})
