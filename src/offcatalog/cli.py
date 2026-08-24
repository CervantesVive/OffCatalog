import os
from pathlib import Path

import typer

from offcatalog.db.connection import get_connection
from offcatalog.db.repository import upsert_file, upsert_local_track
from offcatalog.scanning.extract import extract_local_track

app = typer.Typer(help="Scan an MP3 collection and find tracks not on streaming.")


@app.callback()
def _main() -> None:
    """OffCatalog: find local tracks not available on streaming providers."""


@app.command()
def scan(
    path: str = typer.Argument(".", help="Directory to scan for .mp3 files"),
    db: str = typer.Option("offcatalog.db", "--db", help="Path to the SQLite database"),
) -> None:
    conn = get_connection(db)
    added = 0
    errors = 0
    for root, _dirs, filenames in os.walk(path):
        for filename in filenames:
            if not filename.lower().endswith(".mp3"):
                continue
            file_path = str(Path(root) / filename)
            try:
                stat = os.stat(file_path)
                track = extract_local_track(file_path)
                file_id = upsert_file(conn, file_path, stat.st_mtime, stat.st_size, track.fingerprint)
                upsert_local_track(conn, file_id, track)
            except Exception as exc:
                errors += 1
                typer.echo(f"Skipping {file_path}: {exc}", err=True)
                continue
            added += 1
    typer.echo(f"Scanned {added} track(s), {errors} error(s) -> {db}")
    conn.close()


if __name__ == "__main__":
    app()
