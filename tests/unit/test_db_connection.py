import pytest

from offcatalog.db import connection as connection_module
from offcatalog.db.connection import get_connection


def test_get_connection_applies_migrations(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    tables = {row["name"] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert {"files", "local_tracks", "providers", "provider_candidates",
            "availability_results", "manual_match_decisions", "scan_runs",
            "schema_migrations"} <= tables
    conn.close()


def test_get_connection_is_idempotent(tmp_path):
    db_path = str(tmp_path / "test.db")
    first = get_connection(db_path)
    expected = first.execute("SELECT COUNT(*) AS c FROM schema_migrations").fetchone()["c"]
    first.close()
    conn = get_connection(db_path)  # must not error re-applying, and must not re-insert rows
    count = conn.execute("SELECT COUNT(*) AS c FROM schema_migrations").fetchone()["c"]
    assert count == expected
    conn.close()


def test_duplicate_migration_versions_raises_error(tmp_path, monkeypatch):
    """Regression test: duplicate migration versions must raise ValueError before any DDL executes."""
    # Create a temporary migrations directory with colliding version numbers
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()

    # Write two migrations with the same version prefix
    (migrations_dir / "0001_a.sql").write_text("CREATE TABLE test_table_a (id INTEGER);")
    (migrations_dir / "0001_b.sql").write_text("CREATE TABLE test_table_b (id INTEGER);")

    # Create a test database in a different location
    db_path = str(tmp_path / "test.db")

    # Monkeypatch _MIGRATIONS_DIR to point to our collision directory
    monkeypatch.setattr(connection_module, "_MIGRATIONS_DIR", migrations_dir)

    # Attempting to get_connection should raise ValueError
    with pytest.raises(ValueError, match="Duplicate migration version"):
        get_connection(db_path)

    # Verify no user-created tables exist (only schema_migrations from the CREATE TABLE IF NOT EXISTS)
    import sqlite3
    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()

    # Only schema_migrations should exist; test tables should NOT exist
    assert "test_table_a" not in tables
    assert "test_table_b" not in tables
