import hashlib
import os
import shutil
from datetime import datetime
from pathlib import Path

from pinpoint.defaults import defaults_from_source, source_for_field, confidence_for_source, compute_file_confidence
from pinpoint.models import classify_file, MEDIA_EXTENSIONS, ALL_TAG_FIELDS, DERIVED_ATTRIBUTES
from pinpoint.paths import derive_path


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _dir_has_audio(directory: Path) -> bool:
    audio_exts = MEDIA_EXTENSIONS["audio"]
    return any(f.suffix.lower() in audio_exts for f in directory.iterdir() if f.is_file())


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

        existing = await db.execute_one(
            "SELECT id FROM files WHERE source_path = ?", (str(path),)
        )
        if existing:
            continue

        content_hash = _hash_file(path)

        dupe = await db.execute_one(
            "SELECT id FROM files WHERE content_hash = ?", (content_hash,)
        )
        if dupe:
            continue

        creation_date = None
        try:
            stat = path.stat()
            creation_date = datetime.fromtimestamp(stat.st_birthtime).strftime("%Y-%m-%d")
        except (AttributeError, OSError):
            pass

        file_id = await db.execute_insert(
            """INSERT INTO files (source_path, status, root, file_class, content_hash, creation_date)
               VALUES (?, 'analyzing', ?, ?, ?, ?)""",
            (str(path), root, file_class, content_hash, creation_date),
        )
        await db.log_action("discover", file_id, {"source_path": str(path)})

        await _auto_import(db, file_id, str(path), root, str(input_path), config)


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
    output_dir = config["output"]
    full_path = os.path.join(output_dir, rel_path)

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

    import_mode = config.get("import_mode", "copy")
    try:
        if import_mode == "move":
            shutil.move(source_path, candidate)
        else:
            shutil.copy2(source_path, candidate)
    except Exception as e:
        print(f"Import failed for {source_path}: {e}")
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
        "import_mode": import_mode,
    })
