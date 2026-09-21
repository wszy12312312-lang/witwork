"""全文搜索与替换：跨章扫描（标题+正文）、正则/大小写、逐个/全部替换、一键撤销。

替换前自动建 pre_action 快照并写 replace_logs，撤销即恢复快照内容。
"""
import re

from server.db import get_conn
from server.models import chapters as chm, snapshots as snm

_SNIPPET = 40


def _iter_chapters(book_id, scope="book", volume_id=None, chapter_id=None):
    # 注意：chm.list_chapters 的 SELECT 不含 content，必须逐个 get_chapter 取全文
    rows = chm.list_chapters(book_id)
    if scope == "chapter" and chapter_id:
        rows = [r for r in rows if r["id"] == chapter_id]
    elif scope == "volume" and volume_id:
        rows = [r for r in rows if (r.get("volume_id") or None) == volume_id]
    return [chm.get_chapter(r["id"]) for r in rows if r]


def _find(text, query, use_regex=False, case_sensitive=False):
    if not query:
        return []
    flags = 0 if case_sensitive else re.IGNORECASE
    if use_regex:
        try:
            pat = re.compile(query, flags)
        except re.error:
            return []
        return [(m.start(), m.end()) for m in pat.finditer(text or "")]
    hay = (text or "") if case_sensitive else (text or "").lower()
    needle = query if case_sensitive else query.lower()
    if not needle:
        return []
    out = []
    i = hay.find(needle)
    while i != -1:
        out.append((i, i + len(needle)))
        i = hay.find(needle, i + max(1, len(needle)))
    return out


def _line_col(text, pos):
    pre = text[:pos]
    line = pre.count("\n") + 1
    col = pos - (pre.rfind("\n") + 1) + 1
    return line, col


def search(book_id, query, use_regex=False, case_sensitive=False,
           scope="book", volume_id=None, chapter_id=None, limit=500):
    hits = []
    total = 0
    for ch in _iter_chapters(book_id, scope, volume_id, chapter_id):
        content = ch.get("content") or ""
        title = ch.get("title") or ""
        for field, text in (("title", title), ("content", content)):
            for s, e in _find(text, query, use_regex, case_sensitive):
                line, col = _line_col(text, s)
                snippet = text[max(0, s - _SNIPPET): e + _SNIPPET]
                hits.append({
                    "chapter_id": ch["id"],
                    "chapter_title": title,
                    "field": field,
                    "line": line,
                    "col": col,
                    "offset": s,
                    "snippet": snippet,
                })
                total += 1
                if total >= limit:
                    return {"hits": hits, "total": total, "truncated": True}
    return {"hits": hits, "total": total, "truncated": False}


def replace(book_id, query, replacement, use_regex=False, case_sensitive=False,
            scope="book", volume_id=None, chapter_id=None, chapter_ids=None, dry_run=True):
    """dry_run=True 只返回预览 diff；False 才真正替换（替换前建快照 + 写 log）。"""
    targets = _iter_chapters(book_id, scope, volume_id, chapter_id)
    if chapter_ids:
        targets = [c for c in targets if c["id"] in set(chapter_ids)]
    results = []
    total = 0
    for ch in targets:
        content = ch.get("content") or ""
        spans = _find(content, query, use_regex, case_sensitive)
        if not spans:
            continue
        flags = 0 if case_sensitive else re.IGNORECASE
        if use_regex:
            new_content = re.sub(query, replacement.replace("\\", "\\\\"), content, flags=flags)
            count = len(spans)
        else:
            new_content, count = _replace_plain(content, query, replacement, case_sensitive)
        before = content[max(0, spans[0][0] - _SNIPPET): spans[0][1] + _SNIPPET]
        after_spans = _find(new_content, replacement if replacement else "", False, case_sensitive)
        after = new_content[max(0, after_spans[0][0] - _SNIPPET): after_spans[0][1] + _SNIPPET] if (after_spans and replacement) else ""
        item = {"chapter_id": ch["id"], "chapter_title": ch.get("title"), "count": count,
                "before": before, "after": after, "log_id": None}
        if not dry_run:
            snap = snm.create_snapshot(book_id, ch["id"], kind="pre_action",
                                       title=f"替换前：{query}", content=content, trigger="replace")
            chm.update_chapter(ch["id"], {"content": new_content})
            item["log_id"] = _log(book_id, ch["id"], query, replacement, count, snap["id"])
        results.append(item)
        total += count
    return {"results": results, "total": total}


def _replace_plain(content, query, replacement, case_sensitive):
    if case_sensitive:
        return content.replace(query, replacement), content.count(query)
    # 不区分大小写：逐段替换并保留原大小写位置
    low = content.lower()
    needle = query.lower()
    out = []
    i = 0
    count = 0
    while True:
        j = low.find(needle, i)
        if j == -1:
            out.append(content[i:])
            break
        out.append(content[i:j])
        out.append(replacement)
        count += 1
        i = j + len(needle)
    return "".join(out), count


def _log(book_id, chapter_id, old, new, count, snapshot_id):
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO replace_logs(book_id, chapter_id, field, old, new, count, snapshot_id)
               VALUES (?,?,?,?,?,?,?)""",
            (book_id, chapter_id, "content", old, new, count, snapshot_id),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_logs(book_id=None, conn=None):
    own = conn is None
    conn = conn or get_conn()
    try:
        if book_id is not None:
            rows = conn.execute(
                "SELECT * FROM replace_logs WHERE book_id=? ORDER BY id DESC", (book_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM replace_logs ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def undo_replace(rid):
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM replace_logs WHERE id=?", (rid,)).fetchone()
        if not r:
            raise ValueError("替换记录不存在")
        row = dict(r)
        if row.get("undone"):
            return row
        snap = snm.get_snapshot(row["snapshot_id"]) if row.get("snapshot_id") else None
        if not snap:
            raise ValueError("快照缺失，无法撤销")
        chm.update_chapter(row["chapter_id"], {"content": snap["content"]})
        conn.execute("UPDATE replace_logs SET undone=1 WHERE id=?", (rid,))
        conn.commit()
        return dict(conn.execute("SELECT * FROM replace_logs WHERE id=?", (rid,)).fetchone())
    finally:
        conn.close()
