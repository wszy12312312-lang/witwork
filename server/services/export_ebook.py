"""导出：Markdown / EPUB，以及设定（框架）导出 Markdown / JSON。

EPUB 为最小可用结构（mimetype + container.xml + content.opf + toc.ncx + xhtml），
纯 zipfile 实现，不依赖第三方库。导出前同样经排版引擎，保证与预览一致。
"""
import html
import json
import zipfile
from pathlib import Path

from server.config import DATA_DIR
from server.models import books as bm, chapters as chm
from server.models import knowledge as km, characters as cm, foreshadow as fm
from server.services import typesetting as ts

EXPORT_DIR = DATA_DIR / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def _gather(book_id, typeset=True):
    book = bm.get_book(book_id)
    if not book:
        raise ValueError("作品不存在")
    volumes = bm.list_volumes(book_id)
    rows = chm.list_chapters(book_id)
    out_vols = []
    for v in volumes:
        chs = []
        for c in rows:
            if (c.get("volume_id") or None) == v["id"]:
                full = chm.get_chapter(c["id"])
                content = (full.get("content") or "")
                if typeset and content:
                    content = ts.normalize(content, {})["content"]
                chs.append({"title": c.get("title") or "", "content": content})
        out_vols.append({"title": v["title"], "chapters": chs})
    free = []
    for c in rows:
        if not c.get("volume_id"):
            full = chm.get_chapter(c["id"])
            content = (full.get("content") or "")
            if typeset and content:
                content = ts.normalize(content, {})["content"]
            free.append({"title": c.get("title") or "", "content": content})
    return book, out_vols, free


# ---------------- Markdown ----------------
def export_md(book_id, typeset=True):
    book, vols, free = _gather(book_id, typeset)
    lines = [f"# {book['title']}", ""]
    if book.get("author"):
        lines += [f"> {book['author']}", ""]
    for v in vols:
        lines += [f"\n## {v['title']}\n"]
        for c in v["chapters"]:
            lines += [f"\n### {c['title']}\n", c["content"], ""]
    for c in free:
        lines += [f"\n### {c['title']}\n", c["content"], ""]
    text = "\n".join(lines)
    out = EXPORT_DIR / f"{book['title']}.md"
    out.write_text(text, encoding="utf-8")
    return {"path": str(out), "bytes": out.stat().st_size}


# ---------------- EPUB ----------------
def export_epub(book_id, typeset=True, filename=None):
    book, vols, free = _gather(book_id, typeset)
    name = filename or f"{book['title']}.epub"
    out = EXPORT_DIR / name

    chapters = []  # (title, xhtml_body)
    for v in vols:
        for c in v["chapters"]:
            chapters.append((c["title"], c["content"]))
    for c in free:
        chapters.append((c["title"], c["content"]))
    if not chapters:
        chapters = [("正文", "")]

    manifest, spine, nav = [], [], []
    for i, (title, content) in enumerate(chapters, 1):
        fn = f"chap_{i}.xhtml"
        body = "".join(f"<p>{html.escape(p.strip())}</p>"
                       for p in content.split("\n") if p.strip()) or "<p></p>"
        xhtml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<!DOCTYPE html>\n<html xmlns="http://www.w3.org/1999/xhtml">'
            f"<head><title>{html.escape(title)}</title></head>"
            f"<body><h2>{html.escape(title)}</h2>{body}</body></html>"
        )
        manifest.append(f'<item id="c{i}" href="{fn}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="c{i}"/>')
        nav.append(f'<navPoint id="np{i}" playOrder="{i}">'
                   f'<navLabel><text>{html.escape(title)}</text></navLabel>'
                   f'<content src="{fn}"/></navPoint>')
        chapters[i - 1] = (fn, xhtml, title)

    opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:title>{html.escape(book["title"])}</dc:title>'
        f'<dc:creator>{html.escape(book.get("author") or "佚名")}</dc:creator>'
        '<dc:language>zh-CN</dc:language>'
        '<dc:identifier id="bookid">inkrealm-book</dc:identifier>'
        "</metadata>"
        f'<manifest>{"".join(manifest)}'
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/></manifest>'
        f'<spine toc="ncx">{"".join(spine)}</spine></package>'
    )
    ncx = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        "<head><meta name=\"dtb:uid\" content=\"inkrealm-book\"/></head>"
        f"<docTitle><text>{html.escape(book['title'])}</text></docTitle>"
        f'<navMap>{"".join(nav)}</navMap></ncx>'
    )
    container = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )

    with zipfile.ZipFile(out, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip",
                   compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/toc.ncx", ncx, zipfile.ZIP_DEFLATED)
        for fn, xhtml, _title in chapters:
            z.writestr("OEBPS/" + fn, xhtml, zipfile.ZIP_DEFLATED)
    return {"path": str(out), "bytes": out.stat().st_size, "chapters": len(chapters)}


# ---------------- 设定（框架）导出 ----------------
def export_framework_md(book_id):
    book = bm.get_book(book_id)
    lines = [f"# {book['title']} · 设定", ""]
    for sec in km.list_sections():
        items = km.list_items(sec["key"])
        if not items:
            continue
        lines += [f"\n## {sec['title']}\n"]
        for it in items:
            lines += [f"### {it['title']}", it.get("content") or "", ""]
    chars = cm.list_characters(book_id)
    if chars:
        lines += ["\n## 人物\n"]
        for c in chars:
            bit = [f"### {c['name']}"]
            for f, label in (("appearance", "外貌"), ("personality", "性格"),
                             ("catchphrase", "口癖"), ("status_current", "状态"), ("taboo", "禁忌")):
                if c.get(f):
                    bit.append(f"- {label}：{c[f]}")
            lines += bit + [""]
    fores = fm.list_foreshadowings(book_id)
    if fores:
        lines += ["\n## 伏笔\n"]
        for f in fores:
            lines.append(f"- [{f['status']}][重要度{f['importance']}] {f['title']}：{f.get('content') or ''}")
    text = "\n".join(lines)
    out = EXPORT_DIR / f"{book['title']}-设定.md"
    out.write_text(text, encoding="utf-8")
    return {"path": str(out), "bytes": out.stat().st_size}


def export_framework_json(book_id):
    book = bm.get_book(book_id)
    data = {
        "book": book,
        "sections": [],
        "characters": cm.list_characters(book_id),
        "relations": cm.list_relations(book_id),
        "foreshadowings": fm.list_foreshadowings(book_id),
    }
    for sec in km.list_sections():
        items = km.list_items(sec["key"])
        if items:
            data["sections"].append({"key": sec["key"], "title": sec["title"], "items": items})
    text = json.dumps(data, ensure_ascii=False, indent=2)
    out = EXPORT_DIR / f"{book['title']}-设定.json"
    out.write_text(text, encoding="utf-8")
    return {"path": str(out), "bytes": out.stat().st_size}
