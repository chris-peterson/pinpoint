# Tags

Every tag is `type:value`. Tag values are normalized to **Title Case** with spaces as separators, so `pink floyd`, `Pink_Floyd`, and `PINK FLOYD` all become `Pink Floyd`. Minor words (a, an, the, and, or, of, in, on) stay lowercase unless they're first or last.

```text
artist:Pink Floyd
album:Dark Side of the Moon
name:The Dark Knight
event:Hawaii Vacation:Snorkeling
author:Ursula K Le Guin
```

## `root:` decides everything else

The `root:` tag says what kind of thing the file is. It picks the path formula and it picks which other tag types are meaningful. A `season:` tag on a song is not wrong so much as inert.

Seven roots:

| Root | What it holds |
|---|---|
| `memory` | Photos and home video, colocated |
| `music` | Songs |
| `movie` | Feature films |
| `tv` | TV series episodes |
| `podcast` | Podcast episodes |
| `book` | Audiobooks and ebooks |
| `comedy` | Standup specials and sketches |

The root is set by which `_input/` subdirectory the file arrived in, or inferred from content for a bare drop.

## Tag types per root

The tags Pinpoint prompts for, in the order the review form shows them. Bold ones are expected — a file missing one is flagged as incomplete.

| Root | Tag types |
|---|---|
| `memory` | **event**, person, **name** |
| `music` | **artist**, feat, **album**, year, track, **name** |
| `movie` | series, **name**, year |
| `tv` | **show**, **season**, **episode**, **name** |
| `podcast` | **show**, **episode**, **name** |
| `book` | **author**, series, **name** |
| `comedy` | **artist**, **name**, year |

`person` and `feat` accept multiple values; every other type holds one.

## Nesting

Three tag types nest, using `:` to separate levels. Each level becomes a directory in the output path.

- `event:Hawaii Vacation:Snorkeling` → `Hawaii Vacation/Snorkeling/`
- `series:` on a movie or book, for sub-franchises

## Derived attributes

Two things behave like tags but aren't ones you set:

- **`month`** — `YYYY-MM`, derived from the file's capture date. Sourced in order: embedded media metadata (EXIF, QuickTime), a date in the filename, then filesystem dates, falling back to the discovery date.
- **`class`** — image, audio, video, document. Read from the extension.

## Year is separate from the name

Type the name without the year; `year:` is its own tag. Pinpoint puts the year into the path where the root's formula calls for it — `[1973] Dark Side of the Moon` for an album, `Raiders of the Lost Ark [1981]` for a film, `[2018] Kid Gorgeous` for a special.

## Featured artists

An artist string with a `feat.`, `ft.`, or `featuring` marker splits: the part before it becomes the primary `artist:`, and the collaborators after it become `feat:` tags. The primary artist is never split on `&` or `,`, so `Earth, Wind & Fire` stays one band.

`feat:` is not path-relevant — `artist:Jay-Z` with `feat:Alicia Keys` lands at `music/Jay-Z/Empire State of Mind.mp3`.

## Various Artists

When embedded metadata gives `albumartist = Various Artists`, Pinpoint sets `artist:Various Artists` and keeps the original filename as-is, since a compilation's per-track artist is what you'd want in the filename and the album artist is what you'd want in the folder.

## Where tags are read from

Pinpoint reads tags out of each file's native metadata — EXIF for images, ID3 for MP3, Vorbis comments for FLAC — along with the filename and the directory it arrived in. Tags you set live in the database.

Writing tags back into the files, so the database becomes a rebuildable cache rather than the record of truth, is specified but not yet built. See [SPEC §12](/spec?id=_12-tag-persistence).
