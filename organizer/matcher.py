"""Rule matching logic. Rules are evaluated top-to-bottom; first match wins."""

from __future__ import annotations

import re
from pathlib import Path

from . import metadata
from .config import MatchConfig, Rule


def _extension_ok(match: MatchConfig, path: Path) -> bool:
    if not match.extension:
        return True
    suffix = path.suffix.lower()
    return any(e.lower() == suffix for e in match.extension)


def _regex_ok(match: MatchConfig, path: Path) -> bool:
    if not match.filename_regex:
        return True
    return re.search(match.filename_regex, path.name) is not None


def _size_ok(match: MatchConfig, path: Path) -> bool:
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if match.min_size is not None and size < match.min_size:
        return False
    if match.max_size is not None and size > match.max_size:
        return False
    return True


def _mime_ok(match: MatchConfig, path: Path, mime: str) -> bool:
    if not match.mime_type:
        return True
    mime = mime or metadata.get_mime(path)
    return any(mime == entry or mime.startswith(entry.rstrip("/") + "/") for entry in match.mime_type)


def matches(rule: Rule, path: Path, mime: str = "") -> bool:
    """Return True if ``path`` matches every condition in ``rule.match``."""
    m = rule.match
    return (
        _extension_ok(m, path)
        and _regex_ok(m, path)
        and _size_ok(m, path)
        and _mime_ok(m, path, mime)
    )


def find_rule(rules: list[Rule], path: Path, mime: str = "") -> Rule | None:
    """First rule matched by ``path``, or None."""
    for rule in rules:
        if matches(rule, path, mime):
            return rule
    return None