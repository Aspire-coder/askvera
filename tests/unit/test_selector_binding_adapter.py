import pytest

from scripts.selector_binding_adapter import make_request, assessment, source_alias, alias_registry


def case():
    template = ("Candidate {rank}\nDocument type: policy\nAccess scope: country\nSection: {section}\n"
                "Title: {title}\nCurrent score: 1\nText:\n{content}")
    blocks = [template.format(rank=1, section="bonus", title="Earned Incentive", content="Active managers get benefits."),
              template.format(rank=2, section="4.03", title="Activity Qualification.",
                              content="To be considered Active, an FBO must qualify monthly.")]
    return {"id": "test", "question": "How do I become Active?", "blocks": blocks,
            "expected": True, "governing_sections": ["4.03"]}


def test_ranking_changes_order_not_prompt_or_source_content():
    original, old_rows, old_sources = make_request(case(), "current", "snapshot")
    ranked, rows, sources = make_request(case(), "ranking", "snapshot")
    assert original["system"] == ranked["system"]
    assert rows[0]["section_id"] == "4.03"
    assert old_rows[0]["section_id"] == "bonus"
    assert {source.binding_id for source in old_sources} == {source.binding_id for source in sources}


def test_binding_and_combined_share_protocol_and_stable_ids():
    bound, rows, sources = make_request(case(), "binding", "snapshot")
    combined, combined_rows, combined_sources = make_request(case(), "combined", "snapshot")
    assert bound["system"] == combined["system"]
    assert sources[::-1] == combined_sources
    assert rows[::-1] == combined_rows
    assert "Source ID:" in bound["messages"][0]["content"][0]["text"]


def test_unsupported_language_is_no_change_for_ranking_factor():
    value = {**case(), "language": "de"}
    assert make_request(value, "current", "snapshot")[0] == make_request(value, "ranking", "snapshot")[0]


def test_selected_governing_quote_passes_with_exact_id():
    value = case()
    _, rows, sources = make_request(value, "combined", "snapshot")
    payload = {"directly_answers_top_rank": True, "selected_source_ids": [source_alias(sources[0])],
               "support": [{"source_id": source_alias(sources[0]), "quote": sources[0].content}]}
    assert assessment(payload, value, "combined", rows, sources)[0]
    payload["support"][0]["source_id"] = source_alias(sources[1])
    assert not assessment(payload, value, "combined", rows, sources)[0]


@pytest.mark.parametrize("ids", [[1], ["missing"], None])
def test_invalid_source_ids_fail_closed(ids):
    value = case()
    _, rows, sources = make_request(value, "binding", "snapshot")
    payload = {"directly_answers_top_rank": True, "selected_source_ids": ids, "support": []}
    assert not assessment(payload, value, "binding", rows, sources)[0]


def test_alias_collisions_fail_closed():
    from types import SimpleNamespace
    with pytest.raises(ValueError, match="Ambiguous"):
        alias_registry([SimpleNamespace(binding_id="a" * 16 + "1"), SimpleNamespace(binding_id="a" * 16 + "2")])


def test_scoped_factor_changes_only_target_instruction():
    from scripts.selector_binding_adapter import RETENTION_INSTRUCTION, TARGET_INSTRUCTION
    baseline, rows, sources = make_request(case(), "combined", "snapshot")
    candidate, candidate_rows, candidate_sources = make_request(case(), "scoped", "snapshot")
    assert rows == candidate_rows and sources == candidate_sources
    assert baseline["messages"] == candidate["messages"]
    assert candidate["system"][0]["text"] == baseline["system"][0]["text"].replace(
        RETENTION_INSTRUCTION, TARGET_INSTRUCTION)


def test_scoped_never_overrides_false_flag_from_reason():
    value = case()
    _, rows, sources = make_request(value, "scoped", "snapshot")
    payload = {"directly_answers_top_rank": False, "selected_source_ids": [source_alias(sources[0])],
               "support": [{"source_id": source_alias(sources[0]), "quote": sources[0].content}],
               "reason": "The rule fully answers the question."}
    assert assessment(payload, value, "scoped", rows, sources) == (False, "wrong support decision")


def test_scoped_rejects_changed_baseline(monkeypatch):
    monkeypatch.setattr("scripts.selector_binding_adapter.current_prompt", lambda: "different prompt")
    with pytest.raises(ValueError, match="Baseline retention"):
        make_request(case(), "scoped", "snapshot")


@pytest.mark.parametrize("verdict,passed", [("ANSWER_NO", True), ("ANSWER_YES", False), ("unknown", False)])
def test_bound_verdict_requires_correct_polarity_and_bound_quote(verdict, passed):
    value = {**case(), "polarity": "ANSWER_NO"}
    _, rows, sources = make_request(value, "verdict", "snapshot")
    payload = {"decision": verdict, "draft_answer": "No, monthly qualification is required.",
               "missing_facts": [], "selected_source_ids": [source_alias(sources[0])],
               "support": [{"source_id": source_alias(sources[0]), "quote": sources[0].content}]}
    assert assessment(payload, value, "verdict", rows, sources)[0] is passed
    payload["support"][0]["source_id"] = source_alias(sources[1])
    assert not assessment(payload, value, "verdict", rows, sources)[0]


def test_bound_verdict_does_not_approve_empty_or_mixed_abstention():
    value = {**case(), "expected": False}
    _, rows, sources = make_request(value, "verdict", "snapshot")
    payload = {"decision": "INSUFFICIENT_EVIDENCE", "draft_answer": "", "missing_facts": ["rule"],
               "selected_source_ids": [], "support": []}
    assert assessment(payload, value, "verdict", rows, sources)[0]
    assert not assessment({**payload, "missing_facts": []}, value, "verdict", rows, sources)[0]
    assert not assessment({**payload, "answer_supported": True}, value, "verdict", rows, sources)[0]


def test_structural_orders_validated_selected_quotes_without_adding_sources():
    from scripts.selector_binding_adapter import structural_decision
    value = {**case(), "polarity": "ANSWER_FACT"}
    _, rows, sources = make_request(value, "structural", "snapshot")
    payload = {"decision": "ANSWER_FACT", "draft_answer": "Qualify monthly.", "missing_facts": [],
               "confidence": 0.9, "support": [
                   {"source_id": source_alias(source), "quote": source.content} for source in sources[::-1]]}
    decision = structural_decision(payload, value, rows, sources)
    assert decision.source_ids == tuple(source.binding_id for source in sources)
    assert payload["support"][0]["source_id"] == source_alias(sources[1])
    assert assessment(payload, value, "structural", rows, sources)[0]
    # Omitted governing evidence is not silently added back.
    payload["support"] = payload["support"][:1]
    assert structural_decision(payload, value, rows, sources).source_ids == (sources[1].binding_id,)
    assert not assessment(payload, value, "structural", rows, sources)[0]


def test_structural_unsupported_language_preserves_quote_order():
    from scripts.selector_binding_adapter import structural_decision
    value = {**case(), "language": "de"}
    _, rows, sources = make_request(value, "structural", "snapshot")
    payload = {"decision": "ANSWER_FACT", "draft_answer": "Regel.", "missing_facts": [], "confidence": 0.8,
               "support": [{"source_id": source_alias(source), "quote": source.content} for source in sources]}
    assert structural_decision(payload, value, rows, sources).source_ids == tuple(s.binding_id for s in sources)


def test_structural_processing_does_not_read_expected_answer_labels():
    from scripts.selector_binding_adapter import structural_decision
    value = case()
    _, rows, sources = make_request(value, "structural", "snapshot")
    payload = {"decision": "ANSWER_FACT", "draft_answer": "Monthly qualification.", "missing_facts": [],
               "confidence": 0.9, "support": [{"source_id": source_alias(sources[0]), "quote": sources[0].content}]}
    assert structural_decision(payload, value, rows, sources) == structural_decision(
        payload, {"question": value["question"], "expected": False}, rows, sources)


def test_structural_parent_rule_does_not_make_a_benefit_quote_governing():
    from dataclasses import replace
    from scripts.selector_binding_adapter import structural_decision
    value = case()
    _, rows, sources = make_request(value, "structural", "snapshot")
    content = sources[0].content + " Active managers get benefits."
    sources[0] = replace(sources[0], content=content)
    rows[0] = {**rows[0], "content": content}
    payload = {"decision": "ANSWER_FACT", "draft_answer": "Qualify monthly.", "missing_facts": [],
               "confidence": 0.9, "support": [
                   {"source_id": source_alias(sources[0]), "quote": "Active managers get benefits."},
                   {"source_id": source_alias(sources[0]), "quote": "To be considered Active, an FBO must qualify monthly."}]}
    result = structural_decision(payload, value, rows, sources)
    assert result.support[0].quote.startswith("To be considered Active")
    assert len(result.support) == 2
    assert len(result.source_ids) == 1
