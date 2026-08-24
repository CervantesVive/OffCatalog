from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypedDict

if TYPE_CHECKING:
    from offcatalog.models import LocalTrack


class ProviderCandidate(TypedDict):
    provider_track_id: str
    artist: str
    title: str
    album: str | None
    duration_seconds: float
    isrc: str | None


class StreamingProvider(Protocol):
    name: str

    def search_by_isrc(self, isrc: str) -> ProviderCandidate | None: ...

    def search_track(self, track: LocalTrack) -> list[ProviderCandidate]: ...


class ProviderError(Exception):
    """Raised on network/parse failure. Never on a legitimate 'not found'."""


PROVIDER_REGISTRY: dict[str, type[StreamingProvider]] = {}


def register_provider(cls: type[StreamingProvider]) -> type[StreamingProvider]:
    PROVIDER_REGISTRY[cls.name] = cls
    return cls
