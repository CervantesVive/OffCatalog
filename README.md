# OffCatalog

Scan an MP3 collection and find tracks not on streaming.

OffCatalog walks a local MP3 library, extracts and normalizes ID3 metadata,
checks each track against a streaming provider's catalog (Deezer in v1),
and produces:

- a persistent SQLite catalog of every track and its availability state,
- an interactive review queue for ambiguous matches,
- an `.m3u8` playlist of tracks that are confidently **not** on streaming,
  and
- CSV reports (`unavailable.csv`, `ambiguous.csv`, `errors.csv`).

It never guesses in favor of "available" — see
[`docs/matching.md`](docs/matching.md) for how the matching engine is
biased against false positives.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- (Docker path only) Docker + Docker Compose

## Install

```bash
uv sync
```

## Usage

Run each command from the repo root (or anywhere, passing `--db` to point
at a database file). Every command accepts `--db PATH` (default
`offcatalog.db`), which can also be set via the `OFFCATALOG_DB` environment
variable.

```bash
# Scan a music directory into the local database.
uv run offcatalog scan /path/to/music

# Check unchecked tracks against Deezer (rate-limited automatically).
uv run offcatalog check

# Re-check tracks currently in an ERROR state, and/or limit the batch size.
uv run offcatalog check --retry-errors --limit 200

# Interactively resolve ambiguous matches (same/different/skip).
uv run offcatalog review

# Write playlists/not-on-streaming.m3u8 (tracks unavailable on every checked provider).
uv run offcatalog playlist

# Write the ambiguous-match playlist instead.
uv run offcatalog playlist --state ambiguous --output playlists/ambiguous.m3u8

# Print state counts + a qualifier-frequency breakdown, and write CSV reports
# to reports/unavailable.csv, reports/ambiguous.csv, reports/errors.csv.
uv run offcatalog stats
```

`check` accepts `--provider NAME` (default `deezer`), but note: in v1 this
only selects which *storage key* results are recorded under — Deezer is
always the provider actually queried, since it's the only one implemented.
See [`docs/provider-selection.md`](docs/provider-selection.md) and
`TODO.md`.

### Configuration

Today, all configuration is via CLI flags and environment variables — there
is no config file the CLI reads yet. A `Config` dataclass and TOML loader
exist in `src/offcatalog/config.py` for future use but are not wired into
any command; see `TODO.md`. Provider secrets (none needed for Deezer) go in
a `.env` file — copy `.env.example` to `.env` and fill in anything a future
provider needs.

## Docker

For a homelab/server deployment, the same CLI runs inside a container. The
music directory is mounted **read-only**; a state directory (holding the
SQLite database and generated playlists/reports) is mounted **read-write**.

```bash
# Build the image.
docker compose build

# Scan a music library (mounted via $MUSIC_DIR, default /music).
MUSIC_DIR=/path/to/music docker compose run --rm offcatalog scan /music

# Check, review, playlist, stats — same pattern.
MUSIC_DIR=/path/to/music docker compose run --rm offcatalog check
MUSIC_DIR=/path/to/music docker compose run --rm offcatalog review
MUSIC_DIR=/path/to/music docker compose run --rm offcatalog playlist
MUSIC_DIR=/path/to/music docker compose run --rm offcatalog stats
```

The container sets `OFFCATALOG_DB=/state/offcatalog.db` and a working
directory of `/state`, so the database and any relative output paths
(`playlists/...`, `reports/...`) persist across separate `docker compose
run` invocations via the `OFFCATALOG_STATE_DIR` volume (default `./state`
on the host).

If you also run Navidrome against the same library, see
[`docs/navidrome.md`](docs/navidrome.md) for how to keep the generated
playlist's paths valid across both containers.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — module layout, database
  schema, provider protocol, what data leaves the machine.
- [`docs/matching.md`](docs/matching.md) — the three match levels, version
  qualifiers, and the five availability states.
- [`docs/provider-selection.md`](docs/provider-selection.md) — why Deezer
  was chosen and what's pending for a second provider.
- [`docs/navidrome.md`](docs/navidrome.md) — running alongside Navidrome.
- [`TODO.md`](TODO.md) — tracked future work and why each item is deferred.

## Development

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
```
