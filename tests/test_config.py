from pathlib import Path

import pytest

from organizer.config import Config, load_config

VALID_YAML = """
watch_dirs:
  - path: "~/Downloads"
    recursive: false

rules:
  - name: "music-albums"
    match:
      extension: [".zip"]
    source:
      type: "archive"
      inspect: "audio_tags"
    destination:
      template: "/media/Music/{artist}/{album}"
    on_conflict: "rename"
    action: "extract"

  - name: "documents"
    match:
      extension: [".pdf", ".docx"]
    destination:
      template: "/media/Documents/{year}/{month}"
    on_conflict: "skip"
    action: "move"
"""


def write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return path


def test_load_valid(tmp_path: Path):
    cfg = load_config(write_config(tmp_path, VALID_YAML))
    assert len(cfg.rules) == 2
    assert cfg.rules[0].action == "extract"
    assert cfg.rules[0].source.inspect == "audio_tags"
    assert cfg.rules[1].destination.template == "/media/Documents/{year}/{month}"
    assert cfg.watch_dirs[0].recursive is False


def test_defaults_applied(tmp_path: Path):
    cfg = load_config(
        write_config(tmp_path, 'rules:\n  - name: "r"\n    match:\n      extension: [".x"]\n    destination:\n      template: "/dest"\n')
    )
    rule = cfg.rules[0]
    assert rule.on_conflict == "skip"
    assert rule.action == "move"
    assert rule.source.type == "file"
    assert rule.source.inspect == "none"
    assert rule.destination.create_dirs is True
    assert cfg.logging.level == "info"


def test_missing_conditions_rejected(tmp_path: Path):
    with pytest.raises(ValueError):
        load_config(
            write_config(tmp_path, 'rules:\n  - name: "r"\n    match: {}\n    destination:\n      template: "/dest"\n')
        )


def test_extract_requires_archive(tmp_path: Path):
    with pytest.raises(ValueError):
        load_config(
            write_config(
                tmp_path,
                'rules:\n  - name: "r"\n    match:\n      extension: [".zip"]\n    destination:\n      template: "/d"\n    action: "extract"\n',
            )
        )


def test_invalid_enum_rejected(tmp_path: Path):
    with pytest.raises(ValueError):
        load_config(
            write_config(
                tmp_path,
                'rules:\n  - name: "r"\n    match:\n      extension: [".x"]\n    destination:\n      template: "/d"\n    action: "teleport"\n',
            )
        )


def test_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


def test_example_config_is_valid():
    example = Path(__file__).resolve().parent.parent / "configs" / "example.yaml"
    cfg = load_config(example)
    assert any(r.action == "extract" for r in cfg.rules)


def test_empty_config_allowed():
    assert Config().rules == []