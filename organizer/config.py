"""Configuration model and YAML loader for the file organizer."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field, model_validator


class MatchConfig(BaseModel):
    """Conditions a file must satisfy to trigger a rule."""

    extension: Optional[list[str]] = None
    filename_regex: Optional[str] = None
    min_size: Optional[int] = None
    max_size: Optional[int] = None
    mime_type: Optional[list[str]] = None

    @model_validator(mode="after")
    def _require_some_condition(self) -> "MatchConfig":
        if not any(
            [
                self.extension,
                self.filename_regex,
                self.min_size is not None,
                self.max_size is not None,
                self.mime_type,
            ]
        ):
            raise ValueError("match must specify at least one condition")
        return self


class SourceConfig(BaseModel):
    type: Literal["archive", "file", "directory"] = "file"
    inspect: Literal["audio_tags", "none"] = "none"


class DestinationConfig(BaseModel):
    template: str
    create_dirs: bool = True


class Rule(BaseModel):
    name: str
    match: MatchConfig
    source: SourceConfig = Field(default_factory=SourceConfig)
    destination: DestinationConfig
    on_conflict: Literal["skip", "rename", "overwrite", "prompt"] = "skip"
    action: Literal["move", "copy", "extract"] = "move"

    @model_validator(mode="after")
    def _check_action_source(self) -> "Rule":
        if self.action == "extract" and self.source.type != "archive":
            raise ValueError(
                f"rule '{self.name}': action 'extract' requires source.type 'archive'"
            )
        return self


class WatchDir(BaseModel):
    path: str
    recursive: bool = False


class LoggingConfig(BaseModel):
    level: Literal[
        "debug", "info", "warning", "error", "critical"
    ] = "info"
    file: Optional[str] = None


class Config(BaseModel):
    watch_dirs: list[WatchDir] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config(path: str | Path) -> Config:
    """Load and validate a config.yaml file."""
    config_path = Path(path).expanduser()
    if not config_path.exists():
        raise FileNotFoundError(f"config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    try:
        return Config.model_validate(data)
    except Exception as exc:  # pydantic.ValidationError / TypeError
        raise ValueError(f"invalid config in {config_path}: {exc}") from exc