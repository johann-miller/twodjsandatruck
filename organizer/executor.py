"""Performs move/copy/extract actions, destination template resolution,
and conflict handling."""

from __future__ import annotations

import os
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import click

from . import metadata
from .config import Rule
from .logger import get_logger, log_action, log_error

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_INVALID_PATH_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
_UNSAFE_COMPONENTS = {os.sep, "/", ".", ".."}


class ConflictError(Exception):
    pass


@dataclass
class FileContext:
    path: Path
    tags: dict[str, str] = field(default_factory=dict)
    mtime: datetime = None  # type: ignore[assignment]


def _sanitize_component(value: str) -> str:
    value = _INVALID_PATH_CHARS.sub("", value).strip()
    value = value.replace("/", " ").replace("\\", " ").strip(" .")
    return value


def _resolve_placeholder(name: str, ctx: FileContext) -> str:
    if name in ("artist", "album", "title", "genre") and ctx.tags.get(name):
        return _sanitize_component(ctx.tags[name])
    if name == "year":
        tag_year = ctx.tags.get("year")
        return tag_year or str(ctx.mtime.year)
    if name == "month":
        return f"{ctx.mtime.month:02d}"
    if name == "day":
        return f"{ctx.mtime.day:02d}"
    if name == "filename":
        return ctx.path.name
    if name == "name":
        return ctx.path.stem
    if name == "ext":
        return ctx.path.suffix
    return ""


def resolve_template(template: str, ctx: FileContext) -> Path:
    """Render a destination template into a filesystem path.

    Unknown/empty placeholders resolve to an empty string; duplicate path
    separators and trailing separators are normalized away.
    """
    rendered = _PLACEHOLDER_RE.sub(lambda m: _resolve_placeholder(m.group(1), ctx), template)
    path = Path(rendered)
    return Path(os.path.expanduser(os.path.expandvars(str(path))))


def make_context(path: Path, rule: Rule) -> FileContext:
    tags: dict[str, str] = {}
    if rule.source.inspect == "audio_tags":
        if rule.source.type == "archive":
            tags = metadata.inspect_archive_tags(path)
        else:
            tags = metadata.get_audio_tags(path)
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        mtime = datetime.now()
    return FileContext(path=path, tags=tags, mtime=mtime)


def _unique_file(dst: Path) -> Path:
    if not dst.exists():
        return dst
    stem, ext = dst.stem, dst.suffix
    i = 1
    while True:
        candidate = dst.with_name(f"{stem} ({i}){ext}")
        if not candidate.exists():
            return candidate
        i += 1


def _unique_dir(dst: Path) -> Path:
    if not dst.exists():
        return dst
    i = 1
    while True:
        candidate = dst.with_name(f"{dst.name} ({i})")
        if not candidate.exists():
            return candidate
        i += 1


def _resolve_file_conflict(dst: Path, strategy: str, dry_run: bool) -> tuple[Path, str]:
    if not dst.exists():
        return dst, "ok"
    if strategy == "skip":
        return dst, "skipped"
    if strategy == "rename":
        return _unique_file(dst), "ok"
    if strategy == "overwrite":
        return dst, "ok"
    if strategy == "prompt":
        if dry_run or not click.get_text_stream("stdin").isatty():
            return dst, "skipped"
        if click.confirm(f"Overwrite {dst}?", default=False):
            return dst, "ok"
        return dst, "skipped"
    return dst, "skipped"


def _zip_parts(member) -> tuple[str, ...]:
    return Path(member.filename.replace("\\", "/")).parts


def _leading_folder_count(zf: zipfile.ZipFile, ctx: FileContext, template: str) -> int:
    """How many leading zip folders to strip before extracting.

    Rather than blindly flattening, this only peels folders whose names the
    destination template will already re-create via the ``{artist}``/``{album}``
    placeholders. Anything else (e.g. an album folder under a ``music/{artist}``
    destination) is preserved verbatim. Returns 0 when stripping is unsafe
    (stray top-level files, multiple root folders).
    """
    artist = ctx.tags.get("artist", "").lower().strip()
    album = ctx.tags.get("album", "").lower().strip()
    want_artist = "{artist}" in template
    want_album = "{album}" in template
    if (not want_artist and not want_album) or (want_artist and not artist) or (want_album and not album):
        return 0

    roots: dict[str, str] = {}
    second_level: str | None = None
    for member in zf.infolist():
        parts = _zip_parts(member)
        if not parts or parts[0] in ("/", ""):
            return 0
        if parts[0].lower().strip() in _UNSAFE_COMPONENTS:
            return 0
        if len(parts) == 1 and not member.is_dir():
            return 0
        roots[parts[0].lower().strip()] = parts[0]
        if len(parts) >= 2 and second_level is None:
            second_level = parts[1]

    if len(roots) != 1:
        return 0

    root = next(iter(roots.values())).lower().strip()
    if want_artist and root == artist:
        if want_album and second_level and second_level.lower().strip() == album:
            return 2
        return 1
    if want_album and root == album:
        return 1
    return 0


def _extract_safe(zf: zipfile.ZipFile, dest_dir: Path, strip: int = 0) -> None:
    for member in zf.infolist():
        components = _zip_parts(member)[strip:]
        if not components:
            continue
        if any(part in _UNSAFE_COMPONENTS for part in components):
            continue
        target = dest_dir.joinpath(*components)
        resolved = target.resolve()
        if not resolved.is_relative_to(dest_dir.resolve()):
            continue
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def _extract(path: Path, dest_dir: Path, rule: Rule, dry_run: bool, ctx: FileContext) -> str:
    conflict = dest_dir.exists() and any(dest_dir.iterdir())
    if conflict and rule.on_conflict == "skip":
        return "skipped"
    if conflict and rule.on_conflict == "rename":
        dest_dir = _unique_dir(dest_dir)
    if conflict and rule.on_conflict == "prompt":
        if dry_run or not click.get_text_stream("stdin").isatty():
            return "skipped"
        if not click.confirm(f"Extract into existing directory {dest_dir}?", default=False):
            return "skipped"
    if rule.destination.create_dirs and not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as zf:
        strip = _leading_folder_count(zf, ctx, rule.destination.template)
        get_logger().debug("zip %s: stripping %d leading folder(s)", path, strip)
        if not dry_run:
            _extract_safe(zf, dest_dir, strip)
    return "extract" if dry_run else "extracted"


def _log_result(result: str, path: Path, destination: str, rule: Rule, dry_run: bool) -> None:
    if dry_run:
        get_logger().info("would %s: %s -> %s (rule=%s)", result, path, destination, rule.name)
    else:
        log_action(result, str(path), destination, rule.name)


def process_path(path: Path, rule: Rule, dry_run: bool = False) -> str:
    """Apply ``rule`` to ``path``. Returns the resulting action label."""
    try:
        ctx = make_context(path, rule)
        dest_dir = resolve_template(rule.destination.template, ctx)

        if rule.action == "extract":
            result = _extract(path, dest_dir, rule, dry_run, ctx)
            destination = str(dest_dir)
        else:
            dst = dest_dir / path.name
            dst, result = _resolve_file_conflict(dst, rule.on_conflict, dry_run)
            if rule.destination.create_dirs and not dry_run:
                dest_dir.mkdir(parents=True, exist_ok=True)
            if result == "ok" and not dry_run:
                if rule.action == "move":
                    shutil.move(str(path), str(dst))
                    result = "moved"
                else:
                    shutil.copy2(str(path), str(dst))
                    result = "copied"
            elif result == "ok":
                result = rule.action
            destination = str(dst)

        _log_result(result, path, destination, rule, dry_run)
        return result
    except Exception as exc:
        log_error(str(path), rule.name, exc)
        return "error"