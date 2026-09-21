"""伏笔服务：CRUD + 生命周期动作（每次写事件）+ 看板筛选 + 上下文注入 + 回收检测。

生命周期：create → plant(埋设) → call(调用) → resolve(回收) / abandon(废弃) → reopen(复活)。
"""
from server.models import foreshadow as fm


def create(book_id, title, content=None, importance=3, keywords=None):
    return fm.create_foreshadowing(book_id, title, content, importance, keywords)


def get(fid):
    return fm.get_foreshadowing(fid)


def list_all(book_id=None, status=None):
    return fm.list_foreshadowings(book_id, status)


def update(fid, fields):
    return fm.update_foreshadowing(fid, fields)


def delete(fid):
    fm.delete_foreshadowing(fid)


def do_action(fid, action, chapter_id=None, note=None):
    """执行生命周期动作：写事件 + 推进状态（reopen 回到 planted）。"""
    if action not in fm.VALID_ACTIONS:
        raise ValueError(f"不支持的动作：{action}")
    f = fm.get_foreshadowing(fid)
    if not f:
        raise ValueError("伏笔不存在")
    fm.add_event(fid, action, chapter_id, note)
    if action == "create":
        return f
    status = fm.ACTION_STATUS.get(action)
    if status:
        f = fm.set_status(fid, status, chapter_id)
    return f


def events(fid):
    return fm.list_events(fid)


def injection_text(book_id):
    """写作时注入 planned + planted 清单（按重要度降序）。"""
    rows = fm.list_foreshadowings(book_id)
    sel = [r for r in rows if r["status"] in ("planned", "planted")]
    sel.sort(key=lambda r: -int(r.get("importance") or 0))
    if not sel:
        return ""
    lines = []
    for r in sel:
        lines.append(f"[重要度{int(r.get('importance') or 0)}][{r['status']}] {r['title']}"
                     + (f"：{r['content']}" if r.get("content") else ""))
    return "\n".join(lines)


def scan_text(book_id, text):
    """扫描正文匹配伏笔关键词 → 提示可标记回收（人工确认）。"""
    rows = fm.list_foreshadowings(book_id)
    out = []
    for r in rows:
        if r["status"] not in ("planted", "called"):
            continue
        kws = [k.strip() for k in (r.get("keywords") or "").split(",") if k.strip()]
        kws = kws or [r["title"]]
        hit = [k for k in kws if k and k in (text or "")]
        if hit:
            out.append({"id": r["id"], "title": r["title"], "status": r["status"], "matched": hit})
    return out


def unresolved_high(book_id, min_importance=4):
    """定稿前提醒：高重要度未回收伏笔。"""
    rows = fm.list_foreshadowings(book_id)
    return [r for r in rows
            if r["status"] != "resolved" and int(r.get("importance") or 0) >= min_importance]
