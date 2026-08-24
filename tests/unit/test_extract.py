from pathlib import Path

from offcatalog.scanning.extract import extract_local_track

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_extract_reads_basic_tags():
    track = extract_local_track(str(FIXTURES / "plain_version.mp3"))
    assert track.artist == "depeche mode"
    assert "silence" in track.title
    assert track.raw.artist == "Depeche Mode"
    assert track.raw.title == "Enjoy the Silence"
    assert track.track_number == 3
    assert track.year == 1990


def test_extract_reads_duration():
    track = extract_local_track(str(FIXTURES / "plain_version.mp3"))
    assert 2.5 < track.duration_seconds < 3.5


def test_extract_captures_distinguishing_qualifier():
    track = extract_local_track(str(FIXTURES / "live_version.mp3"))
    assert "live" in track.version_qualifiers


def test_extract_sets_path_and_generates_id():
    path = str(FIXTURES / "plain_version.mp3")
    track = extract_local_track(path)
    assert track.path == path
    assert track.id
