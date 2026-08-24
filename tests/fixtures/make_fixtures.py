"""Run once to (re)generate tests/fixtures/*.mp3. Requires ffmpeg on PATH."""

import subprocess
from pathlib import Path

from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3

FIXTURES = Path(__file__).parent


def make_silent_mp3(path: Path, duration_seconds: float) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            str(duration_seconds),
            "-q:a",
            "9",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def tag(path: Path, **tags: str) -> None:
    audio = MP3(path, ID3=EasyID3)
    for key, value in tags.items():
        audio[key] = value
    audio.save()


if __name__ == "__main__":
    plain = FIXTURES / "plain_version.mp3"
    make_silent_mp3(plain, 3.0)
    tag(
        plain,
        artist="Depeche Mode",
        title="Enjoy the Silence",
        album="Violator",
        tracknumber="3",
        date="1990",
    )

    live = FIXTURES / "live_version.mp3"
    make_silent_mp3(live, 4.0)
    tag(
        live,
        artist="Depeche Mode",
        title="Enjoy the Silence (Live)",
        album="101",
        tracknumber="1",
        date="1989",
    )
