"""知识库服务：入库（切块+嵌入+FTS）、分区检索（RRF 融合）、版本与回滚。

检索 = 向量余弦 + 关键词（FTS5 trigram ≥3字 / LIKE 兜底短词）两路召回 → RRF(k=60) 融合 → top_k。
无真实嵌入时走哈希向量，仍可用关键词召回，离线可用。
"""
import re

from server.adapters.embedding import get_embedder, to_blob, from_blob, cosine
from server.config import get
from server.models import knowledge as km

_CHUNK = 480
_OVERLAP = 80
_RRF_K = 60


def chunk_text(text, size=_CHUNK, overlap=_OVERLAP):
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    out, i = [], 0
    while i < len(text):
        out.append(text[i : i + size])
        if i + size >= len(text):
            break
        i += max(1, size - overlap)
    return out


def _section_title_map():
    return {s["key"]: s["title"] for s in km.list_sections()}


class KnowledgeService:
    def __init__(self):
        self.emb = get_embedder()

    # ---- 入库 ----
    def ingest_text(self, section, title, content, source_type="manual", source_ref=None):
        km.ensure_section(section, title=section)
        item = km.create_item(section, title, content, source_type=source_type, source_ref=source_ref)
        km.add_version(item["id"], content, reason="初始入库")
        self._reindex(item["id"], content)
        km.set_current_version(item["id"], km.list_versions(item["id"])[0]["id"])
        return item

    def ingest_file(self, section, path, source_type="file"):
        text = _read_file(path)
        items = []
        # Markdown：按 ## 标题切块为多个条目
        blocks = _split_md(text)
        if len(blocks) <= 1:
            blocks = [("导入：" + _basename(path), text)]
        for title, body in blocks:
            if not body.strip():
                continue
            items.append(self.ingest_text(section, title.strip(), body.strip(), source_type=source_type, source_ref=path))
        return items

    def _reindex(self, item_id, content):
        chunks = chunk_text(content)
        embs = self.emb.embed(chunks)
        rows = []
        for text, vec in zip(chunks, embs):
            blob = to_blob(vec) if vec else None
            rows.append((text, blob, len(text)))
        km.replace_chunks(item_id, rows)

    # ---- 全量重索引（切换嵌入模型后必做，避免维度陈旧）----
    def reindex_all(self, section=None):
        from server.adapters.embedding import reset_embedders, get_embedder
        reset_embedders()
        self.emb = get_embedder()  # 重建为当前配置（hash / bge-m3 / ...）
        items = km.list_items(section)
        reindexed = 0
        skipped = 0
        for it in items:
            content = it.get("content") or ""
            if content.strip():
                self._reindex(it["id"], content)
                reindexed += 1
            else:
                skipped += 1
        return {"reindexed": reindexed, "skipped": skipped, "mode": self.emb.mode, "dim": self.emb.dim}

    # ---- 检索 ----
    def retrieve(self, query, sections=None, top_k=None):
        top_k = top_k or int(get("retrieval_top_k", 6))
        cands = km.candidate_chunks(sections)
        if not cands:
            return []
        # 向量路
        qvec = self.emb.embed([query], is_query=True)[0] if query.strip() else None
        vec_scores = {}
        for c in cands:
            if qvec:
                vec_scores[c["id"]] = cosine(qvec, from_blob(c["embedding"]))
        # 关键词路
        fts = km.fts_match(query, sections)
        like = km.like_match(query, sections)
        kw_scores = {}
        for c in cands:
            s = 0.0
            if c["id"] in like:
                s += 1.0
            if c["id"] in fts:
                s += 1.0 + max(0.0, -fts[c["id"]])
            if s > 0:
                kw_scores[c["id"]] = s

        fused = self._rrf(cands, vec_scores, kw_scores)
        fused.sort(key=lambda x: x["score"], reverse=True)
        hits = fused[:top_k]
        titles = _section_title_map()
        out = []
        for n, h in enumerate(hits, 1):
            out.append({
                "n": n,
                "item_id": h["item_id"],
                "section": h["section"],
                "section_title": titles.get(h["section"], h["section"]),
                "title": h["title"],
                "snippet": (h["text"][:160] + ("…" if len(h["text"]) > 160 else "")),
                "score": round(h["score"], 5),
            })
        return out

    def _rrf(self, cands, vec_scores, kw_scores):
        # 向量排名
        vec_rank = {}
        for rank, c in enumerate(sorted(cands, key=lambda x: -vec_scores.get(x["id"], 0.0)), 1):
            if vec_scores.get(c["id"], 0.0) > 0:
                vec_rank[c["id"]] = rank
        # 关键词排名
        kw_rank = {}
        for rank, c in enumerate(sorted(cands, key=lambda x: -kw_scores.get(x["id"], 0.0)), 1):
            if kw_scores.get(c["id"], 0.0) > 0:
                kw_rank[c["id"]] = rank
        out = []
        for c in cands:
            cid = c["id"]
            s = 0.0
            if cid in vec_rank:
                s += 1.0 / (_RRF_K + vec_rank[cid])
            if cid in kw_rank:
                s += 1.0 / (_RRF_K + kw_rank[cid])
            if s > 0:
                out.append({**c, "score": s})
        return out

    # ---- 注入文本 / 引用 ----
    def format_retrieval_text(self, hits):
        if not hits:
            return ""
        lines = []
        for h in hits:
            lines.append(f"[{h['n']}] （{h['section_title']}）{h['title']}\n{h['snippet']}")
        return "\n".join(lines)

    def format_citations(self, hits):
        return [
            {"n": h["n"], "section": h["section"], "section_title": h["section_title"], "title": h["title"], "snippet": h["snippet"]}
            for h in hits
        ]

    # ---- 版本 / 回滚 ----
    def update_item(self, item_id, title=None, content=None, reason="编辑", source_message_id=None):
        km.update_item(item_id, title=title, content=content)
        if content is not None:
            km.add_version(item_id, content, reason=reason, source_message_id=source_message_id)
            vs = km.list_versions(item_id)
            km.set_current_version(item_id, vs[0]["id"])
            self._reindex(item_id, content)
        return km.get_item(item_id)

    def rollback_version(self, item_id, version_id):
        v = next((x for x in km.list_versions(item_id) if x["id"] == version_id), None)
        if not v:
            return None
        km.update_item(item_id, content=v["content"])
        km.add_version(item_id, v["content"], reason=f"回滚到版本#{version_id}")
        vs = km.list_versions(item_id)
        km.set_current_version(item_id, vs[0]["id"])
        self._reindex(item_id, v["content"])
        return km.get_item(item_id)


def _read_file(path):
    text = open(path, "r", encoding="utf-8", errors="ignore").read()
    return text


def _split_md(text):
    # 按 ## 标题分块；无 ## 则返回整体
    parts = re.split(r"(?m)^##\s+", text)
    blocks = []
    for i, p in enumerate(parts):
        if i == 0:
            if p.strip():
                blocks.append(("总述", p))
            continue
        # 第一行作为标题
        lines = p.splitlines()
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        blocks.append((title, body))
    return blocks


def _basename(path):
    import os
    return os.path.splitext(os.path.basename(path))[0]


_service = None


def get_service():
    global _service
    if _service is None:
        _service = KnowledgeService()
    return _service
