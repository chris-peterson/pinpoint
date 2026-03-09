"""Queue API — list pending files, accept, reject, skip."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from pinpoint import database as db
from pinpoint.actions import log_action
from pinpoint.defaults import defaults_from_source, extract_audio_metadata
from pinpoint.models import ActionVerb, File, FileStatus
from pinpoint.paths import derive_path

router = APIRouter(prefix="/api/queue", tags=["queue"])


PENDING_FILTER = "status = 'pending' AND skipped_at IS NULL"


@router.get("")
async def list_queue(request: Request, limit: int = 50, offset: int = 0):
    """List pending files, newest first."""
    conn = request.app.state.db
    rows = await db.fetch_all(
        conn,
        f"""SELECT * FROM files WHERE {PENDING_FILTER}
           ORDER BY discovery_date DESC
           LIMIT ? OFFSET ?""",
        (limit, offset),
    )
    count_row = await db.fetch_one(
        conn, f"SELECT COUNT(*) as count FROM files WHERE {PENDING_FILTER}"
    )
    return {
        "files": rows,
        "total": count_row["count"] if count_row else 0,
    }


@router.get("/current")
async def current_file(request: Request):
    """Get the next file to review."""
    conn = request.app.state.db
    row = await db.fetch_one(
        conn,
        f"""SELECT * FROM files WHERE {PENDING_FILTER}
           ORDER BY discovery_date DESC
           LIMIT 1""",
    )
    if row is None:
        return {"file": None, "remaining": 0}

    count_row = await db.fetch_one(
        conn, f"SELECT COUNT(*) as count FROM files WHERE {PENDING_FILTER}"
    )

    # Get tags for this file
    tags = await db.fetch_all(
        conn,
        """SELECT t.name, t.type FROM file_tags ft
           JOIN tags t ON ft.tag_id = t.id
           WHERE ft.file_id = ?""",
        (row["id"],),
    )

    return {
        "file": row,
        "tags": tags,
        "remaining": count_row["count"] if count_row else 0,
    }


# --- Folder-level actions (must be before /{file_id} routes) ---


@router.post("/folder/skip")
async def skip_folder(request: Request):
    """Skip all pending files in a folder."""
    conn = request.app.state.db
    form = await request.form()
    folder = form.get("folder", "")
    if not folder:
        raise HTTPException(400, "Missing folder parameter")

    cursor = await conn.execute(
        "UPDATE files SET skipped_at = datetime('now') WHERE status = 'pending' AND skipped_at IS NULL AND source_path LIKE ?",
        (folder + "/%",),
    )
    await conn.commit()

    return {"status": "skipped", "count": cursor.rowcount}


@router.post("/folder/accept")
async def accept_folder(request: Request):
    """Accept all pending files in a folder using their metadata-derived defaults. [MQ-7]"""
    conn = request.app.state.db
    config = request.app.state.config_holder.config
    form = await request.form()
    folder = form.get("folder", "")
    if not folder:
        raise HTTPException(400, "Missing folder parameter")

    rows = await db.fetch_all(
        conn,
        f"SELECT * FROM files WHERE {PENDING_FILTER} AND source_path LIKE ? ORDER BY source_path",
        (folder + "/%",),
    )

    accepted = 0
    for row in rows:
        file = File.from_row(row)

        # Compute defaults
        input_path = ""
        for inp in config.inputs:
            if file.source_path.startswith(str(inp.path)):
                input_path = str(inp.path)
                break
        field_defaults = defaults_from_source(file.source_path, file.root, input_path)

        # Build tags from defaults
        tag_fields = ("event", "name", "artist", "album", "year", "track", "author", "title", "show", "season", "series")
        tags: dict[str, list[str]] = {}
        for field in tag_fields:
            value = field_defaults.get(field, "")
            if value:
                tags[field] = [value]
                tag_name = f"{field}:{value}"
                existing = await db.fetch_one(conn, "SELECT id FROM tags WHERE name = ?", (tag_name,))
                if existing:
                    tag_id = existing["id"]
                else:
                    cursor = await conn.execute(
                        "INSERT INTO tags (name, type) VALUES (?, ?)", (tag_name, field),
                    )
                    tag_id = cursor.lastrowid
                await conn.execute(
                    "INSERT OR IGNORE INTO file_tags (file_id, tag_id) VALUES (?, ?)",
                    (file.id, tag_id),
                )

        # Derive output path
        creation_date = file.creation_date.date() if file.creation_date else None
        original_filename = Path(file.source_path).name
        relative_path = derive_path(file.root, tags, original_filename, creation_date)
        output_path = config.output / relative_path
        output_path = _resolve_collision(output_path)

        # Move file
        source = Path(file.source_path)
        if not source.exists():
            continue

        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(output_path))

        await conn.execute(
            """UPDATE files SET status = 'managed', managed_path = ?, managed_date = datetime('now')
               WHERE id = ?""",
            (str(output_path), file.id),
        )

        await log_action(conn, ActionVerb.ACCEPT, file.id, {
            "source_path": file.source_path,
            "destination_path": str(output_path),
            "bulk": True,
            "folder": folder,
        })
        accepted += 1

    await conn.commit()
    return {"status": "accepted", "count": accepted}


@router.post("/folder/reject")
async def reject_folder(request: Request):
    """Reject all pending files in a folder."""
    conn = request.app.state.db
    form = await request.form()
    folder = form.get("folder", "")
    if not folder:
        raise HTTPException(400, "Missing folder parameter")

    rows = await db.fetch_all(
        conn,
        "SELECT id, source_path FROM files WHERE status = 'pending' AND source_path LIKE ?",
        (folder + "/%",),
    )

    for row in rows:
        await log_action(conn, ActionVerb.REJECT, row["id"], {
            "source_path": row["source_path"],
            "bulk": True,
            "folder": folder,
        })

    await conn.execute(
        "DELETE FROM files WHERE status = 'pending' AND source_path LIKE ?",
        (folder + "/%",),
    )
    await conn.commit()

    return {"status": "rejected", "count": len(rows)}


# --- Per-file actions ---


@router.post("/{file_id}/accept")
async def accept_file(file_id: int, request: Request):
    """Accept a file: save form tags, derive path, move to output, update status."""
    conn = request.app.state.db
    config = request.app.state.config_holder.config

    row = await db.fetch_one(conn, "SELECT * FROM files WHERE id = ?", (file_id,))
    if row is None:
        raise HTTPException(404, "File not found")
    if row["status"] != FileStatus.PENDING:
        raise HTTPException(400, f"File is not pending (status: {row['status']})")

    file = File.from_row(row)

    # Get form data (tag field values from the UI)
    form = await request.form()

    # Compute defaults from source path
    input_path = ""
    for inp in config.inputs:
        if file.source_path.startswith(str(inp.path)):
            input_path = str(inp.path)
            break
    field_defaults = defaults_from_source(file.source_path, file.root, input_path)

    # Build tags: form values override defaults
    tag_fields = ("event", "name", "artist", "album", "year", "track", "author", "title", "show", "season", "series")
    tags: dict[str, list[str]] = {}
    for field in tag_fields:
        value = form.get(field, "").strip() if field in form else ""
        if not value:
            value = field_defaults.get(field, "")
        if value:
            tags[field] = [value]
            # Persist the tag to the database
            tag_name = f"{field}:{value}"
            existing = await db.fetch_one(conn, "SELECT id FROM tags WHERE name = ?", (tag_name,))
            if existing:
                tag_id = existing["id"]
            else:
                cursor = await conn.execute(
                    "INSERT INTO tags (name, type) VALUES (?, ?)",
                    (tag_name, field),
                )
                tag_id = cursor.lastrowid
            await conn.execute(
                "INSERT OR IGNORE INTO file_tags (file_id, tag_id) VALUES (?, ?)",
                (file_id, tag_id),
            )

    await conn.commit()

    # Derive output path
    creation_date = file.creation_date.date() if file.creation_date else None
    original_filename = Path(file.source_path).name
    relative_path = derive_path(file.root, tags, original_filename, creation_date)
    output_path = config.output / relative_path

    # Handle collisions
    output_path = _resolve_collision(output_path)

    # Move file
    source = Path(file.source_path)
    if not source.exists():
        raise HTTPException(400, "Source file no longer exists")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(output_path))

    # Update database
    await conn.execute(
        """UPDATE files SET status = 'managed', managed_path = ?, managed_date = datetime('now')
           WHERE id = ?""",
        (str(output_path), file_id),
    )
    await conn.commit()

    await log_action(conn, ActionVerb.ACCEPT, file_id, {
        "source_path": file.source_path,
        "destination_path": str(output_path),
    })

    return {"status": "accepted", "path": str(output_path)}


@router.post("/{file_id}/reject")
async def reject_file(file_id: int, request: Request):
    """Reject a file: remove from queue, leave original untouched."""
    conn = request.app.state.db

    row = await db.fetch_one(conn, "SELECT * FROM files WHERE id = ?", (file_id,))
    if row is None:
        raise HTTPException(404, "File not found")

    await log_action(conn, ActionVerb.REJECT, file_id, {
        "source_path": row["source_path"],
    })

    await conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
    await conn.commit()

    return {"status": "rejected"}


@router.post("/{file_id}/skip")
async def skip_file(file_id: int, request: Request):
    """Skip a file: mark as skipped so it doesn't appear in the queue."""
    conn = request.app.state.db

    row = await db.fetch_one(conn, "SELECT * FROM files WHERE id = ?", (file_id,))
    if row is None:
        raise HTTPException(404, "File not found")

    await conn.execute(
        "UPDATE files SET skipped_at = datetime('now') WHERE id = ?", (file_id,)
    )
    await conn.commit()

    return {"status": "skipped"}


def _resolve_collision(path: Path) -> Path:
    """If path exists, append numeric suffix (-1, -2, etc.)."""
    if not path.exists():
        return path

    stem = path.stem
    ext = path.suffix
    parent = path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}-{counter}{ext}"
        if not candidate.exists():
            return candidate
        counter += 1
