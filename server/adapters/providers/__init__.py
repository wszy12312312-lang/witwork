"""Provider 实现包。导入本模块即完成注册。"""
from server.adapters.providers.mock import MockProvider
from server.adapters.providers.ollama import OllamaProvider
from server.adapters.providers.openai import OpenAIProvider
from server.adapters.llm import ProviderRegistry

ProviderRegistry.register("mock", MockProvider)
ProviderRegistry.register("ollama", OllamaProvider)
ProviderRegistry.register("openai", OpenAIProvider)

__all__ = ["MockProvider", "OllamaProvider", "OpenAIProvider"]
