"""Web routes — HTML pages rendered with Jinja2."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from pinpoint import database as db
from pinpoint.defaults import defaults_from_source, defaults_from_source_split, extract_audio_metadata
from pinpoint.models import File
from pinpoint.paths import derive_path

router = APIRouter(tags=["web"])

templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@router.get("/")
async def queue_page(request: Request, root: str = "", file_class: str = ""):
    """Main queue page — the default landing page."""
    conn = request.app.state.db

    # Build filter clause
    base = "status = 'pending' AND skipped_at IS NULL"
    params: list = []
    if root:
        base += " AND root = ?"
        params.append(root)
    if file_class:
        base += " AND file_class = ?"
        params.append(file_class)

    row = await db.fetch_one(
        conn,
        f"""SELECT * FROM files WHERE {base}
           ORDER BY discovery_date DESC
           LIMIT 1""",
        tuple(params),
    )

    count_row = await db.fetch_one(
        conn, f"SELECT COUNT(*) as count FROM files WHERE {base}",
        tuple(params),
    )
    remaining = count_row["count"] if count_row else 0

    # Get available roots and classes for filter dropdowns
    root_rows = await db.fetch_all(
        conn,
        "SELECT DISTINCT root, COUNT(*) as cnt FROM files WHERE status = 'pending' AND skipped_at IS NULL GROUP BY root ORDER BY root",
    )
    class_rows = await db.fetch_all(
        conn,
        "SELECT DISTINCT file_class, COUNT(*) as cnt FROM files WHERE status = 'pending' AND skipped_at IS NULL GROUP BY file_class ORDER BY file_class",
    )

    file_data = None
    tags_list = []
    preview_path = ""
    field_defaults: dict[str, str] = {}

    if row:
        file_data = File.from_row(row)
        config = request.app.state.config_holder.config

        tags_list = await db.fetch_all(
            conn,
            """SELECT t.name, t.type FROM file_tags ft
               JOIN tags t ON ft.tag_id = t.id
               WHERE ft.file_id = ?""",
            (row["id"],),
        )

        # Derive defaults from source path (split for UI source selector)
        input_path = ""
        for inp in config.inputs:
            if file_data.source_path.startswith(str(inp.path)):
                input_path = str(inp.path)
                break
        filename_defaults, metadata_defaults = defaults_from_source_split(
            file_data.source_path, file_data.root, input_path,
        )
        field_defaults = {**filename_defaults, **metadata_defaults}

        # Compute initial path preview using defaults
        tags: dict[str, list[str]] = {}
        for tr in tags_list:
            tag_type = tr["type"]
            tag_name = tr["name"]
            prefix = f"{tag_type}:"
            value = tag_name[len(prefix):] if tag_name.startswith(prefix) else tag_name
            tags.setdefault(tag_type, []).append(value)

        # Merge defaults for path preview (explicit tags override defaults)
        preview_tags = {k: [v] for k, v in field_defaults.items()}
        preview_tags.update(tags)

        creation_date = file_data.creation_date.date() if file_data.creation_date else None
        original_filename = Path(file_data.source_path).name
        relative = derive_path(file_data.root, preview_tags, original_filename, creation_date)
        preview_path = str(config.output / relative)

    # Compute source folder for "skip/reject/accept folder" actions
    source_folder = ""
    folder_count = 0
    folder_ready = False
    if file_data:
        source_folder = str(Path(file_data.source_path).parent)
        folder_rows = await db.fetch_all(
            conn,
            "SELECT id, source_path FROM files WHERE status = 'pending' AND skipped_at IS NULL AND source_path LIKE ?",
            (source_folder + "/%",),
        )
        folder_count = len(folder_rows)

        # [MQ-7] Check if all files in folder have stable metadata for accept-all
        if folder_count > 1 and file_data.root in ("music", "books", "podcasts", "comedy"):
            all_ready = True
            for fr in folder_rows:
                meta = extract_audio_metadata(fr["source_path"])
                # Require at minimum artist and name (or compilation artist)
                if not meta.get("artist") or (not meta.get("name") and meta.get("artist") != "Various Artists"):
                    all_ready = False
                    break
            folder_ready = all_ready

    # Build query string for filter persistence across actions
    filter_qs = ""
    if root or file_class:
        parts = []
        if root:
            parts.append(f"root={root}")
        if file_class:
            parts.append(f"file_class={file_class}")
        filter_qs = "?" + "&".join(parts)

    return templates.TemplateResponse("queue.html", {
        "request": request,
        "file": file_data,
        "tags": tags_list,
        "preview_path": preview_path,
        "remaining": remaining,
        "defaults": field_defaults,
        "filename_defaults": filename_defaults,
        "metadata_defaults": metadata_defaults,
        "source_folder": source_folder,
        "folder_count": folder_count,
        "folder_ready": folder_ready,
        "filter_root": root,
        "filter_class": file_class,
        "filter_qs": filter_qs,
        "available_roots": root_rows,
        "available_classes": class_rows,
        "discovery": request.app.state.discovery_status,
    })


@router.get("/library")
async def library_page(request: Request):
    """Library page — tree view of managed files."""
    conn = request.app.state.db

    rows = await db.fetch_all(
        conn,
        """SELECT id, managed_path, file_class, favorite
           FROM files WHERE status = 'managed'
           ORDER BY managed_path ASC""",
    )

    config = request.app.state.config_holder.config
    output_prefix = str(config.output)

    # Build a nested tree from managed paths
    tree: dict = {}
    for row in rows:
        managed = row["managed_path"] or ""
        # Strip output prefix for display
        if managed.startswith(output_prefix):
            relative = managed[len(output_prefix):].lstrip("/")
        else:
            relative = managed
        parts = relative.split("/") if relative else [managed]

        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        # Leaf node: store file info
        filename = parts[-1] if parts else managed
        node[filename] = {
            "_file": True,
            "id": row["id"],
            "class": row["file_class"],
            "favorite": row["favorite"],
        }

    return templates.TemplateResponse("library.html", {
        "request": request,
        "tree": tree,
        "file_count": len(rows),
    })
