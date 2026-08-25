# Security Policy

OffCatalog is a local-first personal tool with no server component, no user
accounts, and no credentials of its own. The things most worth reporting:

- A bug in the matching engine that could cause a rare/unavailable track to
  be misclassified as `AVAILABLE` — this project's core guarantee is that a
  fuzzy match alone should never do that, so a way to trigger it is a real
  finding, not just a bug report.
- Anything that causes more than normalized artist/title text (or a bare
  ISRC) to be sent to a provider's search API — see the README's "Does
  anything ever get uploaded" answer for what's supposed to leave this
  machine, and nothing else should.
- A vulnerability in a dependency (`mutagen`, `httpx`, `rapidfuzz`, `typer`)
  that's actually reachable through how this project uses it.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repo —
https://github.com/CervantesVive/OffCatalog/security/advisories/new —
rather than opening a public issue. This is a personal project maintained
in my spare time, so there's no formal SLA, but reports won't be ignored.
