from pathlib import Path

import yaml

from pinpoint.models import ROOTS


class ConfigHolder:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config: dict = {}
        self._mtime: float = 0

    def load(self):
        self._mtime = self.config_path.stat().st_mtime
        raw = yaml.safe_load(self.config_path.read_text())
        base_dir = self.config_path.parent

        if "library" not in raw:
            raise ValueError("config: 'library:' is required (no default)")

        library_raw = Path(raw["library"]).expanduser()
        library = str(
            (base_dir / library_raw).resolve()
            if not library_raw.is_absolute()
            else library_raw.resolve()
        )

        data_dir_raw = Path(raw.get("data_dir", "~/.pinpoint")).expanduser()
        data_dir = str(
            (base_dir / data_dir_raw).resolve()
            if not data_dir_raw.is_absolute()
            else data_dir_raw.resolve()
        )

        input_root = str(Path(library) / "_input")
        rejections_dir = str(Path(input_root) / "_rejections")
        inputs = [
            {"path": str(Path(input_root) / root), "root": root}
            for root in ROOTS
        ]

        self.config = {
            "library": library,
            "input_root": input_root,
            "rejections_dir": rejections_dir,
            "inputs": inputs,
            "data_dir": data_dir,
        }

    def check_reload(self):
        try:
            mtime = self.config_path.stat().st_mtime
            if mtime > self._mtime:
                self.load()
        except OSError:
            pass


def ensure_library_layout(config: dict) -> None:
    """Create _input/<root>/ and _input/_rejections/ if missing."""
    Path(config["library"]).mkdir(parents=True, exist_ok=True)
    Path(config["rejections_dir"]).mkdir(parents=True, exist_ok=True)
    for inp in config["inputs"]:
        Path(inp["path"]).mkdir(parents=True, exist_ok=True)
