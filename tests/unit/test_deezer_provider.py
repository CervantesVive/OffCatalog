import httpx
import pytest

from offcatalog.models import LocalTrack, RawTags
from offcatalog.providers.base import ProviderError
from offcatalog.providers.deezer import DeezerProvider


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
        "isrc": None,
        "musicbrainz_track_id": None,
        "musicbrainz_recording_id": None,
        "fingerprint": "fp",
    }
    base.update(overrides)
    return LocalTrack(**base)


def _client_with(handler) -> httpx.Client:
    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport, base_url="https://api.deezer.com")


def test_search_by_isrc_returns_candidate():
    def handler(request):
        assert request.url.path == "/track/isrc:GBAYE9000212"
        return httpx.Response(
            200,
            json={
                "id": 123,
                "title": "Enjoy the Silence",
                "duration": 258,
                "isrc": "GBAYE9000212",
                "artist": {"name": "Depeche Mode"},
                "album": {"title": "Violator"},
            },
        )

    provider = DeezerProvider(client=_client_with(handler))
    candidate = provider.search_by_isrc("GBAYE9000212")
    assert candidate["provider_track_id"] == "123"
    assert candidate["duration_seconds"] == 258.0
    assert candidate["isrc"] == "GBAYE9000212"


def test_search_by_isrc_returns_none_when_not_found():
    def handler(request):
        return httpx.Response(
            200, json={"error": {"type": "DataException", "message": "no data"}}
        )

    provider = DeezerProvider(client=_client_with(handler))
    assert provider.search_by_isrc("ZZZZZZZZZZZZ") is None


def test_search_track_returns_candidates():
    def handler(request):
        assert request.url.path == "/search"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": 1,
                        "title": "Enjoy the Silence",
                        "duration": 258,
                        "artist": {"name": "Depeche Mode"},
                        "album": {"title": "Violator"},
                    },
                ]
            },
        )

    provider = DeezerProvider(client=_client_with(handler))
    candidates = provider.search_track(make_track())
    assert len(candidates) == 1
    assert candidates[0]["artist"] == "Depeche Mode"


def test_search_track_sends_normalized_fields_not_raw_tags():
    captured_queries = []

    def handler(request):
        captured_queries.append(request.url.params["q"])
        return httpx.Response(200, json={"data": []})

    track = make_track(
        raw=RawTags(
            "DEPECHE MODE!!",
            "Enjoy The Silence (Örig. Mix)",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ),
        artist="depeche mode",
        title="enjoy the silence",
    )
    provider = DeezerProvider(client=_client_with(handler))
    provider.search_track(track)

    assert len(captured_queries) == 1
    query = captured_queries[0]
    assert "depeche mode" in query
    assert "enjoy the silence" in query
    # The raw tag text (original casing/punctuation/diacritics) must never
    # leave the machine -- only the normalized fields are sent.
    assert "DEPECHE MODE!!" not in query
    assert "Örig. Mix" not in query


def test_network_failure_raises_provider_error():
    def handler(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    provider = DeezerProvider(client=_client_with(handler))
    with pytest.raises(ProviderError):
        provider.search_track(make_track())


def test_search_by_isrc_raises_on_non_not_found_api_error():
    def handler(request):
        return httpx.Response(
            200, json={"error": {"type": "QuotaException", "message": "rate limited"}}
        )

    provider = DeezerProvider(client=_client_with(handler))
    with pytest.raises(ProviderError):
        provider.search_by_isrc("GBAYE9000212")


def test_search_track_raises_on_non_not_found_api_error():
    def handler(request):
        return httpx.Response(
            200, json={"error": {"type": "QuotaException", "message": "rate limited"}}
        )

    provider = DeezerProvider(client=_client_with(handler))
    with pytest.raises(ProviderError):
        provider.search_track(make_track())


def test_malformed_json_raises_provider_error():
    def handler(request):
        return httpx.Response(200, text="not json")

    provider = DeezerProvider(client=_client_with(handler))
    with pytest.raises(ProviderError):
        provider.search_by_isrc("GBAYE9000212")


def test_malformed_payload_missing_id_raises_provider_error():
    def handler(request):
        return httpx.Response(200, json={"title": "No Id Here", "duration": 100})

    provider = DeezerProvider(client=_client_with(handler))
    with pytest.raises(ProviderError):
        provider.search_by_isrc("GBAYE9000212")


def test_malformed_payload_null_artist_in_search_raises_provider_error():
    def handler(request):
        return httpx.Response(
            200,
            json={"data": [{"id": 1, "title": "T", "duration": 10, "artist": None}]},
        )

    provider = DeezerProvider(client=_client_with(handler))
    with pytest.raises(ProviderError):
        provider.search_track(make_track())


class _FakeRateLimiter:
    def __init__(self):
        self.calls = 0

    def wait(self):
        self.calls += 1


def test_rate_limiter_wait_called_once_per_http_request():
    def handler(request):
        if "isrc" in request.url.path:
            return httpx.Response(200, json={"error": {"type": "DataException"}})
        return httpx.Response(200, json={"data": []})

    limiter = _FakeRateLimiter()
    provider = DeezerProvider(client=_client_with(handler), rate_limiter=limiter)

    provider.search_by_isrc("ZZZZZZZZZZZZ")
    assert limiter.calls == 1

    provider.search_track(make_track())
    assert limiter.calls == 2


@pytest.mark.manual
def test_live_deezer_search_returns_candidates():
    """Manual smoke test against the real Deezer API — NOT run by default.

    Deselected by `addopts = "-m 'not manual'"` in pyproject.toml; run it
    deliberately with `uv run pytest -m manual`. Needs live network access, but
    no credentials (Deezer's catalog search is unauthenticated).
    """
    provider = DeezerProvider()
    candidates = provider.search_track(
        make_track(artist="depeche mode", title="enjoy the silence")
    )
    assert candidates
    assert any("silence" in c["title"].lower() for c in candidates)
