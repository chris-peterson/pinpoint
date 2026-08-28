# ◉ Pinpoint

📖 **[Read the docs →](https://chris-peterson.github.io/pinpoint/)**

Tag your files and let the directory tree follow. Pinpoint is a local-first file organizer: drop files into a library's `_input/` tree, and each one moves to a path derived entirely from its tags.

The docs site covers what Pinpoint does and how to use it. This file is for working on it.

## Layout

```text
src/pinpoint/        Python package
  paths.py           path derivation from tags — the core contract
  discovery.py       scanning, hashing, dedup, watcher, auto-import
  config.py          YAML config + library layout
  database.py        SQLite schema
  defaults.py        tag defaults from metadata and filenames
  models.py          roots, tag fields, confidence weights
  api/routes.py      JSON API
static/              vanilla JS frontend
tests/               pytest
scripts/             sample library generator
docs/                docsify site (published to GitHub Pages)
SPEC.md              requirements — the source of truth
AGENTS.md            build philosophy and conventions
HISTORY.md           what the retired parallel candidates contributed
```

## Setup

Python 3.11+ and [uv](https://docs.astral.sh/uv/). [just](https://github.com/casey/just) for the shorthand below.

```bash
just fresh     # reset db, build the sample library, run on :8420
```

## Commands

| | |
|---|---|
| `just` | Run the server on port 8420 |
| `just fresh` | Reset the database, rebuild the sample library, run |
| `just reset` | Delete the database |
| `just sample` | Rebuild `sample_output/` |
| `just test` | `pytest -v` |
| `just lint` | `ruff check src/` |
| `just format` | `ruff format src/` |
| `just preview-docs` | Serve the docs site locally |

Or directly:

```bash
uv run python -m pinpoint --config config.yaml
uv run --extra dev pytest -v
uv run --extra dev ruff check src/
```

## Spec-driven development

`SPEC.md` is the source of truth. Requirements use EARS syntax with an id (`OP-1`, `CF-LIB`), a `Status:` annotation, and an `Impl:` pointer to the code that satisfies them. Changing behavior means changing the spec.

Two constraints the code is built around:

- **Path derivation is deterministic.** Same tags, same path, always. `paths.py` takes only a root, a tag dict, and the original filename — no clock, no filesystem reads, no config. Keep it that way; it's what makes the output tree reproducible and `test_paths.py` able to assert exact paths.
- **Optional dependencies degrade.** Missing tool means skip that analysis, never crash.

## Docs

`docs/` is a docsify site on the [chris-peterson hub](https://chris-peterson.github.io) — it loads the shared loader and theme, so there's no CSS here. `just docs` copies `SPEC.md` to `docs/spec.md` (gitignored; CI does the same on deploy). `just preview-docs` serves it locally, unthemed, since the hub's CSS resolves relative on loopback.
