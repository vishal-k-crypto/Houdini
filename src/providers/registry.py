"""Provider registry for discovering and instantiating LLM adapters.

The registry scans configuration, environment variables, and optionally the
system PATH to detect available providers (OpenAI, Anthropic, Gemini, Ollama,
CLI agents like Claude Code/Codex, etc.).
"""
from __future__ import annotations

import importlib
import os
import shutil
import sys
from pkgutil import iter_modules
from typing import Any, Dict, List, Optional, Type

from .base import LLMProvider


class ProviderRegistry:
    """Central registry for LLM provider adapters."""

    _providers: Dict[str, Type[LLMProvider]] = {}

    @classmethod
    def register(cls, provider_id: str, adapter_class: Type[LLMProvider]) -> None:
        """Register an adapter class under a provider id."""
        provider_id = provider_id.lower()
        cls._providers[provider_id] = adapter_class

    @classmethod
    def register_alias(cls, alias: str, provider_id: str) -> None:
        """Register an alias pointing to an existing provider id."""
        alias = alias.lower()
        provider_id = provider_id.lower()
        if provider_id not in cls._providers:
            raise KeyError(f"Cannot alias unknown provider: {provider_id}")
        cls._providers[alias] = cls._providers[provider_id]

    @classmethod
    def get(cls, provider_id: str) -> Optional[Type[LLMProvider]]:
        """Return the adapter class for a provider id, or None."""
        return cls._providers.get(provider_id.lower())

    @classmethod
    def list_providers(cls) -> List[str]:
        """Return all registered provider ids."""
        return sorted(cls._providers.keys())

    @classmethod
    def create(
        cls,
        provider_id: str,
        model_name: Optional[str] = None,
        **kwargs,
    ) -> LLMProvider:
        """Instantiate a provider adapter by id."""
        adapter_class = cls.get(provider_id)
        if adapter_class is None:
            raise ValueError(
                f"Unknown provider '{provider_id}'. "
                f"Available: {', '.join(cls.list_providers())}"
            )
        return adapter_class(model_name=model_name, **kwargs)

    @classmethod
    def detect_available(cls) -> Dict[str, Dict[str, Any]]:
        """Return a dict of providers that appear available on this system.

        For local/API providers, this checks environment variables and optional
        health endpoints. For CLI agents, it checks PATH.
        """
        available: Dict[str, Dict[str, Any]] = {}

        for provider_id in cls.list_providers():
            adapter_class = cls._providers[provider_id]
            try:
                if hasattr(adapter_class, "detect") and callable(
                    getattr(adapter_class, "detect")
                ):
                    detect = getattr(adapter_class, "detect")
                    info = detect()
                    if info and info.get("available"):
                        available[provider_id] = info
                else:
                    # Default: if a provider requires a key, check for env var
                    env_key = (
                        getattr(adapter_class, "ENV_KEY", None)
                        if hasattr(adapter_class, "ENV_KEY")
                        else None
                    )
                    if env_key and os.environ.get(env_key):
                        available[provider_id] = {"available": True, "source": env_key}
            except Exception:
                # Detection failures should not break the registry
                pass

        return available

    @classmethod
    def detect_deep(cls) -> Dict[str, Dict[str, Any]]:
        """Deep scan: env vars, PATH, Ollama tags, and CLI agents."""
        available = cls.detect_available()

        # Enrich with CLI agents
        try:
            from .cli_adapter import list_available_cli_agents_info
            cli_agents = list_available_cli_agents_info()
            if cli_agents:
                available["cli"] = {
                    "available": True,
                    "source": "PATH",
                    "agents": cli_agents,
                }
        except Exception:
            pass

        # Try to list Ollama models dynamically
        if "ollama" in available:
            try:
                import json
                import urllib.request
                url = f"{(os.environ.get('OLLAMA_ENDPOINT') or 'http://localhost:11434').rstrip('/')}/api/tags"
                with urllib.request.urlopen(url, timeout=2) as resp:
                    data = resp.read().decode()
                    models = json.loads(data).get("models", [])
                    available["ollama"]["models"] = [m.get("name") for m in models]
            except Exception:
                pass

        return available


    @classmethod
    def auto_load(cls, package: str = "src.providers.adapters") -> None:
        """Dynamically import adapter modules in a package and register them.

        Each adapter module should define a class named
        `<ProviderId>Provider` and call `register()` at import time, or define
        `__provider_id__` and `__provider_class__` module attributes.
        """
        try:
            package_module = importlib.import_module(package)
            package_path = getattr(package_module, "__path__", [])
        except Exception:
            return

        for _, module_name, _ in iter_modules(package_path):
            try:
                module = importlib.import_module(f"{package}.{module_name}")
                provider_id = getattr(module, "__provider_id__", None)
                adapter_class = getattr(module, "__provider_class__", None)
                if provider_id and adapter_class:
                    cls.register(provider_id, adapter_class)
            except Exception:
                # Skip adapters that fail to import (e.g., missing optional deps)
                pass


# Singleton instance
registry = ProviderRegistry()


def discover_providers() -> Dict[str, Dict[str, Any]]:
    """Convenience wrapper around the registry's detect_available()."""
    return registry.detect_available()


def get_default_provider() -> Optional[str]:
    """Pick a sensible default provider based on system availability.

    Priority: configured env > ollama > gemini > openai > anthropic.
    """
    priority = ["ollama", "gemini", "openai", "anthropic"]
    available = registry.detect_available()
    for provider_id in priority:
        if provider_id in available:
            return provider_id
    return None


def register_cli_detector() -> None:
    """Register a lightweight CLI detector for adapters that don't auto-import."""
    # This is called after all adapter modules are imported so that detection
    # has access to the full registry.
    pass
