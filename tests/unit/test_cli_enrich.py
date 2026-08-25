from unittest.mock import patch

import httpx
from typer.testing import CliRunner

from offcatalog.cli import app
from offcatalog.db.connection import get_connection
from offcatalog.db.repository import upsert_file, upsert_local_track
from offcatalog.models import LocalTrack, RawTags

runner = CliRunner()


def _seed_track(
    conn,
    path,
    *,
    musicbrainz_recording_id=None,
    fingerprint=None,
    version_qualifiers=None,
):
    raw = RawTags(
        "Depeche Mode",
        "Enjoy The Silence",
        "Violator",
        None,
        None,
        None,
        None,
        None,
        None,
        musicbrainz_recording_id,
    )
    track = LocalTrack(
        id=path,
        path=path,
        filename=path,
        raw=raw,
        artist="depeche mode",
        album_artist=None,
        title="enjoy the silence",
        album="violator",
        version_qualifiers=version_qualifiers or [],
        track_number=None,
        disc_number=None,
        duration_seconds=258.0,
        year=None,
        isrc=None,
        musicbrainz_track_id=None,
        musicbrainz_recording_id=musicbrainz_recording_id,
        fingerprint=fingerprint or path,
    )
    file_id = upsert_file(conn, path, 1.0, 1, fingerprint or path)
    upsert_local_track(conn, file_id, track)
    return track.id


def _fake_client(handler):
    def factory(*args, **kwargs):
        from offcatalog.musicbrainz.client import MusicBrainzClient

        return MusicBrainzClient(
            client=httpx.Client(
                transport=httpx.MockTransport(handler),
                base_url="https://musicbrainz.org/ws/2",
            )
        )

    return factory


def test_enrich_uses_direct_mbid_lookup_when_embedded(tmp_path):
    db_path = tmp_path / "catalog.db"
    conn = get_connection(str(db_path))
    _seed_track(
        conn, "/x.mp3", musicbrainz_recording_id="7c8837fa-30ec-4427-9eb4-ef23f649eea3"
    )
    conn.close()

    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "id": "7c8837fa-30ec-4427-9eb4-ef23f649eea3",
                "title": "Enjoy the Silence",
                "length": 258000,
                "disambiguation": "",
                "isrcs": ["GBAYE9000212"],
            },
        )

    with patch("offcatalog.cli.MusicBrainzClient", side_effect=_fake_client(handler)):
        result = runner.invoke(app, ["enrich", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "Enriched 1 track(s), 1 ISRC(s) found" in result.output
    assert "depeche mode - enjoy the silence: isrc GBAYE9000212" in result.output
    assert calls == ["/ws/2/recording/7c8837fa-30ec-4427-9eb4-ef23f649eea3"]
    conn = get_connection(str(db_path))
    row = conn.execute("SELECT musicbrainz_isrc FROM local_tracks").fetchone()
    assert row["musicbrainz_isrc"] == "GBAYE9000212"


def test_enrich_falls_back_to_search_then_lookup_when_no_embedded_mbid(tmp_path):
    db_path = tmp_path / "catalog.db"
    conn = get_connection(str(db_path))
    _seed_track(conn, "/x.mp3")
    conn.close()

    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/ws/2/recording/":
            return httpx.Response(
                200,
                json={
                    "count": 1,
                    "recordings": [
                        {
                            "id": "aaaa1111-0000-0000-0000-000000000000",
                            "score": 100,
                            "title": "Enjoy the Silence",
                            "length": 258000,
                            "disambiguation": "",
                        }
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "aaaa1111-0000-0000-0000-000000000000",
                "title": "Enjoy the Silence",
                "length": 258000,
                "disambiguation": "",
                "isrcs": ["GBAYE9000212"],
            },
        )

    with patch("offcatalog.cli.MusicBrainzClient", side_effect=_fake_client(handler)):
        result = runner.invoke(app, ["enrich", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert calls == [
        "/ws/2/recording/",
        "/ws/2/recording/aaaa1111-0000-0000-0000-000000000000",
    ]
    conn = get_connection(str(db_path))
    row = conn.execute("SELECT musicbrainz_isrc FROM local_tracks").fetchone()
    assert row["musicbrainz_isrc"] == "GBAYE9000212"


def test_enrich_rejects_search_candidate_outside_duration_tolerance(tmp_path):
    db_path = tmp_path / "catalog.db"
    conn = get_connection(str(db_path))
    _seed_track(conn, "/x.mp3")  # duration_seconds=258.0
    conn.close()

    def handler(request):
        if request.url.path == "/ws/2/recording/":
            return httpx.Response(
                200,
                json={
                    "count": 1,
                    "recordings": [
                        {
                            "id": "live-version",
                            "score": 100,
                            "title": "Enjoy the Silence",
                            "length": 459840,  # 459.84s -- way outside a 258s track's tolerance
                            "disambiguation": "live",
                        }
                    ],
                },
            )
        raise AssertionError(
            "lookup_by_mbid should not be called for a rejected candidate"
        )

    with patch("offcatalog.cli.MusicBrainzClient", side_effect=_fake_client(handler)):
        result = runner.invoke(app, ["enrich", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "Enriched 1 track(s), 0 ISRC(s) found" in result.output


def test_enrich_records_not_found_and_skips_unchanged_track_on_rerun(tmp_path):
    db_path = tmp_path / "catalog.db"
    conn = get_connection(str(db_path))
    _seed_track(conn, "/x.mp3")
    conn.close()

    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"count": 0, "recordings": []})

    with patch("offcatalog.cli.MusicBrainzClient", side_effect=_fake_client(handler)):
        result = runner.invoke(app, ["enrich", "--db", str(db_path)])
        assert "Enriched 1 track(s), 0 ISRC(s) found" in result.output

        # Second run: same fingerprint, must not re-query MusicBrainz.
        result2 = runner.invoke(app, ["enrich", "--db", str(db_path)])

    assert "Enriched 0 track(s), 0 ISRC(s) found" in result2.output
    assert calls == ["/ws/2/recording/"]  # only the first run's search call


def test_enrich_skips_search_fallback_for_qualified_track_without_embedded_mbid(
    tmp_path,
):
    # Regression for the wrong-version-ISRC bug: a qualified track (e.g. a
    # remix) with no embedded MBID must never go through search-fallback,
    # because the search query is built from the qualifier-stripped base
    # title and can't tell a remix apart from the plain album version. If it
    # did, this handler would hand back a score-100, duration-matching
    # candidate for the *plain* version and the wrong ISRC would get stored.
    db_path = tmp_path / "catalog.db"
    conn = get_connection(str(db_path))
    _seed_track(conn, "/x.mp3", version_qualifiers=["hands and feet mix"])
    conn.close()

    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "count": 1,
                "recordings": [
                    {
                        "id": "plain-version-wrong-recording",
                        "score": 100,
                        "title": "Enjoy the Silence",
                        "length": 258000,  # matches local duration exactly
                        "disambiguation": "",
                    }
                ],
            },
        )

    with patch("offcatalog.cli.MusicBrainzClient", side_effect=_fake_client(handler)):
        result = runner.invoke(app, ["enrich", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert calls == []  # search-fallback must never be invoked for a qualified track
    conn = get_connection(str(db_path))
    row = conn.execute("SELECT musicbrainz_isrc FROM local_tracks").fetchone()
    assert row["musicbrainz_isrc"] is None


def test_enrich_isolates_per_track_failure(tmp_path):
    db_path = tmp_path / "catalog.db"
    conn = get_connection(str(db_path))
    _seed_track(conn, "/bad.mp3", fingerprint="fp-bad")
    _seed_track(conn, "/ok.mp3", fingerprint="fp-ok")
    conn.close()

    # First MusicBrainz call (whichever track is processed first) returns
    # malformed JSON -> ProviderError -> caught and counted as an error.
    # The second call succeeds normally, proving the run continued.
    call_count = {"n": 0}

    def flaky_handler(request):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(200, text="not json")
        return httpx.Response(200, json={"count": 0, "recordings": []})

    with patch(
        "offcatalog.cli.MusicBrainzClient", side_effect=_fake_client(flaky_handler)
    ):
        result = runner.invoke(app, ["enrich", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "Enriched 1 track(s), 0 ISRC(s) found, 1 error(s)" in result.output
