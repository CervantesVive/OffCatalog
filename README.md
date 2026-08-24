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
The name is validated against the provider registry, so a typo or a
not-yet-implemented provider fails fast instead of recording results under a
bogus provider row.
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

## FAQ / common workflows

**First-time setup on my whole library — what's the sequence?**

```bash
uv run offcatalog scan /path/to/music     # populate the catalog
uv run offcatalog check                   # check every track against Deezer (rate-limited, resumable)
uv run offcatalog review                  # resolve anything ambiguous
uv run offcatalog playlist                # write playlists/not-on-streaming.m3u8
uv run offcatalog stats                   # see the breakdown + CSV reports
```

`check` is rate-limited to Deezer's published limit and commits each
track's result as it goes, so it's safe to `Ctrl-C` and re-run later — it
picks up where it left off (only unchecked tracks are selected).

**A track has a real B-side/alternate mix but shows AMBIGUOUS instead of
UNAVAILABLE — why isn't it just marked unavailable?**

Because Deezer's search still returns the artist's *other* tracks even
when the exact recording you have isn't in their catalog. The matching
engine won't call that a confident non-match on title similarity alone —
it hands you the candidate list instead. For example, checking a genuine
"Enjoy the Silence (Hands and Feet Mix)" against real Deezer data returns
17 same-artist/same-title-ish candidates, none matching on duration or
qualifiers, so it's `AMBIGUOUS`, not silently mismatched:

```
Local:  depeche mode - enjoy the silence (401.0s)
  [0] Depeche Mode - Enjoy the Silence (MS Project vs. Depeche Mode) (178.0s) score=1.00
  ...
  [12] Depeche Mode - Enjoy the Silence (Hands and Feet Mix) (401.0s) score=1.00
  ...
[s]ame / [d]ifferent / [k]ip [k]:
```

This is deliberate — see [`docs/matching.md`](docs/matching.md). Run
`review` and confirm it by hand; your decision is permanent (see below).

**How do I work through a big review queue efficiently?**

`review` walks every `AMBIGUOUS` track one at a time. For each, type the
candidate's index and `s` (same recording) or `d` (different) — or just
`k` to skip and revisit later. If there's only one candidate you can type
`s`/`d` directly (defaults to index `0`). There's no bulk-accept; that's
intentional — a queue that can be rubber-stamped defeats the point of
having one.

**Will `check`/`scan` overwrite a decision I made in `review`?**

No. Once you mark a track `same_recording` or `different_recording`, no
future `check` run touches that track's result — verified by test. If you
change your mind, re-run `review` again for that provider; it'll re-offer
any track still `AMBIGUOUS`, but a track you already resolved won't
reappear (its state is no longer `AMBIGUOUS`).

**I fixed a wrong/missing tag (e.g. added a missing ISRC) — do I need to
wipe the database to get it re-checked?**

No. `scan` re-extracts any file whose stat (mtime/size) changed, which
updates its fingerprint; the next `check` run automatically re-checks any
track whose fingerprint no longer matches what its last result was
computed against. Just run `scan` then `check` again.

**I unmounted/moved a drive and re-scanned — are the missing tracks gone
for good?**

No, they're soft-deleted (a `deleted_at` timestamp, not a row deletion),
so `playlist`/`stats`/`review` all stop showing them, but nothing is
lost. Reconnect the drive and `scan` again — if the file's stat matches
what was recorded, it's automatically un-deleted with its full history
intact.

**How do I check just a handful of tracks, or resume a huge check run in
batches?**

```bash
uv run offcatalog check --limit 200
```

Run it repeatedly; each run only picks up tracks that still need
checking, so you can chip away at a 15k-track library across many
sessions without re-doing work.

**A bunch of tracks are stuck in `ERROR` — what happened, and how do I
retry?**

`ERROR` means the Deezer API call itself failed (timeout, rate limit,
malformed response) — it's never used to mean "not on streaming." Retry
with:

```bash
uv run offcatalog check --retry-errors
```

**Can I get a playlist of just the ambiguous tracks, to sanity-check my
`review` decisions?**

```bash
uv run offcatalog playlist --state ambiguous --output playlists/ambiguous.m3u8
```

**What does "not on streaming" actually mean — not on Deezer, or not on
anything?**

In v1, Deezer is the only checked provider, so `playlist`'s default
output (`UNAVAILABLE_EVERYWHERE`) currently means "not on Deezer." The
state is architected to require *every* configured provider to agree
before a track qualifies — once a second provider exists, the same
command will mean "not on any of them," with no code changes needed on
your end.

**Does anything ever get uploaded — my file paths, the audio itself?**

No. Only normalized artist/title text (or a bare ISRC) is sent to
Deezer's public search endpoint — never file paths, audio, or raw ID3
tag text. See ["What leaves this
machine"](docs/architecture.md#what-leaves-this-machine) for the exact
breakdown.

**How do I run this on a schedule / homelab server instead of my laptop?**

See the [Docker](#docker) section above and
[`docs/navidrome.md`](docs/navidrome.md) if you also run Navidrome — the
short version is: mount your music library at the same container path in
both services, and point Navidrome at the `.m3u8` OffCatalog writes into
the shared state volume.

**I want to add Spotify/Apple Music as a second provider — where do I
start?**

The provider seam is `StreamingProvider` in `src/offcatalog/providers/base.py`
— implement `search_by_isrc`/`search_track` against
`ProviderCandidate` shape and register with `@register_provider`. See
[`TODO.md`](TODO.md) for what's already tracked as needed for
multi-provider support (CLI dispatch, the `playlist --provider` filter,
etc.) before it's fully wired up end-to-end.

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
