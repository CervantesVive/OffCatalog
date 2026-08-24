import json
import os
from pathlib import Path

import typer

from offcatalog.db.connection import get_connection
from offcatalog.db.repository import (
    get_availability_state,
    get_file_by_path,
    list_ambiguous_tracks,
    list_candidates_for_track,
    record_check_result,
    record_manual_decision,
    soft_delete_missing_files,
    upsert_file,
    upsert_local_track,
)
from offcatalog.matching.engine import match_track
from offcatalog.matching.types import AvailabilityState
from offcatalog.models import LocalTrack, RawTags
from offcatalog.providers.deezer import DeezerProvider
from offcatalog.ratelimit import TokenBucket
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
    provider_name: str = typer.Option("deezer", "--provider", help="Provider to check against"),
    retry_errors: bool = typer.Option(False, "--retry-errors", help="Re-check tracks currently in ERROR state"),
) -> None:
    conn = get_connection(db)
    rate_limiter = TokenBucket(rate=45, per_seconds=5.0)
    provider = DeezerProvider(rate_limiter=rate_limiter)
    rows = conn.execute("SELECT * FROM local_tracks").fetchall()

    needs_check_states = {AvailabilityState.NOT_CHECKED.value}
    if retry_errors:
        needs_check_states.add(AvailabilityState.ERROR.value)

    checked = 0
    for row in rows:
        if limit is not None and checked >= limit:
            break
        current_state = get_availability_state(conn, row["id"], provider_name)
        if current_state not in needs_check_states:
            continue
        track = _row_to_track(row)
        result = match_track(track, provider)
        record_check_result(conn, track.id, provider_name, result)
        typer.echo(f"{row['artist']} - {row['title']}: {result.state.value} ({result.reason})")
        checked += 1

    typer.echo(f"Checked {checked} track(s)")
    conn.close()


@app.command()
def review(
    db: str = typer.Option("offcatalog.db", "--db", help="Path to the SQLite database"),
    provider_name: str = typer.Option("deezer", "--provider", help="Provider whose ambiguous matches to review"),
) -> None:
    conn = get_connection(db)
    tracks = list_ambiguous_tracks(conn, provider_name)

    for track_row in tracks:
        typer.echo(f"\nLocal:  {track_row['artist']} - {track_row['title']} ({track_row['duration_seconds']}s)")
        candidates = list_candidates_for_track(conn, track_row["id"], provider_name)
        for i, candidate in enumerate(candidates):
            typer.echo(
                f"  [{i}] {candidate['provider_artist']} - {candidate['provider_title']} "
                f"({candidate['provider_duration']}s) score={candidate['match_score']:.2f}"
            )

        choice = typer.prompt("[s]ame / [d]ifferent / [k]ip", default="k")
        if choice == "s" and candidates:
            record_manual_decision(conn, track_row["id"], candidates[0]["id"], "same_recording")
        elif choice == "d" and candidates:
            record_manual_decision(conn, track_row["id"], candidates[0]["id"], "different_recording")

    conn.close()


if __name__ == "__main__":
    app()
