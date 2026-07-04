"""Provider package initialization.

Registers all built-in adapters with the provider registry so they can be
instantiated by id (`openai`, `anthropic`, `gemini`, `ollama`, `webllm`, `cli`).
"""
from __future__ import annotations

from .base import GenerateResult, LLMProvider, ProviderUsage
from .registry import ProviderRegistry, discover_providers, get_default_provider, registry
from .router import ProviderRouter, configure_from_env, get_provider, router

# Register built-in adapters
from .adapters import anthropic_adapter, gemini_adapter, ollama_adapter, openai_adapter, webllm_adapter
from .cli_adapter import CLIAgentProvider

ProviderRegistry.register("openai", openai_adapter.OpenAICompatibleProvider)
ProviderRegistry.register_alias("openrouter", "openai")
ProviderRegistry.register_alias("deepseek", "openai")
ProviderRegistry.register_alias("grok", "openai")
ProviderRegistry.register("anthropic", anthropic_adapter.AnthropicProvider)
ProviderRegistry.register("gemini", gemini_adapter.GeminiProvider)
ProviderRegistry.register("ollama", ollama_adapter.OllamaProvider)
ProviderRegistry.register("webllm", webllm_adapter.WebLLMProvider)
ProviderRegistry.register("cli", CLIAgentProvider)

__all__ = [
    "LLMProvider",
    "GenerateResult",
    "ProviderUsage",
    "ProviderRegistry",
    "ProviderRouter",
    "registry",
    "router",
    "get_provider",
    "discover_providers",
    "get_default_provider",
    "configure_from_env",
]
