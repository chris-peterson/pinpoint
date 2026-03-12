import argparse
import asyncio
from pathlib import Path

import uvicorn

from pinpoint.config import ConfigHolder
from pinpoint.database import init_db
from pinpoint.discovery import run_discovery
from pinpoint.app import create_app


async def main():
    parser = argparse.ArgumentParser(description="Pinpoint — tag-based file organizer")
    parser.add_argument("--config", default="config.yaml", help="Path to config YAML")
    parser.add_argument("--port", type=int, default=8420)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    holder = ConfigHolder(config_path)
    holder.load()

    db = await init_db(holder.config["data_dir"])

    await run_discovery(db, holder.config)

    app = create_app(db, holder)

    config = uvicorn.Config(app, host="0.0.0.0", port=args.port, log_level="info")
    server = uvicorn.Server(config)

    async def periodic_discovery():
        while True:
            await asyncio.sleep(10)
            try:
                await run_discovery(db, holder.config)
            except Exception as e:
                print(f"Discovery error: {e}")

    discovery_task = asyncio.create_task(periodic_discovery())
    try:
        await server.serve()
    finally:
        discovery_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
