"""Tag API — add/remove tags, autocomplete, path preview."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from pinpoint import database as db
from pinpoint.actions import log_action
from pinpoint.defaults import defaults_from_source
from pinpoint.models import ActionVerb, File
from pinpoint.paths import derive_path

router = APIRouter(prefix="/api/tags", tags=["tags"])


class TagInput(BaseModel):
    name: str  # full tag name, e.g. "event:hawaii-vacation"


def parse_tag_type(name: str) -> str:
    """Extract tag type from a tag name. General tags have type 'general'."""
    known_types = {
        "root", "class", "event", "name", "person", "artist",
        "author", "album", "title", "show", "season", "series",
    }
    if ":" in name:
        prefix = name.split(":")[0]
        if prefix in known_types:
            return prefix
    return "general"


@router.post("/files/{file_id}")
async def add_tag(file_id: int, tag_input: TagInput, request: Request):
    """Add a tag to a file."""
    conn = request.app.state.db

    row = await db.fetch_one(conn, "SELECT id FROM files WHERE id = ?", (file_id,))
    if row is None:
        raise HTTPException(404, "File not found")

    tag_type = parse_tag_type(tag_input.name)

    # Upsert tag into dictionary
    existing = await db.fetch_one(conn, "SELECT id FROM tags WHERE name = ?", (tag_input.name,))
    if existing:
        tag_id = existing["id"]
    else:
        tag_id = await db.execute(
            conn,
            "INSERT INTO tags (name, type) VALUES (?, ?)",
            (tag_input.name, tag_type),
        )

    # Link to file (ignore if already linked)
    await conn.execute(
        "INSERT OR IGNORE INTO file_tags (file_id, tag_id) VALUES (?, ?)",
        (file_id, tag_id),
    )
    await conn.commit()

    await log_action(conn, ActionVerb.TAG_ADD, file_id, {"tag": tag_input.name})

    return {"status": "added", "tag_id": tag_id}


@router.delete("/files/{file_id}/{tag_name:path}")
async def remove_tag(file_id: int, tag_name: str, request: Request):
    """Remove a tag from a file."""
    conn = request.app.state.db

    tag_row = await db.fetch_one(conn, "SELECT id FROM tags WHERE name = ?", (tag_name,))
    if tag_row is None:
        raise HTTPException(404, "Tag not found")

    await conn.execute(
        "DELETE FROM file_tags WHERE file_id = ? AND tag_id = ?",
        (file_id, tag_row["id"]),
    )
    await conn.commit()

    await log_action(conn, ActionVerb.TAG_REMOVE, file_id, {"tag": tag_name})

    return {"status": "removed"}


@router.get("/autocomplete")
async def autocomplete(request: Request, q: str = "", type: str = ""):
    """Autocomplete tag names."""
    conn = request.app.state.db

    if type:
        rows = await db.fetch_all(
            conn,
            "SELECT name FROM tags WHERE type = ? AND name LIKE ? LIMIT 20",
            (type, f"%{q}%"),
        )
    else:
        rows = await db.fetch_all(
            conn,
            "SELECT name FROM tags WHERE name LIKE ? LIMIT 20",
            (f"%{q}%",),
        )

    return [row["name"] for row in rows]


@router.get("/preview-path/{file_id}")
async def preview_path(file_id: int, request: Request, **kwargs):
    """Compute the output path preview for a file with its current tags.

    Accepts additional query params as temporary tag overrides for live preview.
    """
    conn = request.app.state.db
    config = request.app.state.config_holder.config

    row = await db.fetch_one(conn, "SELECT * FROM files WHERE id = ?", (file_id,))
    if row is None:
        raise HTTPException(404, "File not found")

    file = File.from_row(row)

    # Get current tags
    tag_rows = await db.fetch_all(
        conn,
        """SELECT t.name, t.type FROM file_tags ft
           JOIN tags t ON ft.tag_id = t.id
           WHERE ft.file_id = ?""",
        (file_id,),
    )

    tags: dict[str, list[str]] = {}
    for tr in tag_rows:
        tag_type = tr["type"]
        tag_name = tr["name"]
        prefix = f"{tag_type}:"
        value = tag_name[len(prefix):] if tag_name.startswith(prefix) else tag_name
        tags.setdefault(tag_type, []).append(value)

    # Compute defaults from source path
    input_path = ""
    for inp in config.inputs:
        if file.source_path.startswith(str(inp.path)):
            input_path = str(inp.path)
            break
    field_defaults = defaults_from_source(file.source_path, file.root, input_path)

    # Start with defaults, then layer DB tags, then query param overrides
    merged: dict[str, list[str]] = {k: [v] for k, v in field_defaults.items()}
    merged.update(tags)

    params = dict(request.query_params)
    for key in ("event", "name", "artist", "album", "year", "author", "title", "show", "season", "series"):
        if key in params and params[key]:
            merged[key] = [params[key]]
        elif key in params and not params[key]:
            merged.pop(key, None)

    creation_date = file.creation_date.date() if file.creation_date else None
    original_filename = Path(file.source_path).name
    relative_path = derive_path(file.root, merged, original_filename, creation_date)

    return {"path": str(config.output / relative_path)}
