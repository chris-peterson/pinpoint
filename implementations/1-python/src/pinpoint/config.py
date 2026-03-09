"""Configuration loading and hot-reload."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class InputConfig:
    path: Path
    root: str


@dataclass(frozen=True)
class Config:
    inputs: list[InputConfig] = field(default_factory=list)
    output: Path = Path("~/.pinpoint/files")
    data_dir: Path = Path("~/.pinpoint")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "pinpoint.db"

    @property
    def thumbnails_dir(self) -> Path:
        return self.data_dir / "thumbnails"


def load_config(path: Path | None = None) -> Config:
    """Load config from YAML file. Falls back to defaults if file doesn't exist."""
    if path is None:
        env_path = os.environ.get("PINPOINT_CONFIG")
        path = Path(env_path) if env_path else Path("~/.pinpoint/config.yaml")

    path = path.expanduser()

    if not path.exists():
        return _expand(Config())

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    inputs = []
    for inp in raw.get("inputs", []):
        if isinstance(inp, dict) and "path" in inp and "root" in inp:
            inputs.append(InputConfig(
                path=Path(inp["path"]).expanduser(),
                root=inp["root"],
            ))
        elif isinstance(inp, str):
            # Bare path string without root — skip with warning
            import logging
            logging.getLogger(__name__).warning(
                "Skipping input %r: must be an object with 'path' and 'root' keys", inp
            )
        else:
            import logging
            logging.getLogger(__name__).warning("Skipping invalid input entry: %r", inp)

    output = Path(raw.get("output", "~/.pinpoint/files")).expanduser()
    data_dir = Path(raw.get("data_dir", "~/.pinpoint")).expanduser()

    return _expand(Config(inputs=inputs, output=output, data_dir=data_dir))


def _expand(config: Config) -> Config:
    """Expand user paths in a config."""
    return Config(
        inputs=[InputConfig(path=i.path.expanduser(), root=i.root) for i in config.inputs],
        output=config.output.expanduser(),
        data_dir=config.data_dir.expanduser(),
    )


class ConfigHolder:
    """Mutable container for atomic config swaps."""

    def __init__(self, config: Config):
        self._config = config

    @property
    def config(self) -> Config:
        return self._config

    def reload(self, path: Path | None = None) -> None:
        self._config = load_config(path)
