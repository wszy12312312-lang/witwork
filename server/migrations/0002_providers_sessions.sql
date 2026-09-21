-- M2：Provider 适配层 + 会话/消息（Step 3-5、10）。只增不改。

CREATE TABLE IF NOT EXISTS providers (
    id              TEXT PRIMARY KEY,
    kind            TEXT NOT NULL,                 -- mock | openai | ollama | anthropic | llamacpp
    name            TEXT NOT NULL,
    base_url        TEXT,
    api_key_ref     TEXT,                          -- 仅存引用名，真实密钥在 secrets.enc
    model           TEXT,
    context_window  INTEGER NOT NULL DEFAULT 8000,
    is_local        INTEGER NOT NULL DEFAULT 0,
    enabled         INTEGER NOT NULL DEFAULT 1,
    extra_json      TEXT,                          -- 各 kind 私有配置
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id                INTEGER,
    title                  TEXT,
    active_provider_id     TEXT,
    summary_upto_message_id INTEGER,
    framework_state_json   TEXT,                   -- Step 11 框架共创状态
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at             TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
    FOREIGN KEY (active_provider_id) REFERENCES providers(id)
);

CREATE TABLE IF NOT EXISTS messages (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    role                TEXT NOT NULL,             -- system | user | assistant
    content             TEXT NOT NULL,
    provider_snapshot_json TEXT,                  -- 发送时 provider 快照(kind+model)
    token_count         INTEGER,
    refs_json           TEXT,                      -- 知识命中卡(Step 7)
    is_summary          INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_book ON sessions(book_id);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
