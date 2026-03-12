from pathlib import Path

import yaml


class ConfigHolder:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config: dict = {}
        self._mtime: float = 0

    def load(self):
        self._mtime = self.config_path.stat().st_mtime
        raw = yaml.safe_load(self.config_path.read_text())
        base_dir = self.config_path.parent

        inputs = []
        for inp in raw.get("inputs", []):
            p = Path(inp["path"]).expanduser()
            resolved = (base_dir / p).resolve() if not p.is_absolute() else p.resolve()
            inputs.append({"path": str(resolved), "root": inp["root"]})

        output_raw = Path(raw.get("output", "~/.pinpoint/files")).expanduser()
        output = str((base_dir / output_raw).resolve() if not output_raw.is_absolute() else output_raw.resolve())

        data_dir_raw = Path(raw.get("data_dir", "~/.pinpoint")).expanduser()
        data_dir = str((base_dir / data_dir_raw).resolve() if not data_dir_raw.is_absolute() else data_dir_raw.resolve())

        import_mode = raw.get("import_mode", "copy")
        if import_mode not in ("copy", "move"):
            import_mode = "copy"

        self.config = {
            "inputs": inputs,
            "output": output,
            "data_dir": data_dir,
            "import_mode": import_mode,
        }

    def check_reload(self):
        try:
            mtime = self.config_path.stat().st_mtime
            if mtime > self._mtime:
                self.load()
        except OSError:
            pass
