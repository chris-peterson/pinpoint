# DECISIONS.md — Implementation 1: Python

Decisions made in this implementation. Documents HOW requirements were met and WHY choices were made. For WHAT the system does, see `../../SPEC.md`.

## Tech Stack

### FastAPI (web framework)
Async-first, which pairs well with file watching and background workers. WebSocket support for live path preview updates. Built-in OpenAPI docs useful during development.

### SQLite via aiosqlite (database)
Natural fit for local-first, single-user. FTS5 for full-text search. WAL mode for concurrent reads during background analysis.

### Raw SQL (data access)
Only 7 tables with a static schema defined by the spec. An ORM adds abstraction without payoff at this scale. Thin helper layer with typed dataclasses for row mapping.

### HTMX + Jinja2 (frontend)
No build step, no node_modules, no bundler. Server-rendered HTML with HTMX for dynamic updates (live path preview, tag autocomplete, queue navigation). This is a single-user local tool — an SPA framework is overkill.

### Pico CSS (styling)
Classless/minimal CSS framework. Keeps markup clean, provides good defaults for forms and layout without custom CSS overhead.

### watchfiles (file watching)
Built on Rust's `notify` crate. Works on macOS (FSEvents) and Linux (inotify). Simpler API than watchdog. Not yet wired up — currently only does initial scan at startup.

### uv (dependency management)
Fast, modern Python package manager. `uv run python -m pinpoint` as the entry point. Replaces pip+venv.

### mutagen (audio metadata)
Reads ID3 (MP3), Vorbis (FLAC/OGG), and MP4 atoms (M4A/AAC). Used to extract artist, album, year, and track title for pre-filling tag fields. Preferred over folder structure when available.

## Architecture

### Path derivation is a pure function
`derive_path()` takes tags, original filename, and creation date — returns a relative path. No side effects, no database access. This makes it trivially testable and guarantees determinism. All 7 roots implemented.

### Tag defaults: metadata > folder structure > filename
When a file enters the queue, defaults are derived in priority order:
1. **Embedded metadata** (ID3/Vorbis/MP4 tags via mutagen) — artist, album with `[year]` prefix, track title
2. **Folder structure** relative to the input path — e.g., `Artist/Album/Track.mp3`
3. **Filename** — track number stripping, slugification

Defaults pre-fill form fields in the UI. Users can edit before accepting. On accept, form values (or defaults if unchanged) are persisted as tags.

### Discovery runs in a dedicated thread pool
File scanning, hashing, and metadata extraction are CPU/IO-bound. These run in a single-thread `ThreadPoolExecutor` separate from the default executor, so they never starve HTTP request handling. Discovery starts as a background `asyncio.create_task` after the server is ready.

### Queue ordering
Files are ordered by `discovery_date DESC` — most recently discovered first. This gives predictable ordering regardless of file creation dates.

### Config hot-reload via atomic replacement
The config is a frozen dataclass. On file change, a new Config object is created and swapped in atomically. Modules hold a reference to a `ConfigHolder` that provides the current config.

### Accept flow persists tags from form data
When a user clicks Accept, the endpoint reads form field values, falls back to computed defaults for empty fields, persists all tag values to the database, then derives the output path and moves the file. This ensures the tag database is always populated on accept, even when the user doesn't modify the defaults.
