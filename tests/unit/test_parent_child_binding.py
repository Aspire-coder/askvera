from __future__ import annotations

from app.retrieval import opensearch_sections
from config import settings


def _row(identifier, content, chunk_type="section", **extra):
    return {
        "id": identifier, "section_id": identifier, "parent_section_id": "",
        "content": content, "chunk_type": chunk_type, "document_type": "policy",
        "access_scope": "country", "source_file": "norway.pdf", "country": "NO",
        "language": "en", **extra,
    }


def test_country_policy_parent_binds_unique_verbatim_child(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", True)
    parent = _row("17.08", "17.08 Voluntary resignation. (c) Reapply after one year.")
    parent["evidence_selector_selected"] = True
    child = _row("17.08-c", "Section 17.08: Voluntary resignation.\n(c) Reapply after one year.", "list_item", parent_section_id="17.08")
    result = opensearch_sections._bind_selected_parent_children([(parent, 1.0), (child, 0.9)])
    assert [row["id"] for row, _ in result] == ["17.08", "17.08-c"]
    assert result[1][0]["parent_bound_child"] is True


def test_directory_or_global_records_never_bind(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", True)
    parent = _row("17.08", "17.08. (c) Reapply after one year.", access_scope="global")
    parent["evidence_selector_selected"] = True
    child = _row("17.08-c", "Section 17.08: Voluntary resignation.\n(c) Reapply after one year.", "list_item", parent_section_id="17.08", access_scope="global")
    assert opensearch_sections._bind_selected_parent_children([(parent, 1.0), (child, 0.9)]) == [(parent, 1.0), (child, 0.9)]


def test_top_selector_pick_is_never_displaced(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", True)
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 2)
    top = _row("17.09-c", "Other", "list_item")
    top["evidence_selector_selected"] = True
    parent = _row("17.08", "17.08. (c) Reapply after one year.")
    parent["evidence_selector_selected"] = True
    child = _row("17.08-c", "Section 17.08: Voluntary resignation.\n(c) Reapply after one year.", "list_item", parent_section_id="17.08")
    result = opensearch_sections._bind_selected_parent_children([(top, 1.1), (parent, 1.0), (child, 0.9)])
    assert [row["id"] for row, _ in result][:2] == ["17.09-c", "17.08"]
