import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse

from pinpoint.api.routes import router


def create_app(db, config_holder) -> FastAPI:
    app = FastAPI(title="Pinpoint", version="0.2.0")

    app.state.db = db
    app.state.config_holder = config_holder

    static_dir = Path(__file__).parent.parent.parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(router)

    @app.get("/preview/{file_id}")
    async def preview(file_id: int):
        file = await db.execute_one("SELECT * FROM files WHERE id = ?", (file_id,))
        if not file:
            return HTMLResponse("Not found", status_code=404)

        file_path = file["output_path"]
        if not file_path or not os.path.exists(file_path):
            return HTMLResponse("File not found on disk", status_code=404)

        return FileResponse(file_path)

    @app.get("/{path:path}")
    async def spa_fallback(path: str):
        index = static_dir / "index.html"
        return FileResponse(str(index))

    return app
