import shutil
from pathlib import Path
from unittest.mock import patch

import httpx
from typer.testing import CliRunner

from offcatalog.cli import app
from offcatalog.db.connection import get_connection
from offcatalog.matching.types import AvailabilityState, MatchResult
from offcatalog.providers.deezer import DeezerProvider

runner = CliRunner()
FIXTURES = Path(__file__).parent.parent / "fixtures"


def _fake_deezer(handler):
    def factory(*args, **kwargs):
        return DeezerProvider(
            client=httpx.Client(
                transport=httpx.MockTransport(handler),
                base_url="https://api.deezer.com",
            )
        )

    return factory


def test_check_stores_available_result(tmp_path):
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    shutil.copy(FIXTURES / "plain_version.mp3", music_dir / "plain_version.mp3")
    db_path = tmp_path / "catalog.db"
    runner.invoke(app, ["scan", str(music_dir), "--db", str(db_path)])

    def handler(request):
        if "isrc" in request.url.path:
            return httpx.Response(200, json={"error": {"type": "DataException"}})
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        # plain_version.mp3 is a synthetic ~3s silent fixture (see
                        # tests/fixtures/README.md), not the real 258s song — duration
                        # here must fall within match_track's 4s tolerance of that.
                        "id": 1,
                        "title": "Enjoy the Silence",
                        "duration": 3,
                        "artist": {"name": "Depeche Mode"},
                        "album": {"title": "Violator"},
                    }
                ]
            },
        )

    with patch("offcatalog.cli.DeezerProvider", side_effect=_fake_deezer(handler)):
        result = runner.invoke(app, ["check", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    conn = get_connection(str(db_path))
    state = conn.execute("SELECT state FROM availability_results").fetchone()["state"]
    assert state == "AVAILABLE"


def test_check_retry_errors_rechecks_error_state(tmp_path):
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    shutil.copy(FIXTURES / "plain_version.mp3", music_dir / "plain_version.mp3")
    db_path = tmp_path / "catalog.db"
    runner.invoke(app, ["scan", str(music_dir), "--db", str(db_path)])

    def failing_handler(request):
        raise httpx.ConnectTimeout("timeout", request=request)

    with patch(
        "offcatalog.cli.DeezerProvider", side_effect=_fake_deezer(failing_handler)
    ):
        runner.invoke(app, ["check", "--db", str(db_path)])

    conn = get_connection(str(db_path))
    assert (
        conn.execute("SELECT state FROM availability_results").fetchone()["state"]
        == "ERROR"
    )

    def ok_handler(request):
        if "isrc" in request.url.path:
            return httpx.Response(200, json={"error": {"type": "DataException"}})
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        # plain_version.mp3 is a synthetic ~3s silent fixture (see
                        # tests/fixtures/README.md), not a real song — duration here
                        # must fall within match_track's 4s tolerance of that.
                        "id": 1,
                        "title": "Enjoy the Silence",
                        "duration": 3,
                        "artist": {"name": "Depeche Mode"},
                        "album": {"title": "Violator"},
                    }
                ]
            },
        )

    with patch("offcatalog.cli.DeezerProvider", side_effect=_fake_deezer(ok_handler)):
        result = runner.invoke(app, ["check", "--db", str(db_path), "--retry-errors"])

    assert result.exit_code == 0, result.output
    conn = get_connection(str(db_path))
    assert (
        conn.execute("SELECT state FROM availability_results").fetchone()["state"]
        == "AVAILABLE"
    )


def test_check_without_retry_errors_leaves_error_state_alone(tmp_path):
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    shutil.copy(FIXTURES / "plain_version.mp3", music_dir / "plain_version.mp3")
    db_path = tmp_path / "catalog.db"
    runner.invoke(app, ["scan", str(music_dir), "--db", str(db_path)])

    def failing_handler(request):
        raise httpx.ConnectTimeout("timeout", request=request)

    with patch(
        "offcatalog.cli.DeezerProvider", side_effect=_fake_deezer(failing_handler)
    ):
        runner.invoke(app, ["check", "--db", str(db_path)])
        result = runner.invoke(
            app, ["check", "--db", str(db_path)]
        )  # no --retry-errors

    assert "Checked 0 track(s)" in result.output


def test_check_rejects_unknown_provider_and_creates_no_provider_row(tmp_path):
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    shutil.copy(FIXTURES / "plain_version.mp3", music_dir / "plain_version.mp3")
    db_path = tmp_path / "catalog.db"
    runner.invoke(app, ["scan", str(music_dir), "--db", str(db_path)])

    result = runner.invoke(app, ["check", "--db", str(db_path), "--provider", "bogus"])

    assert result.exit_code != 0
    assert "bogus" in result.output
    conn = get_connection(str(db_path))
    rows = conn.execute("SELECT name FROM providers WHERE name = 'bogus'").fetchall()
    assert rows == []


def test_check_rechecks_track_whose_fingerprint_changed(tmp_path):
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    shutil.copy(FIXTURES / "plain_version.mp3", music_dir / "plain_version.mp3")
    db_path = tmp_path / "catalog.db"
    runner.invoke(app, ["scan", str(music_dir), "--db", str(db_path)])

    def ok_handler(request):
        if "isrc" in request.url.path:
            return httpx.Response(200, json={"error": {"type": "DataException"}})
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": 1,
                        "title": "Enjoy the Silence",
                        "duration": 3,
                        "artist": {"name": "Depeche Mode"},
                        "album": {"title": "Violator"},
                    }
                ]
            },
        )

    with patch("offcatalog.cli.DeezerProvider", side_effect=_fake_deezer(ok_handler)):
        runner.invoke(app, ["check", "--db", str(db_path)])

        conn = get_connection(str(db_path))
        assert (
            conn.execute("SELECT state FROM availability_results").fetchone()["state"]
            == "AVAILABLE"
        )
        # A re-check without a retag is a no-op...
        result = runner.invoke(app, ["check", "--db", str(db_path)])
        assert "Checked 0 track(s)" in result.output

        # ...but retagging the file (new fingerprint) must reselect it.
        conn.execute("UPDATE files SET fingerprint = 'retagged'")
        conn.commit()
        result = runner.invoke(app, ["check", "--db", str(db_path)])

    assert "Checked 1 track(s)" in result.output
    conn = get_connection(str(db_path))
    assert (
        conn.execute("SELECT checked_fingerprint FROM availability_results").fetchone()[
            "checked_fingerprint"
        ]
        == "retagged"
    )


def test_check_isolates_unexpected_per_track_failure(tmp_path):
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    shutil.copy(FIXTURES / "plain_version.mp3", music_dir / "plain_version.mp3")
    shutil.copy(FIXTURES / "live_version.mp3", music_dir / "live_version.mp3")
    db_path = tmp_path / "catalog.db"
    runner.invoke(app, ["scan", str(music_dir), "--db", str(db_path)])

    def ok_handler(request):
        if "isrc" in request.url.path:
            return httpx.Response(200, json={"error": {"type": "DataException"}})
        return httpx.Response(200, json={"data": []})

    unavailable = MatchResult(
        state=AvailabilityState.UNAVAILABLE,
        score=0.0,
        reason="no_candidates",
        candidate=None,
        all_candidates=[],
    )
    with (
        patch("offcatalog.cli.DeezerProvider", side_effect=_fake_deezer(ok_handler)),
        patch(
            "offcatalog.cli.match_track",
            side_effect=[RuntimeError("unexpected boom"), unavailable],
        ),
    ):
        result = runner.invoke(app, ["check", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "Checked 1 track(s), 1 error(s)" in result.output
    conn = get_connection(str(db_path))
    # the surviving track's result was still persisted
    assert (
        conn.execute("SELECT COUNT(*) AS c FROM availability_results").fetchone()["c"]
        == 1
    )


def test_check_persists_progress_across_interrupted_run(tmp_path):
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    shutil.copy(FIXTURES / "plain_version.mp3", music_dir / "plain_version.mp3")
    shutil.copy(FIXTURES / "live_version.mp3", music_dir / "live_version.mp3")
    db_path = tmp_path / "catalog.db"
    runner.invoke(app, ["scan", str(music_dir), "--db", str(db_path)])

    def ok_handler(request):
        if "isrc" in request.url.path:
            return httpx.Response(200, json={"error": {"type": "DataException"}})
        return httpx.Response(200, json={"data": []})

    with patch("offcatalog.cli.DeezerProvider", side_effect=_fake_deezer(ok_handler)):
        runner.invoke(app, ["check", "--db", str(db_path), "--limit", "1"])

    conn = get_connection(str(db_path))
    checked_count = conn.execute(
        "SELECT COUNT(*) AS c FROM availability_results"
    ).fetchone()["c"]
    assert (
        checked_count == 1
    )  # first track's result persisted even though run was limited/interrupted


def test_check_uses_musicbrainz_isrc_fallback_when_embedded_isrc_missing(tmp_path):
    from offcatalog.db.repository import upsert_file, upsert_local_track
    from offcatalog.models import LocalTrack, RawTags

    db_path = tmp_path / "catalog.db"
    conn = get_connection(str(db_path))
    raw = RawTags(
        "Depeche Mode", "Enjoy The Silence", "Violator", None, None, None, None,
        None, None, None,
    )
    track = LocalTrack(
        id="/x.mp3",
        path="/x.mp3",
        filename="/x.mp3",
        raw=raw,
        artist="depeche mode",
        album_artist=None,
        title="enjoy the silence",
        album="violator",
        version_qualifiers=[],
        track_number=None,
        disc_number=None,
        duration_seconds=258.0,
        year=None,
        isrc=None,
        musicbrainz_track_id=None,
        musicbrainz_recording_id=None,
        fingerprint="/x.mp3",
    )
    file_id = upsert_file(conn, "/x.mp3", 1.0, 1, "/x.mp3")
    upsert_local_track(conn, file_id, track)
    conn.execute(
        "UPDATE local_tracks SET musicbrainz_isrc = ?", ("GBAYE9000212",)
    )
    conn.commit()
    conn.close()

    def handler(request):
        if "isrc:GBAYE9000212" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "id": 1,
                    "title": "Enjoy the Silence",
                    "duration": 258,
                    "isrc": "GBAYE9000212",
                    "artist": {"name": "Depeche Mode"},
                    "album": {"title": "Violator"},
                },
            )
        # The search fallback must never be reached -- if it is, the isrc
        # merge in _row_to_track didn't happen and this proves it by giving
        # zero candidates, which would produce UNAVAILABLE, not AVAILABLE.
        return httpx.Response(200, json={"data": []})

    with patch("offcatalog.cli.DeezerProvider", side_effect=_fake_deezer(handler)):
        result = runner.invoke(app, ["check", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    conn = get_connection(str(db_path))
    row = conn.execute("SELECT state, reason FROM availability_results").fetchone()
    assert row["state"] == "AVAILABLE"
    assert row["reason"] == "isrc_exact"
