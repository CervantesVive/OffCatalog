import os
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


def test_scan_respects_offcatalog_db_env_var(tmp_path):
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    shutil.copy(FIXTURES / "plain_version.mp3", music_dir / "plain_version.mp3")
    db_path = tmp_path / "env_catalog.db"

    result = runner.invoke(
        app, ["scan", str(music_dir)], env={"OFFCATALOG_DB": str(db_path)}
    )

    assert result.exit_code == 0, result.output
    assert db_path.exists()
    conn = get_connection(str(db_path))
    count = conn.execute("SELECT COUNT(*) AS c FROM local_tracks").fetchone()["c"]
    assert count == 1


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


def test_scan_skips_corrupt_file_and_continues(tmp_path):
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    shutil.copy(FIXTURES / "plain_version.mp3", music_dir / "plain_version.mp3")
    (music_dir / "bad.mp3").write_bytes(b"not an mp3")
    db_path = tmp_path / "catalog.db"

    result = runner.invoke(app, ["scan", str(music_dir), "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    conn = get_connection(str(db_path))
    count = conn.execute("SELECT COUNT(*) AS c FROM local_tracks").fetchone()["c"]
    assert count == 1


def test_scan_skips_unchanged_file_without_reextracting(tmp_path, monkeypatch):
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    shutil.copy(FIXTURES / "plain_version.mp3", music_dir / "plain_version.mp3")
    db_path = tmp_path / "catalog.db"
    runner.invoke(app, ["scan", str(music_dir), "--db", str(db_path)])

    calls = []
    import offcatalog.cli as cli_module
    original = cli_module.extract_local_track
    def spy(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(cli_module, "extract_local_track", spy)

    runner.invoke(app, ["scan", str(music_dir), "--db", str(db_path)])
    assert calls == []


def test_scan_soft_deletes_missing_file(tmp_path):
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    target = music_dir / "plain_version.mp3"
    shutil.copy(FIXTURES / "plain_version.mp3", target)
    db_path = tmp_path / "catalog.db"
    runner.invoke(app, ["scan", str(music_dir), "--db", str(db_path)])

    target.unlink()
    runner.invoke(app, ["scan", str(music_dir), "--db", str(db_path)])

    conn = get_connection(str(db_path))
    row = conn.execute("SELECT deleted_at FROM files WHERE path = ?", (str(target),)).fetchone()
    assert row["deleted_at"] is not None


def test_scan_undeletes_file_that_reappears_unchanged(tmp_path):
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    target = music_dir / "plain_version.mp3"
    shutil.copy(FIXTURES / "plain_version.mp3", target)
    db_path = tmp_path / "catalog.db"
    runner.invoke(app, ["scan", str(music_dir), "--db", str(db_path)])

    original_stat = target.stat()
    original_bytes = target.read_bytes()
    target.unlink()
    runner.invoke(app, ["scan", str(music_dir), "--db", str(db_path)])

    conn = get_connection(str(db_path))
    row = conn.execute("SELECT deleted_at FROM files WHERE path = ?", (str(target),)).fetchone()
    assert row["deleted_at"] is not None

    # Restore the same file with identical content, mtime, and size (e.g. a
    # reconnected drive or an rsync/cp -p restore) -- stat alone matches "unchanged".
    target.write_bytes(original_bytes)
    os.utime(target, (original_stat.st_atime, original_stat.st_mtime))
    runner.invoke(app, ["scan", str(music_dir), "--db", str(db_path)])

    conn = get_connection(str(db_path))
    row = conn.execute("SELECT deleted_at FROM files WHERE path = ?", (str(target),)).fetchone()
    assert row["deleted_at"] is None
