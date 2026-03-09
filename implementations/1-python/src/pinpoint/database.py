"""SQLite database connection and query helpers."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

import aiosqlite


async def connect(db_path: Path) -> aiosqlite.Connection:
    """Open a database connection with WAL mode and foreign keys."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(db_path))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_schema(db: aiosqlite.Connection) -> None:
    """Create tables if they don't exist."""
    schema_sql = importlib.resources.files("pinpoint").joinpath("schema.sql").read_text()
    # Execute each statement separately (executescript has issues with aiosqlite + PRAGMAs)
    for statement in schema_sql.split(";"):
        statement = statement.strip()
        if statement:
            await db.execute(statement)
    await db.commit()

    # Apply migrations for existing databases
    await _migrate(db)


async def _migrate(db: aiosqlite.Connection) -> None:
    """Apply incremental migrations to existing databases."""
    # Migration 1: actions.file_id needs ON DELETE SET NULL (was bare FK).
    # SQLite can't ALTER FK constraints, so recreate the table if needed.
    # Check if we need to recreate by looking at the FK definition
    cursor = await db.execute("SELECT sql FROM sqlite_master WHERE name = 'actions' AND type = 'table'")
    row = await cursor.fetchone()
    if row and "ON DELETE SET NULL" not in row[0]:
        await db.execute("ALTER TABLE actions RENAME TO _actions_old")
        await db.execute("""
            CREATE TABLE actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                verb TEXT NOT NULL,
                file_id INTEGER REFERENCES files(id) ON DELETE SET NULL,
                detail TEXT
            )
        """)
        await db.execute("INSERT INTO actions SELECT * FROM _actions_old")
        await db.execute("DROP TABLE _actions_old")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_actions_file ON actions(file_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_actions_verb ON actions(verb)")
        await db.commit()

    # Migration 2: files.skipped_at column for persistent skip tracking.
    cursor = await db.execute("PRAGMA table_info(files)")
    col_names = {row[1] for row in await cursor.fetchall()}
    if "skipped_at" not in col_names:
        await db.execute("ALTER TABLE files ADD COLUMN skipped_at TEXT")
        await db.commit()


async def fetch_one(db: aiosqlite.Connection, query: str, params: tuple = ()) -> dict | None:
    """Execute a query and return the first row as a dict, or None."""
    cursor = await db.execute(query, params)
    row = await cursor.fetchone()
    if row is None:
        return None
    return dict(row)


async def fetch_all(db: aiosqlite.Connection, query: str, params: tuple = ()) -> list[dict]:
    """Execute a query and return all rows as dicts."""
    cursor = await db.execute(query, params)
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def execute(db: aiosqlite.Connection, query: str, params: tuple = ()) -> int:
    """Execute a query and return the lastrowid."""
    cursor = await db.execute(query, params)
    await db.commit()
    return cursor.lastrowid  # type: ignore[return-value]
