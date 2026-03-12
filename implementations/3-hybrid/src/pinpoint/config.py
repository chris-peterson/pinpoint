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
            resolved = (base_dir / Path(inp["path"])).resolve()
            inputs.append({"path": str(resolved), "root": inp["root"]})

        output = str((base_dir / Path(raw.get("output", "~/.pinpoint/files"))).resolve())
        data_dir = str((base_dir / Path(raw.get("data_dir", "~/.pinpoint"))).resolve())

        self.config = {
            "inputs": inputs,
            "output": output,
            "data_dir": data_dir,
        }

    def check_reload(self):
        try:
            mtime = self.config_path.stat().st_mtime
            if mtime > self._mtime:
                self.load()
        except OSError:
            pass
