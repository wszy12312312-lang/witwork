"""从 AI 输出中抽取结构化写回补丁块与引用标记。

约定：补丁放在 ```json ... ``` 围栏内，内容为 {"patches":[...]}。
抽取后从展示文本中剥离该围栏，避免用户看到原始 JSON。
"""
import json
import re

_FENCE = re.compile(r"```json\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_INLINE = re.compile(r"\{\s*\"patches\"\s*:\s*\[.*?\]\s*\}", re.DOTALL)


def extract_patches(text):
    """返回补丁 dict 列表。"""
    out = []
    for m in _FENCE.finditer(text or ""):
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict) and isinstance(obj.get("patches"), list):
                out.extend(obj["patches"])
        except Exception:
            continue
    if not out:
        for m in _INLINE.finditer(text or ""):
            try:
                obj = json.loads(m.group(0))
                if isinstance(obj.get("patches"), list):
                    out.extend(obj["patches"])
            except Exception:
                continue
    return out


def strip_patches(text):
    """去掉展示文本中的补丁围栏。"""
    return _FENCE.sub("", text or "").strip()


def extract_citation_marks(text):
    """返回文本中出现的引用编号集合，如 [1][2]。"""
    return sorted(set(int(x) for x in re.findall(r"\[(\d+)\]", text or "")))
