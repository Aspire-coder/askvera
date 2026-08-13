from app.retrieval.experiments import (
    bounded_neighbor_ids,
    diversify_by_parent,
    reciprocal_rank_fusion,
)


def test_reciprocal_rank_fusion_is_deterministic_and_deduplicates_each_list():
    scores = reciprocal_rank_fusion([["a", "b", "a"], ["b", "c"]], k=10)

    assert scores["b"] > scores["a"] > scores["c"]


def test_parent_diversity_limits_repeated_chunks_without_reordering():
    documents = [
        {"id": "a1", "metadata": {"parent_section_id": "a"}},
        {"id": "a2", "metadata": {"parent_section_id": "a"}},
        {"id": "b1", "metadata": {"parent_section_id": "b"}},
    ]

    result = diversify_by_parent(documents, max_results=3, max_per_parent=1)

    assert [document["id"] for document in result] == ["a1", "b1"]


def test_neighbor_expansion_is_bounded_and_deduplicated():
    assert bounded_neighbor_ids(["a", "a"], ["b", "c"], limit=2) == ["a", "b"]
