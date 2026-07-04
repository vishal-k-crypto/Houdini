"""Provider routing layer for Houdini.

The router selects a provider/model for a given role (planner, supervisor,
vision, worker) based on user preference, fallback rules, and cost/latency
heuristics. It also supports tiered routing (free/local → cheap → frontier).
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .base import LLMProvider
from .registry import registry


class ProviderRouter:
    """Routes tasks to the best available provider based on role and config."""

    # Role-specific config keys (can be expanded in settings.py)
    ROLES = ["planner", "supervisor", "vision", "worker"]

    # Default fallback tiers (provider ids, cheapest/most local first)
    DEFAULT_TIERS: Dict[str, List[str]] = {
        "planner": ["ollama", "gemini", "openai", "anthropic", "cli:claude"],
        "supervisor": ["ollama", "openai", "anthropic", "gemini"],
        "vision": ["gemini", "openai", "anthropic", "ollama"],
        "worker": ["ollama", "openai", "anthropic", "gemini", "cli:codex"],
    }

    def __init__(
        self,
        preferences: Optional[Dict[str, str]] = None,
        tiers: Optional[Dict[str, List[str]]] = None,
        budget_cap_usd: Optional[float] = None,
    ):
        self.preferences = preferences or {}
        self.tiers = tiers or self.DEFAULT_TIERS.copy()
        self.budget_cap_usd = budget_cap_usd

    def provider_for(
        self,
        role: str,
        *,
        prefer_vision: bool = False,
        require_local: bool = False,
    ) -> LLMProvider:
        """Return an instantiated provider for the given role."""
        preferred = self.preferences.get(role)
        if preferred:
            return self._create(preferred, prefer_vision=prefer_vision, require_local=require_local)

        for provider_id in self.tiers.get(role, []):
            provider = self._try_create(provider_id, prefer_vision, require_local)
            if provider is not None:
                return provider

        raise RuntimeError(
            f"No available provider found for role '{role}'. "
            f"Preferences: {self.preferences}, tiers: {self.tiers}"
        )

    def _try_create(
        self,
        provider_id: str,
        prefer_vision: bool,
        require_local: bool,
    ) -> Optional[LLMProvider]:
        try:
            provider = self._create(provider_id, prefer_vision=prefer_vision, require_local=require_local)
            health = provider.health_check()
            if health.get("healthy") is False and not provider.is_local:
                return None
            return provider
        except Exception:
            return None

    def _create(
        self,
        provider_id: str,
        *,
        prefer_vision: bool = False,
        require_local: bool = False,
    ) -> LLMProvider:
        # CLI agents are specified as cli:<agent>
        if provider_id.startswith("cli:"):
            agent = provider_id.split(":", 1)[1]
            return registry.create("cli", agent=agent)

        provider = registry.create(provider_id)
        if require_local and not provider.is_local:
            raise RuntimeError(
                f"Provider '{provider_id}' is not local but local is required."
            )
        if prefer_vision and not provider.supports_vision:
            raise RuntimeError(
                f"Provider '{provider_id}' does not support vision."
            )
        return provider

    def list_available(self) -> List[str]:
        """Return provider ids that are currently available."""
        return list(registry.detect_available().keys())

    def set_preference(self, role: str, provider_id: str) -> None:
        self.preferences[role] = provider_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "preferences": self.preferences,
            "tiers": self.tiers,
            "budget_cap_usd": self.budget_cap_usd,
            "available": self.list_available(),
        }


# Default router instance
router = ProviderRouter()


def get_provider(
    role: str = "worker",
    *,
    prefer_vision: bool = False,
    require_local: bool = False,
) -> LLMProvider:
    """Convenience shortcut for the default router."""
    return router.provider_for(role, prefer_vision=prefer_vision, require_local=require_local)


def configure_from_env() -> None:
    """Load provider preferences from environment variables."""
    for role in ProviderRouter.ROLES:
        env_value = os.environ.get(f"HOUDINI_{role.upper()}_PROVIDER")
        if env_value:
            router.set_preference(role, env_value)

    budget = os.environ.get("HOUDINI_BUDGET_CAP_USD")
    if budget:
        try:
            router.budget_cap_usd = float(budget)
        except ValueError:
            pass


# Initialize preferences from environment on first import
configure_from_env()
