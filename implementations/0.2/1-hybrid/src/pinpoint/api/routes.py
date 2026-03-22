import json
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Request

from pinpoint.defaults import defaults_from_source, compute_file_confidence
from pinpoint.models import ALL_TAG_FIELDS, MULTI_VALUE_FIELDS, DERIVED_ATTRIBUTES, EXPECTED_TAGS, ROOT_FIELDS
from pinpoint.paths import derive_path

router = APIRouter(prefix="/api")



async def _persist_tags(db, file_id: int, tags: dict, source: str = "manual"):
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
                conf = 1.0 if source == "manual" else 0.5
                await db.execute_write(
                    "INSERT OR REPLACE INTO file_tags (file_id, tag_id, source, confidence) VALUES (?, ?, ?, ?)",
                    (file_id, row[0], source, conf),
                )


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

    original_filename = Path(file["output_path"]).name
    path = derive_path(file["root"], tags, original_filename)
    return {"path": path}


@router.get("/files/{file_id}")
async def get_file_detail(file_id: int, request: Request):
    db = request.app.state.db
    file = await db.execute_one("SELECT * FROM files WHERE id = ?", (file_id,))
    if not file:
        return {"error": "Not found"}, 404

    tags = await db.execute(
        """SELECT t.id, t.name, t.type, ft.source, ft.confidence
           FROM tags t
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

    await _persist_tags(db, file_id, tags, source="manual")

    sources = {f: "manual" for f in tags}
    confidence = compute_file_confidence(tags, sources, file["root"])
    await db.execute_write(
        "UPDATE files SET confidence = ? WHERE id = ?", (confidence, file_id)
    )

    if file["status"] == "imported" and file["output_path"]:
        original_filename = Path(file["output_path"]).name
        root = file["root"]

        cd = file["creation_date"]
        if cd:
            tags["month"] = [cd[:7]]
            tags["year"] = [cd[:4]]

        rel_path = derive_path(root, tags, original_filename)
        new_full = os.path.join(config["library"], rel_path)

        if new_full != file["output_path"]:
            os.makedirs(os.path.dirname(new_full), exist_ok=True)
            try:
                shutil.move(file["output_path"], new_full)
                old_dir = os.path.dirname(file["output_path"])
                while old_dir != config["library"]:
                    if os.path.isdir(old_dir) and not os.listdir(old_dir):
                        os.rmdir(old_dir)
                        old_dir = os.path.dirname(old_dir)
                    else:
                        break
                await db.execute_write(
                    "UPDATE files SET output_path = ? WHERE id = ?", (new_full, file_id)
                )
                await db.log_action("relocate", file_id, {
                    "old_path": file["output_path"],
                    "new_path": new_full,
                })
            except Exception as e:
                return {"error": f"Relocate failed: {e}"}

    return {"ok": True}


@router.get("/review")
async def get_review(request: Request):
    db = request.app.state.db

    root_filter = request.query_params.get("root", "")
    class_filter = request.query_params.get("file_class", "")
    max_confidence = request.query_params.get("max_confidence", "")

    where = "f.status = 'imported'"
    params = []
    if root_filter:
        where += " AND f.root = ?"
        params.append(root_filter)
    if class_filter:
        where += " AND f.file_class = ?"
        params.append(class_filter)
    if max_confidence:
        where += " AND f.confidence <= ?"
        params.append(float(max_confidence))

    rows = await db.execute(
        f"""SELECT f.*, GROUP_CONCAT(t.name, ', ') as tag_list
            FROM files f
            LEFT JOIN file_tags ft ON f.id = ft.file_id
            LEFT JOIN tags t ON ft.tag_id = t.id
            WHERE {where}
            GROUP BY f.id
            ORDER BY f.confidence ASC, f.imported_at DESC
            LIMIT 200""",
        tuple(params),
    )

    total_analyzing = (await db.execute_one(
        "SELECT COUNT(*) as count FROM files WHERE status = 'analyzing'"
    ))["count"]
    total_imported = (await db.execute_one(
        "SELECT COUNT(*) as count FROM files WHERE status = 'imported'"
    ))["count"]
    needs_review = (await db.execute_one(
        "SELECT COUNT(*) as count FROM files WHERE status = 'imported' AND confidence < 0.7"
    ))["count"]

    root_counts = await db.execute(
        "SELECT root, COUNT(*) as cnt FROM files WHERE status = 'imported' GROUP BY root"
    )
    class_counts = await db.execute(
        "SELECT file_class, COUNT(*) as cnt FROM files WHERE status = 'imported' GROUP BY file_class"
    )

    return {
        "files": [dict(r) for r in rows],
        "totalAnalyzing": total_analyzing,
        "totalImported": total_imported,
        "needsReview": needs_review,
        "rootCounts": [dict(r) for r in root_counts],
        "classCounts": [dict(r) for r in class_counts],
        "filterRoot": root_filter,
        "filterClass": class_filter,
    }


@router.get("/whats-new")
async def whats_new(request: Request):
    db = request.app.state.db

    rows = await db.execute(
        """SELECT f.*, GROUP_CONCAT(t.name, ', ') as tag_list
           FROM files f
           LEFT JOIN file_tags ft ON f.id = ft.file_id
           LEFT JOIN tags t ON ft.tag_id = t.id
           WHERE f.status = 'imported'
           GROUP BY f.id
           ORDER BY f.imported_at DESC
           LIMIT 100"""
    )

    return {"files": [dict(r) for r in rows]}


@router.get("/missing")
async def get_missing(request: Request):
    db = request.app.state.db

    rows = await db.execute(
        """SELECT f.*, GROUP_CONCAT(t.name, ', ') as tag_list
           FROM files f
           LEFT JOIN file_tags ft ON f.id = ft.file_id
           LEFT JOIN tags t ON ft.tag_id = t.id
           WHERE f.status = 'missing'
           GROUP BY f.id
           ORDER BY f.imported_at DESC"""
    )

    return {"files": [dict(r) for r in rows]}


@router.post("/missing/{file_id}/dismiss")
async def dismiss_missing(file_id: int, request: Request):
    db = request.app.state.db
    await db.execute_write("DELETE FROM file_tags WHERE file_id = ?", (file_id,))
    await db.execute_write("DELETE FROM suggestions WHERE file_id = ?", (file_id,))
    await db.execute_write("DELETE FROM files WHERE id = ? AND status = 'missing'", (file_id,))
    return {"ok": True}


@router.post("/missing/dismiss-all")
async def dismiss_all_missing(request: Request):
    db = request.app.state.db
    missing_ids = await db.execute("SELECT id FROM files WHERE status = 'missing'")
    for row in missing_ids:
        fid = row["id"]
        await db.execute_write("DELETE FROM file_tags WHERE file_id = ?", (fid,))
        await db.execute_write("DELETE FROM suggestions WHERE file_id = ?", (fid,))
    await db.execute_write("DELETE FROM files WHERE status = 'missing'")
    return {"ok": True, "dismissed": len(missing_ids)}


@router.post("/files/{file_id}/bulk-tags")
async def bulk_tag(file_id: int, request: Request):
    return await update_tags(file_id, request)


@router.get("/library")
async def get_library(request: Request):
    db = request.app.state.db

    root_filter = request.query_params.get("root", "")
    class_filter = request.query_params.get("file_class", "")

    where = "f.status = 'imported'"
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
            ORDER BY f.favorite DESC, f.imported_at DESC
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
        """SELECT f.id, f.output_path, f.root, f.file_class,
                  f.status, f.favorite, f.confidence,
                  GROUP_CONCAT(t.name, ', ') as tag_list
           FROM files f
           LEFT JOIN file_tags ft ON f.id = ft.file_id
           LEFT JOIN tags t ON ft.tag_id = t.id
           WHERE f.status IN ('imported', 'drifted')
             AND (f.output_path LIKE ? OR t.name LIKE ?)
           GROUP BY f.id
           ORDER BY f.favorite DESC, f.imported_at DESC
           LIMIT 50""",
        (like_q, like_q),
    )

    return {"results": [dict(r) for r in results]}


@router.get("/browse")
async def browse(request: Request):
    db = request.app.state.db
    config = request.app.state.config_holder.config
    folder_path = request.query_params.get("path", "")
    library_prefix = config["library"]

    if folder_path:
        search_prefix = os.path.join(library_prefix, folder_path) + "/"
    else:
        search_prefix = library_prefix.rstrip("/") + "/"
    rows = await db.execute(
        """SELECT f.id, f.output_path, f.file_class, f.favorite, f.root, f.confidence,
                  GROUP_CONCAT(t.name, ', ') as tag_list
           FROM files f
           LEFT JOIN file_tags ft ON f.id = ft.file_id
           LEFT JOIN tags t ON ft.tag_id = t.id
           WHERE f.status = 'imported' AND f.output_path LIKE ?
           GROUP BY f.id
           ORDER BY f.output_path ASC""",
        (search_prefix + "%",),
    )

    files = []
    subfolders = {}

    for row in rows:
        output = row["output_path"] or ""
        relative = output
        if output.startswith(library_prefix):
            relative = output[len(library_prefix):].lstrip("/")

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
                "confidence": row["confidence"],
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

    analyzing = (await db.execute_one(
        "SELECT COUNT(*) as count FROM files WHERE status = 'analyzing'"
    ))["count"]
    imported = (await db.execute_one(
        "SELECT COUNT(*) as count FROM files WHERE status = 'imported'"
    ))["count"]
    missing = (await db.execute_one(
        "SELECT COUNT(*) as count FROM files WHERE status = 'missing'"
    ))["count"]
    needs_review = (await db.execute_one(
        "SELECT COUNT(*) as count FROM files WHERE status = 'imported' AND confidence < 0.7"
    ))["count"]

    root_counts = await db.execute(
        "SELECT root, COUNT(*) as cnt FROM files WHERE status = 'imported' GROUP BY root ORDER BY root"
    )
    class_counts = await db.execute(
        "SELECT file_class, COUNT(*) as cnt FROM files WHERE status = 'imported' GROUP BY file_class ORDER BY file_class"
    )

    from datetime import datetime
    now = datetime.now()
    month_day = f"{now.month:02d}-{now.day:02d}"
    on_this_day = await db.execute(
        """SELECT id, output_path, file_class, creation_date
           FROM files
           WHERE status = 'imported' AND root = 'memory'
             AND substr(creation_date, 6, 5) = ?
           ORDER BY creation_date ASC
           LIMIT 20""",
        (month_day,),
    )

    return {
        "analyzingCount": analyzing,
        "importedCount": imported,
        "missingCount": missing,
        "needsReviewCount": needs_review,
        "rootCounts": [dict(r) for r in root_counts],
        "classCounts": [dict(r) for r in class_counts],
        "onThisDay": [
            {
                "id": r["id"],
                "fileClass": r["file_class"],
                "year": r["creation_date"][:4] if r["creation_date"] else "?",
                "path": r["output_path"] or "",
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
