"""Pinpoint entry point — start server and discovery."""

from __future__ import annotations

import argparse
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from pinpoint import database
from pinpoint.analysis.worker import run_analysis
from pinpoint.api import files, queue, tags
from pinpoint.config import ConfigHolder, load_config
from pinpoint.discovery import DiscoveryStatus, scan_input
from pinpoint.monitoring import verify_managed_files, watch_output
from pinpoint.web import routes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("pinpoint")


def basename_filter(value: str) -> str:
    """Jinja2 filter to extract filename from a path."""
    return Path(value).name if value else ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    config_holder = app.state.config_holder
    config = config_holder.config

    logger.info("Config loaded: %d input(s), output=%s", len(config.inputs), config.output)
    for inp in config.inputs:
        logger.info("  input: %s (root=%s)", inp.path, inp.root)

    # Initialize database
    logger.info("Opening database at %s", config.db_path)
    db = await database.connect(config.db_path)
    await database.init_schema(db)
    app.state.db = db
    logger.info("Database ready")

    # Ensure output directory exists
    config.output.mkdir(parents=True, exist_ok=True)

    # Dedicated pool for discovery (walk + hash). Needs 2 threads: one for
    # the directory walk and one for per-file I/O (hashing, metadata).
    discovery_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="discovery")
    app.state.discovery_executor = discovery_executor

    discovery_status = DiscoveryStatus()
    app.state.discovery_status = discovery_status

    async def run_discovery():
        # Yield control so uvicorn can finish binding and start serving
        await asyncio.sleep(0)
        logger.info("Starting background discovery...")
        discovery_status.running = True
        for inp in config.inputs:
            logger.info("Scanning: %s (root=%s)", inp.path, inp.root)
            try:
                count = await scan_input(db, inp.path, inp.root, discovery_executor, discovery_status)
                discovery_status.done_inputs.append(str(inp.path))
                if count > 0:
                    logger.info("Discovery complete: %d new files from %s", count, inp.path)
                else:
                    logger.info("Discovery complete: no new files in %s", inp.path)
            except Exception:
                logger.exception("Discovery failed for %s", inp.path)
        discovery_status.running = False
        discovery_status.current_input = ""
        logger.info("All discovery tasks complete")

    discovery_task = asyncio.create_task(run_discovery())

    # Start analysis worker (processes files after discovery finds them)
    analysis_task = None
    if config.analysis.enabled:
        async def run_analysis_worker():
            # Let discovery get a head start
            await asyncio.sleep(2)
            logger.info("Starting background analysis worker...")
            try:
                await run_analysis(db, config.analysis)
            except asyncio.CancelledError:
                logger.info("Analysis worker stopped")
            except Exception:
                logger.exception("Analysis worker crashed")

        analysis_task = asyncio.create_task(run_analysis_worker())

    # Verify managed files exist at expected paths [OM periodic]
    await verify_managed_files(db)

    # Start output directory watcher [OM-1 through OM-7]
    watcher_task = asyncio.create_task(watch_output(db, config.output))

    yield

    # Shutdown
    watcher_task.cancel()
    if analysis_task:
        analysis_task.cancel()
    discovery_task.cancel()
    await db.close()


def create_app(config_path: Path | None = None) -> FastAPI:
    """Create the FastAPI application."""
    config = load_config(config_path)
    config_holder = ConfigHolder(config)

    app = FastAPI(title="Pinpoint", lifespan=lifespan)
    app.state.config_holder = config_holder

    # Mount static files
    static_dir = Path(__file__).parent / "web" / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Register routers
    app.include_router(queue.router)
    app.include_router(tags.router)
    app.include_router(files.router)
    app.include_router(routes.router)

    # Register Jinja2 filters
    routes.templates.env.filters["basename"] = basename_filter

    return app


def main():
    parser = argparse.ArgumentParser(description="Pinpoint — tag-based file organizer")
    parser.add_argument("--config", "-c", type=Path, help="Config file path")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8420, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    app = create_app(args.config)
    app.state.host = args.host
    app.state.port = args.port

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
