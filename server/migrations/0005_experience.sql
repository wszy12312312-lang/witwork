-- M5：全文搜索与替换 / 编辑历史 / 爽点节奏
-- 只增不改：新表全部在此，不改动 0001-0004。

-- 替换留痕（可一键撤销）
CREATE TABLE IF NOT EXISTS replace_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id     INTEGER,
    chapter_id  INTEGER NOT NULL,
    field       TEXT NOT NULL DEFAULT 'content',
    old         TEXT,
    new         TEXT,
    count       INTEGER NOT NULL DEFAULT 0,
    snapshot_id INTEGER,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    undone      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_replace_logs_book ON replace_logs(book_id);

-- 编辑历史（撤销栈持久化，可选）
CREATE TABLE IF NOT EXISTS edit_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL,
    content    TEXT NOT NULL,
    label      TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_edit_history_ch ON edit_history(chapter_id);

-- 爽点标注
CREATE TABLE IF NOT EXISTS beat_marks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id    INTEGER,
    chapter_id INTEGER NOT NULL,
    kind       TEXT NOT NULL,      -- payoff|reversal|hook|pressure|warmth|climax|info
    strength   INTEGER NOT NULL DEFAULT 3,   -- 1-5
    offset     INTEGER NOT NULL DEFAULT 0,   -- 正文字符位置
    text       TEXT,
    source     TEXT NOT NULL DEFAULT 'manual',  -- manual|ai
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_beat_book ON beat_marks(book_id);
CREATE INDEX IF NOT EXISTS idx_beat_ch ON beat_marks(chapter_id);

-- 爽点节奏模板
CREATE TABLE IF NOT EXISTS beat_templates (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    rule_json  TEXT NOT NULL,      -- {"every_chapters":N,"every_words":M,"kind":...,"min_strength":...}
    built_in   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
