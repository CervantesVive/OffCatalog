import json
import os
from collections import Counter
from pathlib import Path

import typer

from offcatalog.db.connection import get_connection
from offcatalog.db.repository import (
    compute_state_counts,
    get_availability_state,
    get_checked_fingerprint,
    get_file_by_path,
    get_file_path_for_track,
    get_musicbrainz_checked_fingerprint,
    list_ambiguous_tracks,
    list_candidates_for_track,
    list_tracks_by_state,
    list_unavailable_everywhere,
    record_check_result,
    record_manual_decision,
    record_musicbrainz_enrichment,
    soft_delete_missing_files,
    upsert_file,
    upsert_local_track,
)
from offcatalog.matching.engine import match_track
from offcatalog.matching.types import AvailabilityState
from offcatalog.models import LocalTrack, RawTags
from offcatalog.musicbrainz.client import MBRecording, MusicBrainzClient
from offcatalog.playlist import write_m3u8
from offcatalog.providers.base import PROVIDER_REGISTRY
from offcatalog.providers.deezer import DeezerProvider
from offcatalog.ratelimit import TokenBucket
from offcatalog.reports import write_csv_report
from offcatalog.scanning.extract import extract_local_track

app = typer.Typer(help="Scan an MP3 collection and find tracks not on streaming.")

_MB_SCORE_FLOOR = 90.0
_MB_DURATION_TOLERANCE_SECONDS = 4.0  # mirrors matching.engine's default duration gate


def _row_to_track(row) -> LocalTrack:
    raw = json.loads(row["raw_tags_json"])
    return LocalTrack(
        id=row["id"],
        path="",
        filename="",
        raw=RawTags(**raw),
        artist=row["artist"],
        album_artist=row["album_artist"],
        title=row["title"],
        album=row["album"],
        version_qualifiers=json.loads(row["version_qualifiers"]),
        track_number=row["track_number"],
        disc_number=row["disc_number"],
        duration_seconds=row["duration_seconds"],
        year=row["year"],
        isrc=row["isrc"] or row["musicbrainz_isrc"],
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
    db: str = typer.Option(
        "offcatalog.db",
        "--db",
        envvar="OFFCATALOG_DB",
        help="Path to the SQLite database",
    ),
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
                file_id = upsert_file(
                    conn, file_path, stat.st_mtime, stat.st_size, track.fingerprint
                )
                upsert_local_track(conn, file_id, track)
            except Exception as exc:  # noqa: BLE001 — per-file isolation: one corrupt/unreadable
                # MP3 anywhere in a 15k+ track tree must not abort the whole scan; mutagen and
                # the stdlib can raise many distinct exception types for a bad file.
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
def enrich(
    db: str = typer.Option(
        "offcatalog.db",
        "--db",
        envvar="OFFCATALOG_DB",
        help="Path to the SQLite database",
    ),
    limit: int | None = typer.Option(
        None, "--limit", help="Max tracks to enrich this run"
    ),
) -> None:
    conn = get_connection(db)
    rate_limiter = TokenBucket(rate=1, per_seconds=1.0)
    client = MusicBrainzClient(rate_limiter=rate_limiter)
    rows = conn.execute(
        "SELECT lt.*, f.fingerprint AS current_fingerprint "
        "FROM local_tracks lt JOIN files f ON f.id = lt.file_id"
    ).fetchall()

    enriched = 0
    found = 0
    errors = 0
    for row in rows:
        if limit is not None and enriched >= limit:
            break
        fingerprint = row["current_fingerprint"]
        if get_musicbrainz_checked_fingerprint(conn, row["id"]) == fingerprint:
            continue
        try:
            track = _row_to_track(row)
            if track.musicbrainz_recording_id:
                recording = client.lookup_by_mbid(track.musicbrainz_recording_id)
            else:
                recording = _search_best_recording(client, track)
            isrc = recording["isrc"] if recording else None
            disambiguation = recording["disambiguation"] if recording else None
            record_musicbrainz_enrichment(
                conn, row["id"], isrc, disambiguation, fingerprint
            )
        except Exception as exc:  # noqa: BLE001 — per-track isolation, same as check()
            errors += 1
            typer.echo(f"Skipping {row['artist']} - {row['title']}: {exc}", err=True)
            continue
        if isrc:
            found += 1
        enriched += 1

    typer.echo(f"Enriched {enriched} track(s), {found} ISRC(s) found, {errors} error(s)")
    conn.close()


def _search_best_recording(
    client: MusicBrainzClient, track: LocalTrack
) -> MBRecording | None:
    candidates = client.search_recording(track)
    best: MBRecording | None = None
    for candidate in candidates:
        if candidate["score"] < _MB_SCORE_FLOOR:
            continue
        if candidate["duration_seconds"] is None:
            continue
        if (
            abs(candidate["duration_seconds"] - track.duration_seconds)
            > _MB_DURATION_TOLERANCE_SECONDS
        ):
            continue
        if best is None or candidate["score"] > best["score"]:
            best = candidate
    if best is None:
        return None
    # search results never carry an ISRC (live-verified) -- resolve it with a
    # second, exact lookup on the chosen candidate's MBID.
    return client.lookup_by_mbid(best["mbid"])


@app.command()
def check(
    db: str = typer.Option(
        "offcatalog.db",
        "--db",
        envvar="OFFCATALOG_DB",
        help="Path to the SQLite database",
    ),
    limit: int | None = typer.Option(
        None, "--limit", help="Max tracks to check this run"
    ),
    provider_name: str = typer.Option(
        "deezer", "--provider", help="Provider to check against"
    ),
    retry_errors: bool = typer.Option(
        False, "--retry-errors", help="Re-check tracks currently in ERROR state"
    ),
) -> None:
    # Validate before get_connection/get_provider_id: an unknown name would otherwise
    # be lazily INSERTed into `providers`, permanently inflating the provider count
    # that list_unavailable_everywhere requires every track to satisfy — silently
    # emptying every future playlist with no CLI way to undo it.
    if provider_name not in PROVIDER_REGISTRY:
        known = ", ".join(sorted(PROVIDER_REGISTRY))
        typer.echo(
            f"Unknown provider {provider_name!r}. Known providers: {known}", err=True
        )
        raise typer.Exit(code=1)

    conn = get_connection(db)
    rate_limiter = TokenBucket(rate=45, per_seconds=5.0)
    provider = DeezerProvider(rate_limiter=rate_limiter)
    rows = conn.execute(
        "SELECT lt.*, f.fingerprint AS current_fingerprint "
        "FROM local_tracks lt JOIN files f ON f.id = lt.file_id"
    ).fetchall()

    needs_check_states = {AvailabilityState.NOT_CHECKED.value}
    if retry_errors:
        needs_check_states.add(AvailabilityState.ERROR.value)

    checked = 0
    errors = 0
    for row in rows:
        if limit is not None and checked >= limit:
            break
        current_state = get_availability_state(conn, row["id"], provider_name)
        fingerprint = row["current_fingerprint"]
        # Retagging a file (adding a missing ISRC, fixing a wrong title — the exact
        # corrective action this tool's reports prompt) changes its fingerprint and
        # must invalidate the stored verdict.
        stale = get_checked_fingerprint(conn, row["id"], provider_name) != fingerprint
        if current_state not in needs_check_states and not stale:
            continue
        try:
            track = _row_to_track(row)
            result = match_track(track, provider)
            record_check_result(
                conn, track.id, provider_name, result, checked_fingerprint=fingerprint
            )
        except Exception as exc:  # noqa: BLE001 — per-track isolation: one malformed
            # provider payload or unreadable row must not abort a multi-hour run and
            # lose every track still unprocessed.
            errors += 1
            typer.echo(f"Skipping {row['artist']} - {row['title']}: {exc}", err=True)
            continue
        typer.echo(
            f"{row['artist']} - {row['title']}: {result.state.value} ({result.reason})"
        )
        checked += 1

    typer.echo(f"Checked {checked} track(s), {errors} error(s)")
    conn.close()


@app.command()
def review(
    db: str = typer.Option(
        "offcatalog.db",
        "--db",
        envvar="OFFCATALOG_DB",
        help="Path to the SQLite database",
    ),
    provider_name: str = typer.Option(
        "deezer", "--provider", help="Provider whose ambiguous matches to review"
    ),
) -> None:
    # Same guard as check(): an unknown name would otherwise be lazily INSERTed
    # into `providers` via list_ambiguous_tracks -> get_provider_id, permanently
    # inflating the provider count that list_unavailable_everywhere requires
    # every track to satisfy — silently emptying every future playlist.
    if provider_name not in PROVIDER_REGISTRY:
        known = ", ".join(sorted(PROVIDER_REGISTRY))
        typer.echo(
            f"Unknown provider {provider_name!r}. Known providers: {known}", err=True
        )
        raise typer.Exit(code=1)

    conn = get_connection(db)
    tracks = list_ambiguous_tracks(conn, provider_name)

    for track_row in tracks:
        typer.echo(
            f"\nLocal:  {track_row['artist']} - {track_row['title']} ({track_row['duration_seconds']}s)"
        )
        mb_isrc = track_row["musicbrainz_isrc"]
        mb_disambiguation = track_row["musicbrainz_disambiguation"]
        if mb_isrc or mb_disambiguation:
            typer.echo(
                f'  MB: isrc={mb_isrc or "none"} disambiguation="{mb_disambiguation or ""}"'
            )
        candidates = list_candidates_for_track(conn, track_row["id"], provider_name)
        for i, candidate in enumerate(candidates):
            typer.echo(
                f"  [{i}] {candidate['provider_artist']} - {candidate['provider_title']} "
                f"({candidate['provider_duration']}s) score={candidate['match_score']:.2f}"
            )

        # MusicBrainz never auto-resolves a decision -- it only changes what's
        # pre-filled; the human still has to hit enter to confirm.
        default_choice = "k"
        if candidates and mb_isrc and candidates[0]["provider_isrc"] == mb_isrc:
            default_choice = "s"
        choice = typer.prompt("[s]ame / [d]ifferent / [k]ip", default=default_choice)
        if choice in ("s", "d") and candidates:
            if len(candidates) > 1:
                index = int(
                    typer.prompt(
                        f"Which candidate? [0-{len(candidates) - 1}]", default="0"
                    )
                )
            else:
                index = 0
            decision = "same_recording" if choice == "s" else "different_recording"
            record_manual_decision(
                conn, track_row["id"], candidates[index]["id"], decision
            )

    conn.close()


@app.command()
def playlist(
    db: str = typer.Option(
        "offcatalog.db",
        "--db",
        envvar="OFFCATALOG_DB",
        help="Path to the SQLite database",
    ),
    state: str = typer.Option(
        "unavailable_everywhere", "--state", help="unavailable_everywhere | ambiguous"
    ),
    output: str = typer.Option(
        "playlists/not-on-streaming.m3u8", "--output", help="Output .m3u8 path"
    ),
) -> None:
    conn = get_connection(db)
    if state == "ambiguous":
        rows = list_ambiguous_tracks(conn, "deezer")
    else:
        rows = list_unavailable_everywhere(conn)

    tracks = [{"path": get_file_path_for_track(conn, row["id"])} for row in rows]
    write_m3u8(tracks, output)
    typer.echo(f"Wrote {len(tracks)} track(s) to {output}")
    conn.close()


@app.command()
def stats(
    db: str = typer.Option(
        "offcatalog.db",
        "--db",
        envvar="OFFCATALOG_DB",
        help="Path to the SQLite database",
    ),
) -> None:
    conn = get_connection(db)
    counts = compute_state_counts(conn)
    total = sum(counts.values())
    typer.echo(f"{total} local tracks")
    for state in ["AVAILABLE", "UNAVAILABLE", "AMBIGUOUS", "NOT_CHECKED", "ERROR"]:
        typer.echo(f"  {counts.get(state, 0)} {state.lower()}")

    qualifier_counts: Counter[str] = Counter()
    for row in conn.execute(
        "SELECT lt.version_qualifiers FROM local_tracks lt "
        "JOIN files f ON f.id = lt.file_id WHERE f.deleted_at IS NULL"
    ):
        qualifier_counts.update(json.loads(row["version_qualifiers"]))
    if qualifier_counts:
        typer.echo(
            "\nCommon categories (heuristic, based on detected version qualifiers):"
        )
        for label, count in qualifier_counts.most_common(5):
            typer.echo(f"  {label}: {count}")

    # UNAVAILABLE/AMBIGUOUS: `reason` holds the matching-engine explanation
    # (e.g. "no_candidates", "fuzzy_candidate"). ERROR: `reason` is only the
    # generic "provider_error"; the actual exception text lives in
    # error_message, which is more useful in errors.csv.
    for state, filename, reason_column in [
        ("UNAVAILABLE", "unavailable.csv", "reason"),
        ("AMBIGUOUS", "ambiguous.csv", "reason"),
        ("ERROR", "errors.csv", "error_message"),
    ]:
        rows = [
            {
                "artist": r["artist"],
                "title": r["title"],
                "album": r["album"],
                "duration": r["duration_seconds"],
                "path": r["file_path"],
                "last_checked": r["checked_at"],
                "reason": r[reason_column] or "",
            }
            for r in list_tracks_by_state(conn, state)
        ]
        write_csv_report(rows, f"reports/{filename}")

    conn.close()


if __name__ == "__main__":
    app()
