"""click entrypoint: organize run | watch | validate."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .config import Config, load_config
from .executor import process_path
from .logger import get_logger, log_error, setup_logging
from .matcher import find_rule
from .watcher import run_watch

console = Console()

_IGNORED_TAIL_SUFFIXES = (".part", ".crdownload", ".partial", ".download", ".tmp")


def _iter_files(root: Path, recursive: bool) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    files = [
        p
        for p in root.glob(pattern)
        if p.is_file()
        and not p.name.startswith(".")
        and not p.name.endswith(_IGNORED_TAIL_SUFFIXES)
    ]
    return sorted(files)


def _rules_table(cfg: Config) -> Table:
    table = Table(title="Configured rules")
    table.add_column("Rule")
    table.add_column("Match")
    table.add_column("Action")
    table.add_column("Destination")
    for rule in cfg.rules:
        match_parts = []
        if rule.match.extension:
            match_parts.append(", ".join(rule.match.extension))
        if rule.match.filename_regex:
            match_parts.append(f"regex:{rule.match.filename_regex}")
        if rule.match.mime_type:
            match_parts.append(", ".join(rule.match.mime_type))
        match_str = ", ".join(match_parts) or "*"
        table.add_row(
            rule.name,
            match_str,
            f"{rule.action} ({rule.on_conflict})",
            rule.destination.template,
        )
    return table


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """File Organizer — move/copy/extract files by YAML-defined rules."""


@cli.command("validate")
@click.option("--config", "config_path", type=click.Path(), default="config.yaml", show_default=True)
def validate(config_path: str) -> None:
    """Validate a config file and print a rule summary."""
    try:
        cfg = load_config(config_path)
    except Exception as exc:
        console.print(f"[bold red]Invalid config:[/] {exc}")
        raise SystemExit(1) from exc
    setup_logging(cfg.logging)
    console.print(f"[green]Config OK:[/] {config_path}")
    if cfg.watch_dirs:
        console.print(f"Watch dirs: {', '.join(w.path for w in cfg.watch_dirs)}")
    console.print(_rules_table(cfg))


@cli.command("run")
@click.option("--config", "config_path", type=click.Path(), default="config.yaml", show_default=True)
@click.option("--source", type=click.Path(exists=True), default=None,
              help="Directory to scan (default: all watch_dirs)")
@click.option("--recursive/--no-recursive", default=None,
              help="Scan source recursively (default: per watch_dir setting)")
@click.option("--rule", "rule_names", multiple=True, help="Only apply named rules")
@click.option("--dry-run", is_flag=True, help="Log intended actions without moving files")
def run(config_path: str, source: str | None, recursive: bool | None,
        rule_names: tuple[str, ...], dry_run: bool) -> None:
    """One-shot scan: match files against rules and act."""
    try:
        cfg = load_config(config_path)
    except Exception as exc:
        console.print(f"[bold red]Invalid config:[/] {exc}")
        raise SystemExit(1) from exc
    setup_logging(cfg.logging)
    logger = get_logger()

    active_rules = [r for r in cfg.rules if r.name in rule_names] if rule_names else cfg.rules
    if rule_names:
        missing = set(rule_names) - {r.name for r in active_rules}
        if missing:
            console.print(f"[yellow]warning: unknown rule filter(s): {', '.join(sorted(missing))}")

    if dry_run:
        console.print("[bold yellow]DRY RUN — no files will be moved, copied, or extracted[/]")

    if source:
        roots = [Path(source)]
        walk = recursive if recursive is not None else True
    else:
        roots = [Path(w.path).expanduser() for w in cfg.watch_dirs]
        walk = None  # per-dir

    stats: dict[str, int] = {}
    files_processed = 0
    for root in roots:
        if not root.is_dir():
            logger.warning("skipping missing source dir: %s", root)
            continue
        recursive_dir = walk if walk is not None else next(
            (w.recursive for w in cfg.watch_dirs if Path(w.path).expanduser() == root), True
        )
        for path in _iter_files(root, recursive_dir):
            files_processed += 1
            rule = find_rule(active_rules, path)
            if rule is None:
                stats["no_rule"] = stats.get("no_rule", 0) + 1
                logger.debug("no matching rule: %s", path)
                continue
            try:
                result = process_path(path, rule, dry_run=dry_run)
                stats[result] = stats.get(result, 0) + 1
            except Exception as exc:
                log_error(str(path), rule.name, exc)
                stats["error"] = stats.get("error", 0) + 1

    table = Table(title=f"Run summary ({files_processed} files scanned)")
    table.add_column("Result")
    table.add_column("Count")
    intent_keys = ["move", "copy", "extract"] if dry_run else []
    for key in intent_keys + ["moved", "copied", "extracted", "skipped", "no_rule", "error"]:
        if stats.get(key):
            label = f"{key} (would)" if dry_run and key in intent_keys else key
            table.add_row(label, str(stats[key]))
    if not any(stats.values()):
        table.add_row("(none)", "0")
    console.print(table)


@cli.command("watch")
@click.option("--config", "config_path", type=click.Path(), default="config.yaml", show_default=True)
@click.option("--dry-run", is_flag=True, help="Log intended actions without moving files")
@click.option("--daemon", is_flag=True,
              help="Run in foreground (systemd/supervisor handles daemonization)")
def watch(config_path: str, dry_run: bool, daemon: bool) -> None:
    """Long-running event loop; trigger rules on filesystem changes."""
    try:
        cfg = load_config(config_path)
    except Exception as exc:
        console.print(f"[bold red]Invalid config:[/] {exc}")
        raise SystemExit(1) from exc
    setup_logging(cfg.logging)
    if daemon:
        console.print("[dim]--daemon runs in foreground; use the systemd unit for backgrounding[/]")
    run_watch(cfg, dry_run=dry_run)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()