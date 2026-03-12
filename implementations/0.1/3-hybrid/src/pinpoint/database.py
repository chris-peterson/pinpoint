import json
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL,
    managed_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    root TEXT NOT NULL,
    file_class TEXT,
    content_hash TEXT,
    perceptual_hash TEXT,
    creation_date TEXT,
    discovery_date TEXT DEFAULT (datetime('now')),
    managed_date TEXT,
    favorite INTEGER DEFAULT 0,
    stack_id INTEGER,
    analysis_status TEXT DEFAULT 'pending',
    skipped_at TEXT,
    last_indexed_at TEXT,
    FOREIGN KEY (stack_id) REFERENCES stacks(id)
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS file_tags (
    file_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    region TEXT,
    applied_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (file_id, tag_id),
    FOREIGN KEY (file_id) REFERENCES files(id),
    FOREIGN KEY (tag_id) REFERENCES tags(id)
);

CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    value TEXT NOT NULL,
    confidence REAL DEFAULT 0.5,
    region TEXT,
    status TEXT DEFAULT 'pending',
    FOREIGN KEY (file_id) REFERENCES files(id)
);

CREATE TABLE IF NOT EXISTS stacks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cover_file_id INTEGER,
    ordering TEXT
);

CREATE TABLE IF NOT EXISTS known_faces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    embedding BLOB,
    source_ref TEXT
);

CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    verb TEXT NOT NULL,
    file_id INTEGER,
    detail TEXT,
    FOREIGN KEY (file_id) REFERENCES files(id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
    source_path, managed_path, content='files', content_rowid='id'
);

CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
CREATE INDEX IF NOT EXISTS idx_files_root ON files(root);
CREATE INDEX IF NOT EXISTS idx_files_hash ON files(content_hash);
CREATE INDEX IF NOT EXISTS idx_file_tags_file ON file_tags(file_id);
CREATE INDEX IF NOT EXISTS idx_file_tags_tag ON file_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_actions_file ON actions(file_id);
"""


class Database:
    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn

    async def execute(self, sql: str, params=()) -> list:
        cursor = await self._conn.execute(sql, params)
        return await cursor.fetchall()

    async def execute_one(self, sql: str, params=()):
        cursor = await self._conn.execute(sql, params)
        return await cursor.fetchone()

    async def execute_insert(self, sql: str, params=()) -> int:
        cursor = await self._conn.execute(sql, params)
        await self._conn.commit()
        return cursor.lastrowid

    async def execute_write(self, sql: str, params=()):
        await self._conn.execute(sql, params)
        await self._conn.commit()

    async def commit(self):
        await self._conn.commit()

    async def log_action(self, verb: str, file_id: int | None, detail: dict | None = None):
        await self._conn.execute(
            "INSERT INTO actions (verb, file_id, detail) VALUES (?, ?, ?)",
            (verb, file_id, json.dumps(detail) if detail else None),
        )
        await self._conn.commit()


async def init_db(data_dir: str) -> Database:
    db_dir = Path(data_dir)
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "pinpoint.db"

    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    await conn.executescript(SCHEMA)
    await conn.commit()

    return Database(conn)
