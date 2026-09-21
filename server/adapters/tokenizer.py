"""Token 估算。

优先用模型返回的 usage（精确）；否则兜底：中文约 1.5 字/token，英文约 4 字符/token 的近似。
"""
import math


def estimate_tokens(text: str) -> int:
    """无需外部依赖的近似估算。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    non_cjk = len(text) - cjk
    # 中文 1.5 字/token；其余按 ~4 字符/token
    return max(1, math.ceil(cjk / 1.5 + non_cjk / 4))


def estimate_messages(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        total += estimate_tokens(m.get("content", "")) + 4  # 每条约 4 token 开销
    return total


def from_usage(usage) -> int | None:
    """若 provider 返回 usage.prompt_tokens 则直接用。"""
    if isinstance(usage, dict):
        return usage.get("prompt_tokens")
    return None
