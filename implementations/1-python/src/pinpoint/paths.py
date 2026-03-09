"""Output path derivation — the core algorithm.

Given a root, tags, original filename, and creation date, deterministically
compute the relative output path. This is a pure function with no side effects.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import PurePosixPath


def derive_path(
    root: str,
    tags: dict[str, list[str]],
    original_filename: str,
    creation_date: date | None = None,
) -> PurePosixPath:
    """Derive the output path for a file based on its root and tags.

    Returns a path relative to the output directory.
    """
    derivers = {
        "memories": _derive_memories,
        "music": _derive_music,
        "books": _derive_books,
        "podcasts": _derive_podcasts,
        "tv": _derive_tv,
        "movies": _derive_movies,
        "comedy": _derive_comedy,
    }

    deriver = derivers.get(root)
    if deriver is None:
        raise ValueError(f"Unknown root: {root}")

    return deriver(tags, original_filename, creation_date)


def _get_name(tags: dict[str, list[str]], original_filename: str) -> tuple[str, str]:
    """Extract the display name and extension from tags/original filename.

    Returns (stem, extension_with_dot).
    """
    ext = PurePosixPath(original_filename).suffix
    names = tags.get("name", [])
    if names:
        return names[0], ext
    return PurePosixPath(original_filename).stem, ext


def _derive_memories(
    tags: dict[str, list[str]],
    original_filename: str,
    creation_date: date | None,
) -> PurePosixPath:
    """memories/YYYY-MM/event-segments/name.ext"""
    stem, ext = _get_name(tags, original_filename)

    date_segment = creation_date.strftime("%Y-%m") if creation_date else "_unknown"

    parts: list[str] = ["memories", date_segment]

    events = tags.get("event", [])
    if events:
        # event:hawaii-vacation:snorkeling -> ["hawaii-vacation", "snorkeling"]
        segments = events[0].split(":")
        parts.extend(segments)

    parts.append(f"{stem}{ext}")
    return PurePosixPath(*parts)


def _derive_music(
    tags: dict[str, list[str]],
    original_filename: str,
    creation_date: date | None,
) -> PurePosixPath:
    """music/artist/album/track name.ext — [OP-3] track number zero-padded."""
    stem, ext = _get_name(tags, original_filename)

    artist = _first_or(tags, "artist", "_unknown")
    parts: list[str] = ["music", artist]

    albums = tags.get("album", [])
    if albums:
        album = albums[0]
        # [OP-6] Prepend [year] to album for chronological browsing
        years = tags.get("year", [])
        if years and not album.startswith("["):
            album = f"[{years[0]}] {album}"
        parts.append(album)

    # [OP-3] Prepend zero-padded track number if available and name
    # doesn't already start with digits (e.g. VA compilation filenames)
    tracks = tags.get("track", [])
    if tracks and not re.match(r"^\d", stem):
        try:
            track_num = int(tracks[0])
            stem = f"{track_num:02d} {stem}"
        except ValueError:
            pass

    parts.append(f"{stem}{ext}")
    return PurePosixPath(*parts)


def _derive_books(
    tags: dict[str, list[str]],
    original_filename: str,
    creation_date: date | None,
) -> PurePosixPath:
    """books/author/title/name.ext"""
    stem, ext = _get_name(tags, original_filename)

    author = _first_or(tags, "author", "_unknown")
    parts: list[str] = ["books", author]

    titles = tags.get("title", [])
    if titles:
        parts.append(titles[0])

    parts.append(f"{stem}{ext}")
    return PurePosixPath(*parts)


def _derive_podcasts(
    tags: dict[str, list[str]],
    original_filename: str,
    creation_date: date | None,
) -> PurePosixPath:
    """podcasts/show/name.ext"""
    stem, ext = _get_name(tags, original_filename)

    show = _first_or(tags, "show", "_unknown")
    return PurePosixPath("podcasts", show, f"{stem}{ext}")


def _derive_tv(
    tags: dict[str, list[str]],
    original_filename: str,
    creation_date: date | None,
) -> PurePosixPath:
    """tv/show/season/name.ext"""
    stem, ext = _get_name(tags, original_filename)

    show = _first_or(tags, "show", "_unknown")
    parts: list[str] = ["tv", show]

    seasons = tags.get("season", [])
    if seasons:
        parts.append(seasons[0])

    parts.append(f"{stem}{ext}")
    return PurePosixPath(*parts)


def _derive_movies(
    tags: dict[str, list[str]],
    original_filename: str,
    creation_date: date | None,
) -> PurePosixPath:
    """movies/series/name.ext (series is optional)"""
    stem, ext = _get_name(tags, original_filename)

    parts: list[str] = ["movies"]

    series = tags.get("series", [])
    if series:
        parts.append(series[0])

    parts.append(f"{stem}{ext}")
    return PurePosixPath(*parts)


def _derive_comedy(
    tags: dict[str, list[str]],
    original_filename: str,
    creation_date: date | None,
) -> PurePosixPath:
    """comedy/artist/name.ext"""
    stem, ext = _get_name(tags, original_filename)

    artist = _first_or(tags, "artist", "_unknown")
    return PurePosixPath("comedy", artist, f"{stem}{ext}")


def _first_or(tags: dict[str, list[str]], key: str, default: str) -> str:
    """Get the first value for a tag key, or the default."""
    values = tags.get(key, [])
    return values[0] if values else default
