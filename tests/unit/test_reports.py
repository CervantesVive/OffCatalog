import csv

from offcatalog.db.connection import get_connection
from offcatalog.db.repository import (
    compute_state_counts,
    list_tracks_by_state,
    record_check_result,
    upsert_file,
    upsert_local_track,
)
from offcatalog.matching.types import AvailabilityState, MatchResult
from offcatalog.models import LocalTrack, RawTags
from offcatalog.reports import write_csv_report


def _seed(conn, path, state, qualifiers=None, reason="t", error_message=None):
    raw = RawTags("A", "T", None, None, None, None, None, None, None, None)
    track = LocalTrack(
        id=path,
        path=path,
        filename=path,
        raw=raw,
        artist="a",
        album_artist=None,
        title="t",
        album=None,
        version_qualifiers=qualifiers or [],
        track_number=None,
        disc_number=None,
        duration_seconds=200.0,
        year=None,
        isrc=None,
        musicbrainz_track_id=None,
        musicbrainz_recording_id=None,
        fingerprint=path,
    )
    file_id = upsert_file(conn, path, 1.0, 1, path)
    upsert_local_track(conn, file_id, track)
    record_check_result(
        conn,
        track.id,
        "deezer",
        MatchResult(
            state=state,
            score=0.0,
            reason=reason,
            candidate=None,
            all_candidates=[],
            error_message=error_message,
        ),
    )


def test_compute_state_counts(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    _seed(conn, "/a.mp3", AvailabilityState.AVAILABLE)
    _seed(conn, "/b.mp3", AvailabilityState.UNAVAILABLE)
    _seed(conn, "/c.mp3", AvailabilityState.UNAVAILABLE)
    counts = compute_state_counts(conn)
    assert counts["AVAILABLE"] == 1
    assert counts["UNAVAILABLE"] == 2
    assert counts.get("AMBIGUOUS", 0) == 0


def test_write_csv_report(tmp_path):
    output = tmp_path / "unavailable.csv"
    write_csv_report([{"artist": "A", "title": "T", "path": "/a.mp3"}], str(output))
    with open(output, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["artist"] == "A"


def test_compute_state_counts_derives_not_checked_from_unchecked_tracks(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    _seed(conn, "/a.mp3", AvailabilityState.AVAILABLE)
    _seed(conn, "/b.mp3", AvailabilityState.UNAVAILABLE)
    # A track that was scanned (in local_tracks) but never checked against
    # any provider — no availability_results row exists for it.
    raw = RawTags("A", "T", None, None, None, None, None, None, None, None)
    track = LocalTrack(
        id="/c.mp3",
        path="/c.mp3",
        filename="/c.mp3",
        raw=raw,
        artist="a",
        album_artist=None,
        title="t",
        album=None,
        version_qualifiers=[],
        track_number=None,
        disc_number=None,
        duration_seconds=200.0,
        year=None,
        isrc=None,
        musicbrainz_track_id=None,
        musicbrainz_recording_id=None,
        fingerprint="/c.mp3",
    )
    file_id = upsert_file(conn, "/c.mp3", 1.0, 1, "/c.mp3")
    upsert_local_track(conn, file_id, track)

    counts = compute_state_counts(conn)
    assert counts["NOT_CHECKED"] == 1
    assert sum(counts.values()) == 3


def test_list_tracks_by_state_returns_matching_engine_reason_for_unavailable(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    _seed(conn, "/a.mp3", AvailabilityState.UNAVAILABLE, reason="no_candidates")
    rows = list_tracks_by_state(conn, "UNAVAILABLE")
    assert rows[0]["reason"] == "no_candidates"
    assert rows[0]["error_message"] is None


def test_list_tracks_by_state_error_message_holds_real_exception_text(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    _seed(
        conn,
        "/a.mp3",
        AvailabilityState.ERROR,
        reason="provider_error",
        error_message="ConnectionError: timed out after 5s",
    )
    rows = list_tracks_by_state(conn, "ERROR")
    assert rows[0]["error_message"] == "ConnectionError: timed out after 5s"
    # reason for ERROR rows is the generic engine label, not the exception text
    assert rows[0]["reason"] == "provider_error"
    assert rows[0]["error_message"] != rows[0]["reason"]
