# Matching

OffCatalog decides whether a local track is available on a streaming
provider by escalating through three match levels
(`src/offcatalog/matching/engine.py`, `match_track()`). The engine is
deliberately biased against false positives: a fuzzy title match must never,
by itself, mark a rare track "available."

## The three match levels

**Level 1 — ISRC exact.** If the local track has an `isrc` tag, the provider
is queried directly by ISRC (`search_by_isrc`). A hit is an automatic
`AVAILABLE`, `score=1.0`, `reason="isrc_exact"` — this is the
highest-confidence path and short-circuits levels 2 and 3 entirely.

**Level 2 — metadata + duration gate.** If there's no ISRC hit, the provider
is searched by artist/title (`search_track`), and each candidate is checked
against three gates simultaneously:

- normalized artist matches exactly,
- duration is within `duration_tolerance_seconds` (default 4s) of the local
  track's duration, and
- version qualifiers are compatible (see below).

The first candidate passing all three gates is `AVAILABLE`,
`reason="meta_duration"`. Failing any one gate doesn't downgrade the
candidate — it's simply rejected, and matching falls through to level 3 with
the full candidate list.

**Level 3 — fuzzy.** `rapidfuzz.fuzz.token_set_ratio` scores `"{artist}
{title}"` against every remaining candidate. The best score decides the
outcome:

- Below 60 (`_AMBIGUOUS_FLOOR`) → `UNAVAILABLE`, `reason="no_confident_candidate"`.
- 60 or above → `AMBIGUOUS`, `reason="fuzzy_candidate"`, with every candidate
  retained for the `review` queue.

Fuzzy matching **never** produces `AVAILABLE` by itself — a strong text
similarity score alone is only ever grounds for a human review prompt, not
an automatic verdict.

If the provider returns zero candidates at all, the result is `UNAVAILABLE`,
`reason="no_candidates"` — no fuzzy comparison to run.

If the provider call itself fails (timeout, 5xx, malformed response), the
result is `ERROR`, `reason="provider_error"`, with the real exception text
in `MatchResult.error_message`. An `ERROR` is never treated as
`UNAVAILABLE` — a failed API call must never be silently read as catalog
absence.

## Version qualifiers: neutral vs. distinguishing

Titles carry parenthetical/bracketed qualifiers — `(Live)`, `(Remastered
2011)`, `(Hands and Feet Mix)` — that `normalize.py`'s `extract_qualifiers()`
pulls out of the title into a separate `version_qualifiers` list rather than
deleting them. Qualifiers are split into two classes:

- **Neutral** — stripped before the compatibility check, because they
  describe the same underlying recording: `Remaster`, `Remastered`,
  `Remastered YYYY`.
- **Distinguishing** — must match exactly on both sides of a comparison, or
  the pair is treated as a different recording: `Live`, `Demo`, `Radio Edit`,
  `Extended Mix`, `12" Mix`, `Instrumental`, `Acoustic`, `Remix`, `Mono`,
  `Stereo`, `Session`, and (via a free-text fallback for anything else in a
  parenthetical group, e.g. regional-edition markers like `(UK Edition)`)
  effectively any other bracketed qualifier not on the known list.

### Worked example

A local file tagged `Depeche Mode — Enjoy the Silence (Hands and Feet Mix)`
extracts to `base_title="enjoy the silence"`,
`version_qualifiers=["hands and feet mix"]`. If the provider's plain
`Enjoy the Silence` (no qualifier) comes back as a candidate, level 2's
qualifier-compatibility gate correctly rejects it — `{"hands and feet mix"}
!= set()` — because the 12" remix is a genuinely different recording from
the album version, not a re-master of it. That rejection is exactly the
behavior the qualifier split exists to guarantee: a distinguishing qualifier
on one side and not the other must never resolve to `AVAILABLE`.

By contrast, `Enjoy the Silence (Remastered 2011)` and plain `Enjoy the
Silence` normalize to the *same* qualifier set (`[]`, since `Remastered
2011` is neutral) and the same `base_title` — so the pair is treated as the
same underlying recording for matching purposes.

## `AvailabilityState`

Five states (`src/offcatalog/matching/types.py`):

| State | Meaning |
|---|---|
| `AVAILABLE` | A confident match was found (ISRC exact or metadata+duration+qualifier gate). |
| `UNAVAILABLE` | The provider was queried and no candidate met the confidence bar — either zero candidates came back, or the best fuzzy score was below the ambiguous floor (60). |
| `AMBIGUOUS` | A candidate looked plausible by fuzzy text similarity but didn't clear the confident-match gates — **this is the deliberate default whenever the engine is uncertain, never `AVAILABLE`.** Ambiguous results queue for human review (`offcatalog review`) rather than being auto-resolved either way. |
| `NOT_CHECKED` | No check has been recorded yet for this track/provider pair. This is a synthetic default (`get_availability_state`) derived from the absence of an `availability_results` row — it's never written to the database directly. |
| `ERROR` | The provider call itself failed (network/parse error). Distinct from `UNAVAILABLE` on purpose: a failed request is not evidence of catalog absence, and `ERROR` rows block the `UNAVAILABLE_EVERYWHERE` playlist verdict (see below) until re-checked and resolved. |

The core design principle carried through the whole engine: **uncertainty
resolves toward `AMBIGUOUS` (for human review) or `ERROR` (for retry),
never toward a false `AVAILABLE`.** A track only becomes `AVAILABLE`
through an ISRC exact match or a candidate that passes every metadata,
duration, and qualifier gate — fuzzy similarity alone is never enough.

## `UNAVAILABLE_EVERYWHERE`

Not a stored state — computed at report/`playlist` time
(`list_unavailable_everywhere` in `db/repository.py`) as: every enabled
provider has an `availability_results` row whose state is `UNAVAILABLE` or
`AMBIGUOUS`, and none is `AVAILABLE`. A provider still in `ERROR` or
`NOT_CHECKED` blocks the verdict — the playlist of "confidently not on
streaming" tracks only includes tracks every provider has actually had a
chance to confirm absent.

## Manual decisions override future checks

`offcatalog review` lets a human resolve an `AMBIGUOUS` track by recording a
`manual_match_decisions` row (`same_recording` flips the track to
`AVAILABLE`; `different_recording` records the verdict but leaves the track
`AMBIGUOUS` — a human "no" never auto-demotes to `UNAVAILABLE`). Once a
decision exists for a track, `record_check_result` skips its own update
entirely on any future rescan (`db/repository.py`, guarded by
`has_manual_decision`) — a human verdict is never silently overwritten by a
subsequent automated `check`.
