"""兼容工具：高频词透镜 / AI 味自查 / 合规词自检 / 外部服务探测。

- 全部离线可跑；外部服务（SD WebUI / ComfyUI / piper TTS）未启动时返回「不可用」而不报错，
  界面据此置灰并给安装提示。
"""
import math
import re
from collections import Counter
from pathlib import Path

import httpx

from server.config import get

_WORDS_PATH = Path(__file__).resolve().parent.parent / "core" / "compliance_words.txt"
_CJK = re.compile(r"[\u4e00-\u9fff]+")
_SENT = re.compile(r"[。！？!?；;]")

AI_TRANSITIONS = [
    "首先", "其次", "再次", "此外", "然而", "因此", "总之", "综上", "总的来说",
    "值得注意的是", "需要指出的是", "某种意义上", "可以说", "进一步", "通过",
    "进行", "实现", "有效", "不仅", "而且", "同时", "随着",
]
_STOP = set("的了是在和与就不都有会很也能还说要对把被从给让向但而或于之其所这那你我他她它们个们上下中里外前后左右")


# ---------------- 高频词透镜 ----------------
def word_freq(text, top_n=50, min_len=2, max_len=4):
    freq = Counter()
    for seg in _CJK.findall(text or ""):
        for n in range(min_len, max_len + 1):
            for i in range(len(seg) - n + 1):
                freq[seg[i:i + n]] += 1
    items = [{"word": w, "count": c} for w, c in freq.items()
             if c >= 2 and not any(ch in _STOP for ch in w)]
    items.sort(key=lambda x: -x["count"])
    kept = []
    for it in items:
        covered = any(it["word"] != o["word"] and it["word"] in o["word"]
                      and o["count"] >= it["count"] * 0.8 for o in items)
        if not covered:
            kept.append(it)
        if len(kept) >= top_n:
            break
    return kept


# ---------------- AI 味自查 ----------------
def _entropy(counter):
    total = sum(counter.values())
    if not total:
        return 0.0
    return -sum((c / total) * math.log2(c / total) for c in counter.values() if c)


def ai_taste(text):
    """返回总分（越高越像 AI）与逐段标注。"""
    raw = text or ""
    paras = [p.strip() for p in raw.split("\n") if p.strip()]
    out = []
    for i, p in enumerate(paras):
        sents = [s for s in _SENT.split(p) if s.strip()]
        lens = [len(s) for s in sents] or [len(p)]
        mean = sum(lens) / len(lens)
        var = sum((x - mean) ** 2 for x in lens) / len(lens)
        cv = (math.sqrt(var) / mean) if mean else 0.0
        chars = [c for c in p if "\u4e00" <= c <= "\u9fff"]
        bigrams = [p[j:j + 2] for j in range(len(p) - 1)]
        rep = 0.0
        if bigrams:
            bc = Counter(bigrams)
            rep = sum(c - 1 for c in bc.values() if c > 1) / len(bigrams)
        trans = sum(p.count(w) for w in AI_TRANSITIONS)
        trans_density = trans / max(1, len(chars)) * 1000
        # 打分：句长越均匀、重复二元越高、过渡词越密 → 越像 AI
        s_cv = max(0.0, 1.0 - cv / 0.8) * 40
        s_rep = min(1.0, rep / 0.25) * 35
        s_tr = min(1.0, trans_density / 12.0) * 25
        score = int(round(s_cv + s_rep + s_tr))
        out.append({
            "index": i, "score": score, "chars": len(chars),
            "sent_cv": round(cv, 3), "bigram_repeat": round(rep, 3),
            "transitions": trans, "entropy": round(_entropy(Counter(chars)), 2),
            "text": p[:60],
        })
    overall = int(round(sum(x["score"] for x in out) / len(out))) if out else 0
    return {"score": overall, "paragraphs": out,
            "signals": ["句长方差", "重复 n-gram", "AI 高频过渡词", "词频熵", "标点分布"]}


# ---------------- 合规词自检 ----------------
def load_compliance_words():
    if not _WORDS_PATH.exists():
        return []
    return [ln.strip() for ln in _WORDS_PATH.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def compliance(text, custom=None):
    words = set(load_compliance_words()) | {w for w in (custom or []) if w}
    hits = []
    for w in sorted(words):
        n = (text or "").count(w)
        if n:
            idx = (text or "").find(w)
            hits.append({"word": w, "count": n, "pos": idx,
                         "context": text[max(0, idx - 12): idx + len(w) + 12]})
    return {"hits": hits, "total": sum(h["count"] for h in hits), "word_count": len(words)}


# ---------------- 外部服务探测 ----------------
def _probe(url, timeout=1.5):
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.get(url)
            return r.status_code < 500
    except Exception:
        return False


def probe_services():
    """探测本地可选服务；未启动返回 available=False，界面据此置灰。"""
    sd = get("sd_url", "http://127.0.0.1:7860")
    comfy = get("comfy_url", "http://127.0.0.1:8188")
    return {
        "sd_webui": {"url": sd, "available": _probe(sd + "/docs"),
                     "hint": "启动 Stable Diffusion WebUI 后可用（默认 7860）"},
        "comfyui": {"url": comfy, "available": _probe(comfy + "/history"),
                    "hint": "启动 ComfyUI 后可用（默认 8188）"},
        "tts": {"url": "local", "available": False,
                "hint": "接入本地 piper 或系统 TTS 后可用"},
    }
