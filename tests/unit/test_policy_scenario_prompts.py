"""Prompt wiring regressions, not a substitute for live answer-quality evaluation."""

import pytest
from types import SimpleNamespace

from app.prompts.builder import PromptBuilder
from config import settings


@pytest.mark.parametrize("language,question", [
    ("de", "Ich bin FBO und habe seit sechs Monaten nichts bestellt. Darf ich den Sponsor wechseln?"),
    ("en", "If I miss my active target one month, do I lose my level?"),
])
def test_scenario_role_does_not_change_access_role(monkeypatch, language, question):
    monkeypatch.setattr(settings, "EVIDENCE_GATED_OUTPUT_ENABLED", True)
    prompt = PromptBuilder().build(
        user_question=question, conversation="", country="DE", language=language,
        role="new_prospect", retrieved_documents="Authorized policy evidence",
    )
    assert prompt.role == "new_prospect"
    assert "User role: new_prospect" in prompt.system_prompt
    assert "without granting access" in prompt.system_prompt
    assert "Inactivity does not imply a role change" in prompt.system_prompt
    assert "Leadership Bonus eligibility and incentive payments" in prompt.system_prompt
    assert "deadline trigger" in prompt.system_prompt
    assert "selected country governs local policy access" in prompt.system_prompt
    assert question in prompt.user_prompt


@pytest.mark.parametrize("provider", ["opensearch", "bedrock"])
def test_both_selectors_receive_scenario_guards(monkeypatch, provider):
    from app.retrieval import opensearch_sections, providers
    from app.retrieval.models import RetrievedDocument

    calls = []

    def converse(**kwargs):
        calls.append(kwargs)
        return {"output": {"message": {"content": [{"text": '{"selected_ranks":[2]}'}]}}}

    client = SimpleNamespace(bedrock_runtime=SimpleNamespace(converse=converse))
    question = "I am a Preferred Customer returning an unopened bottle."
    if provider == "opensearch":
        monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", True)
        monkeypatch.setattr(opensearch_sections, "get_aws_clients", lambda: client)
        rows = [({"id": str(i), "content": "Policy evidence", "metadata": {}}, 1.0) for i in (1, 2)]
        result = opensearch_sections.OpenSearchSectionProvider()._select_evidence_rows(question, rows, "test")
        assert result[0][0]["id"] == "2"
    else:
        monkeypatch.setattr(settings, "BEDROCK_EVIDENCE_SELECTOR_ENABLED", True)
        monkeypatch.setattr(settings, "BEDROCK_RETRIEVAL_RESULT_COUNT", 1)
        monkeypatch.setattr(providers, "get_aws_clients", lambda: client)
        documents = [RetrievedDocument(id=str(i), title="Policy", content="Policy evidence", source="test") for i in (1, 2)]
        result = providers._select_evidence_documents(question, documents, "test")
        assert result[0].id == "2"
    prompt = calls[0]["system"][0]["text"]
    assert "FBO and Preferred Customer rules are not interchangeable" in prompt
    assert "alone do not establish an FBO role" in prompt
    assert "complementary governing clauses" in prompt
