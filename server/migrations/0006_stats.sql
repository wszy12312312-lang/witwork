-- M5 Step16：写作统计与更新提醒
-- 只增不改。

CREATE TABLE IF NOT EXISTS chapter_word_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id     INTEGER,
    chapter_id  INTEGER NOT NULL,
    added       INTEGER NOT NULL DEFAULT 0,
    deleted     INTEGER NOT NULL DEFAULT 0,
    delta       INTEGER NOT NULL DEFAULT 0,
    words_after INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_cwl_ch ON chapter_word_logs(chapter_id);

CREATE TABLE IF NOT EXISTS daily_stats (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT NOT NULL,          -- YYYY-MM-DD
    book_id      INTEGER,
    words_added  INTEGER NOT NULL DEFAULT 0,
    words_deleted INTEGER NOT NULL DEFAULT 0,
    net          INTEGER NOT NULL DEFAULT 0,
    minutes      INTEGER NOT NULL DEFAULT 0,
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_unique ON daily_stats(date, book_id);

CREATE TABLE IF NOT EXISTS writing_goals (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id    INTEGER,
    daily_words INTEGER NOT NULL DEFAULT 2000,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS update_plans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id     INTEGER,
    time_of_day TEXT NOT NULL DEFAULT '20:00',   -- HH:MM
    days        TEXT NOT NULL DEFAULT '1,2,3,4,5,6,7',
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id    INTEGER,
    kind       TEXT NOT NULL,           -- reminder | break_warn | test
    title      TEXT NOT NULL,
    body       TEXT,
    read       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_notif_read ON notifications(read);
