from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _apply_migrations(conn)
    return conn


def _apply_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}

    for migration_file in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        version = int(migration_file.name.split("_", 1)[0])
        if version in applied:
            continue
        conn.executescript(migration_file.read_text())
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
