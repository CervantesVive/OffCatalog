import json
import os
from pathlib import Path

import typer

from offcatalog.db.connection import get_connection
from offcatalog.db.repository import (
    get_availability_state,
    get_file_by_path,
    record_check_result,
    soft_delete_missing_files,
    upsert_file,
    upsert_local_track,
)
from offcatalog.matching.engine import match_track
from offcatalog.matching.types import AvailabilityState
from offcatalog.models import LocalTrack, RawTags
from offcatalog.providers.deezer import DeezerProvider
from offcatalog.scanning.extract import extract_local_track

app = typer.Typer(help="Scan an MP3 collection and find tracks not on streaming.")


def _row_to_track(row) -> LocalTrack:
    raw = json.loads(row["raw_tags_json"])
    return LocalTrack(
        id=row["id"], path="", filename="", raw=RawTags(**raw),
        artist=row["artist"], album_artist=row["album_artist"], title=row["title"],
        album=row["album"], version_qualifiers=json.loads(row["version_qualifiers"]),
        track_number=row["track_number"], disc_number=row["disc_number"],
        duration_seconds=row["duration_seconds"], year=row["year"], isrc=row["isrc"],
        musicbrainz_track_id=row["musicbrainz_track_id"],
        musicbrainz_recording_id=row["musicbrainz_recording_id"],
        fingerprint="",
    )


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
    skipped = 0
    errors = 0
    seen_paths: set[str] = set()
    for root, _dirs, filenames in os.walk(path):
        for filename in filenames:
            if not filename.lower().endswith(".mp3"):
                continue
            file_path = str(Path(root) / filename)
            seen_paths.add(file_path)
            try:
                stat = os.stat(file_path)

                existing = get_file_by_path(conn, file_path)
                if (
                    existing
                    and existing["deleted_at"] is None
                    and existing["mtime"] == stat.st_mtime
                    and existing["size"] == stat.st_size
                ):
                    skipped += 1
                    continue

                track = extract_local_track(file_path)
                file_id = upsert_file(conn, file_path, stat.st_mtime, stat.st_size, track.fingerprint)
                upsert_local_track(conn, file_id, track)
            except Exception as exc:
                errors += 1
                typer.echo(f"Skipping {file_path}: {exc}", err=True)
                continue
            added += 1
    deleted = soft_delete_missing_files(conn, seen_paths)
    typer.echo(
        f"Scanned: {added} added/changed, {skipped} unchanged, {deleted} deleted, {errors} error(s) -> {db}"
    )
    conn.close()


@app.command()
def check(
    db: str = typer.Option("offcatalog.db", "--db", help="Path to the SQLite database"),
    limit: int | None = typer.Option(None, "--limit", help="Max tracks to check this run"),
) -> None:
    conn = get_connection(db)
    provider = DeezerProvider()
    rows = conn.execute("SELECT * FROM local_tracks").fetchall()

    checked = 0
    for row in rows:
        if limit is not None and checked >= limit:
            break
        if get_availability_state(conn, row["id"], provider.name) != AvailabilityState.NOT_CHECKED.value:
            continue
        track = _row_to_track(row)
        result = match_track(track, provider)
        record_check_result(conn, track.id, provider.name, result)
        typer.echo(f"{row['artist']} - {row['title']}: {result.state.value} ({result.reason})")
        checked += 1

    typer.echo(f"Checked {checked} track(s)")
    conn.close()


if __name__ == "__main__":
    app()
