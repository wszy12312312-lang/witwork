from fastapi import APIRouter, HTTPException

from server.core.diff import line_diff
from server.models import books as book_m, chapters as chap_m, snapshots as snap_m

router = APIRouter(prefix="/chapters", tags=["chapters"])


@router.post("")
def create_chapter(payload: dict):
    book_id = payload.get("book_id")
    if not book_m.get_book(book_id):
        raise HTTPException(404, "book not found")
    return chap_m.create_chapter(
        book_id,
        title=payload.get("title", "未命名章节"),
        volume_id=payload.get("volume_id"),
        content=payload.get("content", ""),
        sort_order=payload.get("sort_order", 0),
    )


@router.get("/{chapter_id}")
def get_chapter(chapter_id: int):
    ch = chap_m.get_chapter(chapter_id)
    if not ch:
        raise HTTPException(404, "chapter not found")
    return ch


@router.put("/{chapter_id}")
def update_chapter(chapter_id: int, payload: dict):
    ch = chap_m.get_chapter(chapter_id)
    if not ch:
        raise HTTPException(404, "chapter not found")
    before = ch.get("content") or ""
    updated = chap_m.update_chapter(chapter_id, payload)
    after = updated.get("content") or ""
    # Step16：保存时按 diff 记净增（新增/删除分别计）
    if before != after:
        try:
            from server.services import stats as stats_svc
            stats_svc.record_save(updated.get("book_id"), chapter_id, before, after)
        except Exception:
            pass
    return updated


@router.delete("/{chapter_id}")
def delete_chapter(chapter_id: int):
    if not chap_m.get_chapter(chapter_id):
        raise HTTPException(404, "chapter not found")
    chap_m.soft_delete_chapter(chapter_id)
    return {"ok": True}


@router.post("/{chapter_id}/restore")
def restore_chapter(chapter_id: int):
    """从回收站恢复单章（若其所属卷也被删，一并放回，否则恢复后仍不可见）。"""
    ch = chap_m.restore_chapter(chapter_id)
    if not ch:
        raise HTTPException(404, "chapter not found")
    return ch


@router.post("/{chapter_id}/snapshots")
def create_snapshot(chapter_id: int, payload: dict):
    ch = chap_m.get_chapter(chapter_id)
    if not ch:
        raise HTTPException(404, "chapter not found")
    return snap_m.create_snapshot(
        ch["book_id"],
        chapter_id,
        kind=payload.get("kind", "manual"),
        title=payload.get("title", "手动快照"),
        content=ch["content"],
        trigger=payload.get("trigger"),
    )


@router.get("/{chapter_id}/snapshots")
def list_snapshots(chapter_id: int):
    return snap_m.list_snapshots(chapter_id)


@router.post("/snapshots/{snapshot_id}/restore")
def restore_snapshot(snapshot_id: int):
    snap = snap_m.get_snapshot(snapshot_id)
    if not snap:
        raise HTTPException(404, "snapshot not found")
    # 仅恢复正文，不覆盖真实章节标题
    return chap_m.update_chapter(snap["chapter_id"], {"content": snap["content"]})


@router.get("/{chapter_id}/diff")
def diff(chapter_id: int, snapshot_id: int):
    ch = chap_m.get_chapter(chapter_id)
    snap = snap_m.get_snapshot(snapshot_id)
    if not ch or not snap:
        raise HTTPException(404, "not found")
    return {
        "chapter_id": chapter_id,
        "snapshot_id": snapshot_id,
        "diff": line_diff(snap["content"], ch["content"]),
    }
