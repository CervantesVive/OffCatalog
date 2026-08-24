# Provider selection

OffCatalog checks local tracks against streaming-service catalogs through a
small `StreamingProvider` protocol (see [architecture.md](architecture.md)).
This document records the research behind picking the first (and, in v1,
only) implementation: Deezer.

## Research (2026-08-24)

Researched official catalog-search API availability across the streaming
services a personal music collection would plausibly be checked against:

| Provider | Legit API access | ISRC support | Duration | Auth | Notes |
|---|---|---|---|---|---|
| **Deezer** | Yes — free app registration, no OAuth for catalog search | Yes, dedicated `/track/isrc:<ISRC>` endpoint | Yes | None (no token needed) | ~50 req/5s; ToS allows non-commercial personal projects; no deprecation trend found |
| Spotify | Yes, but shrinking | Yes, via `isrc:` search filter | Yes | Client Credentials flow | Nov 2024 + Feb 2026 changelogs cut several endpoints and search page size (50→10) for non-extended apps; still functional but trending more restrictive |
| Apple Music | Yes, but costly | Yes | Yes | Requires paid Apple Developer Program ($99/yr) + MusicKit JWT signing | Too much friction/cost for v1 |
| YouTube Music | No official API | N/A | N/A | N/A (unofficial `ytmusicapi` scrapes the web client) | Fails "legitimate API access" requirement — excluded |
| Tidal / Amazon Music | No self-serve API | — | — | — | Tidal is partner-only; Amazon has no public catalog API — excluded |

## Decision

**Implement Deezer first**, and — as of this v1 build — implement Deezer
*only*. Reasons:

- Zero-friction legitimate access: a free, unauthenticated `GET` against a
  public catalog-search API, no OAuth dance, no paid developer account.
- Real ISRC exact-match support (`GET /track/isrc:<ISRC>`) — this is the
  matching engine's highest-confidence tier (see
  [matching.md](matching.md)), and not every candidate provider offers it
  this directly.
- Duration returned on every response, needed for the level-2
  metadata+duration gate.
- Generous unauthenticated rate limits (~50 requests/5s), workable for
  checking a large personal library without begging for API keys.
- No visible deprecation trend, unlike Spotify's tightening developer
  program.

Spotify is the natural provider #2 once multi-provider support is wired up
(see the "Deferred" section below and `TODO.md`), but it's riskier to lean on
as the *sole* provider given its attrition pattern (shrinking endpoints,
shrinking page sizes for non-extended apps).

## Open item — verify before adding Spotify as provider #2

There is conflicting/thin sourcing on whether Spotify's Development Mode now
requires a Premium account to use. This was **not** confirmed one way or the
other during research, and does not block Deezer-only v1. Verify manually
before starting Spotify provider work.

## Current status: v1 is Deezer-only

The `StreamingProvider` protocol, `ProviderCandidate` shape, and
`PROVIDER_REGISTRY`/`register_provider` decorator (in
`src/offcatalog/providers/base.py`) are all designed so a second provider is
"implement the protocol, register it" — no schema or CLI redesign needed.
`DeezerProvider` (`src/offcatalog/providers/deezer.py`) is the only
registered implementation.

Two CLI surfaces reference "provider" today but only in a limited sense:

- `check --provider NAME` selects which **storage/lookup key** (the
  `providers.name` row and its `availability_results`/`provider_candidates`
  rows) a result is recorded under. It does **not** select which
  implementation makes the API call — v1 always calls `DeezerProvider`
  regardless of `--provider`'s value, because it's the only registered
  provider. Passing `--provider spotify` today would record real Deezer
  results under a `spotify` row, which is misleading; don't do that until a
  second provider actually exists. See `TODO.md` for the registry-driven
  dispatch work that closes this gap.
- `playlist` has **no** `--provider` flag in v1 — it would be a no-op with a
  single provider, so it was left out rather than shipped as dead weight.

Both are tracked as explicit future work in `TODO.md`, not silently dropped.
