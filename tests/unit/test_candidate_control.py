"""Tests for the admin-portal "current vs experimental" chat toggle storage."""

import pytest
from sqlalchemy.exc import SQLAlchemyError

from services import candidate_control
from services.candidate_control import CandidateFlags, get_candidate_flags, set_candidate_flags


@pytest.fixture(autouse=True)
def _enable_candidate_mode_lookup(monkeypatch):
    # The master switch defaults to off (config/settings.py) specifically so
    # that code elsewhere never touches the database unless an environment
    # opts in - this file is what actually exercises the read/write behavior,
    # so it turns the switch on for its own tests.
    monkeypatch.setattr(candidate_control.settings, "CANDIDATE_MODE_LOOKUP_ENABLED", True)


def _reset_cache() -> None:
    candidate_control._cached_flags = None
    candidate_control._cache_expires_at = 0.0


class _Result:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class _Connection:
    def __init__(self, row=None, raise_error: bool = False):
        self._row = row
        self._raise_error = raise_error
        self.executed: list[tuple[str, dict]] = []

    def execute(self, statement, parameters=None):
        self.executed.append((str(statement), parameters or {}))
        if self._raise_error:
            raise SQLAlchemyError("connection unavailable")
        return _Result(self._row)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Engine:
    def __init__(self, connection: _Connection):
        self._connection = connection

    def connect(self):
        return self._connection

    def begin(self):
        return self._connection


def test_get_candidate_flags_skips_database_when_master_switch_is_off(monkeypatch) -> None:
    _reset_cache()
    monkeypatch.setattr(candidate_control.settings, "CANDIDATE_MODE_LOOKUP_ENABLED", False)

    def _unexpected_engine():
        raise AssertionError("get_engine must not be called when the master switch is off")

    monkeypatch.setattr(candidate_control, "get_engine", _unexpected_engine)

    assert get_candidate_flags() == CandidateFlags()


def test_get_candidate_flags_reads_row_when_present(monkeypatch) -> None:
    _reset_cache()
    row = {
        "narrowing_fallback_enabled": True,
        "in_voice_guardrail_enabled": False,
        "wider_typo_tolerance_enabled": True,
    }
    monkeypatch.setattr(candidate_control, "get_engine", lambda: _Engine(_Connection(row=row)))

    flags = get_candidate_flags()

    assert flags == CandidateFlags(
        narrowing_fallback=True, in_voice_guardrail=False, wider_typo_tolerance=True
    )


def test_get_candidate_flags_fails_open_to_all_false_when_row_missing(monkeypatch) -> None:
    _reset_cache()
    monkeypatch.setattr(candidate_control, "get_engine", lambda: _Engine(_Connection(row=None)))

    assert get_candidate_flags() == CandidateFlags()


def test_get_candidate_flags_fails_open_to_all_false_on_db_error(monkeypatch) -> None:
    _reset_cache()
    monkeypatch.setattr(
        candidate_control, "get_engine", lambda: _Engine(_Connection(raise_error=True))
    )

    assert get_candidate_flags() == CandidateFlags()


def test_get_candidate_flags_is_cached_briefly(monkeypatch) -> None:
    _reset_cache()
    connection = _Connection(row={
        "narrowing_fallback_enabled": True,
        "in_voice_guardrail_enabled": True,
        "wider_typo_tolerance_enabled": True,
    })
    monkeypatch.setattr(candidate_control, "get_engine", lambda: _Engine(connection))

    get_candidate_flags()
    get_candidate_flags()

    assert len(connection.executed) == 1


def test_set_candidate_flags_upserts_and_invalidates_cache(monkeypatch) -> None:
    _reset_cache()
    write_connection = _Connection()
    monkeypatch.setattr(candidate_control, "get_engine", lambda: _Engine(write_connection))

    result = set_candidate_flags(
        CandidateFlags(narrowing_fallback=True, in_voice_guardrail=False, wider_typo_tolerance=False),
        updated_by="admin@example.com",
        reason="Testing Taia-inspired narrowing fallback",
    )

    assert result.narrowing_fallback is True
    sql, params = write_connection.executed[0]
    assert "INSERT INTO chat_candidate_control" in sql
    assert "ON CONFLICT (control_id) DO UPDATE" in sql
    assert params["updated_by"] == "admin@example.com"
    # A fresh read immediately after a write should reflect the write without
    # hitting the database again (cache was invalidated to the new value).
    assert get_candidate_flags() == result
