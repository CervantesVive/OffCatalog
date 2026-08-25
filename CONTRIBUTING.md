# Contributing

This is a personal project, but bug reports, small fixes, and new provider
implementations are welcome.

## Development setup

```bash
uv sync
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
```

## Before opening a PR

- Add or update tests for any behavior change — `uv run pytest -v` should
  pass, including the new/changed cases.
- Run `uv run ruff check .` and `uv run ruff format .` — CI enforces both.
- Keep the false-positive-safety principle intact: nothing should mark a
  track `AVAILABLE` on fuzzy text similarity alone. If you're touching
  matching logic, that's `src/offcatalog/matching/engine.py`.
- `@pytest.mark.manual` tests hit a real provider over the network and are
  excluded from the default run and from CI — they're for local
  verification only, not something a PR needs to pass.

## Pull requests

All changes land via pull request. At least one approving review is
required before merging.

## Reporting bugs or requesting features

Open a GitHub issue. For security issues, see [SECURITY.md](SECURITY.md)
instead of a public issue.

## Releasing (maintainers)

Versions are [SemVer](https://semver.org/) git tags (`vX.Y.Z`), bumped
manually — patch for fixes, minor for new features, major for breaking
changes.

1. Bump `version` in `pyproject.toml`.
2. Commit: `git commit -am "chore: bump version to X.Y.Z"` and push to `main`.
3. Tag and push the tag: `git tag vX.Y.Z && git push origin vX.Y.Z`.
4. The `release` workflow (`.github/workflows/release.yml`) runs the test
   suite, builds the package with `uv build`, and publishes a GitHub
   Release with auto-generated notes (from merged PRs/commits since the
   last tag) and the built wheel/sdist attached. No manual changelog file
   to maintain.
