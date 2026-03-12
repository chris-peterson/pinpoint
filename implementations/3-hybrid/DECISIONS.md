# DECISIONS.md — Implementation 3: Hybrid (Python API + JS SPA)

## Tech Stack

| Choice | Rationale |
|--------|-----------|
| **Python FastAPI** | Async REST API, clean dependency injection, fast JSON serialization |
| **aiosqlite** | Async SQLite for non-blocking DB operations in the event loop |
| **Vanilla JS SPA** | No framework — hash-based client routing, fetch for all API calls, DOM string templates |
| **Mutagen** | Audio metadata extraction (ID3, Vorbis, MP4 atoms) |
| **watchfiles** | Rust-backed file watching for discovery and output monitoring |

## Architecture

- **Strict API/UI separation** — the Python backend is a pure JSON API. No server-side HTML rendering. The frontend is a static SPA served from `static/`.
- **Hash routing** — the SPA uses `#/path` routing so the server only needs a single catch-all route to serve `index.html`. No history API, no server-side route matching needed.
- **Async everything** — FastAPI's async handlers + aiosqlite means the discovery loop, file I/O, and HTTP serving all share one event loop without blocking.
- **No build step** — vanilla JS, vanilla CSS, no bundler, no transpiler.

## Aesthetic Direction

The UI uses a **Swiss Neobrutalist** aesthetic — light cream paper background (#f5f0e8), Instrument Serif for display headings paired with Satoshi for body text, vermillion red (#d62828) as the sole accent color. Flat cards with hairline borders, uppercase micro-labels, and deliberate negative space. The feeling is a printed catalog, not a software dashboard.

## Key Differences from Implementations 1 and 2

- **No server-rendered HTML** — Python serves JSON, JS renders everything. This means the UI can update without full page reloads (accept/skip/reject stay on the queue view).
- **Single index.html** — the entire frontend is one HTML file + one CSS file + one JS file. No templates directory needed.
- **Async DB** — unlike impl 2's synchronous better-sqlite3, this uses aiosqlite for non-blocking access. The tradeoff is slightly more complex code but better behavior under concurrent requests.
- **Config paths resolve relative to config file** — same as impl 2, learned from the same SPEC requirement.
