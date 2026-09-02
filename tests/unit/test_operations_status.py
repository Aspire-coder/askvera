"""Tests for the operations-status low-chunk-coverage safety net."""

from unittest.mock import MagicMock

from services import operations_status


def test_low_coverage_documents_queries_active_documents_below_threshold(monkeypatch) -> None:
    rows = [
        {"filename": "Sparse-Directory.pdf", "country": "GLOBAL", "document_type": "office_directory", "section_count": 1, "logical_document_id": "doc-1"},
    ]
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value = rows
    connection.__enter__.return_value = connection
    connection.__exit__.return_value = False
    engine = MagicMock()
    engine.connect.return_value = connection
    monkeypatch.setattr(operations_status, "get_engine", lambda: engine)
    monkeypatch.setattr(operations_status.settings, "ADMIN_INGESTION_LOW_COVERAGE_THRESHOLD", 2)

    result = operations_status._low_coverage_documents()

    assert result == rows
    query_args = connection.execute.call_args.args
    assert "section_count < :threshold" in str(query_args[0])
    params = connection.execute.call_args.args[1]
    assert params["threshold"] == 2


def test_low_coverage_documents_fails_open_on_database_error(monkeypatch) -> None:
    monkeypatch.setattr(
        operations_status,
        "get_engine",
        lambda: (_ for _ in ()).throw(RuntimeError("db unavailable")),
    )

    assert operations_status._low_coverage_documents() == []


def test_operations_status_surfaces_low_coverage_count_and_action(monkeypatch) -> None:
    low_coverage_doc = {
        "filename": "Sparse-Directory.pdf",
        "country": "GLOBAL",
        "document_type": "office_directory",
        "section_count": 1,
        "logical_document_id": "doc-1",
    }
    monkeypatch.setattr(operations_status, "list_ingestion_jobs", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(operations_status, "_low_coverage_documents", lambda: [low_coverage_doc])
    monkeypatch.setattr(operations_status, "_check_database", lambda: {"status": "healthy", "detail": ""})
    monkeypatch.setattr(operations_status, "_check_cache", lambda: {"status": "healthy", "detail": ""})
    monkeypatch.setattr(
        operations_status.metrics_collector,
        "health_summary",
        lambda: MagicMock(
            status="healthy",
            cache_hit_ratio=1.0,
            retrieval_failure_rate=0.0,
            validation_failures=0,
            audit_queue_depth=0,
        ),
    )

    status = operations_status.operations_status()

    assert status["knowledge_sync"]["low_coverage_documents"] == 1
    assert any(
        "Sparse-Directory.pdf" in action["label"] and "1 chunk" in action["reason"]
        for action in status["assigned_actions"]
    )
