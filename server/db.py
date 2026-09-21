"""数据库连接与迁移框架。

- 迁移只增不改：新表进 0002_xxx.sql 等，永不 ALTER 已发布迁移。
- schema_migrations 记录已应用版本，重启不重复执行。
"""
import sqlite3
from pathlib import Path

from server.config import DB_PATH


def get_conn():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_migrations_table(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL UNIQUE,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )"""
    )


def applied_versions(conn):
    cur = conn.execute("SELECT version FROM schema_migrations")
    return {r["version"] for r in cur.fetchall()}


def run_migrations(conn):
    _ensure_migrations_table(conn)
    applied = applied_versions(conn)
    mig_dir = Path(__file__).resolve().parent / "migrations"
    files = sorted(p for p in mig_dir.glob("*.sql") if p.is_file())
    for f in files:
        version = f.stem
        if version in applied:
            continue
        sql = f.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
        conn.commit()


def init_db():
    conn = get_conn()
    try:
        run_migrations(conn)
    finally:
        conn.close()
