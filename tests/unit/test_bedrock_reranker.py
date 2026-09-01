"""Tests for optional Bedrock candidate reranking."""

from app.retrieval import bedrock_reranker
from config import settings


def _rows():
    return [
        ({"id": "first", "section_title": "First", "content": "first content"}, 3.0),
        ({"id": "second", "section_title": "Second", "content": "second content"}, 2.0),
        ({"id": "third", "section_title": "Third", "content": "third content"}, 1.0),
    ]


class _AgentRuntime:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def rerank(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


class _Clients:
    def __init__(self, agent_runtime):
        self.bedrock_agent_runtime = agent_runtime


def test_rerank_rows_reorders_selected_candidates_and_preserves_remainder(monkeypatch) -> None:
    runtime = _AgentRuntime({"results": [{"index": 1, "relevanceScore": 0.9}, {"index": 0, "relevanceScore": 0.8}]})
    monkeypatch.setattr(bedrock_reranker, "get_aws_clients", lambda: _Clients(runtime))
    monkeypatch.setattr(settings, "OPENSEARCH_RERANK_MODEL_ARN", "arn:model")

    result = bedrock_reranker.rerank_rows("question", _rows(), correlation_id="cid")

    assert [row["id"] for row, _score in result] == ["second", "first", "third"]
    assert runtime.calls[0]["rerankingConfiguration"]["bedrockRerankingConfiguration"]["modelConfiguration"] == {
        "modelArn": "arn:model"
    }


def test_rerank_rows_fails_open_when_bedrock_rejects_request(monkeypatch) -> None:
    runtime = _AgentRuntime(error=ValueError("invalid"))
    monkeypatch.setattr(bedrock_reranker, "get_aws_clients", lambda: _Clients(runtime))
    monkeypatch.setattr(settings, "OPENSEARCH_RERANK_MODEL_ARN", "arn:model")
    original = _rows()

    assert bedrock_reranker.rerank_rows("question", original, correlation_id="cid") == original


def test_rerank_rows_ignores_invalid_and_duplicate_result_indexes(monkeypatch) -> None:
    runtime = _AgentRuntime(
        {"results": [{"index": 2}, {"index": 2}, {"index": 99}, {"index": "1"}]}
    )
    monkeypatch.setattr(bedrock_reranker, "get_aws_clients", lambda: _Clients(runtime))
    monkeypatch.setattr(settings, "OPENSEARCH_RERANK_MODEL_ARN", "arn:model")

    result = bedrock_reranker.rerank_rows("question", _rows(), correlation_id="cid")

    assert [row["id"] for row, _score in result] == ["third", "first", "second"]


def test_rerank_rows_skips_the_network_call_when_no_model_arn_is_configured(monkeypatch) -> None:
    runtime = _AgentRuntime({"results": [{"index": 1}]})
    monkeypatch.setattr(bedrock_reranker, "get_aws_clients", lambda: _Clients(runtime))
    monkeypatch.setattr(settings, "OPENSEARCH_RERANK_MODEL_ARN", "")
    original = _rows()

    result = bedrock_reranker.rerank_rows("question", original, correlation_id="cid")

    assert result == original
    assert runtime.calls == []
