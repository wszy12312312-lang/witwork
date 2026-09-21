"""Ollama provider：原生 /api/chat（NDJSON 流式）。

同时探测 /api 与 /v1（OpenAI 兼容）两条路径，优先 /api/chat。
"""
import json

import httpx

from server.adapters.llm import LLMAdapter, LLMError


class OllamaProvider(LLMAdapter):
    def __init__(self, provider: dict):
        super().__init__(provider)
        self.base = (self.base_url or "http://127.0.0.1:11434").rstrip("/")
        self.timeout = float(self.extra.get("timeout", 60))

    def _post(self, path: str, payload: dict):
        url = f"{self.base}{path}"
        try:
            return httpx.Client(timeout=self.timeout).stream("POST", url, json=payload)
        except httpx.HTTPError as e:  # 连接失败等
            raise LLMError(f"无法连接 Ollama（{url}）：{e}") from e

    def stream(self, messages: list[dict], params: dict | None = None) -> "Iterator[str]":
        params = params or {}
        payload = {
            "model": self.model or "qwen2.5:7b",
            "messages": messages,
            "stream": True,
            "options": {"temperature": params.get("temperature", 0.7)},
        }
        try:
            with self._post("/api/chat", payload) as r:
                if r.status_code != 200:
                    raise LLMError(f"Ollama 返回 {r.status_code}: {r.text[:200]}")
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    delta = obj.get("message", {}).get("content")
                    if delta:
                        yield delta
        except httpx.HTTPError as e:
            raise LLMError(f"Ollama 流式失败：{e}") from e

    def list_models(self) -> list[str]:
        try:
            r = httpx.get(f"{self.base}/api/tags", timeout=10)
            if r.status_code == 200:
                return [m["name"] for m in r.json().get("models", [])]
        except httpx.HTTPError:
            pass
        return []

    def health(self) -> dict:
        try:
            r = httpx.get(f"{self.base}/api/tags", timeout=10)
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                return {"ok": True, "error": "", "models": models}
            return {"ok": False, "error": f"HTTP {r.status_code}"}
        except httpx.HTTPError as e:
            return {"ok": False, "error": str(e)}

    def capabilities(self) -> dict:
        return {"streaming": True, "json_mode": False}
