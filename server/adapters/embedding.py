"""嵌入适配器：本地哈希向量（离线可用）+ Ollama /v1/embeddings 真实向量。

- 默认走 hash：n-gram（CJK 单字/双语素 + 英文词）确定性散列到定长向量，离线、可复现。
- 配置 embedding != 'hash' 时视为 Ollama 模型名，调用本地 /v1/embeddings；失败自动降级 hash。
- 向量以 float32 BLOB 存库（to_blob / from_blob）。
"""
import hashlib
import math
import re
import struct

import httpx

from server.config import get

DIM = 256  # hash 模式固定维度；Ollama 模式维度随模型，读取后原样返回

_RE_WORD = re.compile(r"[a-z0-9]+")


def _ngrams(text):
    grams = set()
    cjk = [c for c in (text or "") if "一" <= c <= "鿿"]
    for c in cjk:
        grams.add("c:" + c)
    for i in range(len(cjk) - 1):
        grams.add("b:" + cjk[i] + cjk[i + 1])
    for w in _RE_WORD.findall((text or "").lower()):
        grams.add("w:" + w)
    return grams


def _hash_dim(g):
    return int.from_bytes(hashlib.md5(g.encode("utf-8")).digest()[:4], "big") % DIM


def _hash_sign(g):
    return 1.0 if (int.from_bytes(hashlib.md5(g.encode("utf-8")).digest()[4:8], "big") & 1) else -1.0


def hash_embed(text: str):
    vec = [0.0] * DIM
    for g in _ngrams(text or ""):
        vec[_hash_dim(g)] += _hash_sign(g)
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def to_blob(vec) -> bytes:
    return struct.pack("<" + "f" * len(vec), *vec)


def from_blob(blob) -> list:
    if not blob:
        return []
    n = len(blob) // 4
    return list(struct.unpack("<" + "f" * n, blob))


def cosine(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class EmbedAdapter:
    def __init__(self, mode=None):
        self.mode = mode or get("embedding", "hash")
        self.dim = DIM
        self.last_error = None

    def embed(self, texts, is_query=False):
        if not texts:
            return []
        if self.mode == "hash":
            return [hash_embed(t) for t in texts]
        # Ollama / OpenAI 兼容 /v1/embeddings
        base = get("embedding_base_url") or "http://127.0.0.1:11434/v1/embeddings"
        model = self.mode
        # bge-m3 检索建议：查询侧加指令前缀（文档侧不加），语义召回质量明显提升
        inputs = texts
        if is_query and model == "bge-m3":
            inputs = ["Represent this sentence for searching relevant passages: " + t for t in texts]
        try:
            with httpx.Client(timeout=20) as c:
                r = c.post(base, json={"model": model, "input": inputs})
                r.raise_for_status()
                data = r.json().get("data", [])
                vecs = [d["embedding"] for d in sorted(data, key=lambda d: d.get("index", 0))]
                if len(vecs) == len(texts):
                    self.dim = len(vecs[0])
                    return vecs
                raise ValueError("embedding 数量不匹配")
        except Exception as e:
            self.last_error = str(e)
            # 降级 hash，保证离线可用
            return [hash_embed(t) for t in texts]


_adapter = None


def get_embedder():
    global _adapter
    if _adapter is None:
        _adapter = EmbedAdapter()
    return _adapter


def reset_embedders():
    """丢弃已缓存的适配器（配置 embedding 切换后强制重建，避免维度/模式陈旧）。"""
    global _adapter
    _adapter = None
