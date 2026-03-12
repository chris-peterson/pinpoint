import hashlib
from pathlib import Path

from pinpoint.models import classify_file, MEDIA_EXTENSIONS


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
        await _scan_input(db, input_path, root)


async def _scan_input(db, input_path: Path, root: str):
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
            from datetime import datetime
            creation_date = datetime.fromtimestamp(stat.st_birthtime).strftime("%Y-%m-%d")
        except (AttributeError, OSError):
            pass

        await db.execute_insert(
            """INSERT INTO files (source_path, status, root, file_class, content_hash, creation_date)
               VALUES (?, 'pending', ?, ?, ?, ?)""",
            (str(path), root, file_class, content_hash, creation_date),
        )
        await db.log_action("discover", None, {"source_path": str(path)})
