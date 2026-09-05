# File Organizer — Spec Sheet

## Overview
Local Python application that moves/organizes files into destination directories based on user-defined, customizable rules (e.g., extracting music album zips into `/media/Music/<Artist>/<Album>/`, creating artist directories as needed).

## Runtime Modes
1. **CLI mode** — one-shot invocation: scan a source directory, apply rules, move/extract files, exit.
2. **Watch mode** — long-running process using filesystem events (`inotify` via `watchdog` or `pyinotify`) to trigger rule evaluation on file creation/modification in watched source directories. Runnable as a systemd user service.

## Configuration Format: YAML

`config.yaml` structure:

```yaml
watch_dirs:
  - path: ~/Downloads
    recursive: false

rules:
  - name: "music-albums"
    match:
      extension: [".zip"]
      # optional: filename regex, min/max size, mime type
    source:
      type: "archive"          # archive | file | directory
      inspect: "audio_tags"    # reads metadata from files inside the zip
    destination:
      template: "/media/Music/{artist}/{album}"
      create_dirs: true
    on_conflict: "rename"      # skip | rename | overwrite | prompt
    action: "extract"          # extract | move | copy

  - name: "documents"
    match:
      extension: [".pdf", ".docx"]
    destination:
      template: "/media/Documents/{year}/{month}"
    on_conflict: "skip"
    action: "move"

logging:
  level: "info"
  file: "~/.local/share/file-organizer/log.txt"
```

### Rule Fields
| Field | Description |
|---|---|
| `match` | Conditions: extension list, regex on filename, size bounds, mime type |
| `source.inspect` | Metadata extraction method: `audio_tags`, `none`, (extensible) |
| `destination.template` | Path template with placeholders (`{artist}`, `{album}`, `{year}`, etc.) resolved from metadata or file timestamps |
| `on_conflict` | Per-rule: `skip`, `rename`, `overwrite`, `prompt` |
| `action` | `move`, `copy`, or `extract` (for archives) |

Rules evaluated top-to-bottom; first match wins (configurable to "all matches" later if needed).

## Core Components
- `organizer/config.py` — YAML loading + validation (schema via `pydantic` or `voluptuous`)
- `organizer/matcher.py` — rule matching logic
- `organizer/metadata.py` — extracts tags (uses `mutagen` for audio, `python-magic` for mime detection)
- `organizer/executor.py` — performs move/copy/extract, handles conflicts, creates directories
- `organizer/watcher.py` — watchdog-based event loop for watch mode
- `organizer/cli.py` — argparse/click entrypoint (`organize run`, `organize watch`, `organize dry-run`)
- `organizer/logger.py` — structured logging setup

## Key Dependencies
- `PyYAML` — config parsing
- `mutagen` — audio metadata (artist/album/title tags)
- `python-magic` — mime type detection
- `watchdog` — filesystem event monitoring (watch mode)
- `click` — CLI interface
- `pydantic` — config schema validation

## CLI Interface
```
organize run --config config.yaml [--source PATH] [--dry-run]
organize watch --config config.yaml [--daemon]
organize validate --config config.yaml
```

`--dry-run` logs intended actions without moving files — required for safe testing of new rules.

## Conflict Handling (per-rule, from config)
- `skip` — leave source file untouched, log warning
- `rename` — append ` (n)` or timestamp suffix to new filename
- `overwrite` — replace existing destination file
- `prompt` — only valid in CLI mode; interactive y/n

## Environment Setup

### Arch Linux
```bash
sudo pacman -S python python-pip
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
`python-magic` requires `file` (libmagic), already present on most Arch installs; otherwise `sudo pacman -S file`.

### Debian / Ubuntu
```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip libmagic1
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## systemd Watch Mode (optional)
`~/.config/systemd/user/file-organizer.service` template included in repo; enabled via:
```bash
systemctl --user enable --now file-organizer.service
```

## Logging
Rotating log file + console output. Every action (move/copy/extract/skip/error) recorded with timestamp, source, destination, rule name.

## Testing
- Unit tests for matcher, metadata extraction, template resolution, conflict handling (pytest, tmp_path fixtures)
- Dry-run mode doubles as manual integration test

## Project Structure
```
file-organizer/
├── organizer/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── matcher.py
│   ├── metadata.py
│   ├── executor.py
│   ├── watcher.py
│   └── logger.py
├── config.example.yaml
├── requirements.txt
├── tests/
├── systemd/
│   └── file-organizer.service
├── README.md
└── SPEC.md
```

## Open Questions / Future Considerations
- Support for multiple matches per file (chained actions)?
- Undo/history log for reverting moves?
- Web UI or TUI for rule editing later?