from scripts.audit_opensearch_index_parity import (
    _aggregation_paths,
    _metadata_value,
    compare_inventories,
)


class _Indices:
    def get_mapping(self, *, index):
        return {
            index: {
                "mappings": {
                    "properties": {
                        field: (
                            {"type": "date"}
                            if field == "effective_date"
                            else
                            {"type": "keyword"}
                            if field != "logical_document_id"
                            else {
                                "type": "text",
                                "fields": {"keyword": {"type": "keyword"}},
                            }
                        )
                        for field in (
                            "source_uri",
                            "logical_document_id",
                            "country",
                            "language",
                            "document_type",
                            "access_scope",
                            "document_version",
                            "effective_date",
                            "ingestion_id",
                        )
                    }
                }
            }
        }


class _Client:
    indices = _Indices()


def test_aggregation_paths_support_keyword_and_text_keyword_mappings() -> None:
    paths = _aggregation_paths(_Client(), "sections")

    assert paths["source_uri"] == "source_uri"
    assert paths["logical_document_id"] == "logical_document_id.keyword"
    assert paths["effective_date"] == "effective_date"


def test_effective_date_normalizes_epoch_milliseconds() -> None:
    assert _metadata_value("effective_date", "1782864000000") == "2026-07-01"
    assert _metadata_value("effective_date", "2026-07-01T00:00:00Z") == (
        "2026-07-01"
    )


def _row(source_uri, ingestion_id, chunk_count):
    return {
        "source_uri": source_uri,
        "logical_document_id": "policy",
        "country": "US",
        "language": "en",
        "document_type": "policy",
        "access_scope": "country",
        "document_version": "2026.1",
        "effective_date": "2026-01-01",
        "ingestion_id": ingestion_id,
        "chunk_count": chunk_count,
    }


def test_chunk_count_difference_does_not_break_document_set_parity() -> None:
    result = compare_inventories(
        [_row("s3://bucket/policy.pdf", "generation-1", 10)],
        [_row("s3://bucket/policy.pdf", "generation-1", 20)],
    )

    assert result["document_set_parity"] is True
    assert result["evaluation_ready"] is True
    assert len(result["chunk_count_differences"]) == 1


def test_missing_document_and_generation_difference_are_reported() -> None:
    current = [
        _row("s3://bucket/shared.pdf", "generation-1", 10),
        _row("s3://bucket/current-only.pdf", "generation-2", 5),
    ]
    vnext = [_row("s3://bucket/shared.pdf", "generation-9", 12)]

    result = compare_inventories(current, vnext)

    assert result["document_set_parity"] is False
    assert result["evaluation_ready"] is False
    assert result["current_only_documents"][0]["source_uri"] == (
        "s3://bucket/current-only.pdf"
    )
    assert result["generation_id_differences"][0]["vnext_ingestion_ids"] == [
        "generation-9"
    ]


def test_generation_id_difference_does_not_block_evaluation() -> None:
    result = compare_inventories(
        [_row("s3://bucket/policy.pdf", "current-generation", 10)],
        [_row("s3://bucket/policy.pdf", "vnext-generation", 10)],
    )

    assert result["source_set_parity"] is True
    assert result["metadata_parity"] is True
    assert result["evaluation_ready"] is True
    assert len(result["generation_id_differences"]) == 1


def test_metadata_mismatch_and_missing_mapping_block_evaluation() -> None:
    current = [_row("s3://bucket/policy.pdf", "generation-1", 10)]
    vnext = [_row("s3://bucket/policy.pdf", "generation-2", 10)]
    vnext[0]["document_version"] = ""

    result = compare_inventories(
        current,
        vnext,
        current_available_fields={
            "source_uri",
            "country",
            "language",
            "document_type",
            "access_scope",
            "logical_document_id",
            "document_version",
            "effective_date",
        },
        vnext_available_fields={
            "source_uri",
            "country",
            "language",
            "document_type",
            "access_scope",
            "document_version",
        },
    )

    assert result["source_set_parity"] is True
    assert result["metadata_parity"] is False
    assert result["evaluation_ready"] is False
    assert result["vnext_unavailable_metadata_fields"] == [
        "effective_date",
        "logical_document_id",
    ]
    assert result["metadata_mismatches"][0]["differences"][
        "document_version"
    ] == {"current": ["2026.1"], "vnext": [""]}
