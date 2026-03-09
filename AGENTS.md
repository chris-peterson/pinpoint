# AGENTS.md — Pinpoint

## What is this project?

Pinpoint is a local-first, tag-based file organization system. Users point it at messy folders, review files in a queue, apply tags, and the system moves each file to a deterministic output path derived entirely from its tags. See `SPEC.md` for the full requirements.

## Starting from scratch

This is a greenfield project. The spec describes *what* the system should do, not *how*. You choose the language, framework, architecture, and file structure. The only constraints are in the spec:

- Must run locally (macOS primary, Linux secondary).
- AI analysis must be local (no cloud APIs except free music/movie metadata lookups).
- Optional dependencies must degrade gracefully — never crash if something isn't installed.

## Build philosophy

- **Run early, run often.** Get the smallest vertical slice working end-to-end before expanding. A good first milestone: discover files from one input folder, show them in a queue, accept one with a `name:` tag, verify it lands at the correct output path.
- **Don't build everything at once.** The spec has many roots, tag types, and analysis pipelines. Start with `root:memories` (images only, no audio, no video analysis). Add roots and analysis incrementally.
- **Test with real files.** Synthetic test data is too clean to catch real problems. Use actual photos, music files, and video.
- **Keep configuration minimal.** The example config in the spec is the entire config. Everything else should be sensible defaults in code.

## Suggested build order

1. **Config loading** — parse the YAML config (inputs + output path). Hot-reload on change.
2. **Database + schema** — set up the data schema described in SPEC.md §10 (files, tags, file_tags, actions, stacks, suggestions, known_faces, full-text index).
3. **Discovery** — scan input folders, hash files, detect duplicates, write to DB as pending. Watch for new files.
4. **Output path derivation** — implement the path formulas from SPEC.md §3. Start with `root:memories` only. Given a file and its tags, compute the output path deterministically.
5. **Queue API** — serve the pending queue (newest first). Accept (move file to output path), reject (remove from DB), skip.
6. **Basic web UI** — queue view showing one file at a time with an image preview, tag inputs for `event:` and `name:`, live output path preview, accept/skip/reject buttons.
7. **Action log** — log every state-changing operation to the actions table.
8. **Tag management** — tag dictionary, autocomplete, add/remove tags, completeness nudge.
9. **Library view** — grid of managed files, search, filters, favorites.
10. **Stacking** — perceptual hashing, auto-stack similar images, name-collision stacking, stack management UI.
11. **AI analysis (images)** — face detection, vision LLM integration, suggestions in queue UI.
12. **Additional roots** — add `root:music`, `root:movies`, etc. one at a time with their tag types and path formulas.
13. **Audio analysis** — metadata extraction, MusicBrainz/AcoustID lookup, batch review mode.
14. **Movie/TV analysis** — filename parsing, TMDb lookup, batch review mode.
15. **Relocation** — when path-affecting tags change on managed files, move the file and clean up empty directories.
16. **Output monitoring** — watch the output tree for external changes (renames, moves, deletes, new files). Detect drift, mark missing files, reverse-derive tags for new files. See SPEC.md §11.
17. **On This Day**, tag dictionary browser, and remaining browse/search features.

## Key design decisions to make

The spec intentionally leaves these to the implementer:

- **Language and framework** — the spec doesn't prescribe Python/FastAPI. Use whatever you think is right.
- **Database engine** — the spec describes tables and indexes but not the engine. SQLite is a natural fit (local-first, single-user) but it's your call.
- **Frontend approach** — embedded SPA, separate frontend, server-rendered templates — your choice. Should be usable in a browser.
- **File structure** — monorepo, multi-file, modular — whatever makes sense for the chosen stack. The spec doesn't dictate.
- **Face detection library** — InsightFace, dlib, OpenCV, or anything else that runs locally.
- **Vision model** — Ollama with moondream/llava, or any local vision model. Must work on CPU (GPU optional).

## Things that matter

- **The output path must be deterministic.** Given the same tags, the same path must always be produced. This is the core contract. See SPEC.md §3 for every root's formula.
- **Discovery must be non-destructive.** Files in input folders are never touched until the user explicitly accepts them.
- **The action log must capture everything.** Every discover, accept, reject, delete, tag change, relocate. This is the debugging safety net.
- **Graceful degradation.** No Ollama? Skip vision suggestions. No InsightFace? Skip face detection. No MusicBrainz? Skip audio lookup. The queue still works — you just type tags manually.
- **Hot-reload config.** Changing the YAML config should take effect without restarting the server.

## Things that don't matter (yet)

- Performance at scale (>100k files). Optimize later.
- Multi-user. Single user only.
- Mobile UI. Desktop browser is fine.
- Comprehensive test coverage. Get it working first, add tests for the tricky parts (path derivation, dedup, relocation).

## Reference

- `SPEC.md` — full requirements specification
- `README.md` — user-facing setup and usage guide
