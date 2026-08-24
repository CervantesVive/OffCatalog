from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    music_root: str = "."
    db_path: str = "offcatalog.db"
    duration_tolerance_seconds: float = 4.0
    minimum_confident_score: float = 92.0
    providers: dict[str, bool] = field(default_factory=lambda: {"deezer": True})


def load_config(path: str | None) -> Config:
    if path is None or not Path(path).exists():
        return Config()

    with open(path, "rb") as f:
        data = tomllib.load(f)

    music = data.get("music", {})
    matching = data.get("matching", {})
    providers = {
        name: section.get("enabled", True)
        for name, section in data.get("providers", {}).items()
    } or {"deezer": True}

    return Config(
        music_root=music.get("root", "."),
        duration_tolerance_seconds=matching.get("duration_tolerance_seconds", 4.0),
        minimum_confident_score=matching.get("minimum_confident_score", 92.0),
        providers=providers,
    )
