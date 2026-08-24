from __future__ import annotations

import os
import re
import uuid

from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3

from offcatalog.models import LocalTrack, RawTags, compute_fingerprint
from offcatalog.normalize import extract_qualifiers, normalize_text


def _first(tags: EasyID3, key: str) -> str | None:
    values = tags.get(key)
    return values[0] if values else None


def _to_int(value: str | None) -> int | None:
    if not value:
        return None
    digits = "".join(ch for ch in value.split("/")[0] if ch.isdigit())
    return int(digits) if digits else None


_YEAR_RE = re.compile(r"^\d{4}")


def _parse_year(value: str | None) -> int | None:
    if not value:
        return None
    match = _YEAR_RE.match(value)
    return int(match.group()) if match else None


def extract_local_track(path: str) -> LocalTrack:
    audio = MP3(path, ID3=EasyID3)
    tags = audio.tags or EasyID3()

    raw = RawTags(
        artist=_first(tags, "artist"),
        title=_first(tags, "title"),
        album=_first(tags, "album"),
        album_artist=_first(tags, "albumartist"),
        track_number=_first(tags, "tracknumber"),
        disc_number=_first(tags, "discnumber"),
        year=_first(tags, "date"),
        isrc=_first(tags, "isrc"),
        musicbrainz_track_id=_first(tags, "musicbrainz_trackid"),
        musicbrainz_recording_id=_first(tags, "musicbrainz_recordingid"),
    )

    extracted_title = extract_qualifiers(raw.title or "")
    duration_seconds = float(audio.info.length)
    file_size = os.path.getsize(path)
    fingerprint = compute_fingerprint(raw, duration_seconds, file_size)

    return LocalTrack(
        id=str(uuid.uuid4()),
        path=path,
        filename=os.path.basename(path),
        raw=raw,
        artist=normalize_text(raw.artist or ""),
        album_artist=normalize_text(raw.album_artist) if raw.album_artist else None,
        title=extracted_title.base_title,
        album=normalize_text(raw.album) if raw.album else None,
        version_qualifiers=extracted_title.qualifiers,
        track_number=_to_int(raw.track_number),
        disc_number=_to_int(raw.disc_number),
        duration_seconds=duration_seconds,
        year=_parse_year(raw.year),
        isrc=raw.isrc,
        musicbrainz_track_id=raw.musicbrainz_track_id,
        musicbrainz_recording_id=raw.musicbrainz_recording_id,
        fingerprint=fingerprint,
    )
