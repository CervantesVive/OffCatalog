from __future__ import annotations

import os


def write_m3u8(tracks, output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for track in tracks:
            path = track["path"] if hasattr(track, "__getitem__") else track.path
            f.write(f"{path}\n")
