import zipfile
from pathlib import Path

from organizer.config import Rule
from organizer.executor import make_context, process_path, resolve_template


def make_move_rule(**overrides) -> Rule:
    defaults = dict(
        name="r",
        match={"extension": [".mp3"]},
        destination={"template": "{dest}"},
    )
    defaults.update(overrides)
    return Rule(**defaults)


def test_move_with_create_dirs(tmp_path: Path):
    src = tmp_path / "src"
    dest = tmp_path / "out"
    src.mkdir()
    f = src / "song.mp3"
    f.write_bytes(b"data")

    rule = make_move_rule(destination={"template": str(dest)})
    assert process_path(f, rule) == "moved"
    assert not f.exists()
    assert (dest / "song.mp3").read_bytes() == b"data"


def test_copy_leaves_source(tmp_path: Path):
    src = tmp_path / "src"
    dest = tmp_path / "out"
    src.mkdir()
    f = src / "song.mp3"
    f.write_bytes(b"data")

    rule = make_move_rule(action="copy", destination={"template": str(dest)})
    assert process_path(f, rule) == "copied"
    assert f.exists()
    assert (dest / "song.mp3").read_bytes() == b"data"


def test_conflict_skip(tmp_path: Path):
    src = tmp_path / "src"
    dest = tmp_path / "out"
    src.mkdir()
    f = src / "song.mp3"
    f.write_bytes(b"new")
    dest.mkdir()
    (dest / "song.mp3").write_bytes(b"old")

    rule = make_move_rule(on_conflict="skip", destination={"template": str(dest)})
    assert process_path(f, rule) == "skipped"
    assert (dest / "song.mp3").read_bytes() == b"old"
    assert f.exists()


def test_conflict_rename(tmp_path: Path):
    src = tmp_path / "src"
    dest = tmp_path / "out"
    src.mkdir()
    f = src / "song.mp3"
    f.write_bytes(b"new")
    dest.mkdir()
    (dest / "song.mp3").write_bytes(b"old")

    rule = make_move_rule(on_conflict="rename", destination={"template": str(dest)})
    assert process_path(f, rule) == "moved"
    assert (dest / "song (1).mp3").read_bytes() == b"new"
    assert (dest / "song.mp3").read_bytes() == b"old"


def test_conflict_rename_increments(tmp_path: Path):
    src = tmp_path / "src"
    dest = tmp_path / "out"
    src.mkdir()
    f = src / "song.mp3"
    f.write_bytes(b"new")
    dest.mkdir()
    (dest / "song.mp3").write_bytes(b"a")
    (dest / "song (1).mp3").write_bytes(b"b")

    rule = make_move_rule(on_conflict="rename", destination={"template": str(dest)})
    process_path(f, rule)
    assert (dest / "song (2).mp3").exists()


def test_conflict_overwrite(tmp_path: Path):
    src = tmp_path / "src"
    dest = tmp_path / "out"
    src.mkdir()
    f = src / "song.mp3"
    f.write_bytes(b"new")
    dest.mkdir()
    (dest / "song.mp3").write_bytes(b"old")

    rule = make_move_rule(on_conflict="overwrite", destination={"template": str(dest)})
    assert process_path(f, rule) == "moved"
    assert (dest / "song.mp3").read_bytes() == b"new"


def test_dry_run_does_not_touch_filesystem(tmp_path: Path):
    src = tmp_path / "src"
    dest = tmp_path / "out"
    src.mkdir()
    f = src / "song.mp3"
    f.write_bytes(b"data")

    rule = make_move_rule(destination={"template": str(dest)})
    assert process_path(f, rule, dry_run=True) == "move"
    assert f.exists()
    assert not dest.exists()


def test_extract_zip(tmp_path: Path):
    src = tmp_path / "src"
    dest = tmp_path / "out"
    src.mkdir()
    archive = src / "album.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("track1.mp3", b"aaa")
        zf.writestr("cover.jpg", b"bbb")

    rule = Rule(
        name="extract",
        match={"extension": [".zip"]},
        source={"type": "archive", "inspect": "none"},
        destination={"template": str(dest)},
        action="extract",
        on_conflict="skip",
    )
    assert process_path(archive, rule) == "extracted"
    assert (dest / "track1.mp3").read_bytes() == b"aaa"
    assert (dest / "cover.jpg").read_bytes() == b"bbb"


def test_extract_refuses_zip_slip(tmp_path: Path):
    src = tmp_path / "src"
    dest = tmp_path / "out"
    outside = tmp_path / "pwned"
    src.mkdir()
    archive = src / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../pwned.txt", b"gotcha")

    rule = Rule(
        name="extract",
        match={"extension": [".zip"]},
        source={"type": "archive", "inspect": "none"},
        destination={"template": str(dest)},
        action="extract",
    )
    process_path(archive, rule)
    assert not outside.exists()


def test_extract_dir_conflict_rename(tmp_path: Path):
    src = tmp_path / "src"
    dest = tmp_path / "out"
    src.mkdir()
    archive = src / "album.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("track1.mp3", b"aaa")
    dest.mkdir()
    (dest / "track1.mp3").write_bytes(b"existing")

    rule = Rule(
        name="extract",
        match={"extension": [".zip"]},
        source={"type": "archive"},
        destination={"template": str(dest)},
        action="extract",
        on_conflict="rename",
    )
    assert process_path(archive, rule) == "extracted"
    assert (tmp_path / "out (1)" / "track1.mp3").read_bytes() == b"aaa"


def test_template_placeholders_from_metadata(tmp_path: Path):
    ctx = FileContextSpy(tmp_path / "x.mp3", tags={"year": "1999"})
    template = "/base/{artist}/{album}/{title}/{year}/{filename}"
    rendered = resolve_template(template, ctx)
    assert str(rendered) == "/base/Artist Mans/Album/Title One/1999/x.mp3"


class FileContextSpy:
    def __init__(self, path: Path, tags=None):
        self.path = path
        self.tags = {
            "artist": "Artist Mans",
            "album": "Album",
            "title": "Title One",
            "year": "",
            "genre": "",
        }
        if tags:
            self.tags.update(tags)
        self.mtime = __import__("datetime").datetime(2001, 2, 3)


def test_template_mtime_fallback(tmp_path: Path):
    ctx = FileContextSpy(tmp_path / "x.pdf")
    rendered = resolve_template("/docs/{year}/{month}/{day}", ctx)
    assert str(rendered) == "/docs/2001/02/03"


def test_template_empty_artist_collapses(tmp_path: Path):
    ctx = FileContextSpy(tmp_path / "x.mp3", tags={"artist": ""})
    rendered = resolve_template("/music/{artist}/{album}", ctx)
    assert str(rendered) == "/music/Album"


def test_make_context_pulls_tags(tmp_path: Path):
    from organizer.config import Rule

    rule = Rule(
        name="r",
        match={"extension": [".mp3"]},
        source={"type": "file", "inspect": "none"},
        destination={"template": "/d"},
    )
    f = tmp_path / "noise.mp3"
    f.write_bytes(b"not really audio")
    ctx = make_context(f, rule)
    assert ctx.tags == {}


def test_invalid_source_is_error(tmp_path: Path):
    f = tmp_path / "song.mp3"
    f.write_bytes(b"data")
    rule = make_move_rule(destination={"template": str(tmp_path / "out")})
    # non-trivial: valid flow is fine; here we test error path via a bogus source
    bogus = tmp_path / "missing.mp3"
    assert process_path(bogus, rule) == "error"