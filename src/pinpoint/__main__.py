import argparse
import asyncio
from pathlib import Path

import uvicorn

from pinpoint.config import ConfigHolder, ensure_library_layout
from pinpoint.database import init_db
from pinpoint.discovery import run_discovery, watch_inputs
from pinpoint.app import create_app


async def main():
    parser = argparse.ArgumentParser(description="Pinpoint v0.2 — tag-based file organizer")
    parser.add_argument("--config", default="config.yaml", help="Path to config YAML")
    parser.add_argument("--port", type=int, default=8420)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    holder = ConfigHolder(config_path)
    holder.load()

    ensure_library_layout(holder.config)
    print(f"Library: {holder.config['library']}")

    db = await init_db(holder.config["data_dir"])

    await run_discovery(db, holder.config)

    app = create_app(db, holder)

    config = uvicorn.Config(app, host="0.0.0.0", port=args.port, log_level="info")
    server = uvicorn.Server(config)

    async def config_reload_loop():
        """Periodically check for config file changes."""
        try:
            while True:
                await asyncio.sleep(10)
                holder.check_reload()
        except asyncio.CancelledError:
            pass

    watcher_task = asyncio.create_task(watch_inputs(db, holder.config))
    reload_task = asyncio.create_task(config_reload_loop())

    try:
        await server.serve()
    finally:
        watcher_task.cancel()
        reload_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
