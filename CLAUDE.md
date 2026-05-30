# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pinpoint is a local-first, tag-based file organization system. Users point it at messy folders (photos, music, movies, etc.), review files in a queue, apply tags, and the system moves each file to a deterministic output path derived entirely from its tags. All AI analysis runs locally — no cloud APIs except free metadata databases (MusicBrainz, AcoustID, TMDb).

## Project Status

The implementation lives at the repo root: a Python (uv) FastAPI JSON API serving a vanilla JS single-page frontend, backed by SQLite. It was selected from an earlier round of parallel candidates; see `HISTORY.md` for what the retired experiments contributed.

## Key Constraints

- **macOS primary, Linux secondary.** Must run locally.
- **Output paths are deterministic.** Given the same tags, the same path must always be produced. This is the core contract. See SPEC.md §3 for every root's path formula.
- **Discovery is non-destructive.** Files in input folders are never touched until the user explicitly accepts them.
- **Action log captures everything.** Every discover, accept, reject, delete, tag change, relocate — append-only audit trail.
- **Graceful degradation.** No Ollama? Skip vision. No InsightFace? Skip face detection. No MusicBrainz? Skip audio lookup. The queue still works with manual tagging.
- **Hot-reload config.** YAML config changes take effect without restart.

## Architecture (from spec)

### File Lifecycle
`Input folder → Discovered → Pending queue → (Accept) → Managed output tree`
Files can also be rejected (removed from queue, original untouched) or skipped.

### Tag System
All tags follow `type:value` format. Some support nesting via `:` (e.g., `event:hawaii-vacation:snorkeling`). The `root:` tag determines which other tags are path-relevant and the output path formula.

### Seven Roots with Distinct Path Formulas
- `memories` → `memories/YYYY-MM/event-segments/name.ext`
- `music` → `music/artist/album/name.ext`
- `books` → `books/author/title/name.ext`
- `podcasts` → `podcasts/show/name.ext`
- `tv` → `tv/show/season/name.ext`
- `movies` → `movies/series/name.ext` (series optional)
- `comedy` → `comedy/artist/name.ext`

Missing path segments use `_unknown`. See SPEC.md §3 for complete rules and edge cases.

### Data Schema (SPEC.md §10)
Tables: `files`, `tags`, `file_tags`, `suggestions`, `stacks`, `known_faces`, `actions` (append-only audit log), plus a full-text search index.

### AI Analysis Pipeline
Background worker processes pending files. Four pipelines: face detection/recognition (images), vision LLM (images), metadata extraction + MusicBrainz/AcoustID (audio), filename parsing + TMDb (movies/TV). Results stored as suggestions with confidence scores.

## Development Approach

SPEC-driven development. `SPEC.md` is the canonical source of truth for requirements; the code at the root implements it.

### Commands

```
just                  # run the server (port 8420)
just test             # run tests
just lint             # ruff check
just format           # ruff format
just sample           # build the sample library
just fresh            # reset db, rebuild sample library, run
```

Or directly with uv:

```
uv run python -m pinpoint --config config.yaml   # run server (port 8420)
uv run --extra dev pytest -v                      # run tests
uv run --extra dev ruff check src/                # lint
uv run --extra dev ruff format src/               # format
```

Key modules (under `src/pinpoint/`): `paths.py` (core path derivation), `discovery.py` (file scanning/hashing), `config.py` (hot-reload YAML config), `database.py` (SQLite + schema), `api/routes.py` (JSON API). The vanilla JS frontend lives in `static/`.

## Reference Files

- `SPEC.md` — full requirements specification (path formulas, tag taxonomy, data schema, UI behavior)
- `AGENTS.md` — build philosophy, suggested build order, key design decisions
- `README.md` — user-facing overview
