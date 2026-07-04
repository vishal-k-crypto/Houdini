"""Tests for the unified provider layer (registry, router, CLI adapter)."""
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _PROJECT_ROOT)

from src.providers.cli_adapter import CLIAgentProvider, list_available_cli_agents
from src.providers.registry import ProviderRegistry, registry, get_default_provider
from src.providers.router import ProviderRouter, get_provider


class TestCLIAgentProvider:
    """Tests for CLI-agent detection and invocation."""

    def test_detect_finds_only_installed_agents(self):
        with patch("src.providers.cli_adapter.shutil.which") as mock_which:
            mock_which.side_effect = lambda cmd: cmd in ("claude", "codex")
            info = CLIAgentProvider.detect()
        assert info["available"] is True
        assert "claude" in info["agents"]
        assert "codex" in info["agents"]
        assert "kimi" not in info["agents"]

    def test_detect_returns_false_when_nothing_installed(self):
        with patch("src.providers.cli_adapter.shutil.which", return_value=None):
            info = CLIAgentProvider.detect()
        assert info["available"] is False
        assert info["agents"] == {}

    def test_list_available_cli_agents(self):
        with patch("src.providers.cli_adapter.shutil.which") as mock_which:
            mock_which.side_effect = lambda cmd: cmd == "claude"
            found = list_available_cli_agents()
        assert found == ["claude"]

    def test_create_cli_provider(self):
        provider = CLIAgentProvider(agent="claude")
        assert provider.provider_id == "cli:claude"
        assert provider.supports_tool_calls is True

    def test_unknown_cli_agent_raises(self):
        with pytest.raises(ValueError, match="Unknown CLI agent"):
            CLIAgentProvider(agent="not-real")

    def test_health_check_reflects_availability(self):
        provider = CLIAgentProvider(agent="claude")
        with patch("src.providers.cli_adapter.shutil.which", return_value="/usr/bin/claude"):
            health = provider.health_check()
        assert health["healthy"] is True


class TestProviderRegistry:
    """Tests for provider registry registration and discovery."""

    def test_registry_has_builtin_providers(self):
        providers = registry.list_providers()
        for expected in ["openai", "anthropic", "gemini", "ollama", "webllm", "cli"]:
            assert expected in providers

    def test_create_ollama_provider(self):
        provider = registry.create("ollama")
        assert provider.provider_id == "ollama"

    def test_create_cli_provider(self):
        provider = registry.create("cli", agent="codex")
        assert provider.provider_id == "cli:codex"

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            registry.create("not-a-provider")

    def test_detect_available_includes_cli(self):
        with patch("src.providers.cli_adapter.shutil.which", return_value="/usr/bin/claude"):
            available = registry.detect_available()
        assert "cli" in available or "ollama" in available or "openai" in available


class TestProviderRouter:
    """Tests for provider routing with preferences and CLI agents."""

    def test_preference_overrides_tier(self):
        router = ProviderRouter(preferences={"worker": "openai"})
        with patch.object(router, "_create") as mock_create:
            fake_provider = MagicMock()
            fake_provider.is_local = False
            fake_provider.health_check.return_value = {"healthy": True}
            mock_create.return_value = fake_provider
            provider = router.provider_for("worker")
        assert provider is fake_provider
        mock_create.assert_called_once_with("openai", prefer_vision=False, require_local=False)

    def test_cli_agent_routing(self):
        router = ProviderRouter(tiers={"worker": ["cli:claude"]})
        with patch("src.providers.cli_adapter.shutil.which", return_value="/usr/bin/claude"):
            provider = router.provider_for("worker")
        assert provider.provider_id == "cli:claude"

    def test_no_available_provider_raises(self):
        router = ProviderRouter(tiers={"worker": ["not-real"]})
        with pytest.raises(RuntimeError, match="No available provider"):
            router.provider_for("worker")
