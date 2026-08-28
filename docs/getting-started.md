# Getting started

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/) for dependency management
- macOS or Linux
- Optionally [just](https://github.com/casey/just) for the shorthand commands below

## Try it against the sample library

```bash
git clone https://github.com/chris-peterson/pinpoint.git
cd pinpoint
just fresh
```

`just fresh` clears the database, generates `sample_output/` with a spread of files across all seven roots, and starts the server. Open <http://localhost:8420> and you'll see the discovered files with the tags Pinpoint inferred and the path each one landed at.

The equivalent without `just`:

```bash
uv run python scripts/create_sample_library.py --output sample_output
uv run python -m pinpoint --config config.yaml
```

## Point it at a real library

Pick a directory that Pinpoint will own — an external drive is the usual choice, since the library holds every managed file.

```yaml
# config.yaml
library: /Volumes/data/files
```

Start the server:

```bash
uv run python -m pinpoint --config config.yaml
```

On startup Pinpoint creates the drop tree under the library:

```text
/Volumes/data/files/_input/
├── _stuck/
├── memory/
├── music/
├── movie/
├── tv/
├── podcast/
├── book/
└── comedy/
```

## Import your first files

Move files into the `_input/` subdirectory matching what they are. The subdirectory sets the file's `root:` tag, which decides every other tag that matters and the path formula that gets applied.

```bash
mv ~/Music/* /Volumes/data/files/_input/music/
mv ~/Pictures/* /Volumes/data/files/_input/memory/
```

The watcher notices each file, waits for it to go quiet (so an in-progress copy finishes first), then hashes, analyzes, tags, and moves it to its derived path. There's no approval gate — low-confidence files are still imported, just flagged for review.

Dropping a file at the root of `_input/` instead works too: Pinpoint infers the root from the file's class and content. Anything it can't place goes to `_input/_stuck/`. Both are covered in [The library](/library).

## Everyday commands

| Command | What it does |
|---|---|
| `just` | Run the server on port 8420 |
| `just fresh` | Reset the database, rebuild the sample library, run |
| `just reset` | Delete the database |
| `just sample` | Rebuild `sample_output/` only |
| `just test` | Run the test suite |
| `just lint` | `ruff check src/` |
| `just format` | `ruff format src/` |

The server takes `--port` to move off 8420 and `--config` to name a different config file.
