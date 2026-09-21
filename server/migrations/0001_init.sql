-- 0001_init.sql : M1 核心表（作品 / 卷 / 章节 / 快照）
-- 迁移只增不改；后续表进 0002_*.sql 等。
CREATE TABLE IF NOT EXISTS books (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  title       TEXT NOT NULL DEFAULT '未命名作品',
  author      TEXT,
  summary     TEXT,
  cover_path  TEXT,
  status      TEXT NOT NULL DEFAULT 'active',   -- active | trashed
  deleted_at  TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS volumes (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  title      TEXT NOT NULL DEFAULT '正文卷',
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_volumes_book ON volumes(book_id);

CREATE TABLE IF NOT EXISTS chapters (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  volume_id  INTEGER REFERENCES volumes(id) ON DELETE SET NULL,
  title      TEXT NOT NULL DEFAULT '未命名章节',
  content    TEXT NOT NULL DEFAULT '',
  words      INTEGER NOT NULL DEFAULT 0,
  sort_order INTEGER NOT NULL DEFAULT 0,
  status     TEXT NOT NULL DEFAULT 'draft',
  deleted_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_chapters_book ON chapters(book_id);
CREATE INDEX IF NOT EXISTS idx_chapters_volume ON chapters(volume_id);

CREATE TABLE IF NOT EXISTS snapshots (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  chapter_id INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
  kind       TEXT NOT NULL DEFAULT 'manual',    -- manual | auto | pre_action
  title      TEXT NOT NULL DEFAULT '',
  content    TEXT NOT NULL DEFAULT '',
  words      INTEGER NOT NULL DEFAULT 0,
  trigger    TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_snapshots_chapter ON snapshots(chapter_id);
