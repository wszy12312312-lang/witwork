-- M3：分区知识库 / AI 人格 / 结构化写回 / 框架共创
-- 只增不改：新表全部在此，不改动 0001/0002。

-- 分区知识库
CREATE TABLE IF NOT EXISTS kb_sections (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    key       TEXT NOT NULL UNIQUE,
    title     TEXT NOT NULL,
    description TEXT,
    built_in  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS kb_items (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    section           TEXT NOT NULL,
    title             TEXT NOT NULL,
    content           TEXT NOT NULL DEFAULT '',
    current_version_id INTEGER,
    source_type       TEXT,               -- manual | file | ai | import
    source_ref        TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_kb_items_section ON kb_items(section);

CREATE TABLE IF NOT EXISTS kb_item_versions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id           INTEGER NOT NULL,
    content           TEXT NOT NULL,
    reason            TEXT,
    source_message_id INTEGER,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_kb_versions_item ON kb_item_versions(item_id);

CREATE TABLE IF NOT EXISTS kb_chunks (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id   INTEGER NOT NULL,
    idx       INTEGER NOT NULL,
    text      TEXT NOT NULL,
    embedding BLOB,
    tokens    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_item ON kb_chunks(item_id);

-- FTS5 trigram：中文子串检索（≥3 字）。短词（<3 字）走 LIKE 兜底，由检索服务合并。
CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(text, tokenize='trigram');

-- AI 写作人格
CREATE TABLE IF NOT EXISTS personas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    system_prompt TEXT NOT NULL DEFAULT '',
    tone          TEXT,
    style_tags_json TEXT,
    focus         TEXT,
    methods_json  TEXT,
    temperature   REAL NOT NULL DEFAULT 0.8,
    forbidden_json TEXT,
    is_default    INTEGER NOT NULL DEFAULT 0,
    active        INTEGER NOT NULL DEFAULT 0,
    built_in      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS persona_versions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id    INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL,
    note          TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_persona_versions ON persona_versions(persona_id);

-- 结构化写回：AI 提议
CREATE TABLE IF NOT EXISTS patches (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        INTEGER,
    target_type       TEXT NOT NULL,       -- kb_item | persona
    section           TEXT,
    title             TEXT,
    op                TEXT NOT NULL,        -- create | update | delete
    fields_json       TEXT NOT NULL,
    reason            TEXT,
    status            TEXT NOT NULL DEFAULT 'pending',  -- pending | applied | rejected | need_confirm
    current_value_json TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    applied_at        TEXT
);
CREATE INDEX IF NOT EXISTS idx_patches_session ON patches(session_id);
CREATE INDEX IF NOT EXISTS idx_patches_status ON patches(status);

-- 框架共创快照
CREATE TABLE IF NOT EXISTS framework_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL,
    phase       TEXT NOT NULL,
    state_json  TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_fw_snap_session ON framework_snapshots(session_id);
