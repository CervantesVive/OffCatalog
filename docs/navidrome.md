# Running alongside Navidrome

OffCatalog produces an `.m3u8` playlist of tracks that look unavailable on
streaming (`playlists/not-on-streaming.m3u8` by default). If you run
[Navidrome](https://www.navidrome.org/) against the same music library, this
page covers how to point Navidrome at that playlist without the paths inside
it going stale.

## Why the mount path has to match

`.m3u8` files store plain filesystem paths, one per line, exactly as
OffCatalog saw them when it scanned (`playlist.py` writes each track's
`files.path` verbatim — no path rewriting or prefixing). If OffCatalog scans
your library at one path and Navidrome reads the same files at a
*different* path, every line in the playlist will point somewhere Navidrome
can't find.

The fix is to mount the exact same host music directory at the exact same
container path in both containers. If both containers see `/music` as the
library root, a playlist entry like `/music/Depeche Mode/Violator/04 - Enjoy
the Silence.mp3` resolves identically for both.

## docker-compose setup

OffCatalog's own `docker-compose.yml` already mounts the music directory
read-only at `/music`:

```yaml
services:
  offcatalog:
    build:
      context: .
      dockerfile: docker/Dockerfile
    volumes:
      - ${MUSIC_DIR:-/music}:/music:ro
      - ${OFFCATALOG_STATE_DIR:-./state}:/state:rw
    environment:
      - OFFCATALOG_DB=/state/offcatalog.db
    working_dir: /state
```

`MUSIC_DIR` (env var, defaulting to `/music` on the host) is the single
source of truth for where your library actually lives. Add a Navidrome
service to the same compose file (or a sibling compose project on the same
host) and mount **the same `MUSIC_DIR` value** at the **same container
path**:

```yaml
services:
  navidrome:
    image: deluan/navidrome:latest
    volumes:
      - ${MUSIC_DIR:-/music}:/music:ro
      - ./navidrome-data:/data
    ports:
      - "4533:4533"
```

As long as both services mount `${MUSIC_DIR}` at `/music`, a playlist
written by OffCatalog scanning `/music/...` paths is directly usable by
Navidrome reading `/music/...` paths — no path translation needed.

## Pointing Navidrome at the generated playlist

OffCatalog writes `playlists/not-on-streaming.m3u8` relative to wherever it
was run from (`offcatalog playlist --output <path>` to change it). Under the
compose setup above, the CLI's `working_dir` is `/state`, so the default
output lands at `/state/playlists/not-on-streaming.m3u8` inside the
container — i.e. `./state/playlists/not-on-streaming.m3u8` on the host
(given the `OFFCATALOG_STATE_DIR:-./state}` mount).

Navidrome auto-discovers `.m3u8` files it can see inside its **music**
folder tree, not an arbitrary data directory — it does not scan `/data`.
To make the generated playlist show up in Navidrome, either:

- Point `--output` at a path inside the music mount, e.g.:

  ```bash
  docker compose run --rm offcatalog playlist \
    --output /music/playlists/not-on-streaming.m3u8
  ```

  (Requires the music volume to be mounted read-write for this one write —
  either temporarily change `:ro` to `:rw` for the OffCatalog service, or
  write to a separate writable subdirectory that's also bind-mounted into
  Navidrome's music path.)

- Or run OffCatalog's `playlist` step outside the read-only constraint (bare
  `uv run offcatalog playlist --output /path/inside/navidrome/music/...` on
  the host, if OffCatalog and Navidrome share the host's filesystem
  directly rather than both being containerized).

Either way, after Navidrome's next library scan (or a manual "Scan Library"
trigger in its UI), `not-on-streaming.m3u8` appears as a playlist you can
browse and play directly from Navidrome.
