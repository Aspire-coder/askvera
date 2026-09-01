from app.retrieval.experiments import diversify_by_parent


def test_parent_diversity_limits_repeated_chunks_without_reordering():
    documents = [
        {"id": "a1", "metadata": {"parent_section_id": "a"}},
        {"id": "a2", "metadata": {"parent_section_id": "a"}},
        {"id": "b1", "metadata": {"parent_section_id": "b"}},
    ]

    result = diversify_by_parent(documents, max_results=3, max_per_parent=1)

    assert [document["id"] for document in result] == ["a1", "b1"]
