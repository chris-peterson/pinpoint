import Database from "better-sqlite3";
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";

const SCHEMA = `
-- §10 Core entities
CREATE TABLE IF NOT EXISTS files (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_path TEXT NOT NULL,
  managed_path TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending','managed','missing','drifted')),
  root TEXT NOT NULL,
  file_class TEXT,
  content_hash TEXT,
  perceptual_hash TEXT,
  creation_date TEXT,
  discovery_date TEXT NOT NULL DEFAULT (datetime('now')),
  managed_date TEXT,
  favorite INTEGER NOT NULL DEFAULT 0,
  stack_id INTEGER REFERENCES stacks(id),
  stack_order INTEGER,
  analysis_status TEXT,
  skipped_at TEXT,
  last_indexed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
CREATE INDEX IF NOT EXISTS idx_files_hash ON files(content_hash);
CREATE UNIQUE INDEX IF NOT EXISTS idx_files_source ON files(source_path);

CREATE TABLE IF NOT EXISTS tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  type TEXT NOT NULL,
  builtin INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS file_tags (
  file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  region TEXT,
  applied_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (file_id, tag_id)
);

CREATE TABLE IF NOT EXISTS suggestions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  value TEXT NOT NULL,
  confidence REAL,
  region TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending','accepted','dismissed'))
);

CREATE INDEX IF NOT EXISTS idx_suggestions_file ON suggestions(file_id, status);

CREATE TABLE IF NOT EXISTS stacks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cover_file_id INTEGER REFERENCES files(id)
);

CREATE TABLE IF NOT EXISTS known_faces (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  label TEXT NOT NULL,
  embedding BLOB,
  source_ref TEXT
);

-- §10 Action log [DM-1]
CREATE TABLE IF NOT EXISTS actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL DEFAULT (datetime('now')),
  verb TEXT NOT NULL,
  file_id INTEGER REFERENCES files(id),
  detail TEXT
);

CREATE INDEX IF NOT EXISTS idx_actions_file ON actions(file_id);

-- Full-text search
CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
  source_path, managed_path, tag_text,
  content='files',
  content_rowid='id'
);
`;

export function openDatabase(dbPath) {
  mkdirSync(dirname(dbPath), { recursive: true });
  const db = new Database(dbPath);
  db.pragma("journal_mode = WAL");
  db.pragma("foreign_keys = ON");
  db.exec(SCHEMA);
  return db;
}
