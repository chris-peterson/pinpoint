"""File API — serve file content for previews."""

from __future__ import annotations

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
