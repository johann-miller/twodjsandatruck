"""Test helpers: build minimal real MP3 files with tags."""

from __future__ import annotations

from pathlib import Path

from mutagen.id3 import ID3, TALB, TDRC, TIT2, TPE1

_MP3_FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 413


def make_mp3(
    path: Path,
    *,
    artist: str = "Some Artist",
    album: str = "Wonderful Album",
    title: str = "My Song",
    year: str = "1999",
) -> Path:
    """Create a valid MPEG-1 Layer III file carrying ID3 tags."""
    path = Path(path)
    tag = ID3()
    tag.add(TPE1(encoding=3, text=artist))
    tag.add(TALB(encoding=3, text=album))
    tag.add(TIT2(encoding=3, text=title))
    tag.add(TDRC(encoding=3, text=year))
    tag.save(path)
    with path.open("ab") as fh:
        fh.write(_MP3_FRAME * 2)
    return path