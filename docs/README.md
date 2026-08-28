# <img src="favicon.svg" alt="pinpoint" width="64" height="64" style="vertical-align: middle"> Pinpoint

Tag your files and let the directory tree follow.

Pinpoint is a local-first file organizer. You give it one directory — the **library** — and drop files into its `_input/` tree. Pinpoint reads embedded metadata, fills in what it can, and moves each file to a path derived entirely from its tags. Change a tag later and the file relocates to match.

It runs entirely on your machine.

## The idea

A path is not something you maintain. It's a function of what the file *is*.

```
artist:Pink Floyd + album:Dark Side of the Moon + year:1973 + track:01 + name:Time
    → music/Pink Floyd/[1973] Dark Side of the Moon/01 - Time.flac
```

Same tags, same path, every time. That determinism is the core contract — see [Where files land](/paths).

## What the output looks like

```text
<library>/
├── memories/
│   └── 2025-01/
│       └── Hawaii Vacation/
│           └── Snorkeling/
│               └── Sunset Over Ocean.jpg
├── music/
│   └── Pink Floyd/
│       ├── [1973] Dark Side of the Moon/
│       │   └── 01 - Time.flac
│       └── [1979] The Wall/
│           └── 03 - Another Brick in the Wall.flac
├── movies/
│   └── Indiana Jones/
│       └── Raiders of the Lost Ark [1981].mkv
├── tv/
│   └── The Office/
│       └── Season 03/
│           └── 05 - The Merger.mkv
├── books/
│   └── Tolkien/
│       └── The Hobbit.m4a
├── podcast/
│   └── Hardcore History/
│       └── 66 - Supernova in the East.mp3
└── comedy/
    └── John Mulaney/
        └── [2018] Kid Gorgeous.mp4
```

You created none of those folders and renamed nothing.

## Quickstart

```bash
git clone https://github.com/chris-peterson/pinpoint.git
cd pinpoint
just fresh
```

That builds a sample library and starts the server on <http://localhost:8420>. Pointing it at a real library is the next step — [Getting started](/getting-started) covers both.

## Where to go next

| Page | What's there |
|---|---|
| [Getting started](/getting-started) | Install, run, and import your first files |
| [The library](/library) | The `_input/` drop tree, the file lifecycle, `_stuck/` |
| [Tags](/tags) | The seven roots and the tag types each one uses |
| [Where files land](/paths) | The path formula for every root |
| [Configuration](/configuration) | `config.yaml`, the data directory, hot reload |
| [Requirements](/spec) | The full EARS specification |

## Status

Under active development, at v0.2. What works today: the `_input/` drop tree and watcher, root inference for bare drops, exact and perceptual-hash deduplication, tag defaults from embedded metadata and filenames, deterministic path derivation for all seven roots, relocation on tag edits, and the review, search, and browse UI.

Specified and not yet built: writing tags back into file metadata, the local vision and face-recognition pipelines, and MusicBrainz, AcoustID, and TMDb lookups. Every requirement in [Requirements](/spec) carries its own status annotation.
