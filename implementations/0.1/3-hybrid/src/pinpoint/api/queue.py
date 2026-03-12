import json
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Request

from pinpoint.defaults import defaults_from_source
from pinpoint.models import ALL_TAG_FIELDS, MULTI_VALUE_FIELDS, DERIVED_ATTRIBUTES, EXPECTED_TAGS
from pinpoint.paths import derive_path, resolve_collision

router = APIRouter(prefix="/api")


def _find_input_path(config: dict, source_path: str) -> str:
    for inp in config.get("inputs", []):
        if source_path.startswith(inp["path"]):
            return inp["path"]
    return ""


async def _persist_tags(db, file_id: int, tags: dict):
    for field, values in tags.items():
        if DERIVED_ATTRIBUTES and field in DERIVED_ATTRIBUTES:
            continue
        for val in values:
            tag_name = f"{field}:{val}"
            await db.execute_write(
                "INSERT OR IGNORE INTO tags (name, type) VALUES (?, ?)", (tag_name, field)
            )
            row = await db.execute_one("SELECT id FROM tags WHERE name = ?", (tag_name,))
            if row:
                await db.execute_write(
                    "INSERT OR IGNORE INTO file_tags (file_id, tag_id) VALUES (?, ?)",
                    (file_id, row[0]),
                )


@router.post("/files/{file_id}/accept")
async def accept_file(file_id: int, request: Request):
    db = request.app.state.db
    config = request.app.state.config_holder.config

    file = await db.execute_one(
        "SELECT * FROM files WHERE id = ? AND status = 'pending'", (file_id,)
    )
    if not file:
        return {"error": "File not found or not pending"}, 404

    source_path = file["source_path"]
    root = file["root"]
    input_path = _find_input_path(config, source_path)

    defs = await defaults_from_source(source_path, root, input_path)
    field_defaults = defs["merged"]

    body = await request.json()

    tags = {}
    for field in ALL_TAG_FIELDS:
        if field in MULTI_VALUE_FIELDS:
            values = body.get(field, [])
            if isinstance(values, str):
                values = [values] if values.strip() else []
            values = [v.strip() for v in values if v.strip()]
            if not values and field_defaults.get(field):
                values = [field_defaults[field]]
            if values:
                tags[field] = values
        else:
            value = body.get(field, "").strip() if isinstance(body.get(field), str) else ""
            if not value:
                value = field_defaults.get(field, "")
            if value:
                tags[field] = [value]

    await _persist_tags(db, file_id, tags)

    original_filename = Path(source_path).name
    rel_path = derive_path(root, tags, original_filename)
    full_path = os.path.join(config["output"], rel_path)

    async def _resolve(p):
        candidate = p
        counter = 1
        base = Path(p)
        while True:
            existing = await db.execute_one(
                "SELECT id FROM files WHERE managed_path = ?", (candidate,)
            )
            if not existing and not Path(candidate).exists():
                return candidate
            candidate = str(base.parent / f"{base.stem}-{counter}{base.suffix}")
            counter += 1

    final_path = await _resolve(full_path)

    os.makedirs(os.path.dirname(final_path), exist_ok=True)
    try:
        shutil.move(source_path, final_path)
    except Exception as e:
        return {"error": f"Move failed: {e}"}

    await db.execute_write(
        "UPDATE files SET status = 'managed', managed_path = ?, managed_date = datetime('now') WHERE id = ?",
        (final_path, file_id),
    )
    await db.log_action("accept", file_id, {
        "source_path": source_path,
        "destination_path": final_path,
    })

    return {"ok": True, "path": final_path}


@router.post("/files/{file_id}/reject")
async def reject_file(file_id: int, request: Request):
    db = request.app.state.db

    file = await db.execute_one(
        "SELECT * FROM files WHERE id = ? AND status = 'pending'", (file_id,)
    )
    if not file:
        return {"error": "Not found"}, 404

    await db.execute_write("DELETE FROM file_tags WHERE file_id = ?", (file_id,))
    await db.execute_write("DELETE FROM suggestions WHERE file_id = ?", (file_id,))
    await db.execute_write("DELETE FROM actions WHERE file_id = ?", (file_id,))
    await db.execute_write("DELETE FROM files WHERE id = ?", (file_id,))
    await db.log_action("reject", None, {"source_path": file["source_path"], "file_id": file_id})

    return {"ok": True}


@router.post("/files/{file_id}/skip")
async def skip_file(file_id: int, request: Request):
    db = request.app.state.db
    await db.execute_write(
        "UPDATE files SET skipped_at = datetime('now') WHERE id = ? AND status = 'pending'",
        (file_id,),
    )
    await db.log_action("discover", file_id, {"action": "skip"})
    return {"ok": True}


@router.post("/files/{file_id}/favorite")
async def toggle_favorite(file_id: int, request: Request):
    db = request.app.state.db
    file = await db.execute_one("SELECT favorite FROM files WHERE id = ?", (file_id,))
    if not file:
        return {"error": "Not found"}, 404

    new_val = 0 if file["favorite"] else 1
    await db.execute_write("UPDATE files SET favorite = ? WHERE id = ?", (new_val, file_id))
    verb = "favorite" if new_val else "unfavorite"
    await db.log_action(verb, file_id, {})
    return {"ok": True, "favorite": bool(new_val)}


@router.post("/files/{file_id}/preview-path")
async def preview_path(file_id: int, request: Request):
    db = request.app.state.db
    file = await db.execute_one("SELECT * FROM files WHERE id = ?", (file_id,))
    if not file:
        return {"error": "Not found"}, 404

    body = await request.json()
    tags = {}
    for field, val in body.items():
        if isinstance(val, str) and val.strip():
            tags[field] = [val.strip()]

    original_filename = Path(file["source_path"]).name
    path = derive_path(file["root"], tags, original_filename)
    return {"path": path}


@router.post("/folder/accept")
async def accept_folder(request: Request):
    db = request.app.state.db
    config = request.app.state.config_holder.config
    body = await request.json()
    folder = body.get("folder")
    if not folder:
        return {"error": "folder is required"}, 400

    rows = await db.execute(
        "SELECT * FROM files WHERE source_path LIKE ? AND status = 'pending' AND skipped_at IS NULL",
        (folder + "/%",),
    )

    if not rows:
        return {"ok": True, "accepted": 0}

    accepted = 0
    errors = []

    for file in rows:
        source_path = file["source_path"]
        root = file["root"]
        input_path = _find_input_path(config, source_path)

        defs = await defaults_from_source(source_path, root, input_path)
        field_defaults = defs["merged"]

        tags = {}
        for field in ALL_TAG_FIELDS:
            value = field_defaults.get(field, "")
            if value:
                tags[field] = [value]
                if field not in DERIVED_ATTRIBUTES:
                    tag_name = f"{field}:{value}"
                    await db.execute_write(
                        "INSERT OR IGNORE INTO tags (name, type) VALUES (?, ?)", (tag_name, field)
                    )
                    tag_row = await db.execute_one("SELECT id FROM tags WHERE name = ?", (tag_name,))
                    if tag_row:
                        await db.execute_write(
                            "INSERT OR IGNORE INTO file_tags (file_id, tag_id) VALUES (?, ?)",
                            (file["id"], tag_row[0]),
                        )

        original_filename = Path(source_path).name
        rel_path = derive_path(root, tags, original_filename)
        full_path = os.path.join(config["output"], rel_path)

        candidate = full_path
        counter = 1
        base = Path(full_path)
        while True:
            existing = await db.execute_one(
                "SELECT id FROM files WHERE managed_path = ?", (candidate,)
            )
            if not existing and not Path(candidate).exists():
                break
            candidate = str(base.parent / f"{base.stem}-{counter}{base.suffix}")
            counter += 1

        os.makedirs(os.path.dirname(candidate), exist_ok=True)
        try:
            shutil.move(source_path, candidate)
            await db.execute_write(
                "UPDATE files SET status = 'managed', managed_path = ?, managed_date = datetime('now') WHERE id = ?",
                (candidate, file["id"]),
            )
            await db.log_action("accept", file["id"], {
                "source_path": source_path,
                "destination_path": candidate,
                "batch": True,
            })
            accepted += 1
        except Exception as e:
            errors.append({"file": source_path, "error": str(e)})

    return {"ok": True, "accepted": accepted, "errors": errors}


@router.get("/files/{file_id}")
async def get_file_detail(file_id: int, request: Request):
    db = request.app.state.db
    file = await db.execute_one("SELECT * FROM files WHERE id = ?", (file_id,))
    if not file:
        return {"error": "Not found"}, 404

    tags = await db.execute(
        """SELECT t.id, t.name, t.type FROM tags t
           JOIN file_tags ft ON t.id = ft.tag_id
           WHERE ft.file_id = ?""",
        (file_id,),
    )

    actions = await db.execute(
        "SELECT * FROM actions WHERE file_id = ? ORDER BY timestamp DESC LIMIT 20",
        (file_id,),
    )

    return {
        "file": dict(file),
        "tags": [dict(t) for t in tags],
        "actions": [dict(a) for a in actions],
    }


@router.post("/files/{file_id}/tags")
async def update_tags(file_id: int, request: Request):
    db = request.app.state.db
    config = request.app.state.config_holder.config

    file = await db.execute_one("SELECT * FROM files WHERE id = ?", (file_id,))
    if not file:
        return {"error": "Not found"}, 404

    body = await request.json()

    await db.execute_write("DELETE FROM file_tags WHERE file_id = ?", (file_id,))

    tags = {}
    for field, val in body.items():
        if field not in ALL_TAG_FIELDS:
            continue
        if field in MULTI_VALUE_FIELDS:
            values = val if isinstance(val, list) else [val]
            values = [v.strip() for v in values if v.strip()]
            if values:
                tags[field] = values
        else:
            v = val.strip() if isinstance(val, str) else str(val)
            if v:
                tags[field] = [v]

    await _persist_tags(db, file_id, tags)

    if file["status"] == "managed" and file["managed_path"]:
        original_filename = Path(file["managed_path"]).name
        root = file["root"]
        rel_path = derive_path(root, tags, original_filename)
        new_full = os.path.join(config["output"], rel_path)

        if new_full != file["managed_path"]:
            os.makedirs(os.path.dirname(new_full), exist_ok=True)
            try:
                shutil.move(file["managed_path"], new_full)
                old_dir = os.path.dirname(file["managed_path"])
                while old_dir != config["output"]:
                    if os.path.isdir(old_dir) and not os.listdir(old_dir):
                        os.rmdir(old_dir)
                        old_dir = os.path.dirname(old_dir)
                    else:
                        break
                await db.execute_write(
                    "UPDATE files SET managed_path = ? WHERE id = ?", (new_full, file_id)
                )
                await db.log_action("relocate", file_id, {
                    "old_path": file["managed_path"],
                    "new_path": new_full,
                })
            except Exception as e:
                return {"error": f"Relocate failed: {e}"}

    return {"ok": True}


@router.get("/queue")
async def get_queue(request: Request):
    db = request.app.state.db
    config = request.app.state.config_holder.config

    root_filter = request.query_params.get("root", "")
    class_filter = request.query_params.get("file_class", "")

    where = "status = 'pending' AND skipped_at IS NULL"
    params = []
    if root_filter:
        where += " AND root = ?"
        params.append(root_filter)
    if class_filter:
        where += " AND file_class = ?"
        params.append(class_filter)

    file = await db.execute_one(
        f"SELECT * FROM files WHERE {where} ORDER BY discovery_date DESC LIMIT 1",
        tuple(params),
    )

    total_pending = (await db.execute_one(
        "SELECT COUNT(*) as count FROM files WHERE status = 'pending' AND skipped_at IS NULL"
    ))["count"]

    root_counts = await db.execute(
        "SELECT root, COUNT(*) as cnt FROM files WHERE status = 'pending' AND skipped_at IS NULL GROUP BY root"
    )
    class_counts = await db.execute(
        "SELECT file_class, COUNT(*) as cnt FROM files WHERE status = 'pending' AND skipped_at IS NULL GROUP BY file_class"
    )

    result = {
        "totalPending": total_pending,
        "rootCounts": [dict(r) for r in root_counts],
        "classCounts": [dict(r) for r in class_counts],
        "filterRoot": root_filter,
        "filterClass": class_filter,
        "file": None,
    }

    if file:
        file_dict = dict(file)
        root = file_dict["root"]
        source_path = file_dict["source_path"]
        input_path = _find_input_path(config, source_path)

        from pinpoint.models import ROOT_FIELDS
        root_fields = ROOT_FIELDS.get(root, [])
        expected_tags = EXPECTED_TAGS.get(root, [])

        defs = await defaults_from_source(source_path, root, input_path)

        tags = {}
        for field, val in defs["merged"].items():
            if val:
                tags[field] = [val]
        original_filename = Path(source_path).name
        path_preview = derive_path(root, tags, original_filename)

        src_dir = str(Path(source_path).parent)
        folder_files = await db.execute(
            "SELECT id, source_path, root FROM files WHERE source_path LIKE ? AND status = 'pending' AND skipped_at IS NULL",
            (src_dir + "/%",),
        )
        folder_count = len(folder_files)

        folder_ready = False
        if folder_count > 1:
            folder_ready = True
            for ff in folder_files:
                ff_input = _find_input_path(config, ff["source_path"])
                ff_defs = await defaults_from_source(ff["source_path"], ff["root"], ff_input)
                ff_expected = EXPECTED_TAGS.get(ff["root"], [])
                for tag in ff_expected:
                    if not ff_defs["merged"].get(tag):
                        folder_ready = False
                        break
                if not folder_ready:
                    break

        result["file"] = file_dict
        result["rootFields"] = root_fields
        result["expectedTags"] = expected_tags
        result["fieldDefaults"] = defs["merged"]
        result["filenameDefs"] = defs["filename_defs"]
        result["metadataDefs"] = defs["metadata_defs"]
        result["pathPreview"] = path_preview
        result["sourceFolder"] = src_dir
        result["folderCount"] = folder_count
        result["folderReady"] = folder_ready
        result["multiValueFields"] = list(MULTI_VALUE_FIELDS)

    return result


@router.get("/library")
async def get_library(request: Request):
    db = request.app.state.db

    root_filter = request.query_params.get("root", "")
    class_filter = request.query_params.get("file_class", "")

    where = "f.status = 'managed'"
    params = []
    if root_filter:
        where += " AND f.root = ?"
        params.append(root_filter)
    if class_filter:
        where += " AND f.file_class = ?"
        params.append(class_filter)

    rows = await db.execute(
        f"""SELECT f.*, GROUP_CONCAT(t.name, ', ') as tag_list
            FROM files f
            LEFT JOIN file_tags ft ON f.id = ft.file_id
            LEFT JOIN tags t ON ft.tag_id = t.id
            WHERE {where}
            GROUP BY f.id
            ORDER BY f.favorite DESC, f.managed_date DESC
            LIMIT 200""",
        tuple(params),
    )

    return {"files": [dict(r) for r in rows]}


@router.get("/search")
async def search(request: Request):
    db = request.app.state.db
    q = request.query_params.get("q", "")
    if len(q) < 2:
        return {"results": []}

    like_q = f"%{q}%"
    results = await db.execute(
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

    return {"results": [dict(r) for r in results]}


@router.get("/browse")
async def browse(request: Request):
    db = request.app.state.db
    config = request.app.state.config_holder.config
    folder_path = request.query_params.get("path", "")
    output_prefix = config["output"]

    search_prefix = os.path.join(output_prefix, folder_path) + "/"
    rows = await db.execute(
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

    files = []
    subfolders = {}

    for row in rows:
        managed = row["managed_path"] or ""
        relative = managed
        if managed.startswith(output_prefix):
            relative = managed[len(output_prefix):].lstrip("/")

        inner = relative
        if relative.startswith(folder_path + "/"):
            inner = relative[len(folder_path) + 1:]

        parts = inner.split("/")
        if len(parts) == 1:
            files.append({
                "id": row["id"],
                "name": parts[0],
                "fileClass": row["file_class"],
                "favorite": row["favorite"],
                "tagList": row["tag_list"] or "",
            })
        else:
            sub_name = parts[0]
            sub_key = folder_path + "/" + sub_name if folder_path else sub_name
            if sub_name not in subfolders:
                subfolders[sub_name] = {
                    "name": sub_name,
                    "key": sub_key,
                    "count": 0,
                    "heroId": None,
                }
            sub = subfolders[sub_name]
            sub["count"] += 1
            if not sub["heroId"] and row["file_class"] == "image":
                sub["heroId"] = row["id"]

    breadcrumbs = []
    accumulated = ""
    for part in folder_path.split("/"):
        if not part:
            continue
        accumulated = accumulated + "/" + part if accumulated else part
        breadcrumbs.append({"label": part, "path": accumulated})

    return {
        "folderPath": folder_path,
        "folderName": folder_path.split("/")[-1] if folder_path else "",
        "breadcrumbs": breadcrumbs,
        "files": files,
        "subfolders": sorted(subfolders.values(), key=lambda s: s["name"]),
    }


@router.get("/stats")
async def stats(request: Request):
    db = request.app.state.db

    pending = (await db.execute_one(
        "SELECT COUNT(*) as count FROM files WHERE status = 'pending' AND skipped_at IS NULL"
    ))["count"]
    managed = (await db.execute_one(
        "SELECT COUNT(*) as count FROM files WHERE status = 'managed'"
    ))["count"]
    missing = (await db.execute_one(
        "SELECT COUNT(*) as count FROM files WHERE status = 'missing'"
    ))["count"]

    root_counts = await db.execute(
        "SELECT root, COUNT(*) as cnt FROM files WHERE status = 'managed' GROUP BY root ORDER BY root"
    )
    class_counts = await db.execute(
        "SELECT file_class, COUNT(*) as cnt FROM files WHERE status = 'managed' GROUP BY file_class ORDER BY file_class"
    )

    from datetime import datetime
    now = datetime.now()
    month_day = f"{now.month:02d}-{now.day:02d}"
    on_this_day = await db.execute(
        """SELECT id, managed_path, file_class, creation_date
           FROM files
           WHERE status = 'managed' AND root = 'memory'
             AND substr(creation_date, 6, 5) = ?
           ORDER BY creation_date ASC
           LIMIT 20""",
        (month_day,),
    )

    return {
        "pendingCount": pending,
        "managedCount": managed,
        "missingCount": missing,
        "rootCounts": [dict(r) for r in root_counts],
        "classCounts": [dict(r) for r in class_counts],
        "onThisDay": [
            {
                "id": r["id"],
                "fileClass": r["file_class"],
                "year": r["creation_date"][:4] if r["creation_date"] else "?",
                "path": r["managed_path"] or "",
            }
            for r in on_this_day
        ],
    }


@router.get("/tags/autocomplete")
async def autocomplete(request: Request):
    db = request.app.state.db
    q = request.query_params.get("q", "")
    if len(q) < 1:
        return {"tags": []}

    rows = await db.execute(
        "SELECT name, type FROM tags WHERE name LIKE ? LIMIT 20",
        (f"%{q}%",),
    )
    return {"tags": [dict(r) for r in rows]}
