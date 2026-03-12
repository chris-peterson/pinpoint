"""Output directory monitoring — detect renames, moves, and deletions. [§11]

Uses watchfiles (Rust-backed notify) to watch the output directory for changes.
Detects three cases:
  1. File renamed/moved — same hash appears at a new path
  2. File deleted — managed file no longer exists anywhere
  3. New file added — unknown file appears in output tree

Also provides a startup verification scan to catch changes that happened
while pinpoint was not running.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import aiosqlite

from pinpoint.actions import log_action
from pinpoint.discovery import classify_file, hash_file
from pinpoint.models import ActionVerb

logger = logging.getLogger(__name__)


async def verify_managed_files(db: aiosqlite.Connection) -> dict[str, int]:
    """Startup scan: check all managed files still exist at their expected paths. [OM periodic]

    Returns counts of {verified, missing, drifted}.
    """
    cursor = await db.execute(
        "SELECT id, managed_path, content_hash FROM files WHERE status = 'managed'"
    )
    rows = await cursor.fetchall()

    counts = {"verified": 0, "missing": 0}

    for row in rows:
        file_id, managed_path, content_hash = row
        if not managed_path:
            continue

        path = Path(managed_path)
        if path.exists():
            counts["verified"] += 1
        else:
            # File is missing from expected location
            await db.execute(
                "UPDATE files SET status = 'missing' WHERE id = ?",
                (file_id,),
            )
            await log_action(db, ActionVerb.MISSING, file_id, {
                "expected_path": managed_path,
                "reason": "startup_verification",
            })
            counts["missing"] += 1
            logger.warning("Managed file missing: %s", managed_path)

    await db.commit()

    if counts["missing"]:
        logger.info(
            "Verification: %d verified, %d missing",
            counts["verified"], counts["missing"],
        )
    else:
        logger.info("Verification: all %d managed files present", counts["verified"])

    return counts


async def watch_output(
    db: aiosqlite.Connection,
    output_dir: Path,
) -> None:
    """Watch the output directory for external changes. Runs until cancelled.

    Detects renames, moves, and deletions of managed files.
    """
    try:
        from watchfiles import awatch, Change
    except ImportError:
        logger.info("watchfiles not available — output monitoring disabled")
        return

    logger.info("Watching output directory: %s", output_dir)

    try:
        async for changes in awatch(output_dir):
            await _process_changes(db, output_dir, changes, Change)
    except asyncio.CancelledError:
        logger.info("Output watcher stopped")
    except Exception:
        logger.exception("Output watcher crashed")


async def _process_changes(db, output_dir, changes, Change) -> None:
    """Process a batch of filesystem changes from watchfiles."""
    deleted_paths: list[str] = []
    added_paths: list[Path] = []
    modified_paths: list[Path] = []

    for change_type, path_str in changes:
        path = Path(path_str)

        if change_type == Change.deleted:
            deleted_paths.append(path_str)
        elif change_type == Change.added:
            if path.is_file() and classify_file(path) is not None:
                added_paths.append(path)
        elif change_type == Change.modified:
            if path.is_file():
                modified_paths.append(path)

    # Handle deletions — check if any managed files are now missing [OM-5, OM-6, OM-7]
    for deleted_path in deleted_paths:
        cursor = await db.execute(
            "SELECT id, content_hash FROM files WHERE managed_path = ? AND status = 'managed'",
            (deleted_path,),
        )
        row = await cursor.fetchone()
        if not row:
            continue

        file_id, content_hash = row

        # Check if the file was moved (same hash appears in an added path)
        moved_to = None
        for added_path in added_paths:
            try:
                new_hash = hash_file(added_path)
                if new_hash == content_hash:
                    moved_to = added_path
                    break
            except OSError:
                continue

        if moved_to:
            # File was renamed/moved [OM-1, OM-2, OM-3]
            new_path_str = str(moved_to)
            await db.execute(
                "UPDATE files SET managed_path = ?, status = 'drifted' WHERE id = ?",
                (new_path_str, file_id),
            )
            await log_action(db, ActionVerb.RENAME, file_id, {
                "old_path": deleted_path,
                "new_path": new_path_str,
            })
            # Remove from added list so we don't also treat it as a new file
            added_paths.remove(moved_to)
            logger.info("Detected rename: %s -> %s", deleted_path, new_path_str)
        else:
            # File was deleted [OM-5, OM-6, OM-7]
            await db.execute(
                "UPDATE files SET status = 'missing' WHERE id = ?",
                (file_id,),
            )
            await log_action(db, ActionVerb.MISSING, file_id, {
                "expected_path": deleted_path,
                "reason": "watcher",
            })
            logger.warning("Detected deletion: %s", deleted_path)

    await db.commit()
