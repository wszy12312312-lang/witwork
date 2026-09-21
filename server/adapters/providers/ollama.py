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
        # 超时：provider 自定义 > 全局配置 ai_timeout > 300s。
        # 旧默认值 60s 会在本地大模型（14B 级）长文生成时被中途掐断。
        try:
            from server.config import get as cfg_get
            fallback = float(cfg_get("ai_timeout", 300) or 300)
        except Exception:
            fallback = 300.0
        self.timeout = float(self.extra.get("timeout") or fallback)

    def _post(self, path: str, payload: dict):
        url = f"{self.base}{path}"
        try:
            return httpx.Client(timeout=self.timeout).stream("POST", url, json=payload)
        except httpx.HTTPError as e:  # 连接失败等
            raise LLMError(
                f"无法连接 Ollama（{url}）：{e}。请确认 Ollama 已启动（ollama serve）"
            ) from e

    def stream(self, messages: list[dict], params: dict | None = None) -> "Iterator[str]":
        params = params or {}
        options: dict = {"temperature": params.get("temperature", 0.7)}
        # 可选采样参数：只在显式给出时下发，避免改变既有默认行为
        for key, opt in (("top_p", "top_p"), ("num_predict", "num_predict"),
                         ("repeat_penalty", "repeat_penalty")):
            if params.get(key) is not None:
                options[opt] = params[key]
        payload = {
            "model": self.model or "qwen2.5:7b",
            "messages": messages,
            "stream": True,
            "options": options,
        }
        try:
            with self._post("/api/chat", payload) as r:
                if r.status_code != 200:
                    body = (r.text or "")[:200]
                    if r.status_code == 404 or "not found" in body.lower():
                        raise LLMError(
                            f"模型「{payload['model']}」在 Ollama 中不存在，请先执行 ollama pull {payload['model']}"
                        )
                    raise LLMError(f"Ollama 返回 {r.status_code}: {body}")
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("error"):
                        raise LLMError(f"Ollama 报错：{obj['error']}")
                    delta = obj.get("message", {}).get("content")
                    if delta:
                        yield delta
        except httpx.ReadTimeout as e:
            raise LLMError(
                f"模型响应超时（{self.timeout:.0f}s）。可在「设置 → 模型」提高超时，或换更小的模型"
            ) from e
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
