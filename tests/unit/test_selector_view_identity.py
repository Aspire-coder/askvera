"""Selector candidate view: clause, heading and source identity within a fixed budget.

The live effect on the selector's top-1 choice is unmeasured; these tests pin
only what the selector is shown and that nothing else changes.
"""

from __future__ import annotations

import hashlib

from app.retrieval import opensearch_sections
from app.retrieval.opensearch_sections import (
    OpenSearchSectionProvider,
    _bind_selected_parent_children,
    _clause_in_selector_view,
    _selector_candidate_text,
    _selector_candidates,
)
from config import settings

# sha256 of the selector system prompt at fb22f38 + the approved 954b4f5c patch.
_BASELINE_SYSTEM_PROMPT_SHA256 = {
    False: "f5d276441aa1cd400879c0d03e0c1183fd9cc5beb524223e8bfd993eb6e9e50d",
    True: "b717c80a22e6bcc813ec65bd1bb57d9b6c8356c5f746f6f04e162153c3522cf0",
}


def _policy_row(section_id: str, content: str, *, chunk_type: str = "section", parent: str = "", title: str = "", **extra):
    return {
        "id": f"NO|no|policy.pdf|{section_id}",
        "section_id": section_id,
        "parent_section_id": parent,
        "section_title": title,
        "content": content,
        "chunk_type": chunk_type,
        "document_type": "policy",
        "access_scope": "country",
        "country": "NO",
        "language": "no",
        "source_file": "policy.pdf",
        "metadata": {},
        **extra,
    }


def _split(view: str) -> tuple[str, str]:
    header, body = view.split("\nText:\n", 1)
    return header, body


def _long_section() -> str:
    clause = ("ord " * 70).strip()
    return "\n".join(["17.09 Oppsigelse eller utestengelse.", *[f"({letter}) {clause}" for letter in "abcdefg"]])


def test_child_view_leads_with_parent_heading_path() -> None:
    row = _policy_row(
        "17.08-c",
        "Section 17.08: Frivillig oppsigelse.\n"
        "(c) Person som tidligere har vært registrert FBO hos FLP, som har valgt\n"
        "oppsigelse eller blitt sagt opp, kan etter ett (1) år (12 måneder) søke om nytt\n"
        "forhandlerskap.",
        chunk_type="list_item",
        parent="17.08",
        title="Person som tidligere har vært registrert FBO hos FLP, som har valgt",
    )

    header, body = _split(_selector_candidate_text(row, 0.9, 3))

    assert "Heading path: 17.08 Frivillig oppsigelse. > (c)" in header
    assert header.index("Section: 17.08-c") < header.index("Heading path:") < header.index("Title:")
    assert body.startswith("(c) Person som tidligere")
    assert "Section 17.08:" not in body
    assert "[Text truncated" not in body


def test_near_identical_clauses_are_distinguished_before_the_text() -> None:
    clause = (
        "(c) After 12 months, a terminated FBO may reapply subject to Home Office\n"
        "approval. Upon such approval, the FBO will enter as a Preferred Customer."
    )
    title = "After 12 months, a terminated FBO may reapply subject to Home Office"
    voluntary = _policy_row("17.08-c", f"Section 17.08: Voluntary Termination.\n{clause}", chunk_type="list_item", parent="17.08", title=title)
    for_cause = _policy_row("17.09-c", f"Section 17.09: Termination or Suspension for Cause.\n{clause}", chunk_type="list_item", parent="17.09", title=title)

    voluntary_header, voluntary_body = _split(_selector_candidate_text(voluntary, 1.0, 1))
    cause_header, cause_body = _split(_selector_candidate_text(for_cause, 1.0, 2))

    assert voluntary_body == cause_body
    assert "Voluntary Termination." in voluntary_header
    assert "Termination or Suspension for Cause." in cause_header
    assert "Voluntary Termination." not in cause_header


def test_definition_rows_keep_their_own_prefix_identity() -> None:
    row = _policy_row(
        "2-part-1-definition-1",
        "Section 2-part-1: Definisjoner (part 1)\nJustert wholesale-pris: rabatt minus gjeldende personlig rabatt.",
        chunk_type="definition",
        parent="2",
        title="Justert wholesale-pris",
    )

    header, body = _split(_selector_candidate_text(row, 1.0, 1))

    assert "Heading path: 2-part-1 Definisjoner (part 1)" in header
    assert body.startswith("Justert wholesale-pris:")


def test_truncated_section_states_the_cut_clause_and_hidden_clauses() -> None:
    content = _long_section()
    row = _policy_row("17.09", content, title="Oppsigelse eller utestengelse.")

    view = _selector_candidate_text(row, 1.0, 1)
    _header, body = _split(view)

    assert body.startswith(content[:1200])
    notice = body[1200:]
    assert notice == f"\n[Text truncated: 1200 of {len(content)} characters shown; clause (e) continues; clauses not shown: (f), (g)]"


def test_truncated_directory_record_states_shown_and_total_characters() -> None:
    content = "Welcome to Forever Norway!\n" + "\n".join(f"Minimum order line {index}: 100 NOK" for index in range(80))
    row = {
        "id": "GLOBAL|en|directory.pdf|sponsoring-081-norway",
        "section_id": "sponsoring-081-norway",
        "parent_section_id": "",
        "section_title": "Forever Norway",
        "content": content,
        "chunk_type": "section",
        "document_type": "office_directory",
        "access_scope": "global",
        "metadata": {"directory_section": "sponsoring", "record_country": "Norway"},
    }

    view = _selector_candidate_text(row, 1.0, 4)

    assert view.endswith(f"\n{content[:1200]}\n[Text truncated: 1200 of {len(content)} characters shown]")
    assert "Document type: office_directory\nAccess scope: global\nRecord type: sponsoring\nRecord country: Norway\nSection: sponsoring-081-norway\nTitle: Forever Norway\n" in view
    assert "Heading path" not in view


def test_hidden_clause_list_is_bounded() -> None:
    content = "Intro\n" + "x" * 1300 + "\n" + "\n".join(f"({letter}) clause" for letter in "abcdefghijklmnopqrstuvwxyz")
    row = _policy_row("9.01", content)

    view = _selector_candidate_text(row, 1.0, 1)
    notice = view.rsplit("\n", 1)[1]

    assert notice.startswith(f"[Text truncated: 1200 of {len(content)} characters shown; clauses not shown: (a), (b)")
    assert notice.endswith("(h), ...]")
    assert "continues" not in notice
    assert len(notice) < 160


def test_short_rows_without_a_parent_keep_the_exact_previous_view() -> None:
    section = _policy_row("17.08", "17.08 Frivillig oppsigelse.\n(c) Kort klausul.", title="Frivillig oppsigelse.")
    directory = {
        "section_id": "sponsoring-003-benin",
        "section_title": "Forever Benin",
        "content": "Minimum order size FBO: €81.",
        "document_type": "office_directory",
        "access_scope": "global",
        "metadata": {"directory_section": "sponsoring", "record_country": "Benin"},
    }

    assert _selector_candidate_text(section, 1.25, 2) == (
        "Candidate 2\nDocument type: policy\nAccess scope: country\nRecord type: \nRecord country: \n"
        "Section: 17.08\nTitle: Frivillig oppsigelse.\nCurrent score: 1.25\n"
        "Text:\n17.08 Frivillig oppsigelse.\n(c) Kort klausul."
    )
    assert _selector_candidate_text(directory, 0.5, 7) == (
        "Candidate 7\nDocument type: office_directory\nAccess scope: global\nRecord type: sponsoring\n"
        "Record country: Benin\nSection: sponsoring-003-benin\nTitle: Forever Benin\nCurrent score: 0.5\n"
        "Text:\nMinimum order size FBO: €81."
    )


def test_prefix_naming_another_section_or_a_row_without_parent_is_not_a_heading() -> None:
    wrong_parent = _policy_row("17.08-c", "Section 17.09: Oppsigelse.\n(c) Tekst.", chunk_type="list_item", parent="17.08")
    no_parent = _policy_row("17.08-c", "Section 17.08: Frivillig oppsigelse.\n(c) Tekst.", chunk_type="list_item")

    for row in (wrong_parent, no_parent):
        header, body = _split(_selector_candidate_text(row, 1.0, 1))
        assert "Heading path" not in header
        assert body == row["content"]


def test_heading_longer_than_the_cap_keeps_the_unchanged_view() -> None:
    at_cap = "h" * 160
    over_cap = "h" * 161
    capped = _policy_row("17.08-c", f"Section 17.08: {at_cap}\n(c) Tekst.", chunk_type="list_item", parent="17.08")
    overlong = _policy_row("17.08-c", f"Section 17.08: {over_cap}\n(c) Tekst.", chunk_type="list_item", parent="17.08")

    capped_header, capped_body = _split(_selector_candidate_text(capped, 1.0, 1))
    overlong_header, overlong_body = _split(_selector_candidate_text(overlong, 1.0, 1))

    assert f"Heading path: 17.08 {at_cap} > (c)" in capped_header
    assert capped_body == "(c) Tekst."
    assert "Heading path" not in overlong_header
    assert overlong_body == overlong["content"]


def test_binding_still_uses_the_unchanged_parent_view(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", True)
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 5)
    content = _long_section()
    clause = ("ord " * 70).strip()
    parent = _policy_row("17.09", content, title="Oppsigelse eller utestengelse.")
    parent["evidence_selector_selected"] = True
    visible_child = _policy_row("17.09-d", f"Section 17.09: Oppsigelse eller utestengelse.\n(d) {clause}", chunk_type="list_item", parent="17.09")
    hidden_child = _policy_row("17.09-f", f"Section 17.09: Oppsigelse eller utestengelse.\n(f) {clause}", chunk_type="list_item", parent="17.09")

    assert _clause_in_selector_view(parent, visible_child) is True
    assert _clause_in_selector_view(parent, hidden_child) is False
    result = _bind_selected_parent_children([(parent, 2.0), (hidden_child, 1.5), (visible_child, 1.0)])
    assert [row["section_id"] for row, _score in result] == ["17.09", "17.09-d", "17.09-f"]


def test_candidate_order_and_rank_mapping_are_unchanged(monkeypatch) -> None:
    prompts: list[str] = []

    class Runtime:
        def converse(self, **kwargs):
            prompts.append(kwargs["messages"][0]["content"][0]["text"])
            return {"output": {"message": {"content": [{"text": '{"selected_ranks":[3,1]}'}]}}}

    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", True)
    monkeypatch.setattr(settings, "OPENSEARCH_RETRIEVAL_HARDENING_ENABLED", False)
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 5)
    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_CANDIDATE_COUNT", 30)
    monkeypatch.setattr(opensearch_sections, "get_aws_clients", lambda: type("Clients", (), {"bedrock_runtime": Runtime()})())
    rows = [
        (_policy_row("17.09-c", "Section 17.09: Oppsigelse.\n(c) Tolv måneder.", chunk_type="list_item", parent="17.09"), 1.4),
        (_policy_row("17.09", _long_section(), title="Oppsigelse."), 1.3),
        (_policy_row("17.08-c", "Section 17.08: Frivillig oppsigelse.\n(c) Ett år.", chunk_type="list_item", parent="17.08"), 1.2),
    ]
    expected_order = [row["section_id"] for row, _score in _selector_candidates(rows, 30)]

    selected = OpenSearchSectionProvider()._select_evidence_rows("Når kan jeg søke igjen?", rows, "cid")

    assert expected_order == ["17.09-c", "17.09", "17.08-c"]
    assert [row["section_id"] for row, _score in selected] == ["17.08-c", "17.09-c", "17.09"]
    prompt = prompts[0]
    positions = [prompt.index(f"Candidate {index}\n") for index in (1, 2, 3)]
    assert positions == sorted(positions)
    assert prompt.count("\nSection: ") == 3
    assert prompt.index("Section: 17.08-c") > positions[2]


def test_selector_prompt_contract_is_unchanged(monkeypatch) -> None:
    captured: list[dict] = []

    class Runtime:
        def converse(self, **kwargs):
            captured.append(kwargs)
            return {"output": {"message": {"content": [{"text": '{"selected_ranks":[1]}'}]}}}

    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", True)
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 5)
    monkeypatch.setattr(opensearch_sections, "get_aws_clients", lambda: type("Clients", (), {"bedrock_runtime": Runtime()})())
    for hardening in (False, True):
        monkeypatch.setattr(settings, "OPENSEARCH_RETRIEVAL_HARDENING_ENABLED", hardening)
        captured.clear()
        OpenSearchSectionProvider()._select_evidence_rows("Q", [({"id": "a", "metadata": {}, "content": "x"}, 1.0)], "cid")
        system_prompt = captured[0]["system"][0]["text"]
        user_prompt = captured[0]["messages"][0]["content"][0]["text"]
        assert hashlib.sha256(system_prompt.encode("utf-8")).hexdigest() == _BASELINE_SYSTEM_PROMPT_SHA256[hardening]
        assert "\n\nSelect up to 5 candidate ranks. Return JSON exactly like this: {" in user_prompt
        assert user_prompt.endswith('"top_rank_confidence":0.9,"reason":"short reason"}.')
