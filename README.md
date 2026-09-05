# File Organizer

A local CLI/watch application that organizes files into destination
directories based on user-defined YAML rules (e.g. extracting music album
zips into `/media/Music/<Artist>/<Album>/`, creating directories as needed).

See [SPEC.md](spec.md) for the full spec sheet.

## Features

- **CLI mode** — one-shot scan, match, and act on a source directory.
- **Watch mode** — long-running process built on `watchdog`; triggers rules
  on file creation/modification with a debounce. Run under systemd.
- **YAML config** — rules with extension/regex/size/mime matches, audio-tag
  inspection (including inside zip archives), path templates with
  `{artist}`, `{album}`, `{year}`, `{month}` placeholders, per-rule conflict
  handling (`skip`/`rename`/`overwrite`/`prompt`).
- **Template-aware zip stripping** — a leading zip folder is removed only when
  it would be re-created by the destination template (its name matches the
  resolved `{artist}`/`{album}` placeholder). Otherwise the zip's own album
  folder is preserved, e.g. a `music/{artist}` destination keeps each zip's
  inner folder while avoiding `Artist/Album/...` duplication.
- **`--dry-run`** — logs intended actions without touching the filesystem.
- Rich console output (summary tables, live watch logging) plus a rotating
  log file.

## Install

### Arch

```bash
sudo pacman -S python python-pip
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`python-magic` requires `libmagic` (`file`); install with
`sudo pacman -S file` if missing.

### Debian / Ubuntu

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip libmagic1
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

Config files live in `configs/`. Copy `configs/example.yaml` to your own
`configs/<name>.yaml` — personal configs there are gitignored, so they stay
out of the public repo. All commands default to `config.yaml` if you don't
pass `--config`:

```bash
# validate a config and show the rules it selected
organize validate --config configs/jellyfin.yaml

# one-shot run over the configured watch dirs
organize run --config configs/jellyfin.yaml

# scan a specific directory recursively
organize run --config configs/jellyfin.yaml --source ~/Downloads --recursive

# safe test run (nothing is moved/copied/extracted)
organize run --config configs/jellyfin.yaml --dry-run

# long-running watch mode
organize watch --config configs/jellyfin.yaml
```

## systemd watch mode

Copy the unit and enable it as a user service:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/file-organizer.service ~/.config/systemd/user/
# adjust ExecStart to your venv path, then:
systemctl --user daemon-reload
systemctl --user enable --now file-organizer.service
```

## Rules, top-to-bottom, first match wins

| Field | Description |
|---|---|
| `match.extension` | File suffix list, case-insensitive |
| `match.filename_regex` | Regex searched against the filename |
| `match.min_size` / `max_size` | Byte bounds |
| `match.mime_type` | Mime type or prefix, e.g. `image/` |
| `source.type` | `file`, `directory`, or `archive` |
| `source.inspect` | `audio_tags` (reads tags via mutagen, inside zips too) or `none` |
| `destination.template` | Path with `{artist} {album} {title} {year} {genre} {filename} {name} {ext} {month} {day}` placeholders; `{year}/{month}` fall back to file mtime |
| `on_conflict` | `skip`, `rename`, `overwrite`, `prompt` (prompt requires an interactive terminal) |
| `action` | `move`, `copy`, or `extract` |

## Testing

```bash
source .venv/bin/activate
pip install pytest
pytest
```