# Configuration

Deliberately minimal. One required key: where the library lives.

```yaml
# config.yaml
library: /Volumes/data/files
```

Everything else has a default in code.

## Keys

| Key | Default | What it is |
|---|---|---|
| `library` | *required* | The directory Pinpoint manages — the `_input/` drop tree and every output tree |
| `data_dir` | `~/.pinpoint` | Where the database and system state live |

There is no default library. An external drive is the usual choice, since the library holds every managed file — and defaulting to your home directory would make an accident too easy.

The data directory is separate from the library on purpose: only the database and derived state live there, so backing up the library is a matter of copying one tree.

## Path resolution

Relative paths resolve against the **config file's own directory**, not your working directory. So the repo's checked-in `config.yaml`:

```yaml
library: sample_output
```

always means `sample_output/` beside `config.yaml`, whichever directory you run from. `~` expands to your home directory.

## Command line

```bash
uv run python -m pinpoint --config config.yaml --port 8420
```

| Flag | Default | |
|---|---|---|
| `--config` | `config.yaml` | Config file to load |
| `--port` | `8420` | Port for the web UI and JSON API |

## Hot reload

Pinpoint checks the config file's mtime every 10 seconds and reloads it in place when it changes. Editing `config.yaml` takes effect without a restart.

## What Pinpoint creates on startup

Given a library path, Pinpoint creates the pieces it needs if they aren't there — the library directory itself, `_input/<root>/` for each of the seven roots, and `_input/_stuck/`. An empty library is valid; it produces an empty output tree.

## Everything else

Path formulas, tag types, expected-tag sets, and confidence weights are constants in the source rather than configuration — `models.py` for the taxonomy, `paths.py` for the formulas. They're fixed because the path contract depends on them being fixed: a configurable formula is a formula that can change under files already on disk.
