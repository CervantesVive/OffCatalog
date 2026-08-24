from offcatalog.models import LocalTrack, RawTags, compute_fingerprint


def make_raw(**overrides) -> RawTags:
    base = {
        "artist": "Depeche Mode",
        "title": "Enjoy the Silence",
        "album": "Violator",
        "album_artist": None,
        "track_number": "3",
        "disc_number": None,
        "year": "1990",
        "isrc": "GBAYE9000212",
        "musicbrainz_track_id": None,
        "musicbrainz_recording_id": None,
    }
    base.update(overrides)
    return RawTags(**base)


def test_fingerprint_stable_for_same_input():
    raw = make_raw()
    fp1 = compute_fingerprint(raw, duration_seconds=258.0, file_size=8_000_000)
    fp2 = compute_fingerprint(raw, duration_seconds=258.0, file_size=8_000_000)
    assert fp1 == fp2


def test_fingerprint_changes_when_tag_changes():
    fp1 = compute_fingerprint(make_raw(), duration_seconds=258.0, file_size=8_000_000)
    fp2 = compute_fingerprint(
        make_raw(title="Enjoy the Silence (Remastered)"),
        duration_seconds=258.0,
        file_size=8_000_000,
    )
    assert fp1 != fp2


def test_fingerprint_changes_when_duration_changes():
    fp1 = compute_fingerprint(make_raw(), duration_seconds=258.0, file_size=8_000_000)
    fp2 = compute_fingerprint(make_raw(), duration_seconds=99.0, file_size=8_000_000)
    assert fp1 != fp2


def test_local_track_holds_raw_and_normalized_separately():
    track = LocalTrack(
        id="t1",
        path="/music/a.mp3",
        filename="a.mp3",
        raw=make_raw(),
        artist="depeche mode",
        album_artist=None,
        title="enjoy the silence",
        album="violator",
        version_qualifiers=[],
        track_number=3,
        disc_number=None,
        duration_seconds=258.0,
        year=1990,
        isrc="GBAYE9000212",
        musicbrainz_track_id=None,
        musicbrainz_recording_id=None,
        fingerprint="deadbeef",
    )
    assert track.raw.title == "Enjoy the Silence"
    assert track.title == "enjoy the silence"
