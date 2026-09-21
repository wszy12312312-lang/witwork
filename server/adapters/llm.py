"""LLM Provider 抽象层。

统一接口：stream / list_models / health / capabilities。
新增 provider 只需实现 LLMAdapter 并在 REGISTRY 注册。
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Iterator


class LLMError(Exception):
    pass


class LLMAdapter(ABC):
    """所有 provider 的统一契约。

    stream() 同步产出文本增量（delta），由上层包成 SSE。
    """

    def __init__(self, provider: dict):
        self.provider = provider
        self.id = provider.get("id")
        self.kind = provider.get("kind")
        self.name = provider.get("name") or self.kind
        self.model = provider.get("model")
        self.base_url = provider.get("base_url")
        extra = provider.get("extra_json")
        self.extra = json.loads(extra) if isinstance(extra, str) and extra else (extra or {})

    @abstractmethod
    def stream(self, messages: list[dict], params: dict | None = None) -> Iterator[str]:
        """产出文本增量。messages: [{role, content}]。"""
        raise NotImplementedError

    @abstractmethod
    def health(self) -> dict:
        """返回 {"ok": bool, "error": str, "models": [...] }。"""
        raise NotImplementedError

    @abstractmethod
    def list_models(self) -> list[str]:
        ...

    def capabilities(self) -> dict:
        """能力声明驱动 UI：streaming / json_mode。"""
        return {"streaming": True, "json_mode": False}

    # 通用工具：把若干消息压成一段纯文本（摘要用）
    def _messages_to_text(self, messages: list[dict]) -> str:
        return "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages)


class ProviderRegistry:
    _REGISTRY: dict[str, type[LLMAdapter]] = {}

    @classmethod
    def register(cls, kind: str, adapter: type[LLMAdapter]):
        cls._REGISTRY[kind] = adapter

    @classmethod
    def build(cls, provider: dict) -> LLMAdapter:
        kind = (provider.get("kind") or "").lower()
        impl = cls._REGISTRY.get(kind)
        if not impl:
            raise LLMError(f"未知 provider 类型: {kind}")
        return impl(provider)

    @classmethod
    def kinds(cls) -> list[str]:
        return sorted(cls._REGISTRY.keys())


def get_adapter(provider: dict) -> LLMAdapter:
    return ProviderRegistry.build(provider)
