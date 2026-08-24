import shutil
from pathlib import Path

from typer.testing import CliRunner

from offcatalog.cli import app
from offcatalog.db.connection import get_connection

runner = CliRunner()
FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_scan_inserts_tracks_found_in_directory(tmp_path):
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    shutil.copy(FIXTURES / "plain_version.mp3", music_dir / "plain_version.mp3")
    shutil.copy(FIXTURES / "live_version.mp3", music_dir / "live_version.mp3")
    db_path = tmp_path / "catalog.db"

    result = runner.invoke(app, ["scan", str(music_dir), "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    conn = get_connection(str(db_path))
    count = conn.execute("SELECT COUNT(*) AS c FROM local_tracks").fetchone()["c"]
    assert count == 2


def test_scan_is_idempotent(tmp_path):
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    shutil.copy(FIXTURES / "plain_version.mp3", music_dir / "plain_version.mp3")
    db_path = tmp_path / "catalog.db"

    runner.invoke(app, ["scan", str(music_dir), "--db", str(db_path)])
    result = runner.invoke(app, ["scan", str(music_dir), "--db", str(db_path)])

    assert result.exit_code == 0
    conn = get_connection(str(db_path))
    count = conn.execute("SELECT COUNT(*) AS c FROM local_tracks").fetchone()["c"]
    assert count == 1
