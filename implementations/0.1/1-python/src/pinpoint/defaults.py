"""Derive default tag values from source path, filename, and embedded metadata.

For music files: ID3/Vorbis/MP4 tags, then folder structure (Artist/Album/Track).
For movies/tv: filename parsing for title, year, season/episode.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path, PurePosixPath

logger = logging.getLogger(__name__)


def slugify(value: str) -> str:
    """Convert a string to a clean Title Case tag value.

    Uses spaces as word separators (human-readable, not URL slugs).

    Examples: "dark side of the moon" -> "Dark Side of the Moon"
              "pink floyd" -> "Pink Floyd"
              "the wall" -> "The Wall"
    """
    value = value.strip()

    # Replace common separators with spaces
    value = re.sub(r"[_\-\s]+", " ", value)
    # Remove non-alphanumeric except spaces, brackets, parens, dots, apostrophes
    value = re.sub(r"[^\w\s\[\]\(\)\.']", " ", value)
    # Collapse multiple spaces
    value = re.sub(r"\s{2,}", " ", value)
    value = value.strip()
    # Title case each word
    value = title_case(value)
    return value


# Words that stay lowercase in Title Case (unless first/last word)
_MINOR_WORDS = {"a", "an", "the", "and", "but", "or", "nor", "for", "yet", "so",
                "in", "on", "at", "to", "of", "by", "as", "is", "if", "vs"}


def title_case(value: str) -> str:
    """Title Case with minor words staying lowercase (except first/last)."""
    words = value.split()
    if not words:
        return value
    result = []
    for i, word in enumerate(words):
        # Preserve bracketed prefixes like [1973]
        if word.startswith("["):
            result.append(word)
        elif i == 0 or i == len(words) - 1:
            result.append(_capitalize_word(word))
        elif word.strip("()'\"").lower() in _MINOR_WORDS:
            result.append(word.lower())
        else:
            result.append(_capitalize_word(word))
    return " ".join(result)


def _capitalize_word(word: str) -> str:
    """Capitalize a word, handling leading punctuation like ( or '."""
    for i, ch in enumerate(word):
        if ch.isalpha():
            return word[:i] + word[i:].capitalize()
    return word


_VA_NAMES = {"various artists", "various", "va"}


def extract_audio_metadata(source_path: str) -> dict[str, str]:
    """Extract metadata from audio files using mutagen.

    Returns a dict of tag_type -> value (already slugified).
    Supports ID3 (MP3), Vorbis (FLAC/OGG), MP4 atoms (M4A/AAC).

    For Various Artists compilations, sets artist to "Various Artists" and
    omits the track name so the original filename is preserved (it typically
    encodes "## - Artist - Track" which is more useful than just the title).
    """
    try:
        import mutagen
    except ImportError:
        return {}

    try:
        audio = mutagen.File(source_path, easy=True)
        if audio is None:
            return {}
    except Exception:
        logger.debug("Failed to read audio metadata from %s", source_path)
        return {}

    defaults: dict[str, str] = {}

    # Detect compilations via albumartist
    albumartist_raw = audio.get("albumartist")
    is_compilation = (
        albumartist_raw
        and albumartist_raw[0].strip().lower() in _VA_NAMES
    )

    # Artist — for compilations use "Various Artists", otherwise prefer track artist
    if is_compilation:
        defaults["artist"] = "Various Artists"
    else:
        artist = audio.get("artist") or albumartist_raw
        if artist:
            defaults["artist"] = slugify(artist[0])

    # Album (without year — year is a separate field)
    album = audio.get("album")
    if album:
        defaults["album"] = slugify(album[0])

    # Year from date metadata
    date = audio.get("date") or audio.get("originaldate")
    if date:
        defaults["year"] = date[0][:4]  # "2023-01-15" -> "2023"

    # Track title — skip for compilations so original filename is preserved
    if not is_compilation:
        title = audio.get("title")
        if title:
            defaults["name"] = slugify(title[0])

    # Track number — [OP-3] zero-padded for ordinal sorting
    tracknumber = audio.get("tracknumber")
    if tracknumber:
        try:
            # Handle "3/12" or "3" formats
            num = int(tracknumber[0].split("/")[0])
            defaults["track"] = str(num)
        except (ValueError, IndexError):
            pass

    return defaults


def defaults_from_source(source_path: str, root: str, input_path: str) -> dict[str, str]:
    """Extract default tag values — merged (metadata wins over filename).

    Returns a dict of tag_type -> suggested_value (already slugified).
    """
    filename_defs, metadata_defs = defaults_from_source_split(source_path, root, input_path)
    return {**filename_defs, **metadata_defs}


def defaults_from_source_split(
    source_path: str, root: str, input_path: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Return (filename_defaults, metadata_defaults) separately.

    filename_defaults: derived from folder structure and filename only.
    metadata_defaults: derived from embedded metadata (ID3, etc.), mapped to root-specific fields.
    """
    source = Path(source_path)
    input_dir = Path(input_path)

    # Compute filename/folder defaults
    try:
        relative = source.relative_to(input_dir)
    except ValueError:
        stem = PurePosixPath(source.name).stem
        filename_defs: dict[str, str] = {"name": slugify(stem)}
        metadata_defs = _metadata_for_root(source_path, root)
        return filename_defs, metadata_defs

    parts = list(relative.parts)
    filename = parts.pop()
    stem = PurePosixPath(filename).stem

    if root == "music":
        filename_defs = _defaults_music(parts, stem)
    elif root == "books":
        filename_defs = _defaults_books(parts, stem)
    elif root == "podcasts":
        filename_defs = _defaults_podcasts(parts, stem)
    elif root == "tv":
        filename_defs = _defaults_tv(parts, stem, filename)
    elif root == "movies":
        filename_defs = _defaults_movies(parts, stem, filename)
    elif root == "comedy":
        filename_defs = _defaults_comedy(parts, stem)
    elif root == "memories":
        filename_defs = _defaults_memories(parts, stem)
    else:
        filename_defs = {}

    # Compute metadata defaults (mapped to root-specific field names)
    metadata_defs = _metadata_for_root(source_path, root)

    # VA compilations: use raw filename stem as name when metadata has no title
    if root == "music" and metadata_defs.get("artist") == "Various Artists" and "name" not in metadata_defs:
        metadata_defs["name"] = stem

    return filename_defs, metadata_defs


def _metadata_for_root(source_path: str, root: str) -> dict[str, str]:
    """Extract embedded metadata and map to root-specific field names."""
    if root not in ("music", "books", "podcasts", "comedy"):
        return {}

    raw = extract_audio_metadata(source_path)
    if not raw:
        return {}

    if root == "books":
        mapped: dict[str, str] = {}
        if "artist" in raw:
            mapped["author"] = raw["artist"]
        if "album" in raw:
            mapped["title"] = raw["album"]
        if "name" in raw:
            mapped["name"] = raw["name"]
        if "track" in raw:
            mapped["track"] = raw["track"]
        return mapped

    if root == "podcasts":
        mapped = {}
        if "artist" in raw:
            mapped["show"] = raw["artist"]
        if "name" in raw:
            mapped["name"] = raw["name"]
        return mapped

    if root == "comedy":
        mapped = {}
        if "artist" in raw:
            mapped["artist"] = raw["artist"]
        if "name" in raw:
            mapped["name"] = raw["name"]
        return mapped

    # music — fields map directly
    return raw


def _defaults_music(parts: list[str], stem: str) -> dict[str, str]:
    """Music: defaults from folder structure and filename only (no metadata)."""
    defaults: dict[str, str] = {"name": slugify(stem)}

    if len(parts) >= 2:
        defaults["artist"] = slugify(parts[0])
        defaults["album"] = slugify(parts[1])
        # If there are 3+ folder parts, combine non-first into album
        # e.g., _Albums/8 Mile/Music From.../track.mp3 -> album = "8 Mile Music From..."
        if len(parts) >= 3:
            defaults["album"] = slugify(" ".join(parts[1:]))
    elif len(parts) == 1:
        defaults["artist"] = slugify(parts[0])

    # Strip track numbers from name (e.g., "01 - Time" -> "Time", "01. Time" -> "Time")
    cleaned = re.sub(r"^\d{1,3}[\s.\-_]+", "", stem)
    if cleaned:
        defaults["name"] = slugify(cleaned)

    return defaults


def _defaults_books(parts: list[str], stem: str) -> dict[str, str]:
    """Books: defaults from folder structure only (no metadata)."""
    defaults: dict[str, str] = {"name": slugify(stem)}

    if len(parts) >= 2:
        defaults["author"] = slugify(parts[0])
        defaults["title"] = slugify(parts[1])
    elif len(parts) == 1:
        defaults["author"] = slugify(parts[0])

    return defaults


def _defaults_podcasts(parts: list[str], stem: str) -> dict[str, str]:
    """Podcasts: defaults from folder structure only (no metadata)."""
    defaults: dict[str, str] = {"name": slugify(stem)}

    if len(parts) >= 1:
        defaults["show"] = slugify(parts[0])

    return defaults


def _defaults_tv(parts: list[str], stem: str, filename: str) -> dict[str, str]:
    """TV: expect Show/Season/Episode or parse S01E02 patterns."""
    defaults: dict[str, str] = {"name": slugify(stem)}

    # Try to parse S01E02 pattern from filename
    match = re.search(r"[Ss](\d{1,2})[Ee](\d{1,2})", filename)
    if match:
        defaults["season"] = match.group(1).lstrip("0") or "0"

    if len(parts) >= 2:
        defaults["show"] = slugify(parts[0])
        defaults["season"] = slugify(parts[1])
    elif len(parts) == 1:
        defaults["show"] = slugify(parts[0])

    return defaults


def _defaults_movies(parts: list[str], stem: str, filename: str) -> dict[str, str]:
    """Movies: try to extract title and year from filename."""
    defaults: dict[str, str] = {"name": slugify(stem)}

    if len(parts) >= 1:
        defaults["series"] = slugify(parts[0])

    # Try to extract year from filename
    match = re.search(r"[\(\[]?((?:19|20)\d{2})[\)\]]?", filename)
    if match:
        year = match.group(1)
        # Clean the name and append year in bracket format
        name_part = filename[: match.start()].strip(" .-_")
        if name_part:
            defaults["name"] = f"{slugify(name_part)} [{year}]"

    return defaults


def _defaults_comedy(parts: list[str], stem: str) -> dict[str, str]:
    """Comedy: defaults from folder structure only (no metadata)."""
    defaults: dict[str, str] = {"name": slugify(stem)}

    if len(parts) >= 1:
        defaults["artist"] = slugify(parts[0])

    return defaults


def _defaults_memories(parts: list[str], stem: str) -> dict[str, str]:
    """Memories: use subfolder names as event segments."""
    defaults: dict[str, str] = {"name": slugify(stem)}

    if parts:
        event = ":".join(slugify(p) for p in parts)
        defaults["event"] = event

    return defaults
