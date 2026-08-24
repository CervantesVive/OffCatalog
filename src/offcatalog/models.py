from __future__ import annotations

import hashlib
from dataclasses import dataclass, fields


@dataclass(frozen=True)
class RawTags:
    artist: str | None
    title: str | None
    album: str | None
    album_artist: str | None
    track_number: str | None
    disc_number: str | None
    year: str | None
    isrc: str | None
    musicbrainz_track_id: str | None
    musicbrainz_recording_id: str | None


@dataclass
class LocalTrack:
    id: str
    path: str
    filename: str
    raw: RawTags
    artist: str
    album_artist: str | None
    title: str
    album: str | None
    version_qualifiers: list[str]
    track_number: int | None
    disc_number: int | None
    duration_seconds: float
    year: int | None
    isrc: str | None
    musicbrainz_track_id: str | None
    musicbrainz_recording_id: str | None
    fingerprint: str


def compute_fingerprint(raw: RawTags, duration_seconds: float, file_size: int) -> str:
    parts = [str(getattr(raw, f.name)) for f in fields(raw)]
    parts.append(f"{duration_seconds:.3f}")
    parts.append(str(file_size))
    digest_input = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(digest_input).hexdigest()
