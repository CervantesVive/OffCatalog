import json

from offcatalog.db.connection import get_connection
from offcatalog.db.repository import (
    get_availability_state,
    get_provider_id,
    record_check_result,
    upsert_file,
    upsert_local_track,
)
from offcatalog.matching.types import AvailabilityState, MatchResult
from offcatalog.models import LocalTrack, RawTags


def make_track(**overrides) -> LocalTrack:
    base = dict(
        id="t1", path="/x.mp3", filename="x.mp3",
        raw=RawTags("Depeche Mode", "Enjoy the Silence", "Violator", None, "3", None, "1990",
                     None, None, None),
        artist="depeche mode", album_artist=None, title="enjoy the silence",
        album="violator", version_qualifiers=[], track_number=3, disc_number=None,
        duration_seconds=258.0, year=1990, isrc=None,
        musicbrainz_track_id=None, musicbrainz_recording_id=None, fingerprint="fp1",
    )
    base.update(overrides)
    return LocalTrack(**base)


def test_upsert_file_then_track_roundtrip(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    file_id = upsert_file(conn, "/x.mp3", mtime=123.0, size=1000, fingerprint="fp1")
    upsert_local_track(conn, file_id, make_track())

    row = conn.execute("SELECT * FROM local_tracks WHERE id = ?", (make_track().id,)).fetchone()
    assert row["artist"] == "depeche mode"
    assert json.loads(row["version_qualifiers"]) == []


def test_upsert_file_is_idempotent_on_path(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    id1 = upsert_file(conn, "/x.mp3", mtime=1.0, size=1, fingerprint="a")
    id2 = upsert_file(conn, "/x.mp3", mtime=2.0, size=2, fingerprint="b")
    assert id1 == id2
    row = conn.execute("SELECT fingerprint FROM files WHERE id = ?", (id1,)).fetchone()
    assert row["fingerprint"] == "b"


def test_record_check_result_and_read_back(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    file_id = upsert_file(conn, "/x.mp3", mtime=1.0, size=1, fingerprint="fp1")
    track = make_track()
    upsert_local_track(conn, file_id, track)

    result = MatchResult(
        state=AvailabilityState.AVAILABLE, score=1.0, reason="isrc_exact",
        candidate={"provider_track_id": "1", "artist": "Depeche Mode", "title": "Enjoy the Silence",
                   "album": "Violator", "duration_seconds": 258.0, "isrc": "GBAYE9000212"},
        all_candidates=[],
    )
    record_check_result(conn, track.id, "deezer", result)

    assert get_availability_state(conn, track.id, "deezer") == "AVAILABLE"


def test_unchecked_track_reports_not_checked(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    get_provider_id(conn, "deezer")
    assert get_availability_state(conn, "nonexistent", "deezer") == "NOT_CHECKED"
