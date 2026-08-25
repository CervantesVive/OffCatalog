# TODO

Tracked future work. Each item is deliberately out of scope for v1 — see the
"why deferred" note on each, not just the fact that it's deferred.

## Providers

- **Spotify as provider #2.** Blocked on manually verifying whether
  Spotify's Development Mode now requires a Premium account — sourcing on
  this was conflicting/thin during research and was left unconfirmed.
  Verify before starting this work; it doesn't block anything else.
- **Apple Music provider.** Deferred on cost/auth friction: requires a paid
  Apple Developer Program account ($99/yr) plus MusicKit JWT signing, both
  disproportionate for a personal-project provider #3.
- **Wire `check --provider` through `PROVIDER_REGISTRY`.** Today
  `--provider NAME` only selects the *storage key* results are recorded
  under; `cli.py`'s `check` command hardcodes `DeezerProvider()`
  regardless of the flag's value. Deferred because there's no functional
  payoff until a second provider is actually registered — dispatch logic
  with only one implementation to dispatch to is speculative. Do this
  alongside (or right after) whichever provider becomes #2.
- **`playlist --provider` filter.** Same reasoning as above — with a single
  registered provider, a provider filter on `playlist` would be a no-op
  flag with nothing to test. Add it once a second provider exists and
  results can actually diverge per provider.
- **Multi-provider scoping in `stats`/reports.** `compute_state_counts` and
  `list_tracks_by_state` (`db/repository.py`) are currently scoped to a
  single (the first-registered) provider — harmless with one provider, but
  will need explicit `provider_id` scoping once a second provider's rows
  coexist in the same tables. Bundle with the registry-dispatch work above.

## UX

- **Textual TUI for `review`.** Plain CLI prompts (`[s]ame / [d]ifferent /
  [k]ip`) are the v1 interface. A TUI is the natural upgrade path if plain
  prompts prove unwieldy at high ambiguous-track counts, but wasn't worth
  building before real usage data on typical ambiguous-queue size existed.
- **Candidate-index input validation in `review`.** When a track has
  multiple candidates, `review` prompts for a numeric index but doesn't
  validate it — a non-numeric or out-of-range entry crashes the review
  session mid-loop instead of re-prompting. Minor UX gap, not fixed in v1;
  low cost since it only interrupts one review session, not persisted
  state.

## Matching

- **Acoustic fingerprinting.** v1 uses a metadata+duration fingerprint
  (hash of raw tags + duration + file size) purely for local change
  detection, not audio-content matching. True acoustic fingerprinting
  (e.g. Chromaprint/AcoustID) was explicitly out of scope for v1 per the
  original design spec — it's a real accuracy improvement for tricky cases
  (mislabeled tags, near-duplicate masters) but a much larger dependency
  and processing-time cost than the metadata approach.
- **Nested-parenthetical qualifiers.** `extract_qualifiers` collapses on
  the first pattern match inside a parenthetical group, so
  `"Track (Live (Acoustic))"` only extracts one qualifier instead of both.
  Not fixed in v1 — no real-world tag observed to exercise this shape yet,
  so it's tracked rather than guessed at.
- **`feat.` credits nested inside another qualifier group.** A title like
  `"Track (Live feat. Other Artist)"` has its featuring credit stripped
  along with the `Live` marker, since the featuring-exclusion check
  (`_FEATURING_GROUP_RE`) only matches when `feat.`/`ft.`/`featuring`
  starts the group. Low-impact (the credit is dropped from qualifier
  extraction, not from `artist`/`title` matching), not fixed in v1.

## Data model / storage

- **`config.toml` support is unwired.** `src/offcatalog/config.py` defines
  a `Config` dataclass and `load_config()` TOML loader, but no CLI command
  calls it — all settings are CLI flags/env vars today. Wiring this up
  (probably as a `--config PATH` option read once at CLI startup, feeding
  defaults for `--db`, matching thresholds, and enabled providers) is real
  future work, not dead code to delete — the loader was built ahead of the
  CLI plumbing that would consume it.
- **`scan_runs` table is never populated.** The schema
  (`db/migrations/0001_init.sql`) defines a `scan_runs` table intended to
  record per-scan history (files added/changed/deleted, start/finish
  times), but `scan()` in `cli.py` never inserts a row into it. Either wire
  it up (useful for a future "scan history" report) or drop the table in a
  later migration — currently it's dead schema.
- **`provider_candidates` retention.** The table is intentionally
  append-only (every `AMBIGUOUS` check appends a full candidate list, so
  `review` always has history) but has no cleanup/retention pass — repeated
  rescans of a still-ambiguous library grow it without bound. Acceptable at
  v1's target scale (a personal library, not unbounded rescan frequency);
  worth a retention pass if it becomes an actual storage concern later.

## Docker

- **No `.dockerignore`.** The build context includes local `.venv/`,
  `__pycache__/`, etc. — a transfer-overhead nit, not a correctness issue,
  since the `Dockerfile` only `COPY`s specific paths (`pyproject.toml`,
  `uv.lock`, `README.md`, `src/`). Cheap to add later.
- **No non-root `USER` in the image.** Common and generally accepted for a
  homelab-scale personal tool's container, but worth hardening if this ever
  runs somewhere more exposed than a private homelab network.

## Explicit non-goals (carried from the original design spec, not new)

- No web UI — this is a CLI tool by design.
- No YouTube Music or Tidal/Amazon Music providers — excluded outright
  during provider research for lacking any legitimate self-serve API
  access, not merely deferred.
