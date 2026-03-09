"""Tag API — add/remove tags, autocomplete, path preview."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from pinpoint import database as db
from pinpoint.actions import log_action
from pinpoint.defaults import defaults_from_source
from pinpoint.models import ActionVerb, File, ROOT_FIELDS
from pinpoint.paths import derive_path
from pinpoint.tag_writer import write_tags

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tags", tags=["tags"])


class TagInput(BaseModel):
    name: str  # full tag name, e.g. "event:hawaii-vacation"


def parse_tag_type(name: str) -> str:
    """Extract tag type from a tag name. General tags have type 'general'."""
    known_types = {
        "root", "event", "name", "person", "artist",
        "author", "album", "show", "season", "series",
        "track", "episode", "year",
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
    from pinpoint.models import ALL_TAG_FIELDS
    for key in ALL_TAG_FIELDS:
        if key in params and params[key]:
            merged[key] = [params[key]]
        elif key in params and not params[key]:
            merged.pop(key, None)

    creation_date = file.creation_date.date() if file.creation_date else None
    original_filename = Path(file.source_path).name
    relative_path = derive_path(file.root, merged, original_filename, creation_date)

    return {"path": str(config.output / relative_path)}


@router.get("/files/{file_id}/html", response_class=HTMLResponse)
async def tags_html(file_id: int, request: Request, exclude_fields: bool = False):
    """Return tag chips as an HTML fragment for htmx swapping."""
    conn = request.app.state.db
    rows = await db.fetch_all(
        conn,
        """SELECT t.name, t.type FROM file_tags ft
           JOIN tags t ON ft.tag_id = t.id
           WHERE ft.file_id = ?
           ORDER BY t.type, t.name""",
        (file_id,),
    )

    # When exclude_fields=true, skip tags that are shown as root-specific fields
    if exclude_fields:
        file_row = await db.fetch_one(conn, "SELECT root FROM files WHERE id = ?", (file_id,))
        field_ids = {fid for fid, _ in ROOT_FIELDS.get(file_row["root"], [])} if file_row else set()
        rows = [r for r in rows if r["type"] not in field_ids]

    chips = []
    for row in rows:
        name = row["name"]
        chips.append(
            f'<span class="tag-chip">{name}'
            f'<a href="#" class="tag-remove" onclick="removeTag({file_id}, \'{name}\'); return false;"'
            f' title="Remove">&times;</a></span>'
        )
    return " ".join(chips) if chips else '<span class="tag-chip empty">No additional tags</span>'


@router.put("/files/{file_id}")
async def save_tags(file_id: int, request: Request):
    """Save root-specific tag fields for a managed file. Relocates if path changes. [TP-5]"""
    conn = request.app.state.db
    config = request.app.state.config_holder.config

    row = await db.fetch_one(conn, "SELECT * FROM files WHERE id = ?", (file_id,))
    if row is None:
        raise HTTPException(404, "File not found")

    file = File.from_row(row)
    form = await request.form()

    root_fields = ROOT_FIELDS.get(file.root, [])
    field_ids = {fid for fid, _ in root_fields}

    # Remove old field-based tags for this file
    old_field_tags = await db.fetch_all(
        conn,
        """SELECT t.id, t.name, t.type FROM file_tags ft
           JOIN tags t ON ft.tag_id = t.id
           WHERE ft.file_id = ? AND t.type IN ({})""".format(
            ",".join("?" for _ in field_ids)
        ),
        (file_id, *field_ids),
    )
    for tag_row in old_field_tags:
        await conn.execute(
            "DELETE FROM file_tags WHERE file_id = ? AND tag_id = ?",
            (file_id, tag_row["id"]),
        )

    # Insert new field-based tags from form
    tags: dict[str, list[str]] = {}
    for field_id, _ in root_fields:
        value = form.get(field_id, "").strip() if field_id in form else ""
        if not value:
            continue
        tags[field_id] = [value]
        tag_name = f"{field_id}:{value}"
        existing = await db.fetch_one(conn, "SELECT id FROM tags WHERE name = ?", (tag_name,))
        if existing:
            tag_id = existing["id"]
        else:
            tag_id = await db.execute(
                conn,
                "INSERT INTO tags (name, type) VALUES (?, ?)",
                (tag_name, field_id),
            )
        await conn.execute(
            "INSERT OR IGNORE INTO file_tags (file_id, tag_id) VALUES (?, ?)",
            (file_id, tag_id),
        )

    # Also include non-field tags for path derivation
    other_tags = await db.fetch_all(
        conn,
        """SELECT t.name, t.type FROM file_tags ft
           JOIN tags t ON ft.tag_id = t.id
           WHERE ft.file_id = ? AND t.type NOT IN ({})""".format(
            ",".join("?" for _ in field_ids)
        ),
        (file_id, *field_ids),
    )
    for tr in other_tags:
        tag_type = tr["type"]
        tag_name = tr["name"]
        prefix = f"{tag_type}:"
        value = tag_name[len(prefix):] if tag_name.startswith(prefix) else tag_name
        tags.setdefault(tag_type, []).append(value)

    await conn.commit()

    # Derive new path
    creation_date = file.creation_date.date() if file.creation_date else None
    original_filename = Path(file.source_path).name
    relative_path = derive_path(file.root, tags, original_filename, creation_date)
    new_path = config.output / relative_path

    old_path = file.managed_path
    relocated = False

    if old_path and str(new_path) != old_path and Path(old_path).exists():
        # Write updated tags to file metadata [TP-5]
        flat_tags = {k: v[0] for k, v in tags.items() if v}
        metadata_writes = write_tags(Path(old_path), flat_tags, file.root, file.file_class)
        if metadata_writes:
            await log_action(conn, ActionVerb.TAG_WRITE, file_id, {
                "writes": [{"field": f, "value": v, "target": t} for f, v, t in metadata_writes],
            })

        # Relocate
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(old_path, str(new_path))

        await conn.execute(
            "UPDATE files SET managed_path = ? WHERE id = ?",
            (str(new_path), file_id),
        )
        await conn.commit()

        await log_action(conn, ActionVerb.RELOCATE, file_id, {
            "old_path": old_path,
            "new_path": str(new_path),
        })
        relocated = True
        logger.info("Relocated %s -> %s", old_path, new_path)

    return {"status": "saved", "path": str(new_path), "relocated": relocated}
