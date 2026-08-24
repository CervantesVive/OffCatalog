import pytest
from typer.testing import CliRunner

from offcatalog.cli import app
from offcatalog.db.connection import get_connection
from offcatalog.db.repository import (
    get_file_path_for_track,
    list_unavailable_everywhere,
    record_check_result,
    upsert_file,
    upsert_local_track,
)
from offcatalog.matching.types import AvailabilityState, MatchResult
from offcatalog.models import LocalTrack, RawTags
from offcatalog.playlist import write_m3u8

runner = CliRunner()


def _seed_track(conn, path, state):
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
        version_qualifiers=[],
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
    result = MatchResult(
        state=state, score=0.0, reason="test", candidate=None, all_candidates=[]
    )
    record_check_result(conn, track.id, "deezer", result)
    return track.id


def _seed_track_two_providers(conn, path, state_a, state_b):
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
        version_qualifiers=[],
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
            state=state_a, score=0.0, reason="test", candidate=None, all_candidates=[]
        ),
    )
    record_check_result(
        conn,
        track.id,
        "spotify",
        MatchResult(
            state=state_b, score=0.0, reason="test", candidate=None, all_candidates=[]
        ),
    )
    return track.id


def test_unavailable_everywhere_excludes_track_available_on_one_of_two_providers(
    tmp_path,
):
    conn = get_connection(str(tmp_path / "t.db"))
    _seed_track_two_providers(
        conn,
        "/mixed_available.mp3",
        AvailabilityState.AVAILABLE,
        AvailabilityState.UNAVAILABLE,
    )

    results = list_unavailable_everywhere(conn)
    ids = {row["id"] for row in results}
    assert "/mixed_available.mp3" not in ids


def test_unavailable_everywhere_excludes_track_errored_on_one_of_two_providers(
    tmp_path,
):
    conn = get_connection(str(tmp_path / "t.db"))
    _seed_track_two_providers(
        conn, "/mixed_error.mp3", AvailabilityState.ERROR, AvailabilityState.UNAVAILABLE
    )

    results = list_unavailable_everywhere(conn)
    ids = {row["id"] for row in results}
    assert "/mixed_error.mp3" not in ids


def test_unavailable_everywhere_includes_track_unavailable_on_both_of_two_providers(
    tmp_path,
):
    conn = get_connection(str(tmp_path / "t.db"))
    track_id = _seed_track_two_providers(
        conn,
        "/both_unavailable.mp3",
        AvailabilityState.UNAVAILABLE,
        AvailabilityState.AMBIGUOUS,
    )

    results = list_unavailable_everywhere(conn)
    ids = {row["id"] for row in results}
    assert track_id in ids


def test_get_file_path_for_track_raises_for_unknown_track(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    with pytest.raises(ValueError):
        get_file_path_for_track(conn, "does-not-exist")


def test_unavailable_everywhere_requires_all_providers_checked_and_none_available(
    tmp_path,
):
    conn = get_connection(str(tmp_path / "t.db"))
    unavailable_id = _seed_track(
        conn, "/unavailable.mp3", AvailabilityState.UNAVAILABLE
    )
    _seed_track(conn, "/available.mp3", AvailabilityState.AVAILABLE)
    _seed_track(conn, "/errored.mp3", AvailabilityState.ERROR)

    results = list_unavailable_everywhere(conn)
    ids = {row["id"] for row in results}
    assert ids == {unavailable_id}


def test_write_m3u8_produces_valid_playlist(tmp_path):
    output = tmp_path / "out.m3u8"
    write_m3u8([{"path": "/music/a.mp3"}, {"path": "/music/b.mp3"}], str(output))
    content = output.read_text(encoding="utf-8")
    assert content.startswith("#EXTM3U")
    assert "/music/a.mp3" in content
    assert "/music/b.mp3" in content


def test_playlist_cli_writes_file(tmp_path):
    db_path = str(tmp_path / "t.db")
    conn = get_connection(db_path)
    _seed_track(conn, "/unavailable.mp3", AvailabilityState.UNAVAILABLE)
    conn.close()

    output_path = tmp_path / "playlist.m3u8"
    result = runner.invoke(
        app, ["playlist", "--db", db_path, "--output", str(output_path)]
    )

    assert result.exit_code == 0, result.output
    assert "/unavailable.mp3" in output_path.read_text(encoding="utf-8")
