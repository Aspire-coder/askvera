import pytest

from app.retrieval.providers import RetrievalQueryPlan
from config import settings
from scripts.evaluate_interaction_history import (
    _EvaluationOpenSearchProvider,
    _SharedEvaluationPlanCache,
    _SharedEvaluationSearchCache,
    _SharedEvaluationTranslationCache,
    VNEXT_PROFILE_FEATURES,
    _configure_vnext_profile,
    _vnext_provider,
)


@pytest.mark.parametrize("profile", sorted(VNEXT_PROFILE_FEATURES))
def test_vnext_profile_enables_only_declared_features(monkeypatch, profile) -> None:
    for name in (
        "RETRIEVAL_VNEXT_GLOSSARY_ENABLED",
        "RETRIEVAL_VNEXT_EVIDENCE_SELECTOR_ENABLED",
        "RETRIEVAL_VNEXT_RRF_ENABLED",
        "RETRIEVAL_VNEXT_PARENT_DIVERSITY_ENABLED",
        "RETRIEVAL_VNEXT_NEIGHBOR_EXPANSION_ENABLED",
        "RETRIEVAL_VNEXT_RERANK_ENABLED",
    ):
        monkeypatch.setattr(settings, name, True)

    features = _configure_vnext_profile(profile)

    assert settings.RETRIEVAL_VNEXT_GLOSSARY_ENABLED == ("glossary" in features)
    assert settings.RETRIEVAL_VNEXT_EVIDENCE_SELECTOR_ENABLED == (
        "evidence_selector" in features
    )
    assert settings.RETRIEVAL_VNEXT_RRF_ENABLED == ("rrf" in features)
    assert settings.RETRIEVAL_VNEXT_PARENT_DIVERSITY_ENABLED == (
        "parent_diversity" in features
    )
    assert settings.RETRIEVAL_VNEXT_NEIGHBOR_EXPANSION_ENABLED == (
        "neighbor_expansion" in features
    )
    assert settings.RETRIEVAL_VNEXT_RERANK_ENABLED == ("rerank" in features)


def test_unknown_vnext_profile_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown vNext profile"):
        _configure_vnext_profile("not-a-profile")


def test_rank_baseline_enables_no_experimental_features(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_INDEX", "production")
    monkeypatch.setattr(settings, "OPENSEARCH_GLOSSARY_ENABLED", True)
    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", False)
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 5)
    monkeypatch.setattr(settings, "RETRIEVAL_VNEXT_RESULT_COUNT", 8)

    provider = _vnext_provider("rank-baseline", "isolated-candidate")

    assert provider.index_name == "isolated-candidate"
    assert provider.experimental_features is False
    assert provider.result_count == 5
    assert provider.glossary_enabled is False
    assert provider.evidence_selector_enabled is False


def test_rank_rrf_changes_only_experimental_ranking(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_INDEX", "production")
    monkeypatch.setattr(settings, "OPENSEARCH_GLOSSARY_ENABLED", True)
    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", False)
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 5)

    provider = _vnext_provider("rank-rrf", "isolated-candidate")

    assert provider.experimental_features is True
    assert provider.result_count == 5
    assert provider.glossary_enabled is False
    assert provider.evidence_selector_enabled is False
    assert settings.RETRIEVAL_VNEXT_RRF_ENABLED is True


def test_rank_rerank_uses_bounded_managed_ranker_without_selector(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_INDEX", "production")
    monkeypatch.setattr(settings, "OPENSEARCH_GLOSSARY_ENABLED", True)
    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", True)
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 5)
    monkeypatch.setattr(settings, "RETRIEVAL_VNEXT_RERANK_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "RETRIEVAL_VNEXT_RERANK_MODEL_ARN",
        "arn:aws:bedrock:us-east-1::foundation-model/cohere.rerank-v3-5:0",
    )

    provider = _vnext_provider("rank-rerank", "isolated-candidate")

    assert provider.experimental_features is True
    assert provider.enable_bedrock_rerank is True
    assert provider.evidence_selector_enabled is False
    assert provider.authority_ranking_enabled is False


def test_rank_rerank_requires_an_enabled_model(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_INDEX", "production")
    monkeypatch.setattr(settings, "RETRIEVAL_VNEXT_RERANK_MODEL_ARN", "")

    with pytest.raises(RuntimeError, match="rerank profile requires"):
        _vnext_provider("rank-rerank", "isolated-candidate")


def test_same_index_rank_ablation_requires_explicit_override(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_INDEX", "production")

    with pytest.raises(RuntimeError, match="matches OPENSEARCH_INDEX"):
        _vnext_provider("rank-rrf", "production")

    provider = _vnext_provider(
        "rank-rrf",
        "production",
        allow_same_index_rank_ablation=True,
    )

    assert provider.index_name == "production"
    assert provider.experimental_features is True


def test_same_index_override_rejects_non_rank_profile(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_INDEX", "production")

    with pytest.raises(RuntimeError, match="matches OPENSEARCH_INDEX"):
        _vnext_provider(
            "full",
            "production",
            allow_same_index_rank_ablation=True,
        )


def test_paired_evaluation_providers_share_one_query_plan(monkeypatch) -> None:
    calls = []
    expected = RetrievalQueryPlan(["shared plan"])
    monkeypatch.setattr(
        "scripts.evaluate_interaction_history.OpenSearchSectionProvider._build_search_plan",
        lambda *_args: calls.append("planned") or expected,
    )
    cache = _SharedEvaluationPlanCache()
    current = _EvaluationOpenSearchProvider(plan_cache=cache)
    candidate = _EvaluationOpenSearchProvider(
        index_name="candidate",
        plan_cache=cache,
    )

    first = current._build_search_plan("question", "DE", "de", "current")
    second = candidate._build_search_plan("question", "DE", "de", "candidate")

    assert first is expected
    assert second is expected
    assert calls == ["planned"]


def test_paired_rank_ablation_reuses_identical_search_response() -> None:
    class Client:
        def __init__(self) -> None:
            self.calls = 0

        def search(self, **_kwargs):
            self.calls += 1
            return {"hits": {"hits": [{"_id": "one"}]}}

    client = Client()
    cache = _SharedEvaluationSearchCache(client)
    body = {"query": {"match_all": {}}}

    first = cache.search(index="production", body=body)
    first["hits"]["hits"][0]["_id"] = "mutated"
    second = cache.search(index="production", body=body)

    assert client.calls == 1
    assert second["hits"]["hits"][0]["_id"] == "one"


def test_paired_evaluation_providers_share_one_global_translation(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "scripts.evaluate_interaction_history.OpenSearchSectionProvider._global_search_query",
        lambda *_args: calls.append("translated") or "shared translation",
    )
    plans = _SharedEvaluationPlanCache()
    translations = _SharedEvaluationTranslationCache()
    current = _EvaluationOpenSearchProvider(
        plan_cache=plans,
        translation_cache=translations,
    )
    candidate = _EvaluationOpenSearchProvider(
        plan_cache=plans,
        translation_cache=translations,
    )

    first = current._global_search_query("Frage", "de", "current")
    second = candidate._global_search_query("Frage", "de", "candidate")

    assert first == "shared translation"
    assert second == "shared translation"
    assert calls == ["translated"]
