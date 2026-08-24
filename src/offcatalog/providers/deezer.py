from __future__ import annotations

import json

import httpx

from offcatalog.models import LocalTrack
from offcatalog.providers.base import ProviderCandidate, ProviderError, register_provider

_NOT_FOUND_ERROR_TYPE = "DataException"


@register_provider
class DeezerProvider:
    name = "deezer"
    BASE_URL = "https://api.deezer.com"

    def __init__(self, client: httpx.Client | None = None, rate_limiter=None) -> None:
        self._client = client or httpx.Client(base_url=self.BASE_URL, timeout=10.0)
        self._rate_limiter = rate_limiter

    def search_by_isrc(self, isrc: str) -> ProviderCandidate | None:
        data = self._get(f"/track/isrc:{isrc}")
        if "error" in data:
            self._raise_unless_not_found(data)
            return None
        return self._to_candidate(data)

    def search_track(self, track: LocalTrack) -> list[ProviderCandidate]:
        query = f'artist:"{track.raw.artist or track.artist}" track:"{track.raw.title or track.title}"'
        data = self._get("/search", params={"q": query})
        if "error" in data:
            self._raise_unless_not_found(data)
            return []
        return [self._to_candidate(item) for item in data.get("data", [])]

    @staticmethod
    def _raise_unless_not_found(data: dict) -> None:
        error = data.get("error", {})
        if error.get("type") != _NOT_FOUND_ERROR_TYPE:
            raise ProviderError(f"Deezer API error: {error}")

    def _get(self, path: str, **kwargs) -> dict:
        if self._rate_limiter is not None:
            self._rate_limiter.wait()
        try:
            response = self._client.get(path, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Deezer request to {path} failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Deezer request to {path} returned malformed JSON: {exc}") from exc

    @staticmethod
    def _to_candidate(item: dict) -> ProviderCandidate:
        return ProviderCandidate(
            provider_track_id=str(item["id"]),
            artist=item.get("artist", {}).get("name", ""),
            title=item.get("title", ""),
            album=item.get("album", {}).get("title"),
            duration_seconds=float(item.get("duration", 0)),
            isrc=item.get("isrc"),
        )
