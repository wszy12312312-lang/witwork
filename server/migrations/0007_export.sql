-- M5 Step18：Word 导出模板
-- 只增不改。

CREATE TABLE IF NOT EXISTS export_templates (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    style_json TEXT NOT NULL,   -- {font, size, line_spacing, indent_chars, cover, toc, header, footer}
    built_in   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
