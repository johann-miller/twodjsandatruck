"""Metadata extraction: audio tags (mutagen), mime type (python-magic),
and in-archive audio inspection."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import magic
import mutagen

AUDIO_EXTENSIONS = {
    ".mp3",
    ".mp4",
    ".m4a",
    ".flac",
    ".ogg",
    ".oga",
    ".opus",
    ".wav",
    ".wma",
    ".aac",
    ".ape",
    ".aiff",
    ".aif",
}

_YEAR_RE = re.compile(r"^(\d{4})")


def _first_value(audio, key: str) -> str:
    try:
        value = audio.get(key)
    except (KeyError, TypeError, AttributeError, ValueError):
        return ""
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    if value is None:
        return ""
    return str(value).strip()


def get_audio_tags(src: str | Path) -> dict[str, str]:
    """Return normalized {artist, album, title, year, genre} tags."""
    tags = {"artist": "", "album": "", "title": "", "year": "", "genre": ""}
    try:
        audio = mutagen.File(str(src), easy=True)
    except Exception:
        return tags
    if audio is None:
        return tags

    tags["artist"] = _first_value(audio, "artist")
    tags["album"] = _first_value(audio, "album")
    tags["title"] = _first_value(audio, "title")
    tags["genre"] = _first_value(audio, "genre")
    year = _first_value(audio, "date") or _first_value(audio, "year")
    match = _YEAR_RE.search(year)
    if match:
        tags["year"] = match.group(1)
    return tags


def inspect_archive_tags(src: str | Path) -> dict[str, str]:
    """Extract audio tags from the first audio file inside a zip archive.

    Used for source.inspect: 'audio_tags' on archive rules.
    """
    tags = {"artist": "", "album": "", "title": "", "year": "", "genre": ""}
    try:
        with zipfile.ZipFile(src) as zf:
            for name in zf.namelist():
                suffix = Path(name).suffix.lower()
                if suffix not in AUDIO_EXTENSIONS:
                    continue
                data = zf.read(name)
                try:
                    audio = mutagen.File(io.BytesIO(data), easy=True)
                except Exception:
                    continue
                if audio is None:
                    continue
                return {
                    "artist": _first_value(audio, "artist"),
                    "album": _first_value(audio, "album"),
                    "title": _first_value(audio, "title"),
                    "genre": _first_value(audio, "genre"),
                    "year": _year_or_empty(audio),
                }
    except (zipfile.BadZipFile, OSError):
        pass
    return tags


def _year_or_empty(audio) -> str:
    year = _first_value(audio, "date") or _first_value(audio, "year")
    match = _YEAR_RE.search(year)
    return match.group(1) if match else ""


def get_mime(src: str | Path) -> str:
    try:
        return str(magic.from_file(str(src), mime=True))
    except Exception:
        return ""


def inspect(src: str | Path, method: str) -> dict[str, str]:
    """Dispatch to the metadata method requested by source.inspect."""
    if method == "audio_tags":
        return get_audio_tags(src)
    return {}