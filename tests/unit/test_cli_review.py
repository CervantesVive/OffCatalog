from unittest.mock import patch

from typer.testing import CliRunner

from offcatalog.cli import app
from offcatalog.db.connection import get_connection
from offcatalog.db.repository import (
    list_ambiguous_tracks,
    list_candidates_for_track,
    record_check_result,
    upsert_file,
    upsert_local_track,
)
from offcatalog.matching.types import AvailabilityState, MatchResult
from offcatalog.models import LocalTrack, RawTags

runner = CliRunner()


def _seed_track(conn):
    raw = RawTags(
        "Artist", "Title (Remix)", "Album", None, None, None, None, None, None, None
    )
    track = LocalTrack(
        id="t1",
        path="/x.mp3",
        filename="x.mp3",
        raw=raw,
        artist="artist",
        album_artist=None,
        title="title",
        album="album",
        version_qualifiers=[],
        track_number=None,
        disc_number=None,
        duration_seconds=200.0,
        year=None,
        isrc=None,
        musicbrainz_track_id=None,
        musicbrainz_recording_id=None,
        fingerprint="fp",
    )
    file_id = upsert_file(conn, "/x.mp3", 1.0, 1, "fp")
    upsert_local_track(conn, file_id, track)
    return track


def _seed_ambiguous_track(conn):
    track = _seed_track(conn)
    candidate = {
        "provider_track_id": "1",
        "artist": "Artist",
        "title": "Title (Remix)",
        "album": "Album",
        "duration_seconds": 400.0,
        "isrc": None,
    }
    result = MatchResult(
        state=AvailabilityState.AMBIGUOUS,
        score=0.7,
        reason="fuzzy_candidate",
        candidate=None,
        all_candidates=[candidate],
    )
    record_check_result(conn, track.id, "deezer", result)
    return track.id


def test_list_ambiguous_tracks(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    track_id = _seed_ambiguous_track(conn)
    ambiguous = list_ambiguous_tracks(conn, "deezer")
    assert len(ambiguous) == 1
    assert ambiguous[0]["id"] == track_id


def test_review_same_recording_flips_to_available(tmp_path):
    db_path = str(tmp_path / "t.db")
    conn = get_connection(db_path)
    _seed_ambiguous_track(conn)
    conn.close()

    with patch("typer.prompt", return_value="s"):
        result = runner.invoke(app, ["review", "--db", db_path, "--provider", "deezer"])

    assert result.exit_code == 0, result.output
    conn = get_connection(db_path)
    state = conn.execute("SELECT state FROM availability_results").fetchone()["state"]
    assert state == "AVAILABLE"


def test_review_decision_persists_across_rescan(tmp_path):
    db_path = str(tmp_path / "t.db")
    conn = get_connection(db_path)
    track_id = _seed_ambiguous_track(conn)
    conn.close()

    with patch("typer.prompt", return_value="s"):
        runner.invoke(app, ["review", "--db", db_path, "--provider", "deezer"])

    conn = get_connection(db_path)
    # simulate a rescan re-recording the same AMBIGUOUS result
    candidate = {
        "provider_track_id": "1",
        "artist": "Artist",
        "title": "Title (Remix)",
        "album": "Album",
        "duration_seconds": 400.0,
        "isrc": None,
    }
    stale_result = MatchResult(
        state=AvailabilityState.AMBIGUOUS,
        score=0.7,
        reason="fuzzy_candidate",
        candidate=None,
        all_candidates=[candidate],
    )
    record_check_result(conn, track_id, "deezer", stale_result)

    state = conn.execute("SELECT state FROM availability_results").fetchone()["state"]
    assert state == "AVAILABLE"  # manual decision must not be overwritten


def test_review_picks_specified_candidate_not_default(tmp_path):
    db_path = str(tmp_path / "t.db")
    conn = get_connection(db_path)
    track = _seed_track(conn)
    candidate_a = {
        "provider_track_id": "1",
        "artist": "Artist",
        "title": "Title (Remix)",
        "album": "Album",
        "duration_seconds": 400.0,
        "isrc": None,
    }
    candidate_b = {
        "provider_track_id": "2",
        "artist": "Artist",
        "title": "Title (Live)",
        "album": "Album",
        "duration_seconds": 405.0,
        "isrc": None,
    }
    result = MatchResult(
        state=AvailabilityState.AMBIGUOUS,
        score=0.7,
        reason="fuzzy_candidate",
        candidate=None,
        all_candidates=[candidate_a, candidate_b],
    )
    record_check_result(conn, track.id, "deezer", result)
    candidates = list_candidates_for_track(conn, track.id, "deezer")
    assert len(candidates) == 2
    conn.close()

    with patch("typer.prompt", side_effect=["s", "1"]):
        result = runner.invoke(app, ["review", "--db", db_path, "--provider", "deezer"])

    assert result.exit_code == 0, result.output
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT provider_candidate_id FROM manual_match_decisions"
    ).fetchone()
    assert row["provider_candidate_id"] == candidates[1]["id"]


def test_unavailable_result_does_not_persist_candidates(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    track = _seed_track(conn)
    candidate = {
        "provider_track_id": "1",
        "artist": "Artist",
        "title": "Title (Remix)",
        "album": "Album",
        "duration_seconds": 400.0,
        "isrc": None,
    }
    result = MatchResult(
        state=AvailabilityState.UNAVAILABLE,
        score=0.3,
        reason="no_confident_candidate",
        candidate=None,
        all_candidates=[candidate],
    )
    record_check_result(conn, track.id, "deezer", result)

    count = conn.execute("SELECT COUNT(*) AS c FROM provider_candidates").fetchone()[
        "c"
    ]
    assert count == 0


def test_review_rejects_unknown_provider_and_creates_no_provider_row(tmp_path):
    db_path = tmp_path / "catalog.db"
    conn = get_connection(str(db_path))
    _seed_ambiguous_track(conn)
    conn.close()

    result = runner.invoke(app, ["review", "--db", str(db_path), "--provider", "bogus"])

    assert result.exit_code != 0
    assert "bogus" in result.output
    conn = get_connection(str(db_path))
    rows = conn.execute("SELECT name FROM providers WHERE name = 'bogus'").fetchall()
    assert rows == []


def test_review_displays_musicbrainz_metadata_line(tmp_path):
    db_path = str(tmp_path / "t.db")
    conn = get_connection(db_path)
    _seed_ambiguous_track(conn)
    conn.execute(
        "UPDATE local_tracks SET musicbrainz_isrc = ?, musicbrainz_disambiguation = ?",
        ("GBAYE9000212", "live, 1990-07-06"),
    )
    conn.commit()
    conn.close()

    with patch("typer.prompt", return_value="k"):
        result = runner.invoke(app, ["review", "--db", db_path, "--provider", "deezer"])

    assert result.exit_code == 0, result.output
    assert 'MB: isrc=GBAYE9000212 disambiguation="live, 1990-07-06"' in result.output


def test_review_omits_musicbrainz_line_when_no_data(tmp_path):
    db_path = str(tmp_path / "t.db")
    conn = get_connection(db_path)
    _seed_ambiguous_track(conn)
    conn.close()

    with patch("typer.prompt", return_value="k"):
        result = runner.invoke(app, ["review", "--db", db_path, "--provider", "deezer"])

    assert "MB:" not in result.output


def test_review_defaults_to_same_when_musicbrainz_isrc_matches_top_candidate(tmp_path):
    db_path = str(tmp_path / "t.db")
    conn = get_connection(db_path)
    track = _seed_track(conn)
    candidate = {
        "provider_track_id": "1",
        "artist": "Artist",
        "title": "Title (Remix)",
        "album": "Album",
        "duration_seconds": 400.0,
        "isrc": "GBAYE9000212",
    }
    result = MatchResult(
        state=AvailabilityState.AMBIGUOUS,
        score=0.7,
        reason="fuzzy_candidate",
        candidate=None,
        all_candidates=[candidate],
    )
    record_check_result(conn, track.id, "deezer", result)
    conn.execute("UPDATE local_tracks SET musicbrainz_isrc = ?", ("GBAYE9000212",))
    conn.commit()
    conn.close()

    with patch("typer.prompt", return_value="k") as mock_prompt:
        runner.invoke(app, ["review", "--db", db_path, "--provider", "deezer"])

    assert mock_prompt.call_args.kwargs["default"] == "s"


def test_review_defaults_to_skip_when_musicbrainz_isrc_does_not_match(tmp_path):
    db_path = str(tmp_path / "t.db")
    conn = get_connection(db_path)
    track = _seed_track(conn)
    candidate = {
        "provider_track_id": "1",
        "artist": "Artist",
        "title": "Title (Remix)",
        "album": "Album",
        "duration_seconds": 400.0,
        "isrc": "GBAYE9000212",
    }
    result = MatchResult(
        state=AvailabilityState.AMBIGUOUS,
        score=0.7,
        reason="fuzzy_candidate",
        candidate=None,
        all_candidates=[candidate],
    )
    record_check_result(conn, track.id, "deezer", result)
    conn.execute("UPDATE local_tracks SET musicbrainz_isrc = ?", ("USUM71703861",))
    conn.commit()
    conn.close()

    with patch("typer.prompt", return_value="k") as mock_prompt:
        runner.invoke(app, ["review", "--db", db_path, "--provider", "deezer"])

    assert mock_prompt.call_args.kwargs["default"] == "k"
