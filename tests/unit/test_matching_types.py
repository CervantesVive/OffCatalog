from offcatalog.matching.types import AvailabilityState, MatchResult


def test_availability_state_values():
    assert AvailabilityState.AVAILABLE.value == "AVAILABLE"
    assert AvailabilityState.UNAVAILABLE.value == "UNAVAILABLE"
    assert AvailabilityState.AMBIGUOUS.value == "AMBIGUOUS"
    assert AvailabilityState.NOT_CHECKED.value == "NOT_CHECKED"
    assert AvailabilityState.ERROR.value == "ERROR"


def test_match_result_defaults():
    result = MatchResult(
        state=AvailabilityState.UNAVAILABLE, score=0.0, reason="no_candidates",
        candidate=None, all_candidates=[],
    )
    assert result.error_message is None
