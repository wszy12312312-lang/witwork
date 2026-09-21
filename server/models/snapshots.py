"""snapshots 数据访问（无业务逻辑）。"""
from server.db import get_conn
from server.models.chapters import count_words


def create_snapshot(book_id, chapter_id, kind="manual", title="", content="", trigger=None, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        words = count_words(content)
        cur = conn.execute(
            "INSERT INTO snapshots(book_id, chapter_id, kind, title, content, words, trigger) "
            "VALUES (?,?,?,?,?,?,?)",
            (book_id, chapter_id, kind, title, content, words, trigger),
        )
        conn.commit()
        r = conn.execute("SELECT * FROM snapshots WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(r)
    finally:
        if own:
            conn.close()


def list_snapshots(chapter_id, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        rows = conn.execute(
            "SELECT id, chapter_id, kind, title, words, trigger, created_at FROM snapshots "
            "WHERE chapter_id=? ORDER BY id DESC",
            (chapter_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def get_snapshot(snapshot_id, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        r = conn.execute("SELECT * FROM snapshots WHERE id=?", (snapshot_id,)).fetchone()
        return dict(r) if r else None
    finally:
        if own:
            conn.close()
