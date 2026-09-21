from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from urllib.parse import quote

from server.models import books as book_m, chapters as chap_m

router = APIRouter(prefix="/books", tags=["books"])


@router.get("")
def get_books(include_trashed: bool = False):
    return book_m.list_books(include_trashed=include_trashed)


@router.post("")
def create_book(payload: dict):
    title = (payload.get("title") or "未命名作品").strip() or "未命名作品"
    return book_m.create_book(
        title=title,
        author=payload.get("author"),
        summary=payload.get("summary"),
        cover_path=payload.get("cover_path"),
    )


# ⚠️ 必须声明在 GET /{book_id} 之前：否则 "/books/trash" 会被 {book_id} 吃掉（返回 404）。
@router.get("/trash")
def get_trash():
    """回收站：作品 / 卷 / 章节三类已删除项，供前端统一展示与恢复。"""
    return book_m.list_trashed()


@router.get("/{book_id}")
def get_book(book_id: int):
    book = book_m.get_book(book_id)
    if not book:
        raise HTTPException(404, "book not found")
    volumes = book_m.list_volumes(book_id)
    chapters = chap_m.list_chapters(book_id)
    return {**book, "volumes": volumes, "chapters": chapters}


@router.put("/{book_id}")
def update_book(book_id: int, payload: dict):
    if not book_m.get_book(book_id):
        raise HTTPException(404, "book not found")
    return book_m.update_book(book_id, payload)


@router.delete("/{book_id}")
def delete_book(book_id: int):
    if not book_m.get_book(book_id):
        raise HTTPException(404, "book not found")
    book_m.soft_delete_book(book_id)
    return {"ok": True}


@router.post("/{book_id}/restore")
def restore_book(book_id: int):
    book_m.restore_book(book_id)
    return {"ok": True}


@router.post("/{book_id}/volumes")
def create_volume(book_id: int, payload: dict):
    if not book_m.get_book(book_id):
        raise HTTPException(404, "book not found")
    return book_m.create_volume(
        book_id, payload.get("title", "正文卷"), payload.get("sort_order", 0)
    )


@router.put("/volumes/{volume_id}")
def update_volume(volume_id: int, payload: dict):
    v = book_m.update_volume(volume_id, payload)
    if not v:
        raise HTTPException(404, "volume not found")
    return v


@router.delete("/volumes/{volume_id}")
def delete_volume(volume_id: int):
    """删除单卷（软删）：卷 + 其下章节一并进回收站，可整体恢复。"""
    if not book_m.get_volume(volume_id):
        raise HTTPException(404, "volume not found")
    return book_m.soft_delete_volume(volume_id)


@router.post("/volumes/{volume_id}/restore")
def restore_volume(volume_id: int):
    r = book_m.restore_volume(volume_id)
    if not r:
        raise HTTPException(404, "volume not found")
    return r


@router.get("/{book_id}/export")
def export_book(book_id: int, fmt: str = "txt"):
    book = book_m.get_book(book_id)
    if not book:
        raise HTTPException(404, "book not found")
    if fmt != "txt":
        raise HTTPException(400, "only txt supported in M1")
    chapters = chap_m.list_chapters(book_id)
    volumes = book_m.list_volumes(book_id)
    vol_map = {v["id"]: v["title"] for v in volumes}
    chap_by_vol = {}
    no_vol = []
    for ch in chapters:
        if ch["volume_id"]:
            chap_by_vol.setdefault(ch["volume_id"], []).append(ch)
        else:
            no_vol.append(ch)
    lines = [book["title"], ""]
    if book.get("author"):
        lines += ["作者：" + book["author"], ""]
    for v in volumes:
        lines += ["", "", "## " + v["title"], ""]
        for ch in chap_by_vol.get(v["id"], []):
            full = chap_m.get_chapter(ch["id"]) or ch
            lines += ["", "# " + ch["title"], "", full.get("content", "")]
    for ch in no_vol:
        full = chap_m.get_chapter(ch["id"]) or ch
        lines += ["", "# " + ch["title"], "", full.get("content", "")]
    text = "\n".join(lines)
    # 文件名含中文，需用 RFC 5987 编码；并附 ASCII 回退
    safe = f"book_{book['id']}.txt"
    disp = f"attachment; filename=\"{safe}\"; filename*=UTF-8''{quote(book['title'] + '.txt')}"
    return PlainTextResponse(text, headers={"Content-Disposition": disp})
