"""watchdog-based event loop for watch mode."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .config import Config
from .executor import process_path
from .logger import get_logger
from .matcher import find_rule

_IGNORED_SUFFIXES = frozenset(
    {".part", ".crdownload", ".partial", ".download", ".tmp", ".temp", ".swp", "~"}
)
_IGNORED_NAMES = frozenset({".goutputstream-", ".DS_Store", "Thumbs.db"})


def _is_ignored(path: Path) -> bool:
    if path.name in _IGNORED_NAMES or path.name.startswith("."):
        return True
    for suffix in _IGNORED_SUFFIXES:
        if path.name.endswith(suffix):
            return True
    return False


class _DebouncedHandler(FileSystemEventHandler):
    """Runs processor on each stable file path, debouncing high-frequency
    events (e.g. an in-progress download)."""

    def __init__(self, processor, delay: float = 2.0):
        self._processor = processor
        self._delay = delay
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def _schedule(self, path: str):
        with self._lock:
            old = self._timers.pop(path, None)
            if old:
                old.cancel()
            timer = threading.Timer(self._delay, self._fire, args=[path])
            timer.daemon = True
            self._timers[path] = timer
            timer.start()

    def _fire(self, path: str):
        with self._lock:
            self._timers.pop(path, None)
        self._processor(path)

    def on_created(self, event):
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._schedule(event.dest_path)

    def on_closed(self, event):
        if not event.is_directory:
            self._schedule(event.src_path)


def make_processor(config: Config, dry_run: bool = False):
    logger = get_logger()

    def process(path: str):
        path = Path(path)
        if path.is_dir() or _is_ignored(path):
            return
        rule = find_rule(config.rules, path)
        if rule is None:
            return
        logger.debug("event matched rule=%s file=%s", rule.name, path)
        process_path(path, rule, dry_run=dry_run)

    return process


def run_watch(config: Config, dry_run: bool = False) -> None:
    logger = get_logger()
    observer = Observer()
    processor = make_processor(config, dry_run=dry_run)
    handler = _DebouncedHandler(processor)

    watched: list[tuple[str, bool]] = []
    for watch in config.watch_dirs:
        path = os.path.expanduser(watch.path)
        if Path(path).is_dir():
            observer.schedule(handler, path, recursive=watch.recursive)
            watched.append((path, watch.recursive))
            logger.info("watching %s (recursive=%s)", path, watch.recursive)
        else:
            logger.warning("skipping missing watch dir: %s", watch.path)

    if not watched:
        logger.error("no valid watch dirs configured")
        return

    observer.start()
    logger.info("watch mode started (dry_run=%s) — press Ctrl+C to stop", dry_run)
    try:
        while observer.is_alive():
            observer.join(timeout=1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()