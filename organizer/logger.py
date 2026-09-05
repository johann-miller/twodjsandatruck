"""Logging setup: rotating file handler plus rich console handler."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

from .config import LoggingConfig

FILE_SIZE_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3

_console = Console()


def setup_logging(cfg: LoggingConfig) -> None:
    """Configure root package logging from a LoggingConfig."""
    logger = logging.getLogger("organizer")
    logger.setLevel(cfg.level.upper())
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = RichHandler(
        console=_console,
        level=cfg.level.upper(),
        show_path=False,
        rich_tracebacks=True,
    )
    logger.addHandler(console_handler)

    if cfg.file:
        log_path = Path(cfg.file).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=FILE_SIZE_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)


def get_logger() -> logging.Logger:
    return logging.getLogger("organizer")


def log_action(action: str, source: str, destination: str, rule: str) -> None:
    """Emit the structured, parseable record required by the spec.

    Format matches the rotating-file handler's formatter so records are
    consistent whether they land in the console or the log file.
    """
    get_logger().log(
        logging.INFO,
        "action=%s source=%r destination=%r rule=%r",
        action,
        source,
        destination,
        rule,
    )


def log_error(source: str, rule: str, error: Exception) -> None:
    get_logger().error(
        "action=error source=%r rule=%r error=%r", source, rule, str(error)
    )