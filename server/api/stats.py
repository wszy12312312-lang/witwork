"""写作统计与更新提醒 API。"""
import datetime

from fastapi import APIRouter

from server.services import stats as stats_svc
from server.services import reminder as rem_svc

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/daily")
def daily(date: str | None = None, book_id: int | None = None):
    return stats_svc.daily(date, book_id)


@router.get("/range")
def range_(start: str, end: str, book_id: int | None = None):
    return stats_svc.range_stats(start, end, book_id)


@router.get("/heatmap")
def heatmap(book_id: int | None = None, days: int = 180):
    return stats_svc.heatmap(book_id, days)


@router.get("/streak")
def streak(book_id: int | None = None):
    return {"days": stats_svc.streak(book_id)}


@router.get("/goals")
def get_goal(book_id: int | None = None):
    return stats_svc.get_goal(book_id)


@router.put("/goals")
def set_goal(payload: dict):
    return stats_svc.set_goal(payload.get("book_id"), payload.get("daily_words", 2000))


@router.get("/update-plans")
def plans(book_id: int | None = None):
    return stats_svc.list_plans(book_id)


@router.post("/update-plans")
def add_plan(payload: dict):
    return stats_svc.add_plan(payload.get("book_id"), payload.get("time_of_day", "20:00"),
                              payload.get("days", "1,2,3,4,5,6,7"), payload.get("enabled", 1))


@router.delete("/update-plans/{pid}")
def del_plan(pid: int):
    stats_svc.delete_plan(pid)
    return {"ok": True}


@router.post("/reminders/test")
def test_reminder(payload: dict | None = None):
    body = payload or {}
    return rem_svc.test_reminder(body.get("book_id"))


@router.get("/notifications")
def notifications(unread: bool = False, book_id: int | None = None):
    return rem_svc.list_notifications(unread, book_id)


@router.post("/notifications/read")
def read(payload: dict | None = None):
    nid = (payload or {}).get("id")
    rem_svc.mark_read(nid)
    return {"ok": True}


@router.get("/today")
def today(book_id: int | None = None):
    """聚合今日概览：字数 + 目标 + 连续天数。"""
    d = stats_svc.daily(book_id=book_id)
    goal = stats_svc.get_goal(book_id)
    return {
        "date": datetime.date.today().isoformat(),
        "net": d.get("net", 0),
        "added": d.get("words_added", 0),
        "deleted": d.get("words_deleted", 0),
        "minutes": d.get("minutes", 0),
        "goal": goal.get("daily_words", 2000),
        "streak": stats_svc.streak(book_id),
    }
