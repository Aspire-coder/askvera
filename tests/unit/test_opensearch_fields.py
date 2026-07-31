from utils.opensearch_fields import (
    exact_term_query,
    exact_terms_query,
    has_exact_keyword_mapping,
)


def test_exact_term_query_supports_current_and_legacy_mappings() -> None:
    assert exact_term_query("ingestion_id", "run-1") == {
        "bool": {
            "should": [
                {"term": {"ingestion_id": "run-1"}},
                {"term": {"ingestion_id.keyword": "run-1"}},
            ],
            "minimum_should_match": 1,
        }
    }


def test_exact_terms_query_supports_current_and_legacy_mappings() -> None:
    assert exact_terms_query("ingestion_id", ["run-1", "run-2"]) == {
        "bool": {
            "should": [
                {"terms": {"ingestion_id": ["run-1", "run-2"]}},
                {
                    "terms": {
                        "ingestion_id.keyword": ["run-1", "run-2"]
                    }
                },
            ],
            "minimum_should_match": 1,
        }
    }


def test_exact_mapping_accepts_keyword_or_keyword_subfield() -> None:
    assert has_exact_keyword_mapping({"type": "keyword"})
    assert has_exact_keyword_mapping(
        {
            "type": "text",
            "fields": {"keyword": {"type": "keyword"}},
        }
    )
    assert not has_exact_keyword_mapping({"type": "text"})
