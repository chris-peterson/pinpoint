-- Pinpoint database schema

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL,
    managed_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'managed', 'missing', 'drifted')),
    root TEXT NOT NULL,
    file_class TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    perceptual_hash TEXT,
    creation_date TEXT,
    discovery_date TEXT NOT NULL DEFAULT (datetime('now')),
    managed_date TEXT,
    favorite INTEGER NOT NULL DEFAULT 0,
    stack_id INTEGER REFERENCES stacks(id),
    analysis_status TEXT,
    skipped_at TEXT,
    last_indexed_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_files_content_hash ON files(content_hash);
CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
CREATE INDEX IF NOT EXISTS idx_files_root ON files(root);

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
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (file_id, tag_id)
);

CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    value TEXT NOT NULL,
    confidence REAL,
    region TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'dismissed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_suggestions_file ON suggestions(file_id);

CREATE TABLE IF NOT EXISTS stacks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cover_file_id INTEGER REFERENCES files(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS known_faces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    embedding BLOB NOT NULL,
    source_file_id INTEGER REFERENCES files(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    verb TEXT NOT NULL,
    file_id INTEGER REFERENCES files(id) ON DELETE SET NULL,
    detail TEXT
);

CREATE INDEX IF NOT EXISTS idx_actions_file ON actions(file_id);
CREATE INDEX IF NOT EXISTS idx_actions_verb ON actions(verb);

-- Full-text search index
CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
    source_path,
    managed_path,
    tags,
    content='',
    tokenize='unicode61'
);
