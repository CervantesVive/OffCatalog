# Test fixtures

`plain_version.mp3` and `live_version.mp3` are a few KB of silent audio
(generated via ffmpeg's `anullsrc`) with ID3 tags, not copyrighted content.
They are committed to the repo so tests don't depend on ffmpeg/mutagen at
test time.

To regenerate (requires `ffmpeg` on PATH):

```bash
uv run python tests/fixtures/make_fixtures.py
```
