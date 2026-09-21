"""写作统计：保存时用文本 diff 计算净增（新增/删除分别计），聚合成日报与热力图。

- 字数口径：非空白字符数（与 chapters.words 一致）。
- 时长：按编辑活跃计时，5 分钟无操作暂停。
"""
import datetime
import difflib

from server.db import get_conn

_IDLE_MINUTES = 5
_last_active = {}  # book_id -> datetime


def count_words(text):
    return sum(1 for ch in (text or "") if not ch.isspace())


def _today():
    return datetime.date.today().isoformat()


def _diff_counts(before, after):
    added = deleted = 0
    sm = difflib.SequenceMatcher(None, before or "", after or "", autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("insert", "replace"):
            added += count_words(after[j1:j2])
        if tag in ("delete", "replace"):
            deleted += count_words(before[i1:i2])
    return added, deleted


def _ensure_daily(date, book_id, conn):
    conn.execute(
        "INSERT OR IGNORE INTO daily_stats(date, book_id) VALUES (?,?)", (date, book_id)
    )


def record_save(book_id, chapter_id, before, after):
    added, deleted = _diff_counts(before, after)
    delta = added - deleted
    if added == 0 and deleted == 0:
        return {"added": 0, "deleted": 0, "delta": 0}
    date = _today()
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO chapter_word_logs(book_id, chapter_id, added, deleted, delta, words_after)
               VALUES (?,?,?,?,?,?)""",
            (book_id, chapter_id, added, deleted, delta, count_words(after)),
        )
        _ensure_daily(date, book_id, conn)
        conn.execute(
            """UPDATE daily_stats SET words_added=words_added+?, words_deleted=words_deleted+?,
               net=words_added+?-(words_deleted+?), updated_at=datetime('now')
               WHERE date=? AND book_id IS ?""",
            (added, deleted, added, deleted, date, book_id),
        )
        conn.commit()
    finally:
        conn.close()
    touch_minutes(book_id)
    return {"added": added, "deleted": deleted, "delta": delta}


def touch_minutes(book_id):
    """编辑活跃计时：距上次活跃 ≤5 分钟才累加，否则视为新一段。"""
    now = datetime.datetime.now()
    prev = _last_active.get(book_id)
    _last_active[book_id] = now
    if not prev:
        return 0
    gap = (now - prev).total_seconds() / 60.0
    if gap <= 0 or gap > _IDLE_MINUTES:
        return 0
    mins = int(round(gap))
    if mins <= 0:
        return 0
    conn = get_conn()
    try:
        _ensure_daily(_today(), book_id, conn)
        conn.execute(
            "UPDATE daily_stats SET minutes=minutes+?, updated_at=datetime('now') WHERE date=? AND book_id IS ?",
            (mins, _today(), book_id),
        )
        conn.commit()
    finally:
        conn.close()
    return mins


def daily(date=None, book_id=None):
    date = date or _today()
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM daily_stats WHERE date=? AND book_id IS ?", (date, book_id)
        ).fetchone()
        return dict(row) if row else {"date": date, "book_id": book_id,
                                      "words_added": 0, "words_deleted": 0, "net": 0, "minutes": 0}
    finally:
        conn.close()


def range_stats(start, end, book_id=None):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM daily_stats WHERE date BETWEEN ? AND ? AND book_id IS ? ORDER BY date",
            (start, end, book_id),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def heatmap(book_id=None, days=180):
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days - 1)
    return range_stats(start.isoformat(), end.isoformat(), book_id)


def streak(book_id=None):
    """连续更新天数。"""
    rows = heatmap(book_id, days=365)
    n = 0
    for r in reversed(rows):
        if (r.get("net") or 0) > 0:
            n += 1
        else:
            break
    return n


def get_goal(book_id=None):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM writing_goals WHERE book_id IS ?", (book_id,)).fetchone()
        return dict(row) if row else {"book_id": book_id, "daily_words": 2000}
    finally:
        conn.close()


def set_goal(book_id, daily_words):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM writing_goals WHERE book_id IS ?", (book_id,))
        cur = conn.execute(
            "INSERT INTO writing_goals(book_id, daily_words) VALUES (?,?)",
            (book_id, int(daily_words)),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM writing_goals WHERE id=?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()


# ---------- 更新计划 ----------
def list_plans(book_id=None):
    conn = get_conn()
    try:
        if book_id is not None:
            rows = conn.execute("SELECT * FROM update_plans WHERE book_id=? ORDER BY id", (book_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM update_plans ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_plan(book_id, time_of_day="20:00", days="1,2,3,4,5,6,7", enabled=1):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO update_plans(book_id, time_of_day, days, enabled) VALUES (?,?,?,?)",
            (book_id, time_of_day, days, enabled),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM update_plans WHERE id=?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()


def delete_plan(pid):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM update_plans WHERE id=?", (pid,))
        conn.commit()
    finally:
        conn.close()
