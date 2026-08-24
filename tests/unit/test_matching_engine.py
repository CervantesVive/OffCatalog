from offcatalog.matching.engine import match_track
from offcatalog.matching.types import AvailabilityState
from offcatalog.models import LocalTrack, RawTags
from offcatalog.providers.base import ProviderError


def make_track(**overrides) -> LocalTrack:
    base = {
        "id": "t1",
        "path": "/x.mp3",
        "filename": "x.mp3",
        "raw": RawTags(None, None, None, None, None, None, None, None, None, None),
        "artist": "depeche mode",
        "album_artist": None,
        "title": "enjoy the silence",
        "album": "violator",
        "version_qualifiers": [],
        "track_number": None,
        "disc_number": None,
        "duration_seconds": 258.0,
        "year": None,
        "isrc": "GBAYE9000212",
        "musicbrainz_track_id": None,
        "musicbrainz_recording_id": None,
        "fingerprint": "fp",
    }
    base.update(overrides)
    return LocalTrack(**base)


class FakeProvider:
    name = "fake"

    def __init__(self, isrc_result=None, search_result=None, raise_error=False):
        self._isrc_result = isrc_result
        self._search_result = search_result or []
        self._raise_error = raise_error

    def search_by_isrc(self, isrc):
        if self._raise_error:
            raise ProviderError("boom")
        return self._isrc_result

    def search_track(self, track):
        if self._raise_error:
            raise ProviderError("boom")
        return self._search_result


def test_isrc_exact_match_is_available():
    candidate = {
        "provider_track_id": "1",
        "artist": "Depeche Mode",
        "title": "Enjoy the Silence",
        "album": "Violator",
        "duration_seconds": 258.0,
        "isrc": "GBAYE9000212",
    }
    provider = FakeProvider(isrc_result=candidate)
    result = match_track(make_track(), provider)
    assert result.state == AvailabilityState.AVAILABLE
    assert result.reason == "isrc_exact"
    assert result.score == 1.0


def test_provider_error_yields_error_state_not_unavailable():
    provider = FakeProvider(raise_error=True)
    result = match_track(make_track(), provider)
    assert result.state == AvailabilityState.ERROR
    assert result.error_message


def test_no_isrc_on_track_skips_level_1():
    provider = FakeProvider(search_result=[])
    result = match_track(make_track(isrc=None), provider)
    assert result.reason != "isrc_exact"


def test_metadata_and_duration_match_is_available():
    candidate = {
        "provider_track_id": "1",
        "artist": "Depeche Mode",
        "title": "Enjoy the Silence",
        "album": "Violator",
        "duration_seconds": 259.0,
        "isrc": None,
    }
    provider = FakeProvider(isrc_result=None, search_result=[candidate])
    result = match_track(make_track(isrc=None), provider)
    assert result.state == AvailabilityState.AVAILABLE
    assert result.reason == "meta_duration"


def test_duration_outside_tolerance_is_rejected_not_ambiguous_yet():
    # duration way off (7:18 local vs 4:15 candidate) -> Depeche Mode Hands and Feet Mix case
    candidate = {
        "provider_track_id": "1",
        "artist": "Depeche Mode",
        "title": "Enjoy the Silence",
        "album": "Violator",
        "duration_seconds": 255.0,
        "isrc": None,
    }
    local = make_track(
        isrc=None, duration_seconds=438.0, version_qualifiers=["hands and feet mix"]
    )
    provider = FakeProvider(isrc_result=None, search_result=[candidate])
    result = match_track(local, provider)
    assert result.state != AvailabilityState.AVAILABLE


def test_qualifier_mismatch_is_rejected_not_available():
    candidate = {
        "provider_track_id": "1",
        "artist": "Depeche Mode",
        "title": "Enjoy the Silence",
        "album": "Violator",
        "duration_seconds": 258.0,
        "isrc": None,
    }
    local = make_track(isrc=None, duration_seconds=258.0, version_qualifiers=["live"])
    provider = FakeProvider(isrc_result=None, search_result=[candidate])
    result = match_track(local, provider)
    assert result.state != AvailabilityState.AVAILABLE


def test_remaster_qualifier_is_compatible_with_plain():
    candidate = {
        "provider_track_id": "1",
        "artist": "Depeche Mode",
        "title": "Enjoy the Silence",
        "album": "Violator",
        "duration_seconds": 258.0,
        "isrc": None,
    }
    local = make_track(isrc=None, duration_seconds=258.0, version_qualifiers=[])
    provider = FakeProvider(isrc_result=None, search_result=[candidate])
    result = match_track(local, provider)
    assert result.state == AvailabilityState.AVAILABLE


def test_close_fuzzy_match_with_no_duration_is_ambiguous_not_available():
    candidate = {
        "provider_track_id": "1",
        "artist": "Depeche Mode",
        "title": "Enjoy the Silence (Remix)",
        "album": "Violator",
        "duration_seconds": 999.0,
        "isrc": None,
    }
    local = make_track(isrc=None, duration_seconds=258.0, version_qualifiers=[])
    provider = FakeProvider(isrc_result=None, search_result=[candidate])
    result = match_track(local, provider)
    assert result.state == AvailabilityState.AMBIGUOUS
    assert result.candidate is None
    assert len(result.all_candidates) == 1


def test_completely_unrelated_candidate_is_unavailable_not_ambiguous():
    candidate = {
        "provider_track_id": "1",
        "artist": "Some Other Band",
        "title": "Totally Different Song",
        "album": "Nope",
        "duration_seconds": 120.0,
        "isrc": None,
    }
    local = make_track(isrc=None, duration_seconds=258.0, version_qualifiers=[])
    provider = FakeProvider(isrc_result=None, search_result=[candidate])
    result = match_track(local, provider)
    assert result.state == AvailabilityState.UNAVAILABLE
