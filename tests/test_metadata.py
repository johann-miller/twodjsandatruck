import zipfile
from pathlib import Path

from organizer import metadata

from .helpers import make_mp3


def test_get_mime_text():
    tmp = Path(".")
    f = tmp / "plain.txt"
    f.write_text("hello plain text")
    try:
        assert metadata.get_mime(f) == "text/plain"
    finally:
        f.unlink()


def test_get_mime_missing():
    assert metadata.get_mime("/definitely/not/here.txt") == ""


def test_get_audio_tags_invalid():
    tags = metadata.get_audio_tags("/definitely/not/here.mp3")
    assert tags == {"artist": "", "album": "", "title": "", "year": "", "genre": ""}


def test_get_audio_tags_from_real_mp3(tmp_path: Path):
    mp3 = make_mp3(tmp_path / "song.mp3")
    tags = metadata.get_audio_tags(mp3)
    assert tags["artist"] == "Some Artist"
    assert tags["album"] == "Wonderful Album"
    assert tags["title"] == "My Song"
    assert tags["year"] == "1999"


def test_inspect_archive_tags(tmp_path: Path):
    song = make_mp3(tmp_path / "track1.mp3", artist="Zip Band", album="Zip Album",
                    title="Zipped")

    archive = tmp_path / "album.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(song, "subdir/track1.mp3")
        zf.writestr("cover.jpg", b"not audio")

    tags = metadata.inspect_archive_tags(archive)
    assert tags["artist"] == "Zip Band"
    assert tags["album"] == "Zip Album"
    assert tags["title"] == "Zipped"


def test_inspect_archive_no_audio(tmp_path: Path):
    archive = tmp_path / "noaudio.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", "hello")
    assert metadata.inspect_archive_tags(archive) == {
        "artist": "",
        "album": "",
        "title": "",
        "year": "",
        "genre": "",
    }