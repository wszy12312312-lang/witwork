-- M4：人物与记忆 / 伏笔管理 / 词条库与角色库
-- 只增不改：新表全部在此，不改动 0001-0003。

-- 人物（L0 人物卡）
CREATE TABLE IF NOT EXISTS characters (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id       INTEGER,
    name          TEXT NOT NULL,
    aliases_json  TEXT,                -- 别名/异写
    appearance    TEXT,                -- 外貌
    personality   TEXT,                -- 性格
    catchphrase   TEXT,                -- 口癖
    status_current TEXT,               -- 当前状态
    taboo         TEXT,                -- 禁忌
    kb_item_id    INTEGER,             -- 与人物分区条目双向同步
    template_id   INTEGER,             -- 来自角色模板
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_characters_book ON characters(book_id);

-- 人物关系网
CREATE TABLE IF NOT EXISTS character_relations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id    INTEGER,
    from_id    INTEGER NOT NULL,
    to_id      INTEGER NOT NULL,
    relation   TEXT NOT NULL,
    note       TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_char_rel_book ON character_relations(book_id);

-- 出场记录（L1 摘要 / L2 原文块）
CREATE TABLE IF NOT EXISTS character_appearances (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL,
    chapter_id   INTEGER,
    summary      TEXT,
    excerpt      TEXT,                 -- 原文块
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_char_app ON character_appearances(character_id);

-- 伏笔
CREATE TABLE IF NOT EXISTS foreshadowings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id           INTEGER,
    title             TEXT NOT NULL,
    content           TEXT,
    status            TEXT NOT NULL DEFAULT 'planned',  -- planned|planted|called|resolved|abandoned
    importance        INTEGER NOT NULL DEFAULT 3,       -- 1-5
    keywords          TEXT,                             -- 逗号分隔，用于回收检测
    planted_chapter_id  INTEGER,
    resolved_chapter_id INTEGER,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_fore_book ON foreshadowings(book_id);
CREATE INDEX IF NOT EXISTS idx_fore_status ON foreshadowings(status);

-- 伏笔事件（生命周期留痕）
CREATE TABLE IF NOT EXISTS foreshadow_events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    foreshadowing_id INTEGER NOT NULL,
    action           TEXT NOT NULL,    -- create|plant|call|resolve|abandon|reopen
    chapter_id       INTEGER,
    note             TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_fore_ev ON foreshadow_events(foreshadowing_id);

-- 词条库
CREATE TABLE IF NOT EXISTS entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id         INTEGER,
    name            TEXT NOT NULL,
    category        TEXT,
    aliases_json    TEXT,                -- 异写
    description     TEXT,
    first_chapter_id INTEGER,            -- 首次出现章节
    kb_item_id      INTEGER,             -- 与 entry 分区条目同步
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_entries_book ON entries(book_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_entries_name ON entries(book_id, name);

-- 角色模板库
CREATE TABLE IF NOT EXISTS role_library (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    category   TEXT NOT NULL,            -- 主角|反派|配角|群像|组织
    fields_json TEXT,                    -- 预置字段集
    is_global  INTEGER NOT NULL DEFAULT 0,
    built_in   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 词频缓存（词条抽取用）
CREATE TABLE IF NOT EXISTS word_freq_cache (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id   INTEGER,
    word      TEXT NOT NULL,
    count     INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_wfc ON word_freq_cache(book_id, word);
