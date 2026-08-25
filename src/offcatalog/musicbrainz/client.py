from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, TypedDict

import httpx

from offcatalog.providers.base import ProviderError

if TYPE_CHECKING:
    from offcatalog.models import LocalTrack

_USER_AGENT = "OffCatalog/0.1 ( https://github.com/CervantesVive/OffCatalog )"

# MusicBrainz's server occasionally 503s or times out under its own transient
# load -- observed in real usage as scattered failures interspersed with many
# successful requests, not a sustained per-IP block (see MusicBrainz API rate
# limiting docs: exceeding the rate returns 503, but ordinary server load can
# too). A short retry recovers most of these instead of permanently losing
# that track's enrichment for the rest of the run.
_MAX_ATTEMPTS = 3  # 1 initial attempt + 2 retries
_RETRY_BACKOFF_SECONDS = 2.0
_RETRYABLE_STATUS_CODES = {502, 503, 504}


class MBRecording(TypedDict):
    mbid: str
    isrc: str | None
    disambiguation: str | None
    duration_seconds: float | None
    score: float


class MusicBrainzClient:
    BASE_URL = "https://musicbrainz.org/ws/2"

    def __init__(self, client: httpx.Client | None = None, rate_limiter=None) -> None:
        self._client = client or httpx.Client(
            base_url=self.BASE_URL, timeout=10.0, headers={"User-Agent": _USER_AGENT}
        )
        self._rate_limiter = rate_limiter

    def lookup_by_mbid(self, recording_id: str) -> MBRecording | None:
        data = self._get(
            f"/recording/{recording_id}", params={"inc": "isrcs", "fmt": "json"}
        )
        if data is None:
            return None
        return self._to_recording(data, score=100.0)

    def search_recording(self, track: LocalTrack) -> list[MBRecording]:
        # artist is an unquoted term group, not a phrase: tag spellings often
        # diverge from MusicBrainz's canonical artist name in token order/form
        # (e.g. "y la 440" vs "4.40"), and a quoted phrase requires exact
        # token-adjacency match, so it wrongly returns zero results.
        query = f'artist:({track.artist}) AND recording:"{track.title}"'
        data = self._get("/recording/", params={"query": query, "fmt": "json"})
        if data is None:
            return []
        return [
            self._to_recording(item, score=float(item.get("score", 0)))
            for item in data.get("recordings", [])
        ]

    def _get(self, path: str, **kwargs) -> dict | None:
        last_error = ""
        for attempt in range(_MAX_ATTEMPTS):
            if self._rate_limiter is not None:
                self._rate_limiter.wait()
            try:
                response = self._client.get(path, **kwargs)
            except httpx.TimeoutException as exc:
                last_error = str(exc)
                if attempt < _MAX_ATTEMPTS - 1:
                    time.sleep(_RETRY_BACKOFF_SECONDS)
                    continue
                raise ProviderError(
                    f"MusicBrainz request to {path} failed: {exc}"
                ) from exc
            except httpx.HTTPError as exc:
                raise ProviderError(
                    f"MusicBrainz request to {path} failed: {exc}"
                ) from exc

            if response.status_code == 404:
                return None
            if response.status_code in _RETRYABLE_STATUS_CODES:
                last_error = f"{response.status_code} {response.reason_phrase}"
                if attempt < _MAX_ATTEMPTS - 1:
                    time.sleep(_RETRY_BACKOFF_SECONDS)
                    continue
                raise ProviderError(
                    f"MusicBrainz request to {path} failed after {_MAX_ATTEMPTS} "
                    f"attempts: {last_error}"
                )
            try:
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as exc:
                raise ProviderError(
                    f"MusicBrainz request to {path} failed: {exc}"
                ) from exc
            except json.JSONDecodeError as exc:
                raise ProviderError(
                    f"MusicBrainz request to {path} returned malformed JSON: {exc}"
                ) from exc
        raise AssertionError("unreachable")  # loop always returns or raises

    @staticmethod
    def _to_recording(item: dict, *, score: float) -> MBRecording:
        # A payload missing "id" would otherwise raise KeyError past match_track's
        # `except ProviderError` and abort the whole enrich run on one bad row
        # (same rationale as DeezerProvider._to_candidate).
        try:
            length_ms = item.get("length")
            isrcs = item.get("isrcs")
            return MBRecording(
                mbid=item["id"],
                isrc=isrcs[0] if isrcs else None,
                disambiguation=item.get("disambiguation") or None,
                duration_seconds=(length_ms / 1000.0)
                if length_ms is not None
                else None,
                score=score,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError(
                f"MusicBrainz returned an unmappable recording payload: {item!r}"
            ) from exc
