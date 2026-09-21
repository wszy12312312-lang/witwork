"""OpenAI 兼容 provider：覆盖云端与 vLLM / 本地 OpenAI 协议服务。"""
import json

import httpx

from server.adapters.llm import LLMAdapter, LLMError


class OpenAIProvider(LLMAdapter):
    def __init__(self, provider: dict):
        super().__init__(provider)
        self.base = (self.base_url or "http://127.0.0.1:8000").rstrip("/")
        self.api_key = self.extra.get("api_key") or ""  # 测试用明文；生产走 secrets.enc
        self.timeout = float(self.extra.get("timeout", 120))

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def stream(self, messages: list[dict], params: dict | None = None) -> "Iterator[str]":
        params = params or {}
        payload = {
            "model": self.model or "gpt-4o-mini",
            "messages": messages,
            "stream": True,
            "temperature": params.get("temperature", 0.7),
        }
        if params.get("json_mode"):
            payload["response_format"] = {"type": "json_object"}
        try:
            with httpx.Client(timeout=self.timeout).stream(
                "POST", f"{self.base}/v1/chat/completions", headers=self._headers(), json=payload
            ) as r:
                if r.status_code != 200:
                    raise LLMError(f"OpenAI 兼容服务返回 {r.status_code}: {r.text[:200]}")
                for line in r.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = obj.get("choices", [{}])[0].get("delta", {}).get("content")
                    if delta:
                        yield delta
        except httpx.HTTPError as e:
            raise LLMError(f"OpenAI 兼容服务流式失败：{e}") from e

    def list_models(self) -> list[str]:
        try:
            r = httpx.get(f"{self.base}/v1/models", headers=self._headers(), timeout=10)
            if r.status_code == 200:
                return [m["id"] for m in r.json().get("data", [])]
        except httpx.HTTPError:
            pass
        return []

    def health(self) -> dict:
        try:
            r = httpx.get(f"{self.base}/v1/models", headers=self._headers(), timeout=10)
            if r.status_code == 200:
                return {"ok": True, "error": "", "models": [m["id"] for m in r.json().get("data", [])]}
            return {"ok": False, "error": f"HTTP {r.status_code}"}
        except httpx.HTTPError as e:
            return {"ok": False, "error": str(e)}

    def capabilities(self) -> dict:
        return {"streaming": True, "json_mode": True}
