import shutil
from pathlib import Path
from unittest.mock import patch

import httpx
from typer.testing import CliRunner

from offcatalog.cli import app
from offcatalog.db.connection import get_connection
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
