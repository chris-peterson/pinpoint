# Implementation History

## SPEC 0.2 — graduated to the repo root

### 0.2/1-hybrid — Python API + JS Frontend

**Stack:** Python + uv, vanilla JS frontend, SQLite

**Status:** Selected as the implementation and flattened to the repo root. The `implementations/<spec>/<n>-<name>/` tree was retired once this was the de-facto choice — `just run` now runs it directly from root.

---

## SPEC 0.1 (abandoned)

Three implementations built against the v0.1 spec. All abandoned when the spec was revised to v0.2 — in a SPEC-driven approach, it's easier to throw them away than retrofit to fundamentally changed requirements.

### 0.1/3-hybrid — Python API + Vanilla JS SPA

**Stack:** FastAPI (JSON API only), aiosqlite, vanilla JS SPA with hash routing, mutagen, watchfiles

**Strengths:**
- Strict API/UI separation — Python serves JSON, JS renders everything
- Single-page app with hash routing, no server-side route matching needed
- Distinctive "Swiss Neobrutalist" aesthetic — cream paper, Instrument Serif, vermillion accents
- Async everything on one event loop

**Weaknesses:**
- All-vanilla JS SPA without a framework meant a lot of manual DOM wiring
- Single `index.html` + one JS file approach doesn't scale well as features grow
- Third attempt at the same spec — diminishing returns on architectural exploration

**Why abandoned:** SPEC 0.1 → 0.2 rewrite. Requirements changed fundamentally.

---

### 0.1/2-js — Express 5 + Vanilla JS + better-sqlite3

**Stack:** Node.js ESM, Express 5, better-sqlite3, Nunjucks, music-metadata, chokidar

**Strengths:**
- Synchronous SQLite via better-sqlite3 simplified the data layer considerably
- Strong UI aesthetic — "warm darkroom" theme with Fraunces/DM Mono typography, grain textures
- Vanilla JS frontend with predictive search and chip inputs (no framework overhead)
- No build step

**Weaknesses:**
- Less feature-complete than the Python implementation
- Express 5's path-to-regexp v8 required workarounds (query params instead of path segments for browse)
- Nunjucks is Jinja2-compatible but not identical — some template logic needed adjustment

**Why abandoned:** SPEC 0.1 → 0.2 rewrite. Requirements changed fundamentally.

---

### 0.1/1-python — FastAPI + HTMX + SQLite

**Stack:** FastAPI, aiosqlite, HTMX + Jinja2, Pico CSS, mutagen, watchfiles, uv

**Strengths:**
- Most complete of the three — 46 of 81 requirements fully implemented, 10 partial
- Solid path derivation engine (`paths.py`) with 38 tests covering all 7 roots
- Full AI analysis pipeline: vision LLM (Ollama/LLaVA), TMDb lookups, audio metadata extraction
- Tag persistence to native metadata, xattrs, and macOS Finder tags
- Append-only action log with all 17 verbs
- Clean architecture: path derivation as a pure function, async discovery in a dedicated thread pool

**Weaknesses:**
- HTMX approach made interactive UI features (live search, chip inputs) awkward
- Search/browse section mostly unimplemented (0 of 9 done)
- Output monitoring not started (0 of 7)
- No perceptual hash stacking

**Why abandoned:** SPEC 0.1 → 0.2 rewrite. Requirements changed fundamentally.
