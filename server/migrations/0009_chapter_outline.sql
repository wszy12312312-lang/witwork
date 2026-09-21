-- 0009_chapter_outline.sql
-- 章节新增「大纲」字段：支持「按本章大纲让 AI 生成正文」与「把想法交给 AI 生成大纲」。
-- 迁移只增不改：这里只加列，不动旧迁移。
ALTER TABLE chapters ADD COLUMN outline TEXT;
