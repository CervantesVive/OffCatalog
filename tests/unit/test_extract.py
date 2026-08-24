from pathlib import Path

from offcatalog.scanning.extract import _parse_year, extract_local_track

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


def test_parse_year_takes_leading_year_from_full_iso_timestamp():
    # ID3v2.4 date tags are commonly a full timestamp (e.g. "1990-04-01"),
    # not a bare year. Must not concatenate all digits into "19900401".
    assert _parse_year("1990-04-01") == 1990


def test_parse_year_handles_bare_year():
    assert _parse_year("1990") == 1990


def test_parse_year_handles_none_and_empty():
    assert _parse_year(None) is None
    assert _parse_year("") is None
