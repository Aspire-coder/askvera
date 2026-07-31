from __future__ import annotations

from contextlib import contextmanager

from scripts import run_db_migrations


class _Result:
    def __init__(self, *, scalar_value=None, rows=None):
        self._scalar_value = scalar_value
        self._rows = rows or []

    def scalar(self):
        return self._scalar_value

    def mappings(self):
        return self._rows


class _Connection:
    def __init__(self):
        self.statements: list[str] = []

    def execute(self, statement, _params=None):
        sql = str(statement)
        self.statements.append(sql)
        if "to_regclass" in sql:
            return _Result(scalar_value=None)
        raise AssertionError(f"Dry-run unexpectedly executed SQL: {sql}")


class _Engine:
    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def begin(self):
        yield self.connection


def test_migration_dry_run_does_not_create_tracking_table(
    monkeypatch,
    tmp_path,
) -> None:
    migration = tmp_path / "001_test.sql"
    migration.write_text("CREATE TABLE example (id TEXT);", encoding="utf-8")
    connection = _Connection()
    monkeypatch.setattr(run_db_migrations, "MIGRATIONS_DIR", tmp_path)
    monkeypatch.setattr(
        run_db_migrations,
        "init_db",
        lambda _correlation_id: _Engine(connection),
    )

    pending = run_db_migrations.apply_migrations(dry_run=True)

    assert pending == ["001_test.sql"]
    assert len(connection.statements) == 1
    assert "to_regclass" in connection.statements[0]
