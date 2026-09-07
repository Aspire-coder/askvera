from contextlib import ExitStack

from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.retrieval import opensearch_sections
from app.retrieval.models import RetrievedDocument, RetrievalResult
from scripts.followup_chat_adapter import install
from utils.validators import ChatRequest


def test_target_switch_and_policy_boundary_with_restoration():
    bot = AIOrchestrator()
    original = opensearch_sections._directory_target_country_names
    history = "user: How do I join in Belgium?\nvera: Earlier answer\nuser: What about Germany?"
    with ExitStack() as stack:
        install(stack, bot)
        query = bot._build_retrieval_query("Tell me more", history, "test")
        assert "What about Germany?" in query
        assert query.endswith("Follow-up request: Tell me more")
        assert "Earlier answer" not in query
        assert opensearch_sections._directory_target_country_names(query, "US") == {"Germany"}
        scope = bot._scope_query("Tell me more", query, history)
        document = RetrievedDocument(
            id="us", title="US policy", content="US rules", source="s3://approved/us.pdf",
            country="US", language="en", score=1, metadata={"access_scope": "country"},
        )
        result = RetrievalResult(documents=[document], citations=[], confidence=1)
        body = ChatRequest(message="Tell me more", sessionId="test", country="US", language="en")
        assert bot._is_cross_market_local_evidence(scope, result, body)
        assert body.country == "US"
        fresh = bot._build_retrieval_query("What is the refund policy?", "", "next")
        assert fresh == "What is the refund policy?"
        assert opensearch_sections._directory_target_country_names(fresh, "US") == original(fresh, "US")
    assert opensearch_sections._directory_target_country_names is original


def test_first_question_reference_preserves_explicit_original_target():
    bot = AIOrchestrator()
    with ExitStack() as stack:
        install(stack, bot)
        query = bot._build_retrieval_query(
            "Explain my first question", "user: Joining in Belgium?\nuser: What about Germany?", "test",
        )
        assert opensearch_sections._directory_target_country_names(query, "US") == {"Belgium"}
