"""books / volumes 数据访问（无业务逻辑）。"""
from server.db import get_conn

_ALLOWED_BOOK = {"title", "author", "summary", "cover_path", "status"}


def list_books(conn=None, include_trashed=False):
    own = conn is None
    conn = conn or get_conn()
    try:
        sql = "SELECT * FROM books"
        if not include_trashed:
            sql += " WHERE deleted_at IS NULL"
        # 注意：books 表没有 sort_order 列（见 0001_init.sql），此处不可按 sort_order 排序
        sql += " ORDER BY id"
        return [dict(r) for r in conn.execute(sql).fetchall()]
    finally:
        if own:
            conn.close()


def get_book(book_id, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        r = conn.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
        return dict(r) if r else None
    finally:
        if own:
            conn.close()


def create_book(title, author=None, summary=None, cover_path=None, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO books(title, author, summary, cover_path) VALUES (?,?,?,?)",
            (title, author, summary, cover_path),
        )
        conn.commit()
        return get_book(cur.lastrowid, conn)
    finally:
        if own:
            conn.close()


def update_book(book_id, fields, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cols = [c for c in fields if c in _ALLOWED_BOOK]
        if not cols:
            return get_book(book_id, conn)
        sets = ", ".join(f"{c}=?" for c in cols) + ", updated_at=datetime('now')"
        vals = [fields[c] for c in cols] + [book_id]
        conn.execute(f"UPDATE books SET {sets} WHERE id=?", vals)
        conn.commit()
        return get_book(book_id, conn)
    finally:
        if own:
            conn.close()


def soft_delete_book(book_id, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        conn.execute(
            "UPDATE books SET deleted_at=datetime('now'), status='trashed', updated_at=datetime('now') WHERE id=?",
            (book_id,),
        )
        conn.commit()
    finally:
        if own:
            conn.close()


def restore_book(book_id, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        conn.execute(
            "UPDATE books SET deleted_at=NULL, status='active', updated_at=datetime('now') WHERE id=?",
            (book_id,),
        )
        conn.commit()
    finally:
        if own:
            conn.close()


def list_volumes(book_id, conn=None, include_trashed=False):
    own = conn is None
    conn = conn or get_conn()
    try:
        sql = "SELECT * FROM volumes WHERE book_id=?"
        if not include_trashed:
            sql += " AND deleted_at IS NULL"
        sql += " ORDER BY sort_order, id"
        rows = conn.execute(sql, (book_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def get_volume(volume_id, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        r = conn.execute("SELECT * FROM volumes WHERE id=?", (volume_id,)).fetchone()
        return dict(r) if r else None
    finally:
        if own:
            conn.close()


def create_volume(book_id, title, sort_order=0, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO volumes(book_id, title, sort_order) VALUES (?,?,?)",
            (book_id, title, sort_order),
        )
        conn.commit()
        r = conn.execute("SELECT * FROM volumes WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(r)
    finally:
        if own:
            conn.close()


def update_volume(volume_id, fields, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cols = [c for c in fields if c in {"title", "sort_order"}]
        if cols:
            sets = ", ".join(f"{c}=?" for c in cols)
            conn.execute(
                f"UPDATE volumes SET {sets} WHERE id=?",
                [fields[c] for c in cols] + [volume_id],
            )
            conn.commit()
        r = conn.execute("SELECT * FROM volumes WHERE id=?", (volume_id,)).fetchone()
        return dict(r) if r else None
    finally:
        if own:
            conn.close()


# ---- 卷软删除 / 恢复（单卷删除按钮用） ----
# 关键点：删卷**只标记卷自己**，不动它下面章节的 deleted_at。
# 章节的可见性在 chapters.list_chapters 里由「自己的 deleted_at + 所属卷的 deleted_at」共同决定。
# 好处（对比早期按时间戳配对的做法）：
#   1) 恢复该卷时，它下面的章节原样回来，不需要任何配对逻辑；
#   2) 用户此前**单独**删掉的章节不会被卷恢复误唤回（时间戳秒级精度会撞车，测过确实会）；
#   3) 卷的删除只写一行，天然原子。

def _count_alive_chapters(conn, volume_id):
    r = conn.execute(
        "SELECT COUNT(*) AS n FROM chapters WHERE volume_id=? AND deleted_at IS NULL",
        (volume_id,),
    ).fetchone()
    return int(r["n"]) if r else 0


def soft_delete_volume(volume_id, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        chapters = _count_alive_chapters(conn, volume_id)
        conn.execute("UPDATE volumes SET deleted_at=datetime('now') WHERE id=?", (volume_id,))
        conn.commit()
        return {"ok": True, "volume_id": volume_id, "chapters": chapters}
    finally:
        if own:
            conn.close()


def restore_volume(volume_id, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        row = conn.execute("SELECT * FROM volumes WHERE id=?", (volume_id,)).fetchone()
        if not row:
            return None
        conn.execute("UPDATE volumes SET deleted_at=NULL WHERE id=?", (volume_id,))
        conn.commit()
        return {"ok": True, "volume_id": volume_id, "chapters": _count_alive_chapters(conn, volume_id)}
    finally:
        if own:
            conn.close()


def list_trashed(conn=None):
    """回收站统一视图：作品 / 卷 / 章节。

    随卷一起被删的章节不再单列（它们会跟着「恢复该卷」一起回来），避免同一个
    章节在回收站里出现两次。
    """
    own = conn is None
    conn = conn or get_conn()
    try:
        books = [dict(r) for r in conn.execute(
            "SELECT * FROM books WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC, id"
        ).fetchall()]
        volumes = [dict(r) for r in conn.execute(
            "SELECT v.*, b.title AS book_title, "
            "  (SELECT COUNT(*) FROM chapters c WHERE c.volume_id = v.id AND c.deleted_at IS NULL) AS chapters "
            "FROM volumes v "
            "LEFT JOIN books b ON b.id = v.book_id "
            "WHERE v.deleted_at IS NOT NULL ORDER BY v.deleted_at DESC, v.id"
        ).fetchall()]
        chapters = [dict(r) for r in conn.execute(
            "SELECT c.id, c.book_id, c.volume_id, c.title, c.words, c.deleted_at, "
            "       b.title AS book_title, v.title AS volume_title "
            "FROM chapters c "
            "LEFT JOIN books b ON b.id = c.book_id "
            "LEFT JOIN volumes v ON v.id = c.volume_id "
            "WHERE c.deleted_at IS NOT NULL "
            "  AND (c.volume_id IS NULL OR v.deleted_at IS NULL) "
            "ORDER BY c.deleted_at DESC, c.id"
        ).fetchall()]
        return {"books": books, "volumes": volumes, "chapters": chapters}
    finally:
        if own:
            conn.close()
