"""Write tags to file metadata on accept. [TP-1, TP-2, TP-4]

Implements the spec's tag persistence philosophy: files are the source of truth.
Tags are written to native metadata formats (EXIF, ID3, Vorbis) and extended
attributes before the file is moved to the output tree.

Returns a list of (field, value, target) tuples describing what was written,
for logging purposes.
"""

from __future__ import annotations

import logging
import os
import plistlib
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Tags that are derived from output path structure — never written to metadata [TP-3]
PATH_DERIVED_TAGS = {"show", "season", "episode", "series"}

# Tags computed from file properties — never written [TP-3]
COMPUTED_TAGS = {"class", "month", "year"}


def write_tags(
    file_path: Path,
    tags: dict[str, str],
    root: str,
    file_class: str,
) -> list[tuple[str, str, str]]:
    """Write tags to a file's native metadata and extended attributes.

    Args:
        file_path: Path to the file (before it's moved to output).
        tags: Dict of tag_type -> value (e.g. {"artist": "Pink Floyd", "album": "The Wall"}).
        root: The root category (memories, music, etc.).
        file_class: The file class (image, audio, video, etc.).

    Returns:
        List of (field, value, target) describing each write operation.
        target is one of: "id3", "vorbis", "mp4", "exif", "xattr", "finder_tag"
    """
    writes: list[tuple[str, str, str]] = []

    # Write native metadata based on file type
    if file_class == "audio":
        writes.extend(_write_audio_tags(file_path, tags))
    elif file_class == "image":
        writes.extend(_write_image_tags(file_path, tags))

    # Write xattrs for format-agnostic tags [TP-2]
    writes.extend(_write_xattrs(file_path, tags, root))

    for field, value, target in writes:
        logger.info("Wrote %s=%s to %s [%s]", field, value, file_path.name, target)

    return writes


def _write_audio_tags(file_path: Path, tags: dict[str, str]) -> list[tuple[str, str, str]]:
    """Write tags to audio files using mutagen. [TP-1]"""
    try:
        import mutagen
        from mutagen.easyid3 import EasyID3
        from mutagen.easymp4 import EasyMP4Tags
    except ImportError:
        logger.warning("mutagen not available — skipping audio tag writing")
        return []

    writes: list[tuple[str, str, str]] = []

    try:
        audio = mutagen.File(file_path, easy=True)
        if audio is None:
            logger.warning("Could not open audio file for tag writing: %s", file_path)
            return []
    except Exception:
        logger.warning("Failed to open audio file for tag writing: %s", file_path, exc_info=True)
        return []

    # Determine backend name for logging
    if isinstance(audio.tags, EasyID3):
        backend = "id3"
    elif isinstance(audio.tags, EasyMP4Tags):
        backend = "mp4"
    else:
        backend = "vorbis"

    # Map pinpoint tag names to mutagen easy tag names
    field_map = {
        "artist": "artist",
        "album": "album",
        "name": "title",
        "year": "date",
        "track": "tracknumber",
    }

    for tag_field, mutagen_key in field_map.items():
        value = tags.get(tag_field)
        if not value:
            continue
        # Skip path-derived and computed tags
        if tag_field in PATH_DERIVED_TAGS or tag_field in COMPUTED_TAGS:
            continue
        try:
            audio[mutagen_key] = [value]
            writes.append((tag_field, value, backend))
        except Exception:
            logger.warning("Failed to write %s to %s", mutagen_key, file_path, exc_info=True)

    if writes:
        try:
            audio.save()
        except Exception:
            logger.error("Failed to save audio tags for %s", file_path, exc_info=True)
            return []

    return writes


def _write_image_tags(file_path: Path, tags: dict[str, str]) -> list[tuple[str, str, str]]:
    """Write EXIF tags to image files using Pillow. [TP-1]

    Currently writes DateTimeOriginal from the date tag.
    Event (Iptc4xmpExt:Event) and person tags require pyexiv2/exiftool — deferred.
    """
    if file_path.suffix.lower() not in (".jpg", ".jpeg", ".tiff", ".tif"):
        return []

    date_value = tags.get("date")
    if not date_value:
        return []

    try:
        from PIL import Image
        from PIL.ExifTags import IFD
    except ImportError:
        logger.warning("Pillow not available — skipping image tag writing")
        return []

    writes: list[tuple[str, str, str]] = []

    try:
        img = Image.open(file_path)
        exif = img.getexif()
        exif_ifd = exif.get_ifd(IFD.Exif)

        # Write DateTimeOriginal (tag 36867) in EXIF format
        exif_date = date_value.replace("-", ":").replace("T", " ")
        if len(exif_date) == 10:
            exif_date += " 00:00:00"
        exif_ifd[36867] = exif_date
        exif_ifd[36868] = exif_date  # DateTimeDigitized
        writes.append(("date", date_value, "exif"))

        img.save(str(file_path), exif=exif.tobytes())
    except Exception:
        logger.warning("Failed to write EXIF tags to %s", file_path, exc_info=True)
        return []

    return writes


def _setxattr(path: str, name: str, value: bytes) -> None:
    """Set an extended attribute, using the right API per platform."""
    if sys.platform == "darwin":
        subprocess.run(
            ["xattr", "-w", name, value.decode("utf-8", errors="replace"), path],
            check=True, capture_output=True,
        )
    else:
        os.setxattr(path, name, value)


def _setxattr_bytes(path: str, name: str, value: bytes) -> None:
    """Set an extended attribute with raw bytes (binary plist etc.)."""
    if sys.platform == "darwin":
        hex_value = " ".join(f"{b:02X}" for b in value)
        subprocess.run(
            ["xattr", "-w", "-x", name, hex_value, path],
            check=True, capture_output=True,
        )
    else:
        os.setxattr(path, name, value)


def _write_xattrs(
    file_path: Path, tags: dict[str, str], root: str,
) -> list[tuple[str, str, str]]:
    """Write extended attributes for format-agnostic tags. [TP-2, TP-6, TP-8]"""
    writes: list[tuple[str, str, str]] = []

    # Always write root as xattr
    try:
        _setxattr(str(file_path), "user.pinpoint.root", root.encode("utf-8"))
        writes.append(("root", root, "xattr"))
    except (OSError, subprocess.CalledProcessError):
        logger.warning("Failed to write xattr root to %s", file_path, exc_info=True)

    # Write Finder tags on macOS [TP-6]
    if sys.platform == "darwin":
        writes.extend(_write_finder_tags(file_path, tags, root))

    return writes


def _write_finder_tags(
    file_path: Path, tags: dict[str, str], root: str,
) -> list[tuple[str, str, str]]:
    """Mirror tags to macOS Finder tags (com.apple.metadata:_kMDItemUserTags). [TP-6]"""
    writes: list[tuple[str, str, str]] = []

    # Build Finder tag list — root + any path-relevant tags with values
    finder_tags = [f"pinpoint:{root}"]
    for field, value in tags.items():
        if field in COMPUTED_TAGS or field in PATH_DERIVED_TAGS:
            continue
        if value:
            finder_tags.append(f"{field}:{value}")

    try:
        # Finder tags are stored as a plist-encoded array
        plist_data = plistlib.dumps(finder_tags, fmt=plistlib.FMT_BINARY)
        _setxattr_bytes(
            str(file_path),
            "com.apple.metadata:_kMDItemUserTags",
            plist_data,
        )
        writes.append(("finder_tags", ", ".join(finder_tags), "finder_tag"))
    except (OSError, subprocess.CalledProcessError):
        logger.debug("Failed to write Finder tags to %s", file_path, exc_info=True)

    return writes
