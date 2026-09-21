"""chapters 数据访问（无业务逻辑）。"""
from server.db import get_conn

_ALLOWED = {"title", "content", "volume_id", "status", "sort_order", "outline"}


def count_words(text):
    if not text:
        return 0
    return sum(1 for ch in text if not ch.isspace())


def list_chapters(book_id, conn=None, include_trashed=False):
    """列出作品章节。

    可见性规则：章节自己没被删 **且** 它所属的卷没被删。
    卷的删除状态在这里「顺带」生效（而不是删卷时去改章节的 deleted_at），
    这样「恢复该卷」天然把它下面的章节原样带回来，也不会误唤回用户单独删掉的章节，
    更不需要靠时间戳去配对（秒级精度会撞车）。
    """
    own = conn is None
    conn = conn or get_conn()
    try:
        cols = ("c.id, c.book_id, c.volume_id, c.title, c.words, c.sort_order, "
                "c.status, c.created_at, c.updated_at")
        sql = (f"SELECT {cols} FROM chapters c "
               "LEFT JOIN volumes v ON v.id = c.volume_id")
        if include_trashed:
            sql += " WHERE c.book_id=?"
            args = (book_id,)
        else:
            # 三重可见性：章节自己没删 + 所属卷没删 + 所属作品没删。
            # 漏掉第三条时，删掉整个作品后其章节仍会被列出（"作品删了原文还在"）。
            sql += (" WHERE c.deleted_at IS NULL "
                    "AND (c.volume_id IS NULL OR v.deleted_at IS NULL) "
                    "AND NOT EXISTS (SELECT 1 FROM books b WHERE b.id = c.book_id "
                    "                AND b.deleted_at IS NOT NULL) "
                    "AND c.book_id=?")
            args = (book_id,)
        sql += " ORDER BY c.sort_order, c.id"
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        if own:
            conn.close()


def get_chapter(chapter_id, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        r = conn.execute("SELECT * FROM chapters WHERE id=?", (chapter_id,)).fetchone()
        return dict(r) if r else None
    finally:
        if own:
            conn.close()


def create_chapter(book_id, title="未命名章节", volume_id=None, content="", sort_order=0, outline="", conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        words = count_words(content)
        cur = conn.execute(
            "INSERT INTO chapters(book_id, volume_id, title, content, words, sort_order, outline) VALUES (?,?,?,?,?,?,?)",
            (book_id, volume_id, title, content, words, sort_order, outline),
        )
        conn.commit()
        return get_chapter(cur.lastrowid, conn)
    finally:
        if own:
            conn.close()


def update_chapter(chapter_id, fields, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        cols = [c for c in fields if c in _ALLOWED]
        if not cols:
            return get_chapter(chapter_id, conn)
        sets, vals = [], []
        for c in cols:
            if c == "content":
                sets.append("content=?")
                sets.append("words=?")
                vals.append(fields[c])
                vals.append(count_words(fields[c]))
            else:
                sets.append(f"{c}=?")
                vals.append(fields[c])
        sets.append("updated_at=datetime('now')")
        vals.append(chapter_id)
        conn.execute(f"UPDATE chapters SET {', '.join(sets)} WHERE id=?", vals)
        conn.commit()
        return get_chapter(chapter_id, conn)
    finally:
        if own:
            conn.close()


def soft_delete_chapter(chapter_id, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        conn.execute(
            "UPDATE chapters SET deleted_at=datetime('now'), updated_at=datetime('now') WHERE id=?",
            (chapter_id,),
        )
        conn.commit()
    finally:
        if own:
            conn.close()


def restore_chapter(chapter_id, conn=None):
    """从回收站恢复单章。卷若仍处于删除状态则一并放回，否则章节会「看不见」。"""
    own = conn is None
    conn = conn or get_conn()
    try:
        row = conn.execute("SELECT * FROM chapters WHERE id=?", (chapter_id,)).fetchone()
        if not row:
            return None
        vol_id = row["volume_id"]
        if vol_id:
            conn.execute("UPDATE volumes SET deleted_at=NULL WHERE id=? AND deleted_at IS NOT NULL", (vol_id,))
        conn.execute(
            "UPDATE chapters SET deleted_at=NULL, updated_at=datetime('now') WHERE id=?",
            (chapter_id,),
        )
        conn.commit()
        return get_chapter(chapter_id, conn)
    finally:
        if own:
            conn.close()
