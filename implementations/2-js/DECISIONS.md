# DECISIONS.md — Implementation 2: JavaScript

## Tech Stack

| Choice | Rationale |
|--------|-----------|
| **Node.js + ESM** | Native ES modules, no build step, fast startup |
| **Express 5** | Minimal HTTP framework, mature ecosystem |
| **better-sqlite3** | Synchronous SQLite bindings — simple, fast, no async overhead for DB ops |
| **Nunjucks** | Jinja2-compatible templates for server-rendered HTML |
| **music-metadata** | Audio tag extraction (ID3, Vorbis, MP4 atoms) |
| **chokidar** | File watching for discovery and output monitoring |
| **Vanilla JS frontend** | No framework — predictive search via fetch + debounce, chip inputs for multi-value fields |

## Architecture

- **Synchronous DB access** — better-sqlite3 is synchronous by design. This simplifies the code considerably vs. async wrappers. The single-user, local-first nature of Pinpoint means there's no concurrent write pressure.
- **Server-rendered HTML** — Nunjucks templates render full pages. Interactive features (search, path preview, chip input) use vanilla JS with fetch calls returning either JSON or HTML fragments.
- **No bundler** — All JS is inline in templates or served as static files. No webpack, no Vite, no build step.

## Aesthetic Direction

The UI uses a **warm darkroom** aesthetic — dark warm tones (#1a1714 base), Fraunces serif for display text paired with DM Mono for body/code, grain texture overlay, and amber/copper accent colors. Designed to feel like a photographer's catalog tool, not a generic admin panel.

## Key Differences from Implementation 1 (Python)

- Synchronous discovery (no async) — simpler code, same performance for local scanning
- Express 5 with path-to-regexp v8 — wildcards use query params instead of path segments (`/browse?path=...`)
- Config paths resolve relative to the config file directory, not CWD
- All tag field logic shared through `models.js` constants
