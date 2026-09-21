"""词条服务：CRUD / 从正文抽取候选（新词发现）/ 异写归一化。"""
import re

from server.models import entries as em, chapters as chm

_STOP = set("的了是在和与就不都有会很也能还说要对把被从给让向但而或于之其所这那你我他她它们个们上下中里外前后左右")
_CJK = re.compile(r"[\u4e00-\u9fff]+")


def create(book_id, name, category=None, aliases=None, description=None, first_chapter_id=None):
    return em.create_entry(book_id, name, category, aliases, description, first_chapter_id)


def list_all(book_id=None, category=None):
    return em.list_entries(book_id, category)


def get(eid):
    return em.get_entry(eid)


def update(eid, fields):
    return em.update_entry(eid, fields)


def delete(eid):
    em.delete_entry(eid)


def _ngram_freq(text, n_min=2, n_max=4):
    freq = {}
    for seg in _CJK.findall(text or ""):
        for n in range(n_min, n_max + 1):
            for i in range(len(seg) - n + 1):
                g = seg[i:i + n]
                freq[g] = freq.get(g, 0) + 1
    return freq


def extract(book_id, texts, top_n=30, min_count=2):
    """新词发现：2-4 字 CJK n-gram 词频，剔除停用字、已有词条、被更长词覆盖的短词。"""
    if isinstance(texts, str):
        texts = [texts]
    freq = {}
    for t in texts:
        for g, c in _ngram_freq(t).items():
            freq[g] = freq.get(g, 0) + c
    em.save_word_freq(book_id, freq)
    known = em.all_entry_names(book_id)
    cands = []
    for g, c in freq.items():
        if c < min_count or g in known:
            continue
        if any(ch in _STOP for ch in g):
            continue
        cands.append({"word": g, "count": c})
    # 去掉被更长高频词覆盖的短词
    cands.sort(key=lambda x: -x["count"])
    kept = []
    for cd in cands:
        g = cd["word"]
        covered = any(
            (g != o["word"] and g in o["word"] and o["count"] >= cd["count"] * 0.8)
            for o in cands
        )
        if not covered:
            kept.append(cd)
        if len(kept) >= top_n:
            break
    return kept


def normalize(book_id, chapter_ids=None):
    """按规范词形统一异写：把别名替换为规范词，返回每章替换次数。"""
    entries = em.list_entries(book_id)
    pairs = []
    for e in entries:
        aliases = []
        try:
            import json
            aliases = json.loads(e.get("aliases_json") or "[]")
        except Exception:
            aliases = []
        for a in aliases:
            if a and a != e["name"]:
                pairs.append((a, e["name"]))
    if not pairs:
        return {}
    ids = chapter_ids
    if not ids:
        rows = chm.list_chapters(book_id)
        ids = [r["id"] for r in rows]
    out = {}
    for cid in ids:
        ch = chm.get_chapter(cid)
        if not ch:
            continue
        content = ch.get("content") or ""
        total = 0
        for a, canon in pairs:
            total += content.count(a)
            content = content.replace(a, canon)
        if total:
            chm.update_chapter(cid, {"content": content})
            out[cid] = total
    return out
