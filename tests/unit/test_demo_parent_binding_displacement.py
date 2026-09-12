"""Parent-child binding must survive displacing a later selected parent.

Live diagnostic at ec82147 (SE, en, "What is the return policy?") stopped with a
bare ``StopIteration``: binding the first parent's child into a full selection
displaced a later selected parent; when the loop reached that parent it
displaced another row and then looked the parent up with ``next(...)`` and no
default.  Everything here is offline; sockets, boto3 sessions, AWS clients and
embeddings are blocked.
"""

from __future__ import annotations

import socket
from collections import Counter

import pytest

from app.retrieval import opensearch_sections
from app.retrieval.opensearch_sections import OpenSearchSectionProvider, _bind_selected_parent_children
from app.retrieval.providers import RetrievalQueryPlan
from config import settings


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("network access is not allowed in this test")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(opensearch_sections.boto3, "Session", refuse)
    monkeypatch.setattr(opensearch_sections, "get_aws_clients", refuse)
    monkeypatch.setattr(opensearch_sections, "embed_text", refuse)
    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", True)


def _row(identifier, content, chunk_type="section", parent="", selected=False, **extra):
    row = {
        "id": identifier,
        "section_id": identifier,
        "parent_section_id": parent,
        "content": content,
        "chunk_type": chunk_type,
        "document_type": "policy",
        "access_scope": "country",
        "source_file": "sweden.pdf",
        "country": "SE",
        "language": "en",
        "metadata": {},
        **extra,
    }
    if selected:
        row["evidence_selector_selected"] = True
    return row


def _family(section_id, clause, *, selected=True):
    parent = _row(section_id, f"{section_id} Returns. (c) {clause}", selected=selected)
    child = _row(
        f"{section_id}-c",
        f"Section {section_id}: Returns.\n(c) {clause}",
        chunk_type="list_item",
        parent=section_id,
    )
    return parent, child


def _ids(result):
    return [row["id"] for row, _score in result]


def _displacement_rows():
    """Selector picks A, an unrelated clause X, then B; both parents have bindable children."""
    parent_a, child_a = _family("10.01", "Return unopened product within 30 days.")
    other = _row("9.00", "Other selected clause.", chunk_type="list_item", selected=True)
    parent_b, child_b = _family("10.02", "Refunds are paid to the original payment method.")
    rows = [(parent_a, 2.0), (other, 1.95), (parent_b, 1.9), (child_a, 1.5), (child_b, 1.4)]
    return rows, parent_a, child_a, other, parent_b, child_b


def test_binding_that_displaces_a_later_selected_parent_does_not_raise(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 3)
    rows, parent_a, child_a, other, parent_b, child_b = _displacement_rows()
    before = Counter(_ids(rows))

    result = _bind_selected_parent_children(list(rows))

    # A keeps the top spot with its child bound right after it; B was displaced
    # by that binding and does not bring its own child back; X keeps its place.
    assert [row for row, _score in result] == [parent_a, child_a, other, parent_b, child_b]
    assert child_a.get("parent_bound_child") is True
    assert "parent_bound_child" not in child_b
    assert Counter(_ids(result)) == before
    assert [score for _row_, score in result] == [2.0, 1.5, 1.95, 1.9, 1.4]


def test_three_selected_parents_keep_every_row_once(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 3)
    parent_a, child_a = _family("10.01", "Return unopened product within 30 days.")
    parent_b, child_b = _family("10.02", "Refunds are paid to the original payment method.")
    parent_c, child_c = _family("10.03", "Shipping costs are not refunded.")
    rows = [(parent_a, 3.0), (parent_b, 2.9), (parent_c, 2.8), (child_a, 1.5), (child_b, 1.4), (child_c, 1.3)]

    result = _bind_selected_parent_children(list(rows))

    assert _ids(result) == ["10.01", "10.01-c", "10.02", "10.03", "10.02-c", "10.03-c"]
    assert Counter(_ids(result)) == Counter(_ids(rows))
    assert child_a.get("parent_bound_child") is True
    assert "parent_bound_child" not in child_b
    assert "parent_bound_child" not in child_c


def test_adjacent_parents_with_no_further_room_are_unchanged(monkeypatch) -> None:
    """Did not crash before the fix; the output must be identical."""
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 2)
    parent_a, child_a = _family("10.01", "Return unopened product within 30 days.")
    parent_b, child_b = _family("10.02", "Refunds are paid to the original payment method.")
    rows = [(parent_a, 2.0), (parent_b, 1.9), (child_a, 1.5), (child_b, 1.4)]

    result = _bind_selected_parent_children(list(rows))

    assert _ids(result) == ["10.01", "10.01-c", "10.02", "10.02-c"]
    assert child_a["parent_bound_child"] is True
    assert "parent_bound_child" not in child_b


def test_single_parent_and_child_binding_is_unchanged(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 5)
    parent, child = _family("10.01", "Return unopened product within 30 days.")
    other = _row("11.00", "Unrelated section.")

    result = _bind_selected_parent_children([(parent, 2.0), (other, 1.8), (child, 1.5)])

    assert _ids(result) == ["10.01", "10.01-c", "11.00"]
    assert child["parent_bound_child"] is True


def test_room_left_in_selection_binds_both_parents_without_displacement(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 5)
    rows, _parent_a, child_a, _other, _parent_b, child_b = _displacement_rows()

    result = _bind_selected_parent_children(list(rows))

    assert _ids(result) == ["10.01", "10.01-c", "9.00", "10.02", "10.02-c"]
    assert child_a["parent_bound_child"] is True
    assert child_b["parent_bound_child"] is True


def test_full_selection_with_no_displaceable_position_is_unchanged(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 1)
    parent, child = _family("10.01", "Return unopened product within 30 days.")
    rows = [(parent, 2.0), (child, 1.5)]

    result = _bind_selected_parent_children(list(rows))

    assert result == rows
    assert "parent_bound_child" not in child


def test_displaced_top_row_is_never_chosen(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 2)
    top = _row("9.00", "Top pick.", chunk_type="list_item", selected=True)
    parent, child = _family("10.01", "Return unopened product within 30 days.")

    result = _bind_selected_parent_children([(top, 3.0), (parent, 2.0), (child, 1.5)])

    assert _ids(result) == ["9.00", "10.01", "10.01-c"]
    assert "parent_bound_child" not in child


def test_rows_without_ids_keep_their_existing_conservative_behaviour(monkeypatch) -> None:
    """Empty ids compare equal, so an id-less child reads as already selected.

    This is the pre-existing protection semantics and is deliberately kept:
    an id-less child never binds while any selected row is also id-less.
    """
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 3)
    rows, *_rest = _displacement_rows()
    for row, _score in rows:
        row["id"] = ""

    result = _bind_selected_parent_children(list(rows))

    assert result == rows
    assert not any(row.get("parent_bound_child") for row, _score in result)


def test_id_less_later_parent_is_displaced_without_raising(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 3)
    rows, parent_a, child_a, other, parent_b, child_b = _displacement_rows()
    parent_b["id"] = ""

    result = _bind_selected_parent_children(list(rows))

    assert [row for row, _score in result] == [parent_a, child_a, other, parent_b, child_b]
    assert child_a["parent_bound_child"] is True
    assert "parent_bound_child" not in child_b


def test_parent_missing_after_displacement_restores_the_popped_row(monkeypatch) -> None:
    """Defensive path: if a displacement ever removed the current parent, nothing is lost."""
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 2)
    parent_a, child_a = _family("10.01", "Return unopened product within 30 days.")
    parent_b, child_b = _family("10.02", "Refunds are paid to the original payment method.")
    rows = [(parent_a, 2.0), (parent_b, 1.9), (child_a, 1.5), (child_b, 1.4)]

    def current_parent_position(selected, protected_ids):
        return next(index for index, (row, _score) in enumerate(selected) if row["chunk_type"] == "section" and row["id"] in protected_ids and not row.get("parent_bound_child"))

    monkeypatch.setattr(opensearch_sections, "_displaceable_position", current_parent_position)

    result = _bind_selected_parent_children(list(rows))

    assert result == rows
    assert "parent_bound_child" not in child_a
    assert "parent_bound_child" not in child_b


def test_selector_selected_child_bound_by_its_own_parent_is_not_duplicated(monkeypatch) -> None:
    """A selector-picked child can be displaced by one parent's binding and
    then re-bound by its own parent; it must appear exactly once, right
    after that parent, not once in `selected` and once in `displaced`.

    Layout (selected_count=4, OPENSEARCH_RESULT_COUNT=4):
      0 parent_a (selected)   1 z (selected, filler)
      2 parent_b (selected)   3 child_b (selected -- the selector's own pick)
      4 child_a (not selected -- parent_a's real, unselected child)

    Binding parent_a's child_a fills the selection and pops the last
    non-protected row from the end, which is child_b (position 3) --
    displacing it before its own parent (parent_b) is even processed.
    When the loop reaches parent_b, `_bound_child` still finds child_b (the
    lookup scans all rows, not just `selected`), and child_b is no longer in
    `selected`, so the existing "already selected" guard does not catch it;
    parent_b binds it again, popping the filler `z` to make room.
    """
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 4)
    parent_a, child_a = _family("10.01", "Return unopened product within 30 days.")
    parent_b, child_b = _family("10.02", "Refunds are paid to the original payment method.")
    child_b["evidence_selector_selected"] = True
    z = _row("9.00", "Filler selected clause.", chunk_type="list_item", selected=True)
    rows = [(parent_a, 4.0), (z, 3.9), (parent_b, 3.8), (child_b, 3.7), (child_a, 2.0)]
    before = Counter(_ids(rows))

    result = _bind_selected_parent_children(list(rows))

    ids = _ids(result)
    assert Counter(ids) == before, f"every row id must appear exactly once, got {ids}"
    parent_b_index = ids.index("10.02")
    assert ids[parent_b_index + 1] == "10.02-c", "the selected child must sit right after its own parent"
    assert child_b.get("parent_bound_child") is True
    assert child_a.get("parent_bound_child") is True


def test_retrieve_with_displacing_selection_returns_documents(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 3)
    monkeypatch.setattr(settings, "OPENSEARCH_RETRIEVAL_HARDENING_ENABLED", False)
    monkeypatch.setattr(settings, "ADMIN_INGESTION_GENERATION_POINTER_ENABLED", False)
    monkeypatch.setattr(settings, "RETRIEVAL_PARENT_DIVERSITY_ENABLED", False)
    monkeypatch.setattr(settings, "SECTION_RETRIEVAL_MIN_SCORE", 0.0)
    rows, *_rest = _displacement_rows()
    for row, _score in rows:
        row.pop("evidence_selector_selected", None)

    class Client:
        def search(self, **_kwargs):
            return {"hits": {"hits": []}}

    provider = OpenSearchSectionProvider()
    monkeypatch.setattr(
        provider,
        "_build_search_plan",
        lambda *_args: RetrievalQueryPlan(["What is the return policy?"], include_global_documents=False),
    )
    monkeypatch.setattr(opensearch_sections, "_client", lambda: Client())
    monkeypatch.setattr(opensearch_sections, "_text_query", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(opensearch_sections, "_vector_query", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(provider, "_merge_hits", lambda *_args, **_kwargs: list(rows))

    def select(_message, candidates, _correlation_id):
        for row, _score in candidates[:3]:
            row["evidence_selector_selected"] = True
        return list(candidates)

    monkeypatch.setattr(provider, "_select_evidence_rows", select)

    result = provider.retrieve("What is the return policy?", "SE", "en", "new_prospect", "cid")

    assert [document.id for document in result.documents] == ["10.01", "10.01-c", "9.00"]
    assert result.metadata["parent_bound_children"] == ["10.01-c"]
