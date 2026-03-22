"""File discovery — scan _input/<root>/ subdirs, hash, dedup, perceptual hash, auto-import.

Provides two discovery modes:
  1. Initial scan — walk every <library>/_input/<root>/ tree on startup.
  2. Continuous watch — use watchfiles to detect new files dropped into _input/<root>/.

Files that cannot be processed are moved to <library>/_input/_rejections/, which is
never re-scanned.
"""

import asyncio
import hashlib
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

from pinpoint.defaults import defaults_from_source, source_for_field, confidence_for_source, compute_file_confidence
from pinpoint.models import classify_file, MEDIA_EXTENSIONS, ALL_TAG_FIELDS, DERIVED_ATTRIBUTES
from pinpoint.paths import derive_path

PHASH_THRESHOLD = 10
QUIET_PERIOD_SECS = 2.0
DRAIN_TICK_SECS = 0.5


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _compute_phash(path: Path) -> str | None:
    """Compute a perceptual hash for an image. Returns hex string or None."""
    try:
        import imagehash
        from PIL import Image

        with Image.open(path) as img:
            return str(imagehash.phash(img))
    except Exception:
        return None


def _phash_hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def _dir_has_audio(directory: Path) -> bool:
    audio_exts = MEDIA_EXTENSIONS["audio"]
    return any(f.suffix.lower() in audio_exts for f in directory.iterdir() if f.is_file())


async def _find_phash_stack(db, phash: str, file_id: int) -> int | None:
    """Find an existing stack for a near-duplicate image, or create one."""
    rows = await db.execute(
        "SELECT id, perceptual_hash, stack_id FROM files "
        "WHERE perceptual_hash IS NOT NULL AND id != ?",
        (file_id,),
    )
    for row in rows:
        existing_id, existing_phash, existing_stack_id = row[0], row[1], row[2]
        if _phash_hamming(phash, existing_phash) <= PHASH_THRESHOLD:
            if existing_stack_id:
                await db.execute_write(
                    "UPDATE files SET stack_id = ? WHERE id = ?",
                    (existing_stack_id, file_id),
                )
                return existing_stack_id
            else:
                stack_id = await db.execute_insert(
                    "INSERT INTO stacks (cover_file_id) VALUES (?)",
                    (existing_id,),
                )
                await db.execute_write(
                    "UPDATE files SET stack_id = ? WHERE id IN (?, ?)",
                    (stack_id, existing_id, file_id),
                )
                return stack_id
    return None


async def discover_file(
    db, path: Path, file_class: str, root: str, input_path: str,
    config: dict,
) -> int | None:
    """Discover a single file: hash, dedup, phash, auto-import.

    Returns the new file_id, or None if the file was a duplicate or failed.
    """
    content_hash = _hash_file(path)

    dupe = await db.execute_one(
        "SELECT id FROM files WHERE content_hash = ?", (content_hash,)
    )
    if dupe:
        return None

    creation_date = None
    try:
        stat = path.stat()
        creation_date = datetime.fromtimestamp(stat.st_birthtime).strftime("%Y-%m-%d")
    except (AttributeError, OSError):
        pass

    phash = None
    if file_class == "image":
        phash = _compute_phash(path)

    file_id = await db.execute_insert(
        """INSERT INTO files (status, root, file_class, content_hash, perceptual_hash, creation_date)
           VALUES ('analyzing', ?, ?, ?, ?, ?)""",
        (root, file_class, content_hash, phash, creation_date),
    )
    await db.log_action("discover", file_id, {
        "source_path": str(path),
        "content_hash": content_hash,
        "perceptual_hash": phash,
    })

    if phash:
        stack_id = await _find_phash_stack(db, phash, file_id)
        if stack_id:
            print(f"  Auto-stacked {path.name} into stack {stack_id} (phash match)")

    await _auto_import(db, file_id, str(path), root, input_path, config)
    return file_id


async def run_discovery(db, config: dict):
    for inp in config.get("inputs", []):
        input_path = Path(inp["path"])
        root = inp["root"]
        if not input_path.exists():
            continue
        await _scan_input(db, input_path, root, config)


async def _scan_input(db, input_path: Path, root: str, config: dict):
    for path in input_path.rglob("*"):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue

        ext = path.suffix.lower()
        file_class = classify_file(ext)

        if file_class == "image" and root in ("music", "book", "podcast"):
            if _dir_has_audio(path.parent):
                continue

        await discover_file(db, path, file_class, root, str(input_path), config)


async def watch_inputs(db, config: dict):
    """Continuously watch _input/<root>/ folders for new files.

    Files are buffered through a quiet-period gate (QUIET_PERIOD_SECS) so that
    in-progress copies finish before pinpoint reads them. A path is processed
    only after it has been quiet (no events, stable size+mtime) for the
    configured period. Runs until cancelled.
    """
    try:
        from watchfiles import awatch
    except ImportError:
        print("watchfiles not available — input watching disabled, falling back to polling")
        await _poll_discovery(db, config)
        return

    input_lookup: dict[str, dict] = {}
    watch_paths = []
    for inp in config.get("inputs", []):
        p = Path(inp["path"])
        if p.exists():
            input_lookup[str(p)] = inp
            watch_paths.append(p)

    if not watch_paths:
        return

    print(f"Watching {len(watch_paths)} input folder(s) for new files")

    pending: dict[str, float] = {}
    last_stat: dict[str, tuple[int, float]] = {}
    lock = asyncio.Lock()

    async def producer():
        async for changes in awatch(*watch_paths):
            now = time.time()
            async with lock:
                for _change_type, path_str in changes:
                    if Path(path_str).name.startswith("."):
                        continue
                    pending[path_str] = now

    async def drainer():
        while True:
            await asyncio.sleep(DRAIN_TICK_SECS)
            now = time.time()
            ready: list[str] = []
            async with lock:
                for path_str, last_event in list(pending.items()):
                    if now - last_event < QUIET_PERIOD_SECS:
                        continue
                    path = Path(path_str)
                    if not path.is_file():
                        pending.pop(path_str, None)
                        last_stat.pop(path_str, None)
                        continue
                    try:
                        st = path.stat()
                    except OSError:
                        continue
                    size_mtime = (st.st_size, st.st_mtime)
                    if last_stat.get(path_str) != size_mtime:
                        last_stat[path_str] = size_mtime
                        pending[path_str] = now  # not stable yet — reset clock
                        continue
                    ready.append(path_str)
                    pending.pop(path_str, None)
                    last_stat.pop(path_str, None)

            for path_str in ready:
                await _process_pending(db, config, input_lookup, Path(path_str))

    try:
        await asyncio.gather(producer(), drainer())
    except asyncio.CancelledError:
        print("Input watcher stopped")


async def _process_pending(db, config: dict, input_lookup: dict[str, dict], path: Path):
    if not path.is_file():
        return

    file_class = classify_file(path.suffix.lower())
    if file_class is None:
        return

    inp = None
    path_str = str(path)
    for inp_str, inp_config in input_lookup.items():
        if path_str.startswith(inp_str):
            inp = inp_config
            break
    if inp is None:
        return

    root = inp["root"]
    if file_class == "image" and root in ("music", "book", "podcast"):
        if _dir_has_audio(path.parent):
            return

    file_id = await discover_file(db, path, file_class, root, inp["path"], config)
    if file_id:
        print(f"  Watcher discovered: {path.name}")


async def _poll_discovery(db, config: dict):
    """Fallback: poll for new files every 10 seconds."""
    try:
        while True:
            await asyncio.sleep(10)
            await run_discovery(db, config)
    except asyncio.CancelledError:
        pass


async def _auto_import(db, file_id: int, source_path: str, root: str, input_path: str, config: dict):
    defs = await defaults_from_source(source_path, root, input_path)
    merged = defs["merged"]

    tags = {}
    sources = {}
    for field in ALL_TAG_FIELDS:
        if field in DERIVED_ATTRIBUTES:
            continue
        val = merged.get(field, "")
        if val:
            tags[field] = [val]
            sources[field] = source_for_field(field, defs["filename_defs"], defs["metadata_defs"])

    creation_date_row = await db.execute_one(
        "SELECT creation_date FROM files WHERE id = ?", (file_id,)
    )
    if creation_date_row and creation_date_row["creation_date"]:
        cd = creation_date_row["creation_date"]
        tags["month"] = [cd[:7]]
        tags["year"] = [cd[:4]]

    for field, values in tags.items():
        if field in DERIVED_ATTRIBUTES:
            continue
        for val in values:
            tag_name = f"{field}:{val}"
            await db.execute_write(
                "INSERT OR IGNORE INTO tags (name, type) VALUES (?, ?)", (tag_name, field)
            )
            row = await db.execute_one("SELECT id FROM tags WHERE name = ?", (tag_name,))
            if row:
                src = sources.get(field, "fallback")
                conf = confidence_for_source(src)
                await db.execute_write(
                    "INSERT OR IGNORE INTO file_tags (file_id, tag_id, source, confidence) VALUES (?, ?, ?, ?)",
                    (file_id, row[0], src, conf),
                )

    confidence = compute_file_confidence(tags, sources, root)

    original_filename = Path(source_path).name
    rel_path = derive_path(root, tags, original_filename)
    full_path = os.path.join(config["library"], rel_path)

    candidate = full_path
    counter = 1
    base = Path(full_path)
    while True:
        existing = await db.execute_one(
            "SELECT id FROM files WHERE output_path = ?", (candidate,)
        )
        if not existing and not Path(candidate).exists():
            break
        candidate = str(base.parent / f"{base.stem}-{counter}{base.suffix}")
        counter += 1

    os.makedirs(os.path.dirname(candidate), exist_ok=True)

    try:
        shutil.move(source_path, candidate)
    except Exception as e:
        print(f"Import failed for {source_path}: {e} — moving to _rejections/")
        await _reject_file(db, file_id, source_path, config, reason=str(e))
        return

    await db.execute_write(
        """UPDATE files SET status = 'imported', output_path = ?,
           imported_at = datetime('now'), confidence = ?,
           analysis_status = 'complete'
           WHERE id = ?""",
        (candidate, confidence, file_id),
    )
    await db.log_action("auto_import", file_id, {
        "source_path": source_path,
        "destination_path": candidate,
        "confidence": confidence,
    })


async def _reject_file(db, file_id: int, source_path: str, config: dict, reason: str):
    """Move a file to <library>/_input/_rejections/<root>/<relative-path>/ and mark it rejected.

    Mirrors the file's path under _input/<root>/ so the rejection location preserves
    the source context. Restoration is a single mv back into _input/<root>/.
    """
    src = Path(source_path)
    input_root = Path(config["input_root"])
    rejections_root = Path(config["rejections_dir"])

    try:
        rel = src.relative_to(input_root)
    except ValueError:
        rel = Path(src.name)

    dest = rejections_root / rel
    counter = 1
    while dest.exists():
        dest = dest.parent / f"{src.stem}-{counter}{src.suffix}"
        counter += 1

    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        shutil.move(source_path, str(dest))
    except Exception as e:
        print(f"Reject move failed for {source_path}: {e}")
        return

    await db.execute_write(
        "UPDATE files SET status = 'rejected', output_path = ? WHERE id = ?",
        (str(dest), file_id),
    )
    await db.log_action("reject", file_id, {
        "source_path": source_path,
        "destination_path": str(dest),
        "reason": reason,
    })
