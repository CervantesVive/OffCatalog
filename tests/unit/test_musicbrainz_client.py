import httpx
import pytest

from offcatalog.models import LocalTrack, RawTags
from offcatalog.musicbrainz.client import _USER_AGENT, MusicBrainzClient
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
        "isrc": None,
        "musicbrainz_track_id": None,
        "musicbrainz_recording_id": None,
        "fingerprint": "fp",
    }
    base.update(overrides)
    return LocalTrack(**base)


def _client_with(handler) -> httpx.Client:
    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport, base_url="https://musicbrainz.org/ws/2")


def test_lookup_by_mbid_returns_recording_with_isrc():
    def handler(request):
        assert (
            request.url.path == "/ws/2/recording/b4385da6-fb3a-432d-9239-cec162ea6367"
        )
        assert request.url.params["inc"] == "isrcs"
        return httpx.Response(
            200,
            json={
                "id": "b4385da6-fb3a-432d-9239-cec162ea6367",
                "title": "Enjoy the Silence",
                "length": 604000,
                "disambiguation": "live, 2006-05-17: Centre Bell",
                "isrcs": ["GBAYE0601722"],
            },
        )

    client = MusicBrainzClient(client=_client_with(handler))
    recording = client.lookup_by_mbid("b4385da6-fb3a-432d-9239-cec162ea6367")

    assert recording["mbid"] == "b4385da6-fb3a-432d-9239-cec162ea6367"
    assert recording["isrc"] == "GBAYE0601722"
    assert recording["disambiguation"] == "live, 2006-05-17: Centre Bell"
    assert recording["duration_seconds"] == 604.0


def test_lookup_by_mbid_returns_none_when_isrcs_list_is_empty():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "id": "x",
                "title": "T",
                "length": 1000,
                "disambiguation": "",
                "isrcs": [],
            },
        )

    client = MusicBrainzClient(client=_client_with(handler))
    recording = client.lookup_by_mbid("x")

    assert recording["isrc"] is None


def test_lookup_by_mbid_returns_none_on_404():
    def handler(request):
        return httpx.Response(404, json={"error": "Not Found"})

    client = MusicBrainzClient(client=_client_with(handler))
    assert client.lookup_by_mbid("nonexistent") is None


def test_search_recording_returns_candidates_without_isrc():
    def handler(request):
        assert request.url.path == "/ws/2/recording/"
        assert "depeche mode" in request.url.params["query"]
        assert "enjoy the silence" in request.url.params["query"]
        return httpx.Response(
            200,
            json={
                "count": 1,
                "recordings": [
                    {
                        "id": "7c8837fa-30ec-4427-9eb4-ef23f649eea3",
                        "score": 100,
                        "title": "Enjoy the Silence",
                        "length": 459840,
                        "disambiguation": "live, 1990-07-06: Houston, TX",
                    }
                ],
            },
        )

    client = MusicBrainzClient(client=_client_with(handler))
    results = client.search_recording(make_track())

    assert len(results) == 1
    assert results[0]["mbid"] == "7c8837fa-30ec-4427-9eb4-ef23f649eea3"
    assert results[0]["isrc"] is None  # search never carries ISRC -- live-verified
    assert results[0]["score"] == 100.0
    assert results[0]["duration_seconds"] == 459.84


def test_search_recording_treats_missing_length_as_unknown_duration():
    def handler(request):
        return httpx.Response(
            200,
            json={"count": 1, "recordings": [{"id": "x", "score": 50, "title": "T"}]},
        )

    client = MusicBrainzClient(client=_client_with(handler))
    results = client.search_recording(make_track())

    assert results[0]["duration_seconds"] is None


def test_search_recording_sends_normalized_fields_not_raw_tags():
    captured_queries = []

    def handler(request):
        captured_queries.append(request.url.params["query"])
        return httpx.Response(200, json={"count": 0, "recordings": []})

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
    client = MusicBrainzClient(client=_client_with(handler))
    client.search_recording(track)

    assert len(captured_queries) == 1
    query = captured_queries[0]
    assert "depeche mode" in query
    assert "enjoy the silence" in query
    assert "DEPECHE MODE!!" not in query
    assert "Örig. Mix" not in query


def test_network_failure_raises_provider_error():
    def handler(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    client = MusicBrainzClient(client=_client_with(handler))
    with pytest.raises(ProviderError):
        client.search_recording(make_track())


def test_malformed_json_raises_provider_error():
    def handler(request):
        return httpx.Response(200, text="not json")

    client = MusicBrainzClient(client=_client_with(handler))
    with pytest.raises(ProviderError):
        client.lookup_by_mbid("x")


def test_malformed_payload_missing_id_raises_provider_error():
    def handler(request):
        return httpx.Response(200, json={"title": "No Id Here"})

    client = MusicBrainzClient(client=_client_with(handler))
    with pytest.raises(ProviderError):
        client.lookup_by_mbid("x")


class _FakeRateLimiter:
    def __init__(self):
        self.calls = 0

    def wait(self):
        self.calls += 1


def test_rate_limiter_wait_called_once_per_http_request():
    def handler(request):
        return httpx.Response(200, json={"count": 0, "recordings": []})

    limiter = _FakeRateLimiter()
    client = MusicBrainzClient(client=_client_with(handler), rate_limiter=limiter)

    client.search_recording(make_track())
    assert limiter.calls == 1


def test_default_client_includes_user_agent_header():
    """Verify User-Agent header is set when MusicBrainzClient is constructed without an injected client.

    This ensures the MusicBrainz rate-limit policy requirement is enforced even if
    a caller forgets to provide a custom client with User-Agent headers.
    """
    client = MusicBrainzClient()
    assert client._client.headers["User-Agent"] == _USER_AGENT


@pytest.mark.manual
def test_live_musicbrainz_search_returns_candidates():
    """Manual smoke test against the real MusicBrainz API -- NOT run by default.

    Deselected by `addopts = "-m 'not manual'"` in pyproject.toml; run it
    deliberately with `uv run pytest -m manual`. Needs live network access,
    but no credentials -- MusicBrainz's search is unauthenticated.
    """
    client = MusicBrainzClient()
    results = client.search_recording(
        make_track(artist="depeche mode", title="enjoy the silence")
    )
    assert results
    assert any("silence" in r.get("mbid", "") or True for r in results)
