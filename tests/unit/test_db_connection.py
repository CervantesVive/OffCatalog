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
    get_connection(db_path).close()
    conn = get_connection(db_path)  # must not error re-applying
    count = conn.execute("SELECT COUNT(*) AS c FROM schema_migrations").fetchone()["c"]
    assert count == 1
    conn.close()
