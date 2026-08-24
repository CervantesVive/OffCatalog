from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from offcatalog.providers.base import ProviderCandidate


class AvailabilityState(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_CHECKED = "NOT_CHECKED"
    ERROR = "ERROR"


@dataclass
class MatchResult:
    state: AvailabilityState
    score: float
    reason: str
    candidate: ProviderCandidate | None
    all_candidates: list[ProviderCandidate]
    error_message: str | None = None
