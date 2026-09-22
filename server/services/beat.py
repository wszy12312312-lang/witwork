"""爽点节奏：标注 / 模板 / 指标 / 平淡预警 / 插入建议。

7 类爽点：payoff 回报 / reversal 反转 / hook 钩子 / pressure 压力 / warmth 温情 / climax 高潮 / info 信息。
模板驱动目标节奏线；按字数窗口检测连续平淡段并给出带位置的插入建议。
"""
from server.db import get_conn
from server.models import chapters as chm

KINDS = ["payoff", "reversal", "hook", "pressure", "warmth", "climax", "info"]
KIND_LABEL = {
    "payoff": "回报", "reversal": "反转", "hook": "钩子", "pressure": "压力",
    "warmth": "温情", "climax": "高潮", "info": "信息",
}
DEFAULT_TEMPLATES = [
    ("三章一小爽", {"every_chapters": 3, "kind": "payoff", "min_strength": 3}),
    ("十章一大爽", {"every_chapters": 10, "kind": "climax", "min_strength": 4}),
    ("商业连载", {"every_words": 3000, "kind": "payoff", "min_strength": 3}),
]


def seed_templates():
    conn = get_conn()
    try:
        for name, rule in DEFAULT_TEMPLATES:
            if conn.execute("SELECT 1 FROM beat_templates WHERE name=? AND built_in=1", (name,)).fetchone():
                continue
            import json
            conn.execute(
                "INSERT INTO beat_templates(name, rule_json, built_in) VALUES (?,?,1)",
                (name, json.dumps(rule, ensure_ascii=False)),
            )
        conn.commit()
    finally:
        conn.close()


def list_templates():
    conn = get_conn()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM beat_templates ORDER BY built_in DESC, id").fetchall()]
    finally:
        conn.close()


def add_mark(book_id, chapter_id, kind, strength=3, offset=0, text=None, source="manual"):
    if kind not in KINDS:
        raise ValueError(f"未知爽点类型：{kind}")
    # beat_marks.chapter_id 是 NOT NULL：以前不校验直接 INSERT，
    # 缺失时抛 sqlite3.IntegrityError（不是 ValueError，API 层接不住）→ 500。
    if chapter_id in (None, ""):
        raise ValueError("缺少章节：爽点标记必须挂在某一章上")
    try:
        chapter_id = int(chapter_id)
        book_id = int(book_id) if book_id not in (None, "") else None
    except (TypeError, ValueError):
        raise ValueError("book_id / chapter_id 必须是整数")
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT book_id FROM chapters WHERE id=? AND deleted_at IS NULL", (chapter_id,)
        ).fetchone()
        if not row:
            raise ValueError("章节不存在或已删除")
        if book_id is None:
            book_id = row["book_id"]
        cur = conn.execute(
            """INSERT INTO beat_marks(book_id, chapter_id, kind, strength, offset, text, source)
               VALUES (?,?,?,?,?,?,?)""",
            (book_id, chapter_id, kind, int(strength), int(offset), text, source),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM beat_marks WHERE id=?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()


def list_marks(book_id=None, chapter_id=None):
    conn = get_conn()
    try:
        sql = "SELECT * FROM beat_marks"
        wh, args = [], []
        if book_id is not None:
            wh.append("book_id=?")
            args.append(book_id)
        if chapter_id is not None:
            wh.append("chapter_id=?")
            args.append(chapter_id)
        if wh:
            sql += " WHERE " + " AND ".join(wh)
        sql += " ORDER BY chapter_id, offset, id"
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def delete_mark(mid):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM beat_marks WHERE id=?", (mid,))
        conn.commit()
    finally:
        conn.close()


def metrics(book_id, template_id=None, flat_threshold=3000):
    """每章数量与平均强度、按类型间隔、连续平淡长度、与模板偏离度。"""
    import json
    chapters = chm.list_chapters(book_id)
    marks = list_marks(book_id)
    by_ch = {}
    for m in marks:
        by_ch.setdefault(m["chapter_id"], []).append(m)
    per_chapter = []
    cursor = 0  # 累计字数位置，用于平淡段检测
    flat_runs = []
    run = 0
    for c in chapters:
        ms = by_ch.get(c["id"], [])
        words = c.get("words") or 0
        per_chapter.append({
            "chapter_id": c["id"], "title": c.get("title"), "words": words,
            "count": len(ms),
            "avg_strength": round(sum(x["strength"] for x in ms) / len(ms), 2) if ms else 0,
            "kinds": sorted({x["kind"] for x in ms}),
        })
        if not ms:
            run += words
        else:
            if run >= flat_threshold:
                flat_runs.append({"end_chapter": c.get("title"), "length": run})
            run = 0
        cursor += words
    if run >= flat_threshold:
        flat_runs.append({"end_chapter": "结尾", "length": run})
    # 按类型间隔（章序号差）
    intervals = {}
    for k in KINDS:
        idxs = [i for i, c in enumerate(chapters) if any(m["kind"] == k for m in by_ch.get(c["id"], []))]
        if len(idxs) >= 2:
            intervals[k] = [b - a for a, b in zip(idxs, idxs[1:])]
    deviation = None
    if template_id:
        tpl = next((t for t in list_templates() if t["id"] == template_id), None)
        if tpl:
            rule = json.loads(tpl["rule_json"])
            gap = rule.get("every_chapters")
            need_kind = rule.get("kind")
            min_strength = int(rule.get("min_strength", 3))
            misses = 0
            for i, c in enumerate(per_chapter):
                if gap and need_kind:
                    if (i + 1) % gap == 0:
                        ok = any(m["kind"] == need_kind and m["strength"] >= min_strength
                                 for m in by_ch.get(c["chapter_id"], []))
                        if not ok:
                            misses += 1
            deviation = {"template": tpl["name"], "misses": misses}
    return {"per_chapter": per_chapter, "intervals": intervals, "flat_runs": flat_runs,
            "deviation": deviation, "total_marks": len(marks)}


def suggest(book_id, template_id=None, flat_threshold=3000):
    """问题清单 + 具体插入位置与建议类型。"""
    m = metrics(book_id, template_id, flat_threshold)
    out = []
    for run in m["flat_runs"]:
        out.append({"chapter": run["end_chapter"], "position_words": run["length"],
                    "kind": "payoff", "reason": f"连续 {run['length']} 字无爽点，建议插入回报型情节"})
    for pc in m["per_chapter"]:
        if pc["words"] and pc["count"] == 0 and pc["words"] >= flat_threshold:
            out.append({"chapter": pc["title"], "position_words": pc["words"],
                        "kind": "hook", "reason": "本章无任何爽点，建议章末加钩子"})
    if m["deviation"] and m["deviation"]["misses"]:
        out.append({"chapter": "全书", "position_words": 0, "kind": "payoff",
                    "reason": f"与模板「{m['deviation']['template']}」偏离 {m['deviation']['misses']} 处"})
    return out
