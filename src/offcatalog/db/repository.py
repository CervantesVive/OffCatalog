from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from offcatalog.matching.types import AvailabilityState, MatchResult
from offcatalog.models import LocalTrack


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_file(conn: sqlite3.Connection, path: str, mtime: float, size: int, fingerprint: str) -> str:
    existing = conn.execute("SELECT id FROM files WHERE path = ?", (path,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE files SET mtime=?, size=?, fingerprint=?, last_scanned_at=?, deleted_at=NULL WHERE id=?",
            (mtime, size, fingerprint, _now(), existing["id"]),
        )
        conn.commit()
        return existing["id"]

    file_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO files (id, path, mtime, size, fingerprint, last_scanned_at) VALUES (?,?,?,?,?,?)",
        (file_id, path, mtime, size, fingerprint, _now()),
    )
    conn.commit()
    return file_id


def upsert_local_track(conn: sqlite3.Connection, file_id: str, track: LocalTrack) -> None:
    # A file has at most one local_tracks row. extract_local_track() assigns a fresh
    # random id on every call, so reuse the existing row's id (if any) for this file_id
    # rather than track.id, otherwise every re-scan of an unchanged file would insert a
    # duplicate row instead of updating in place.
    existing = conn.execute(
        "SELECT id FROM local_tracks WHERE file_id = ?", (file_id,)
    ).fetchone()
    track_id = existing["id"] if existing else track.id

    conn.execute(
        """
        INSERT INTO local_tracks (
            id, file_id, artist, album_artist, title, album, version_qualifiers,
            track_number, disc_number, duration_seconds, year, isrc,
            musicbrainz_track_id, musicbrainz_recording_id, raw_tags_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            file_id=excluded.file_id, artist=excluded.artist, album_artist=excluded.album_artist,
            title=excluded.title, album=excluded.album, version_qualifiers=excluded.version_qualifiers,
            track_number=excluded.track_number, disc_number=excluded.disc_number,
            duration_seconds=excluded.duration_seconds, year=excluded.year, isrc=excluded.isrc,
            musicbrainz_track_id=excluded.musicbrainz_track_id,
            musicbrainz_recording_id=excluded.musicbrainz_recording_id,
            raw_tags_json=excluded.raw_tags_json
        """,
        (
            track_id, file_id, track.artist, track.album_artist, track.title, track.album,
            json.dumps(track.version_qualifiers), track.track_number, track.disc_number,
            track.duration_seconds, track.year, track.isrc, track.musicbrainz_track_id,
            track.musicbrainz_recording_id, json.dumps(asdict(track.raw)),
        ),
    )
    conn.commit()
    conn.commit()


def get_file_by_path(conn: sqlite3.Connection, path: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM files WHERE path = ?", (path,)).fetchone()


def soft_delete_missing_files(conn: sqlite3.Connection, seen_paths: set[str]) -> int:
    rows = conn.execute("SELECT id, path FROM files WHERE deleted_at IS NULL").fetchall()
    deleted = 0
    for row in rows:
        if row["path"] not in seen_paths:
            conn.execute("UPDATE files SET deleted_at = ? WHERE id = ?", (_now(), row["id"]))
            deleted += 1
    conn.commit()
    return deleted


def get_provider_id(conn: sqlite3.Connection, name: str) -> str:
    row = conn.execute("SELECT id FROM providers WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    provider_id = str(uuid.uuid4())
    conn.execute("INSERT INTO providers (id, name) VALUES (?, ?)", (provider_id, name))
    conn.commit()
    return provider_id


def record_check_result(conn: sqlite3.Connection, local_track_id: str, provider_name: str, result: MatchResult) -> None:
    provider_id = get_provider_id(conn, provider_name)
    best_candidate_id = None

    if result.candidate is not None:
        best_candidate_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO provider_candidates (
                id, local_track_id, provider_id, provider_track_id, provider_artist,
                provider_title, provider_album, provider_duration, match_score, match_reason, checked_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                best_candidate_id, local_track_id, provider_id,
                result.candidate["provider_track_id"], result.candidate["artist"],
                result.candidate["title"], result.candidate.get("album"),
                result.candidate["duration_seconds"], result.score, result.reason, _now(),
            ),
        )

    conn.execute(
        """
        INSERT INTO availability_results (local_track_id, provider_id, state, best_candidate_id, checked_at, error_message)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(local_track_id, provider_id) DO UPDATE SET
            state=excluded.state, best_candidate_id=excluded.best_candidate_id,
            checked_at=excluded.checked_at, error_message=excluded.error_message
        """,
        (local_track_id, provider_id, result.state.value, best_candidate_id, _now(), result.error_message),
    )
    conn.commit()


def get_availability_state(conn: sqlite3.Connection, local_track_id: str, provider_name: str) -> str:
    provider_id = get_provider_id(conn, provider_name)
    row = conn.execute(
        "SELECT state FROM availability_results WHERE local_track_id = ? AND provider_id = ?",
        (local_track_id, provider_id),
    ).fetchone()
    return row["state"] if row else AvailabilityState.NOT_CHECKED.value
