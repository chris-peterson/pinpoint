"""Web routes — HTML pages rendered with Jinja2."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates

from pinpoint import database as db
from pinpoint.analysis.suggestions import suggestions_as_defaults
from pinpoint.defaults import defaults_from_source_split, extract_audio_metadata
from pinpoint.models import File, ROOT_FIELDS
from pinpoint.paths import derive_path

router = APIRouter(tags=["web"])

templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# How to group managed files into folder cards per root
_FOLDER_GROUPING: dict[str, list[str]] = {
    "memories": ["event"],
    "music": ["artist", "album"],
    "books": ["author"],
    "podcasts": ["show"],
    "tv": ["show", "season"],
    "movies": ["series"],
    "comedy": ["artist"],
}


@router.get("/")
async def home_page(request: Request, q: str = "", root: str = "", file_class: str = ""):
    """Home page — search, browse folder cards, On This Day."""
    conn = request.app.state.db

    # Stats
    pending_row = await db.fetch_one(
        conn, "SELECT COUNT(*) as count FROM files WHERE status = 'pending' AND skipped_at IS NULL"
    )
    managed_row = await db.fetch_one(
        conn, "SELECT COUNT(*) as count FROM files WHERE status = 'managed'"
    )
    missing_row = await db.fetch_one(
        conn, "SELECT COUNT(*) as count FROM files WHERE status = 'missing'"
    )
    pending_count = pending_row["count"] if pending_row else 0
    managed_count = managed_row["count"] if managed_row else 0
    missing_count = missing_row["count"] if missing_row else 0

    # Available roots/classes for filter dropdowns
    root_rows = await db.fetch_all(
        conn,
        "SELECT DISTINCT root, COUNT(*) as cnt FROM files WHERE status = 'managed' GROUP BY root ORDER BY root",
    )
    class_rows = await db.fetch_all(
        conn,
        "SELECT DISTINCT file_class, COUNT(*) as cnt FROM files WHERE status = 'managed' GROUP BY file_class ORDER BY file_class",
    )

    # Search
    results = []
    if q:
        like_q = f"%{q}%"
        results = await db.fetch_all(
            conn,
            """SELECT f.id, f.managed_path, f.source_path, f.root, f.file_class,
                      f.status, f.favorite,
                      GROUP_CONCAT(t.name, ', ') as tag_list
               FROM files f
               LEFT JOIN file_tags ft ON f.id = ft.file_id
               LEFT JOIN tags t ON ft.tag_id = t.id
               WHERE f.status IN ('managed', 'drifted')
                 AND (f.managed_path LIKE ? OR f.source_path LIKE ? OR t.name LIKE ?)
               GROUP BY f.id
               ORDER BY f.favorite DESC, f.managed_date DESC
               LIMIT 50""",
            (like_q, like_q, like_q),
        )

    # Folder cards (browse mode, no search query)
    folders: list[dict] = []
    if not q:
        browse_filter = "status = 'managed'"
        browse_params: list = []
        if root:
            browse_filter += " AND root = ?"
            browse_params.append(root)
        if file_class:
            browse_filter += " AND file_class = ?"
            browse_params.append(file_class)

        managed_files = await db.fetch_all(
            conn,
            f"""SELECT f.id, f.managed_path, f.root, f.file_class, f.favorite,
                       GROUP_CONCAT(t.name, ', ') as tag_list
                FROM files f
                LEFT JOIN file_tags ft ON f.id = ft.file_id
                LEFT JOIN tags t ON ft.tag_id = t.id
                WHERE {browse_filter}
                GROUP BY f.id
                ORDER BY f.managed_date DESC""",
            tuple(browse_params),
        )

        config = request.app.state.config_holder.config
        output_prefix = str(config.output)
        seen_folders: dict[str, dict] = {}

        for row in managed_files:
            managed = row["managed_path"] or ""
            file_root = row["root"]
            grouping_keys = _FOLDER_GROUPING.get(file_root, [])

            # Strip output prefix for display
            if managed.startswith(output_prefix):
                relative = managed[len(output_prefix):].lstrip("/")
            else:
                relative = managed
            parts = relative.split("/")

            # Determine folder depth from grouping keys (+1 for root dir)
            depth = len(grouping_keys) + 1  # e.g. music/artist/album = 3
            folder_parts = parts[:depth] if len(parts) > depth else parts[:-1]
            folder_key = "/".join(folder_parts) if folder_parts else file_root

            if folder_key not in seen_folders:
                seen_folders[folder_key] = {
                    "key": folder_key,
                    "label": folder_parts[-1] if folder_parts else file_root,
                    "root": file_root,
                    "count": 0,
                    "hero_id": None,
                    "has_images": False,
                }
            card = seen_folders[folder_key]
            card["count"] += 1

            # Pick hero image (first image file in folder)
            if not card["hero_id"] and row["file_class"] == "image":
                card["hero_id"] = row["id"]
                card["has_images"] = True

        folders = sorted(seen_folders.values(), key=lambda c: c["key"])

    # On This Day — memories from today's month+day in previous years
    today = date.today()
    on_this_day = []
    otd_rows = await db.fetch_all(
        conn,
        """SELECT id, managed_path, file_class, creation_date
           FROM files
           WHERE status = 'managed' AND root = 'memories'
             AND strftime('%m-%d', creation_date) = ?
           ORDER BY creation_date ASC
           LIMIT 20""",
        (today.strftime("%m-%d"),),
    )
    for row in otd_rows:
        cd = row["creation_date"] or ""
        year = cd[:4] if len(cd) >= 4 else "?"
        on_this_day.append({
            "id": row["id"],
            "file_class": row["file_class"],
            "year": year,
            "path": row["managed_path"] or "",
        })

    return templates.TemplateResponse("home.html", {
        "request": request,
        "q": q,
        "results": results,
        "pending_count": pending_count,
        "managed_count": managed_count,
        "missing_count": missing_count,
        "folders": folders,
        "on_this_day": on_this_day,
        "filter_root": root,
        "filter_class": file_class,
        "available_roots": root_rows,
        "available_classes": class_rows,
    })


@router.get("/queue")
async def queue_page(request: Request, root: str = "", file_class: str = ""):
    """Queue page — review and tag pending files."""
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
    filename_defaults: dict[str, str] = {}
    metadata_defaults: dict[str, str] = {}
    ai_defaults: dict[str, str] = {}
    analysis_status = None

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

        # Load AI suggestions as defaults (middle priority: filename < AI < metadata)
        ai_defaults = await suggestions_as_defaults(conn, row["id"])
        analysis_status = file_data.analysis_status

        # Merge: filename < AI < metadata (metadata wins)
        field_defaults = {**filename_defaults, **ai_defaults, **metadata_defaults}

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
        "ai_defaults": ai_defaults,
        "analysis_status": analysis_status,
        "source_folder": source_folder,
        "folder_count": folder_count,
        "folder_ready": folder_ready,
        "filter_root": root,
        "filter_class": file_class,
        "filter_qs": filter_qs,
        "available_roots": root_rows,
        "available_classes": class_rows,
        "pending_count": remaining,
        "discovery": request.app.state.discovery_status,
        "root_fields": ROOT_FIELDS.get(file_data.root if file_data else "", []),
    })


@router.get("/api/search")
async def search_api(request: Request, q: str = ""):
    """Live search — returns HTML fragment for HTMX swap."""
    conn = request.app.state.db

    if len(q) < 2:
        return templates.TemplateResponse("_search_results.html", {
            "request": request, "results": [], "q": q,
        })

    like_q = f"%{q}%"
    results = await db.fetch_all(
        conn,
        """SELECT f.id, f.managed_path, f.source_path, f.root, f.file_class,
                  f.status, f.favorite,
                  GROUP_CONCAT(t.name, ', ') as tag_list
           FROM files f
           LEFT JOIN file_tags ft ON f.id = ft.file_id
           LEFT JOIN tags t ON ft.tag_id = t.id
           WHERE f.status IN ('managed', 'drifted')
             AND (f.managed_path LIKE ? OR f.source_path LIKE ? OR t.name LIKE ?)
           GROUP BY f.id
           ORDER BY f.favorite DESC, f.managed_date DESC
           LIMIT 50""",
        (like_q, like_q, like_q),
    )

    return templates.TemplateResponse("_search_results.html", {
        "request": request, "results": results, "q": q,
    })


@router.get("/browse/{folder_path:path}")
async def browse_folder(folder_path: str, request: Request):
    """Browse a specific folder — shows files in that managed folder."""
    conn = request.app.state.db
    config = request.app.state.config_holder.config
    output_prefix = str(config.output)

    # Find files whose managed_path starts with this folder
    search_prefix = str(config.output / folder_path) + "/"
    rows = await db.fetch_all(
        conn,
        """SELECT f.id, f.managed_path, f.file_class, f.favorite, f.root,
                  GROUP_CONCAT(t.name, ', ') as tag_list
           FROM files f
           LEFT JOIN file_tags ft ON f.id = ft.file_id
           LEFT JOIN tags t ON ft.tag_id = t.id
           WHERE f.status = 'managed' AND f.managed_path LIKE ?
           GROUP BY f.id
           ORDER BY f.managed_path ASC""",
        (search_prefix + "%",),
    )

    # Separate into direct children and subfolders
    files = []
    subfolders: dict[str, dict] = {}
    for row in rows:
        managed = row["managed_path"] or ""
        if managed.startswith(output_prefix):
            relative = managed[len(output_prefix):].lstrip("/")
        else:
            relative = managed

        # Path relative to the browsed folder
        if relative.startswith(folder_path + "/"):
            inner = relative[len(folder_path) + 1:]
        else:
            inner = relative

        parts = inner.split("/")
        if len(parts) == 1:
            # Direct child file
            files.append({
                "id": row["id"],
                "name": parts[0],
                "file_class": row["file_class"],
                "favorite": row["favorite"],
                "tag_list": row["tag_list"] or "",
            })
        else:
            # In a subfolder
            subfolder_name = parts[0]
            subfolder_key = folder_path + "/" + subfolder_name
            if subfolder_name not in subfolders:
                subfolders[subfolder_name] = {
                    "name": subfolder_name,
                    "key": subfolder_key,
                    "count": 0,
                    "hero_id": None,
                }
            subfolders[subfolder_name]["count"] += 1
            if not subfolders[subfolder_name]["hero_id"] and row["file_class"] == "image":
                subfolders[subfolder_name]["hero_id"] = row["id"]

    pending_row = await db.fetch_one(
        conn, "SELECT COUNT(*) as count FROM files WHERE status = 'pending' AND skipped_at IS NULL"
    )
    pending_count = pending_row["count"] if pending_row else 0

    # Breadcrumb parts
    breadcrumbs = []
    accumulated = ""
    for part in folder_path.split("/"):
        accumulated = accumulated + "/" + part if accumulated else part
        breadcrumbs.append({"label": part, "path": accumulated})

    return templates.TemplateResponse("browse.html", {
        "request": request,
        "folder_path": folder_path,
        "folder_name": folder_path.split("/")[-1],
        "breadcrumbs": breadcrumbs,
        "files": files,
        "subfolders": sorted(subfolders.values(), key=lambda s: s["name"]),
        "pending_count": pending_count,
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

    pending_row = await db.fetch_one(
        conn, "SELECT COUNT(*) as count FROM files WHERE status = 'pending' AND skipped_at IS NULL"
    )
    pending_count = pending_row["count"] if pending_row else 0

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
        "pending_count": pending_count,
    })


@router.get("/file/{file_id}")
async def file_detail_page(file_id: int, request: Request):
    """File detail page — preview and tag editor for a managed file."""
    conn = request.app.state.db

    row = await db.fetch_one(conn, "SELECT * FROM files WHERE id = ?", (file_id,))
    if row is None:
        raise HTTPException(404, "File not found")

    file_data = File.from_row(row)

    tags = await db.fetch_all(
        conn,
        """SELECT t.name, t.type FROM file_tags ft
           JOIN tags t ON ft.tag_id = t.id
           WHERE ft.file_id = ?
           ORDER BY t.type, t.name""",
        (file_id,),
    )

    # Extract current values for root-specific fields
    root_fields = ROOT_FIELDS.get(file_data.root, [])
    field_ids = {field_id for field_id, _ in root_fields}
    tag_values: dict[str, str] = {}
    extra_tags = []
    for tag in tags:
        tag_type = tag["type"]
        tag_name = tag["name"]
        prefix = f"{tag_type}:"
        value = tag_name[len(prefix):] if tag_name.startswith(prefix) else tag_name
        if tag_type in field_ids:
            tag_values[tag_type] = value
        else:
            extra_tags.append(tag)

    pending_row = await db.fetch_one(
        conn, "SELECT COUNT(*) as count FROM files WHERE status = 'pending' AND skipped_at IS NULL"
    )
    pending_count = pending_row["count"] if pending_row else 0

    return templates.TemplateResponse("file_detail.html", {
        "request": request,
        "file": file_data,
        "tags": tags,
        "extra_tags": extra_tags,
        "tag_values": tag_values,
        "root_fields": root_fields,
        "pending_count": pending_count,
    })
