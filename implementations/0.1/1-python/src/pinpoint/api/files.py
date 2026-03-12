"""File API — serve file content for previews."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from pinpoint import database as db

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/{file_id}/content")
async def serve_file(file_id: int, request: Request):
    """Serve a file's content for preview."""
    conn = request.app.state.db

    row = await db.fetch_one(conn, "SELECT * FROM files WHERE id = ?", (file_id,))
    if row is None:
        raise HTTPException(404, "File not found")

    # Use managed path if available, otherwise source path
    file_path = row["managed_path"] or row["source_path"]
    path = Path(file_path)

    if not path.exists():
        raise HTTPException(404, "File not found on disk")

    return FileResponse(path)


@router.post("/{file_id}/reveal")
async def reveal_file(file_id: int, request: Request):
    """Reveal a file in Finder (macOS) or file manager."""
    conn = request.app.state.db

    row = await db.fetch_one(conn, "SELECT * FROM files WHERE id = ?", (file_id,))
    if row is None:
        raise HTTPException(404, "File not found")

    file_path = row["managed_path"] or row["source_path"]
    path = Path(file_path)

    if not path.exists():
        raise HTTPException(404, "File not found on disk")

    _reveal_path(path)
    return {"ok": True}


@router.post("/reveal-folder")
async def reveal_folder(request: Request):
    """Reveal a managed folder in Finder. Path must be under the output directory."""
    form = await request.form()
    folder = str(form.get("path", ""))
    if not folder:
        raise HTTPException(400, "Missing path")

    config = request.app.state.config_holder.config
    output_dir = Path(config.output).resolve()
    target = (output_dir / folder).resolve()

    # Ensure path is within output directory
    if not str(target).startswith(str(output_dir)):
        raise HTTPException(403, "Path outside output directory")
    if not target.exists():
        raise HTTPException(404, "Folder not found on disk")

    _reveal_path(target)
    return {"ok": True}


def _reveal_path(path: Path) -> None:
    """Open a file or folder in the system file manager."""
    if sys.platform == "darwin":
        if path.is_dir():
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["open", "-R", str(path)])
    elif sys.platform == "linux":
        subprocess.Popen(["xdg-open", str(path.parent if path.is_file() else path)])
