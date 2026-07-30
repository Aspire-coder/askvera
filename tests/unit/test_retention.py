"""Tests for independent operational-data retention policies."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from services import retention
from utils.exceptions import AwsServiceError


class FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, int]]] = []

    def execute(self, statement, params):
        sql = str(statement)
        self.calls.append((sql, params))
        return SimpleNamespace(rowcount=2)


class FakeEngine:
    def __init__(self) -> None:
        self.connection = FakeConnection()

    @contextmanager
    def begin(self):
        yield self.connection


def test_cleanup_uses_independent_retention_windows(monkeypatch) -> None:
    engine = FakeEngine()
    monkeypatch.setattr(retention, "get_engine", lambda: engine)
    monkeypatch.setattr(retention.settings, "RETRIEVAL_SHADOW_RETENTION_DAYS", 11)
    monkeypatch.setattr(retention.settings, "CHAT_ANALYTICS_RETENTION_DAYS", 22)
    monkeypatch.setattr(retention.settings, "FEEDBACK_RETENTION_DAYS", 33)
    monkeypatch.setattr(retention.settings, "SUPPORT_REQUEST_RETENTION_DAYS", 44)
    monkeypatch.setattr(retention.settings, "INGESTION_JOB_RETENTION_DAYS", 55)
    monkeypatch.setattr(retention.settings, "CONSENT_LOG_RETENTION_DAYS", 66)
    monkeypatch.setattr(retention.settings, "CHAT_TRANSCRIPT_RETENTION_DAYS", 77)

    result = retention.cleanup_retained_data(batch_size=3)

    assert set(result) == {
        "retrieval_shadow_comparisons",
        "chat_analytics",
        "feedback_events",
        "support_requests",
        "ingestion_jobs",
        "consent_log",
        "chat_sessions",
    }
    assert [params["retention_days"] for _, params in engine.connection.calls] == [11, 22, 33, 44, 55, 66, 77]
    ingestion_sql = next(sql for sql, _ in engine.connection.calls if "DELETE FROM ingestion_jobs" in sql)
    assert "completed" in ingestion_sql
    assert "failed" in ingestion_sql


def test_cleanup_rejects_disabled_retention_window(monkeypatch) -> None:
    monkeypatch.setattr(retention, "get_engine", FakeEngine)
    monkeypatch.setattr(retention.settings, "RETRIEVAL_SHADOW_RETENTION_DAYS", 0)

    with pytest.raises(AwsServiceError, match="retention cleanup"):
        retention.cleanup_retained_data()
