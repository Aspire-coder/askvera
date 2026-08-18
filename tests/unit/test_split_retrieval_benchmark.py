from scripts.split_retrieval_benchmark import _group_key, split_rows


def test_related_section_questions_share_a_split_group() -> None:
    first = {
        "case_id": "a",
        "country": "DE",
        "language": "de",
        "expected_section_ids": "4.03",
        "expected_document_names": "policy.pdf",
    }
    second = {**first, "case_id": "b"}
    assert _group_key(first) == _group_key(second)
    assert split_rows([first, second])[0]["split"] == split_rows([first, second])[1]["split"]
