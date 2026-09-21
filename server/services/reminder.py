"""更新提醒：按 update_plans 到点检查今日净增是否达标，未达标则推送站内通知；
连续 N 天未更新触发断更警告。进程内调度器每 60s 检查一次。"""
import datetime
import threading
import time

from server.db import get_conn
from server.services import stats as stats_svc

_BREAK_DAYS = 3
_started = False


def notify(book_id, kind, title, body=None):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO notifications(book_id, kind, title, body) VALUES (?,?,?,?)",
            (book_id, kind, title, body),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM notifications WHERE id=?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()


def list_notifications(unread_only=False, book_id=None):
    conn = get_conn()
    try:
        sql = "SELECT * FROM notifications"
        wh, args = [], []
        if unread_only:
            wh.append("read=0")
        if book_id is not None:
            wh.append("book_id=?")
            args.append(book_id)
        if wh:
            sql += " WHERE " + " AND ".join(wh)
        sql += " ORDER BY id DESC LIMIT 100"
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def mark_read(nid=None):
    conn = get_conn()
    try:
        if nid:
            conn.execute("UPDATE notifications SET read=1 WHERE id=?", (nid,))
        else:
            conn.execute("UPDATE notifications SET read=1")
        conn.commit()
    finally:
        conn.close()


def _already_today(book_id, kind):
    conn = get_conn()
    try:
        r = conn.execute(
            "SELECT 1 FROM notifications WHERE book_id IS ? AND kind=? AND date(created_at)=date('now') LIMIT 1",
            (book_id, kind),
        ).fetchone()
        return r is not None
    finally:
        conn.close()


def check_plans(now=None):
    """到点检查：今日净增 < 目标则提醒。返回触发数量。"""
    now = now or datetime.datetime.now()
    weekday = str(now.isoweekday())  # 1=周一 … 7=周日
    hhmm = now.strftime("%H:%M")
    fired = 0
    for p in stats_svc.list_plans():
        if not p.get("enabled"):
            continue
        if weekday not in (p.get("days") or "").split(","):
            continue
        if hhmm < (p.get("time_of_day") or "20:00"):
            continue
        book_id = p.get("book_id")
        goal = int(stats_svc.get_goal(book_id).get("daily_words") or 0)
        net = int(stats_svc.daily(book_id=book_id).get("net") or 0)
        if net >= goal:
            continue
        if _already_today(book_id, "reminder"):
            continue
        notify(book_id, "reminder", "今日更新未达标",
               f"目标 {goal} 字，当前净增 {net} 字，还差 {goal - net} 字。")
        fired += 1
    return fired


def check_break(book_id=None, days=_BREAK_DAYS):
    """连续 days 天净增为 0 → 断更警告。"""
    fired = 0
    targets = [book_id] if book_id is not None else sorted({p.get("book_id") for p in stats_svc.list_plans()})
    today = datetime.date.today()
    for bid in targets:
        zeros = 0
        for i in range(1, days + 1):
            d = (today - datetime.timedelta(days=i)).isoformat()
            if int(stats_svc.daily(d, bid).get("net") or 0) == 0:
                zeros += 1
            else:
                break
        if zeros >= days and not _already_today(bid, "break_warn"):
            notify(bid, "break_warn", f"已连续 {zeros} 天未更新", "别忘了回来写两笔。")
            fired += 1
    return fired


def test_reminder(book_id=None):
    return notify(book_id, "test", "测试提醒", "这是一条测试通知，用于验证提醒链路。")


def _loop():
    while True:
        try:
            check_plans()
            check_break()
        except Exception:
            pass
        time.sleep(60)


def start_scheduler():
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(target=_loop, daemon=True)
    t.start()
