"""Mock provider：完全离线，用于无模型时联调界面与回归测试。"""
import time
from typing import Iterator

from server.adapters.llm import LLMAdapter


class MockProvider(LLMAdapter):
    def stream(self, messages: list[dict], params: dict | None = None) -> Iterator[str]:
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break
        reply = (
            "（演示模式 · mock 模型）已收到你的输入："
            f"「{last_user[:60]}」。"
            "这是本地占位回复，用于在无真实大模型时联调界面与流式渲染。"
            "配置本地 Ollama 或云端 OpenAI 兼容服务后即可获得真实写作辅助。"
        )
        # 按词切分模拟流式
        for ch in reply:
            yield ch
            time.sleep(0.004)

    def list_models(self) -> list[str]:
        return ["mock"]

    def health(self) -> dict:
        return {"ok": True, "error": "", "models": ["mock"]}

    def capabilities(self) -> dict:
        return {"streaming": True, "json_mode": True}

    def summarize(self, messages: list[dict]) -> str:
        return "[摘要] " + self._messages_to_text(messages)[-400:]
