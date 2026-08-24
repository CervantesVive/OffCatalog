from __future__ import annotations

from offcatalog.matching.types import AvailabilityState, MatchResult
from offcatalog.models import LocalTrack
from offcatalog.providers.base import ProviderError, StreamingProvider


def match_track(
    track: LocalTrack,
    provider: StreamingProvider,
    *,
    duration_tolerance_seconds: float = 4.0,
    minimum_confident_score: float = 92.0,
) -> MatchResult:
    try:
        if track.isrc:
            isrc_candidate = provider.search_by_isrc(track.isrc)
            if isrc_candidate is not None:
                return MatchResult(
                    state=AvailabilityState.AVAILABLE, score=1.0, reason="isrc_exact",
                    candidate=isrc_candidate, all_candidates=[isrc_candidate],
                )
        candidates = provider.search_track(track)
    except ProviderError as exc:
        return MatchResult(
            state=AvailabilityState.ERROR, score=0.0, reason="provider_error",
            candidate=None, all_candidates=[], error_message=str(exc),
        )

    return _match_by_metadata(
        track, candidates,
        duration_tolerance_seconds=duration_tolerance_seconds,
        minimum_confident_score=minimum_confident_score,
    )


def _match_by_metadata(
    track: LocalTrack,
    candidates: list,
    *,
    duration_tolerance_seconds: float,
    minimum_confident_score: float,
) -> MatchResult:
    if not candidates:
        return MatchResult(
            state=AvailabilityState.UNAVAILABLE, score=0.0, reason="no_candidates",
            candidate=None, all_candidates=[],
        )
    return MatchResult(
        state=AvailabilityState.UNAVAILABLE, score=0.0, reason="no_candidates",
        candidate=None, all_candidates=candidates,
    )
