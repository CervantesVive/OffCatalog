import httpx
import pytest

from offcatalog.models import LocalTrack, RawTags
from offcatalog.providers.base import ProviderError
from offcatalog.providers.deezer import DeezerProvider


def make_track(**overrides) -> LocalTrack:
    base = dict(
        id="t1", path="/x.mp3", filename="x.mp3",
        raw=RawTags(None, None, None, None, None, None, None, None, None, None),
        artist="depeche mode", album_artist=None, title="enjoy the silence",
        album="violator", version_qualifiers=[], track_number=None, disc_number=None,
        duration_seconds=258.0, year=None, isrc=None,
        musicbrainz_track_id=None, musicbrainz_recording_id=None, fingerprint="fp",
    )
    base.update(overrides)
    return LocalTrack(**base)


def _client_with(handler) -> httpx.Client:
    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport, base_url="https://api.deezer.com")


def test_search_by_isrc_returns_candidate():
    def handler(request):
        assert request.url.path == "/track/isrc:GBAYE9000212"
        return httpx.Response(200, json={
            "id": 123, "title": "Enjoy the Silence", "duration": 258,
            "isrc": "GBAYE9000212",
            "artist": {"name": "Depeche Mode"}, "album": {"title": "Violator"},
        })

    provider = DeezerProvider(client=_client_with(handler))
    candidate = provider.search_by_isrc("GBAYE9000212")
    assert candidate["provider_track_id"] == "123"
    assert candidate["duration_seconds"] == 258.0
    assert candidate["isrc"] == "GBAYE9000212"


def test_search_by_isrc_returns_none_when_not_found():
    def handler(request):
        return httpx.Response(200, json={"error": {"type": "DataException", "message": "no data"}})

    provider = DeezerProvider(client=_client_with(handler))
    assert provider.search_by_isrc("ZZZZZZZZZZZZ") is None


def test_search_track_returns_candidates():
    def handler(request):
        assert request.url.path == "/search"
        return httpx.Response(200, json={"data": [
            {"id": 1, "title": "Enjoy the Silence", "duration": 258,
             "artist": {"name": "Depeche Mode"}, "album": {"title": "Violator"}},
        ]})

    provider = DeezerProvider(client=_client_with(handler))
    candidates = provider.search_track(make_track())
    assert len(candidates) == 1
    assert candidates[0]["artist"] == "Depeche Mode"


def test_network_failure_raises_provider_error():
    def handler(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    provider = DeezerProvider(client=_client_with(handler))
    with pytest.raises(ProviderError):
        provider.search_track(make_track())
