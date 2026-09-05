from pathlib import Path

from organizer.config import Rule
from organizer.matcher import find_rule, matches


def make_rule(
    name="r",
    *,
    extension=None,
    regex=None,
    min_size=None,
    max_size=None,
    mime=None,
) -> Rule:
    match = {}
    if extension is not None:
        match["extension"] = extension
    if regex is not None:
        match["filename_regex"] = regex
    if min_size is not None:
        match["min_size"] = min_size
    if max_size is not None:
        match["max_size"] = max_size
    if mime is not None:
        match["mime_type"] = mime
    return Rule(
        name=name,
        match=match,
        destination={"template": "/dest"},
    )


def test_extension_match_case_insensitive(tmp_path: Path):
    f = tmp_path / "Album.ZIP"
    f.write_bytes(b"x")
    assert matches(make_rule(extension=[".zip"]), f)
    assert not matches(make_rule(extension=[".pdf"]), f)


def test_filename_regex(tmp_path: Path):
    f = tmp_path / "mysong_v2.flac"
    f.write_bytes(b"x")
    assert matches(make_rule(regex=r"mysong.*flac"), f)
    assert not matches(make_rule(regex=r"^other"), f)


def test_size_bounds(tmp_path: Path):
    f = tmp_path / "big.bin"
    f.write_bytes(b"12345")
    assert matches(make_rule(min_size=5), f)
    assert matches(make_rule(max_size=5), f)
    assert not matches(make_rule(min_size=6), f)
    assert not matches(make_rule(max_size=4), f)


def test_mime_prefix(tmp_path: Path):
    f = tmp_path / "photo.jpg"
    f.write_bytes(b"\xff\xd8\xff\xe0")
    assert matches(make_rule(mime=["image/"], extension=[".jpg"]), f)
    assert matches(make_rule(mime=["image/jpeg"]), f)
    assert not matches(make_rule(mime=["video/"]), f)


def test_mime_fallback_to_real_file(tmp_path: Path):
    f = tmp_path / "plain.txt"
    f.write_text("hello plain text")
    assert matches(make_rule(mime=["text/plain"]), f)


def test_all_conditions_must_match(tmp_path: Path):
    f = tmp_path / "x.zip"
    f.write_bytes(b"00000")
    rule = make_rule(extension=[".zip"], min_size=10)
    assert not matches(rule, f)


def test_first_match_wins(tmp_path: Path):
    f = tmp_path / "song.mp3"
    f.write_bytes(b"x")
    first = make_rule(name="first", extension=[".mp3"])
    second = make_rule(name="second", extension=[".mp3"])
    assert find_rule([first, second], f) is first
    assert find_rule([second, first], f) is second


def test_no_match_returns_none(tmp_path: Path):
    f = tmp_path / "file.xyz"
    f.write_bytes(b"x")
    assert find_rule([make_rule(extension=[".mp3"])], f) is None