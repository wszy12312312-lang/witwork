-- 0008_volume_trash.sql
-- 卷也支持软删除（与 books / chapters 一致），这样「删除单卷」可恢复。
-- 迁移只增不改：这里只加列，不动旧迁移。
ALTER TABLE volumes ADD COLUMN deleted_at TEXT;
CREATE INDEX IF NOT EXISTS idx_volumes_deleted ON volumes(deleted_at);
