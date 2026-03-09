# ◉ Pinpoint

Stop thinking about filenames and folder structures. Just tag your files and let Pinpoint figure out the rest.

Pinpoint is a local-first, tag-based file organization system. Point it at your messy folders, review and tag files with AI assistance, and they land in a clean, predictable directory tree — derived entirely from their tags.

## How it works

**You have messy folders.** Camera rolls, downloads, ripped music, movie files scattered everywhere.

**Pinpoint watches them.** It discovers files, detects duplicates, and queues everything for review.

**You tag.** One file at a time (or in batches for audio/video). The UI shows you a preview, suggests tags via AI, and shows exactly where the file will land.

**Pinpoint organizes.** The file moves to a deterministic path based on your tags. Change a tag later, and the file physically relocates.

## What the output looks like

```
~/.pinpoint/files/
├── memories/
│   └── 2025-01/
│       └── hawaii-vacation/
│           └── snorkeling/
│               ├── sunset-over-ocean.jpg
│               ├── max-diving-with-fishes.mov
│               └── drone-flyover.mp4
├── music/
│   └── pink-floyd/
│       ├── [1973] dark-side-of-the-moon/
│       │   ├── time.flac
│       │   └── money.flac
│       └── [1979] the-wall/
│           └── another-brick-in-the-wall.flac
├── movies/
│   ├── indiana-jones/
│   │   ├── raiders-of-the-lost-ark [1981].mkv
│   │   └── the-last-crusade [1989].mkv
│   └── there-will-be-blood [2007].mkv
├── tv/
│   └── the-office/
│       └── 3/
│           └── the-merger.mkv
├── books/
│   └── tolkien/
│       └── the-hobbit/
│           ├── chapter-1.m4a
│           └── chapter-2.m4a
├── podcasts/
│   └── hardcore-history/
│       └── ep-66-supernova-in-the-east.mp3
└── comedy/
    └── john-mulaney/
        └── kid-gorgeous [2018].mp4
```

You didn't create any of these folders or rename any files. You just tagged them.

## Tags are the source of truth

Every filename and folder is derived from tags. The tag types that matter depend on what kind of file it is:

| What | Tags you set | Where it lands |
|---|---|---|
| Vacation photo | `event:hawaii-vacation:snorkeling` `name:sunset-over-ocean` | `memories/2025-01/hawaii-vacation/snorkeling/sunset-over-ocean.jpg` |
| Song | `artist:pink-floyd` `album:[1973] dark-side-of-the-moon` `name:time` | `music/pink-floyd/[1973] dark-side-of-the-moon/time.flac` |
| Movie | `series:indiana-jones` `name:raiders-of-the-lost-ark [1981]` | `movies/indiana-jones/raiders-of-the-lost-ark [1981].mkv` |
| TV episode | `show:the-office` `season:3` `name:the-merger` | `tv/the-office/3/the-merger.mkv` |
| Audiobook chapter | `author:tolkien` `title:the-hobbit` `name:chapter-1` | `books/tolkien/the-hobbit/chapter-1.m4a` |

Change a tag, and the file moves to match.

## AI assistance

Pinpoint runs analysis locally to suggest tags before you review each file:

- **Images**: face detection and recognition, scene description via local vision model
- **Audio**: embedded metadata extraction, MusicBrainz/AcoustID lookup for unknown tracks
- **Movies/TV**: filename parsing, TMDb lookup for canonical titles and metadata

Suggestions appear as one-click chips in the review queue. Accept, edit, or dismiss.

All AI runs locally. No cloud APIs except free/open metadata databases (MusicBrainz, AcoustID, TMDb).

## Configuration

```yaml
inputs:
  - path: ~/Pictures
    root: memories
  - path: ~/Music
    root: music
  - path: ~/Movies
    root: movies

output: ~/.pinpoint/files
```

That's it. Everything else has sensible defaults.

## Status

Under active development. See [SPEC.md](SPEC.md) for the full requirements and [AGENTS.md](AGENTS.md) for development guidance.
