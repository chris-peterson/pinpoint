"""File discovery — scan input folders, hash, dedup, insert pending."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue

import aiosqlite

from pinpoint.actions import log_action
from pinpoint.models import ActionVerb

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryStatus:
    """Shared discovery status, readable by the web layer."""
    running: bool = False
    current_input: str = ""
    processed: int = 0
    new: int = 0
    duplicates: int = 0
    done_inputs: list[str] = field(default_factory=list)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".heic", ".heif", ".webp", ".tiff", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".wmv", ".flv", ".webm"}
AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".wav", ".ogg", ".opus", ".aac", ".wma"}

ALL_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

_SENTINEL = None  # signals end of walk


def classify_file(path: Path) -> str | None:
    """Determine the file class from extension. Returns None if unsupported."""
    ext = path.suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    return None


def hash_file(path: Path) -> str:
    """Compute SHA-256 content hash."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def extract_creation_date(path: Path, file_class: str) -> datetime | None:
    """Extract creation date from media metadata or filesystem.

    Prefers embedded metadata over filesystem dates.
    """
    if file_class == "image":
        dt = _exif_date(path)
        if dt:
            return dt

    # Fall back to filesystem
    stat = path.stat()
    # birthtime on macOS, ctime on Linux
    ts = getattr(stat, "st_birthtime", None) or stat.st_ctime
    return datetime.fromtimestamp(ts)


def _exif_date(path: Path) -> datetime | None:
    """Try to extract EXIF DateTimeOriginal."""
    try:
        from PIL import Image
        from PIL.ExifTags import Base as ExifBase

        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                return None
            # DateTimeOriginal
            dt_str = exif.get(ExifBase.DateTimeOriginal) or exif.get(ExifBase.DateTime)
            if dt_str:
                return datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return None


def _walk_files(input_path: Path, file_queue: Queue) -> None:
    """Walk the directory tree and put supported files into the queue.

    Uses os.scandir for speed instead of rglob. Sends _SENTINEL when done.
    Skips images in directories that contain audio files (likely album art).
    """
    try:
        for dirpath, _dirnames, filenames in os.walk(input_path):
            # Classify all files in this directory first
            classified = []
            has_audio = False
            for filename in filenames:
                full = Path(dirpath) / filename
                file_class = classify_file(full)
                if file_class is not None:
                    classified.append((full, file_class))
                    if file_class == "audio":
                        has_audio = True

            for full, file_class in classified:
                # Skip images alongside audio files (cover art, booklet scans, etc.)
                if has_audio and file_class == "image":
                    continue
                file_queue.put((full, file_class))
    finally:
        file_queue.put(_SENTINEL)


async def scan_input(
    db: aiosqlite.Connection,
    input_path: Path,
    root: str,
    executor=None,
    status: DiscoveryStatus | None = None,
) -> int:
    """Scan an input folder and insert new files as pending.

    Streams files as they're discovered so items appear in the queue immediately.

    Args:
        executor: Optional ThreadPoolExecutor for CPU-bound work.
        status: Optional shared status object for UI reporting.

    Returns the number of new files discovered.
    """
    if not input_path.exists():
        logger.warning("Input path does not exist: %s", input_path)
        return 0

    loop = asyncio.get_event_loop()
    file_queue: Queue = Queue(maxsize=200)

    if status:
        status.current_input = str(input_path)

    # Start directory walk in background thread
    logger.info("Scanning %s for supported files...", input_path)
    walk_future = loop.run_in_executor(executor, _walk_files, input_path, file_queue)

    count = 0
    skipped = 0
    processed = 0
    t0 = time.monotonic()

    while True:
        # Pull next file from the walk queue (non-blocking with short sleep)
        try:
            item = await loop.run_in_executor(executor, file_queue.get, True, 0.5)
        except Empty:
            continue

        if item is _SENTINEL:
            break

        path, file_class = item
        processed += 1
        if status:
            status.processed = processed

        try:
            content_hash = await loop.run_in_executor(executor, hash_file, path)
        except OSError:
            logger.debug("Could not hash %s, skipping", path)
            continue

        # Check for duplicate
        cursor = await db.execute(
            "SELECT id FROM files WHERE content_hash = ?", (content_hash,)
        )
        if await cursor.fetchone():
            skipped += 1
            if status:
                status.duplicates = skipped
            if processed % 100 == 0:
                elapsed = time.monotonic() - t0
                logger.info(
                    "Processed %d — %d new, %d dupes — %.1fs elapsed",
                    processed, count, skipped, elapsed,
                )
            continue

        creation_date = await loop.run_in_executor(
            executor, extract_creation_date, path, file_class
        )
        creation_date_str = creation_date.isoformat() if creation_date else None

        cursor = await db.execute(
            """INSERT INTO files (source_path, status, root, file_class, content_hash, creation_date)
               VALUES (?, 'pending', ?, ?, ?, ?)""",
            (str(path), root, file_class, content_hash, creation_date_str),
        )
        file_id = cursor.lastrowid

        await log_action(db, ActionVerb.DISCOVER, file_id, {
            "source_path": str(path),
            "content_hash": content_hash,
        })

        count += 1
        if status:
            status.new = count

        # Commit every 50 new files so they appear in the queue immediately
        if count % 50 == 0:
            await db.commit()
            elapsed = time.monotonic() - t0
            logger.info(
                "Processed %d — %d new, %d dupes — %.1fs elapsed",
                processed, count, skipped, elapsed,
            )

    # Wait for walk thread to finish
    await walk_future

    await db.commit()
    elapsed = time.monotonic() - t0
    logger.info(
        "Discovery complete: %d new, %d duplicates skipped (%.1fs)",
        count, skipped, elapsed,
    )
    return count
