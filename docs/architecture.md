# Architecture

OffCatalog is a local-first CLI tool: it scans an MP3 collection, checks each
track against a streaming provider's catalog, and stores results in a local
SQLite database. There is no server component and no web UI.

## Module layout

```
src/offcatalog/
  cli.py                    # typer app: scan / check / review / playlist / stats
  config.py                 # Config dataclass + TOML loader (see "Config" below — not yet wired into the CLI)
  models.py                 # RawTags, LocalTrack, compute_fingerprint
  normalize.py               # text normalization, version-qualifier extraction
  ratelimit.py               # TokenBucket, injected into DeezerProvider
  playlist.py                 # .m3u8 writer
  reports.py                  # CSV report writer
  scanning/
    extract.py                # mutagen ID3 -> LocalTrack (raw + normalized)
  matching/
    engine.py                 # match_track(): level 1/2/3 matching
    types.py                  # AvailabilityState, MatchResult
  providers/
    base.py                   # StreamingProvider Protocol, ProviderCandidate,
                               # ProviderError, PROVIDER_REGISTRY, register_provider
    deezer.py                  # DeezerProvider — the only registered provider in v1
  db/
    connection.py               # sqlite3 stdlib connection + tiny numbered-migration runner
    repository.py               # all SQL: upserts, queries, check-result recording
    migrations/
      0001_init.sql              # full initial schema
      0002_availability_results_reason.sql  # adds availability_results.reason
docker/
  Dockerfile
docker-compose.yml
docs/
  architecture.md, provider-selection.md, matching.md, navidrome.md
README.md, TODO.md, .env.example
tests/
  fixtures/                    # generates real MP3s with ID3 tags for extraction tests
  unit/                        # one test module per src module, plus CLI-level tests
```

Data flows in one direction through the pipeline:

```
.mp3 file --(mutagen)--> RawTags/LocalTrack --(normalize.py)--> normalized fields
   --(matching/engine.py + a provider)--> MatchResult --(db/repository.py)--> SQLite
   --(playlist.py / reports.py)--> .m3u8 / .csv output
```

Raw and normalized fields are kept separate on `LocalTrack` (`raw: RawTags`
alongside normalized `artist`/`title`/etc.) — normalization must never be
lossy for matching purposes, and the untouched raw tags are what's actually
sent to the provider's search query (see "What leaves this machine" below).

## Database

SQLite, accessed through stdlib `sqlite3` (`db/connection.py`,
`db/repository.py`) — no ORM. `get_connection(db_path)` opens the connection,
enables `PRAGMA foreign_keys = ON`, and applies any migration `.sql` files
under `db/migrations/` that haven't already run, tracked in a
`schema_migrations` table. Migrations are numbered filenames
(`0001_init.sql`, `0002_...sql`); the runner rejects duplicate version
numbers up front, before executing any DDL, so a colliding migration file
fails cleanly instead of leaving the database half-migrated. There is no
separate `migrate` command — every `get_connection()` call (i.e. every CLI
command) brings the schema up to date automatically.

### Schema

- **`files`** — one row per scanned path. `mtime`/`size` support cheap
  change detection (skip re-parsing ID3 tags when neither changed).
  `deleted_at` is a soft delete — rows are never removed, just marked, so a
  reconnected drive or restored file can resurrect its history.
- **`local_tracks`** — one row per file's extracted track metadata,
  keyed by `file_id`. `version_qualifiers` and `raw_tags_json` are stored as
  JSON text columns (SQLite has no native array/object type). A file has at
  most one `local_tracks` row — `upsert_local_track` reuses the existing
  row's id on re-scan rather than inserting a duplicate.
- **`providers`** — one row per provider name (`"deezer"`, etc.), created
  lazily by `get_provider_id()` the first time that name is referenced.
- **`provider_candidates`** — **append-only history**, not upserted. Every
  `check` run that produces an `AVAILABLE` result inserts exactly one row
  (the winning candidate). Every `AMBIGUOUS` result inserts one row **per
  candidate** the provider returned, so `review` always has full history to
  show a human, even across repeated rescans. `UNAVAILABLE` results insert
  zero rows — there's no candidate worth keeping. This means the table grows
  on every rescan of an ambiguous track; there is no retention/cleanup pass
  in v1 (see `TODO.md`).
- **`availability_results`** — the current-state table, one row per
  `(local_track_id, provider_id)` pair, upserted (`ON CONFLICT ... DO
  UPDATE`) on every `check`. Holds `state`, `best_candidate_id` (nullable —
  only set for `AVAILABLE`), `checked_at`, `error_message`, and `reason`.
  `reason` (added by migration `0002`) holds the matching engine's
  explanation string — `isrc_exact`, `meta_duration`, `fuzzy_candidate`,
  `no_candidates`, `no_confident_candidate`, or `provider_error` — and is
  populated unconditionally by `record_check_result`. `error_message` is
  separate and holds the actual exception text, populated **only** on the
  `ERROR` path. `stats`'s CSV reports source `unavailable.csv`/
  `ambiguous.csv`'s `reason` column from `availability_results.reason`, and
  `errors.csv`'s `reason` column from `error_message` — deliberately
  different columns, because `error_message` is empty for every non-`ERROR`
  state.
- **`manual_match_decisions`** — one row per human verdict on an ambiguous
  candidate (`same_recording` / `different_recording`). Checked by
  `has_manual_decision()` at the top of `record_check_result` — once a
  decision exists for a track, further automated `check` runs skip updating
  that track's `availability_results` row entirely, so a human verdict is
  never overwritten by a subsequent rescan.
- **`scan_runs`** — defined in the schema (`id`, `started_at`,
  `finished_at`, `files_added/changed/deleted`) but **not currently written
  to by any code path** — `scan()` in `cli.py` doesn't insert a row here.
  The table exists for a future scan-history feature; see `TODO.md`.

`UNAVAILABLE_EVERYWHERE` is not a stored state — it's derived at
report/playlist time by `list_unavailable_everywhere()` (see
[matching.md](matching.md) for the exact rule).

## Provider Protocol and registry

`providers/base.py` defines the seam a second provider plugs into:

```python
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


def register_provider(cls): ...  # decorator, adds cls to PROVIDER_REGISTRY by cls.name
```

`DeezerProvider` (`providers/deezer.py`) is decorated with
`@register_provider`, so `PROVIDER_REGISTRY["deezer"]` is populated at
import time. It is the **only** registered provider in v1 — see
[provider-selection.md](provider-selection.md) for why Deezer was chosen and
what's pending before Spotify becomes provider #2.

**Important nuance:** `PROVIDER_REGISTRY` is populated but not yet consulted
by the CLI. `check --provider NAME` only selects which `providers.name` row
results are stored/looked-up under — `cli.py`'s `check` command
unconditionally constructs `DeezerProvider(...)` and calls it, regardless of
`--provider`'s value. Registry-driven dispatch (look up the class in
`PROVIDER_REGISTRY` and instantiate *that*) is deferred until a second
provider actually exists to dispatch to — see `TODO.md`.

## Matching engine

`matching/engine.py`'s `match_track(track, provider)` runs the three-level
matching described in full in [matching.md](matching.md): ISRC exact,
metadata+duration+qualifier gate, then rapidfuzz fuzzy fallback. It returns
a `MatchResult` (`matching/types.py`) with `state: AvailabilityState`,
`score`, `reason`, the winning `candidate` (if any), and the full
`all_candidates` list (used to persist ambiguous-match history).

## Config

`config.py` defines a `Config` dataclass (`music_root`, `db_path`,
`duration_tolerance_seconds`, `minimum_confident_score`, `providers`) and a
`load_config(path)` function that parses a TOML file shaped like:

```toml
[music]
root = "/music"
[matching]
duration_tolerance_seconds = 4
minimum_confident_score = 92
[providers.deezer]
enabled = true
```

**As shipped in v1, this module is not wired into `cli.py`.** No CLI command
calls `load_config()` or reads a `config.toml` file — every setting that
exists today (the database path, matching thresholds inside
`match_track`'s defaults) comes from CLI flags/env vars or hardcoded
defaults, not a config file. The dataclass and loader exist and are ready to
be wired up, but the README does not tell users to write a `config.toml`
because nothing currently reads one. See `TODO.md`.

## Rate limiting

`ratelimit.py`'s `TokenBucket(rate, per_seconds)` is injected into
`DeezerProvider`, which calls `.wait()` inside its internal `_get()` before
every real HTTP request — not once per track in the `check` loop. This
matters because a single `match_track` call can issue up to two Deezer
requests per track (an ISRC lookup, then a fallback search on a miss), so
throttling has to live at the actual request boundary to stay correct
against Deezer's published ~50 requests/5s limit.

## What leaves this machine

Only normalized track metadata is ever sent to a provider's search
endpoint: **artist, title, album (if present), duration, and ISRC (if
present)** — the exact fields in `ProviderCandidate`'s inputs
(`DeezerProvider.search_track`/`search_by_isrc` build their query from
`track.raw.artist`/`track.raw.title` or the normalized equivalents, plus the
ISRC string for the direct lookup).

**Never sent:** file paths, audio data, raw ID3 blobs, or any other tag not
listed above (e.g. no `musicbrainz_track_id`, no `track_number`, no
filename). The provider call is a plain HTTPS `GET` to a public
catalog-search endpoint; Deezer's catalog search requires no API key or
account credentials at all (see [provider-selection.md](provider-selection.md)).

## CLI command summary

See the README for exact commands and flags. In brief:

- `scan <path>` — walks for `.mp3` files, extracts/updates `local_tracks`,
  soft-deletes files no longer found.
- `check` — runs unchecked (or `--retry-errors`'d) tracks through the
  matching engine against Deezer, persists results.
- `review` — interactive prompt over `AMBIGUOUS` tracks, records
  `manual_match_decisions`.
- `playlist` — writes an `.m3u8` of tracks matching `--state`
  (`unavailable_everywhere` by default, or `ambiguous`).
- `stats` — prints state counts and a qualifier-frequency breakdown, and
  writes `unavailable.csv`/`ambiguous.csv`/`errors.csv` under `reports/`.

All five commands accept `--db` (default `offcatalog.db`), which also reads
from the `OFFCATALOG_DB` environment variable via typer's `envvar=`
parameter — this is how the Docker deployment points the CLI at
`/state/offcatalog.db` without repeating `--db` on every invocation (see
[navidrome.md](navidrome.md) and the README's Docker section).
