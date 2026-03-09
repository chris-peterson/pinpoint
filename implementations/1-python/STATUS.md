# STATUS.md — Requirements Traceability Matrix (Implementation 1: Python)

Maps SPEC.md requirement IDs to implementation status and code locations.

## Legend

- **Done** — implemented and tested
- **Partial** — some aspects implemented, gaps noted
- **N/S** — not started

---

## §1 Core Model

| ID | Requirement | Status | Code |
|---|---|---|---|
| [CM-1] | Input folders with default root | Done | `config.py`, `discovery.py` |
| [CM-2] | Single output directory, path from tags | Done | `config.py`, `paths.py` |
| [CM-3] | Pending: known, original untouched | Done | `discovery.py` |
| [CM-4] | Managed: accepted, moved to output | Done | `api/queue.py:accept_file` |

## §2 Tag Taxonomy

| ID | Requirement | Status | Code |
|---|---|---|---|
| [TX-1] | `type:value` tag structure | Done | `schema.sql`, `models.py` |
| [TX-2] | Root override per-file in queue | N/S | |
| [TX-3] | `class:` auto-assigned from extension | Done | `discovery.py:classify_file` |
| [TX-4] | `name:` replaces filename | Done | `paths.py:_get_name` |
| [TX-5] | `favorite` column for fast sorting | Partial | Schema exists, no UI toggle |
| [TX-6] | Tag dictionary / autocomplete | Partial | Endpoint exists, no tree view |

## §3 Output Path Structure

| ID | Requirement | Status | Code |
|---|---|---|---|
| [OP-1] | Deterministic path from tags | Done | `paths.py:derive_path` — 38 tests |
| [OP-2] | Memories date from metadata > filesystem | Partial | EXIF for images, not QuickTime |
| [OP-3] | Music track number zero-padded in filename | Done | `paths.py:_derive_music`, `defaults.py:extract_audio_metadata` |
| [OP-4] | VA compilations preserve original filename | Done | `defaults.py:_defaults_music`, `paths.py:_derive_music` |
| [OP-5] | Title Case tag values | Done | `defaults.py:slugify`, `defaults.py:title_case` — 12 tests |
| [OP-6] | Year auto-prepended to album | Done | `paths.py:_derive_music` |
| [OP-7] | `name:` replaces filename, absent keeps original | Done | `paths.py:_get_name` |
| [OP-8] | `_unknown` for missing path segments | Done | `paths.py:_first_or` |
| [OP-9] | Collision suffixes (`-1`, `-2`) | Done | `api/queue.py:_resolve_collision` |
| [OP-10] | Stack dissolve removes suffix | N/S | |
| [OP-11] | Tag change triggers relocation | N/S | |

## §4 Migration Queue

| ID | Requirement | Status | Code |
|---|---|---|---|
| [MQ-1] | One file at a time, newest first | Done | `web/routes.py:queue_page` |
| [MQ-2] | Full-size preview | Done | `templates/queue.html`, `api/files.py` |
| [MQ-3] | File metadata display | Done | `templates/queue.html .file-info` |
| [MQ-4] | Live path preview via HTMX | Done | `api/tags.py:preview_path` |
| [MQ-5] | Queue count badge | Partial | Count on page, no sidebar |
| [MQ-6] | Batch table/list view | N/S | |
| [MQ-7] | Accept all (stable metadata) | Done | `api/queue.py:accept_folder`, `templates/queue.html` |
| [MQ-8] | Editable rows before batch accept | N/S | |
| [MQ-9] | Click row for single-file detail | N/S | |

## §5 Dedup & Stacking

| ID | Requirement | Status | Code |
|---|---|---|---|
| [DS-1] | Content hash dedup at discovery | Done | `discovery.py:hash_file` |
| [DS-2] | Perceptual hash auto-stack | N/S | |

## §6 AI Analysis

| ID | Requirement | Status | Code |
|---|---|---|---|
| [AI-1] | Read embedded audio tags | Done | `defaults.py:extract_audio_metadata` |
| [AI-2] | Extract title, artist, album, year, track | Done | `defaults.py:extract_audio_metadata` |
| [AI-3] | Skip album art images during discovery | Done | `discovery.py:_walk_files` |

## §7 Library & Browse

| ID | Requirement | Status | Code |
|---|---|---|---|
| [LB-1] | Tree view of managed files | Done | `web/routes.py:library_page`, `templates/library.html` |
| [LB-2] | Contextual icons (play, image, film) | Done | `templates/library.html` |
| [LB-3] | Filters (date, root, class, tags) | Partial | Root + class filters on queue |
| [LB-4] | Full-text search | N/S | FTS5 in schema, not wired |
| [LB-5] | On This Day | N/S | |

## §8 Favorites

| ID | Requirement | Status | Code |
|---|---|---|---|
| [FV-1] | Boolean column for fast sorting | Done | `schema.sql` |
| [FV-2] | Star toggle in UI | N/S | |

## §9 File Detail

| ID | Requirement | Status | Code |
|---|---|---|---|
| [FD-1] | Full-size preview overlay | N/S | |
| [FD-2] | Editable tags sidebar | N/S | |

## §10 Data Model

| ID | Requirement | Status | Code |
|---|---|---|---|
| [DM-1] | Append-only action log | Done | `actions.py:log_action`, all 17 verbs in `models.py` |
| [DM-2] | files, tags, file_tags tables | Done | `schema.sql`, `database.py` |
| [DM-3] | suggestions, stacks, known_faces | Done | Schema only, no logic |

## §11 Output Monitoring

| ID | Requirement | Status | Code |
|---|---|---|---|
| [OM-1] | Detect rename via watcher | N/S | |
| [OM-2] | Update managed_path on rename | N/S | |
| [OM-3] | Log rename action | N/S | |
| [OM-4] | Tags remain source of truth (no reverse-derive) | N/S | |
| [OM-5] | Detect external delete | N/S | |
| [OM-6] | Mark file as missing (not deleted) | N/S | |
| [OM-7] | Log missing action | N/S | |

## §12 Extended Attributes (macOS)

| ID | Requirement | Status | Code |
|---|---|---|---|
| [XA-1] | Write tags to xattr | N/S | |
| [XA-2] | Import xattr/Finder tags | N/S | |

## §13 Configuration

| ID | Requirement | Status | Code |
|---|---|---|---|
| [CF-1] | YAML config with inputs + output | Done | `config.py:load_config` |
| [CF-2] | Default data dir `~/.pinpoint/` | Done | `config.py` |
| [CF-3] | `--config` CLI flag | Done | `__main__.py` |
| [CF-4] | Hot-reload on file change | Partial | `ConfigHolder` exists, watcher not connected |

---

## Summary

| Section | Done | Partial | N/S |
|---|---|---|---|
| §1 Core Model | 4 | 0 | 0 |
| §2 Tag Taxonomy | 3 | 2 | 1 |
| §3 Output Path | 8 | 1 | 2 |
| §4 Queue | 5 | 1 | 3 |
| §5 Dedup | 1 | 0 | 1 |
| §6 AI Analysis | 3 | 0 | 0 |
| §7 Library | 2 | 1 | 2 |
| §8 Favorites | 1 | 0 | 1 |
| §9 File Detail | 0 | 0 | 2 |
| §10 Data Model | 3 | 0 | 0 |
| §11 Monitoring | 0 | 0 | 7 |
| §12 macOS xattr | 0 | 0 | 2 |
| §13 Configuration | 3 | 1 | 0 |
| **Total** | **33** | **6** | **21** |

```mermaid
pie title Requirement Status
    "Done" : 33
    "Partial" : 6
    "Not Started" : 21
```
