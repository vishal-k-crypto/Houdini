"""Tests for provider deep detection, connection testing, .env persistence, and smart routing overrides."""
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _PROJECT_ROOT)

from src.api.server import app
from src.providers.registry import registry
from src.providers.smart_router import smart_router


def test_registry_detect_deep():
    """Test registry.detect_deep returns CLI and Ollama info if present."""
    with patch("src.providers.cli_adapter.shutil.which", return_value="/usr/bin/claude"):
        available = registry.detect_deep()
        
    assert "cli" in available
    assert available["cli"]["available"] is True
    assert "claude" in available["cli"]["agents"]


def test_detect_endpoint():
    """Test GET /api/providers/detect returns available providers and CLI agents."""
    client = TestClient(app)
    with patch("src.providers.cli_adapter.shutil.which", return_value="/usr/bin/claude"):
        res = client.get("/api/providers/detect")
        
    assert res.status_code == 200
    data = res.json()
    assert "providers" in data
    
    # Verify we got a list with cli provider
    cli_provider = next((p for p in data["providers"] if p["id"] == "cli"), None)
    assert cli_provider is not None
    assert cli_provider["available"] is True
    assert "claude" in cli_provider["agents"]


def test_test_connection_endpoint_cli():
    """Test POST /api/settings/test-connection for a CLI provider."""
    client = TestClient(app)
    
    # Mock successful path check
    with patch("src.providers.cli_adapter.shutil.which", return_value="/usr/bin/claude"):
        res = client.post("/api/settings/test-connection", json={
            "provider": "cli",
            "model": "claude"
        })
    assert res.status_code == 200
    assert res.json()["success"] is True
    assert "available on PATH" in res.json()["message"]
    
    # Mock failed path check
    with patch("src.providers.cli_adapter.shutil.which", return_value=None):
        res = client.post("/api/settings/test-connection", json={
            "provider": "cli",
            "model": "claude"
        })
    assert res.status_code == 200
    assert res.json()["success"] is False
    assert "not found" in res.json()["error"]


def test_test_connection_endpoint_api():
    """Test POST /api/settings/test-connection for an API provider."""
    client = TestClient(app)
    
    mock_provider = MagicMock()
    mock_provider.generate.return_value = MagicMock(text="SUCCESS")
    
    with patch("src.providers.registry.ProviderRegistry.create", return_value=mock_provider):
        res = client.post("/api/settings/test-connection", json={
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-fake-key"
        })
        
    assert res.status_code == 200
    assert res.json()["success"] is True
    assert "Connection verified" in res.json()["message"]


def test_settings_persistence_to_env():
    """Test update_settings persists values to .env file."""
    client = TestClient(app)
    
    env_file = Path(_PROJECT_ROOT) / ".env"
    if env_file.exists():
        env_file.unlink()
        
    res = client.post("/api/settings", json={
        "provider": "openai",
        "model": "gpt-4o",
        "api_key": "sk-persist-test",
    })
    
    assert res.status_code == 200
    assert env_file.exists()
    
    content = env_file.read_text()
    assert "HOUDINI_DEFAULT_PROVIDER=openai" in content
    assert "HOUDINI_OPENAI_MODEL=gpt-4o" in content
    assert "OPENAI_API_KEY=sk-persist-test" in content
    
    # Clean up
    env_file.unlink()


def test_smart_router_routes_cli_coding_tasks():
    """Test smart router routes coding/reasoning tasks to CLI agents if available."""
    # Ensure preference is empty so router defaults apply
    smart_router.preferences = {}
    
    with patch("src.providers.cli_adapter.shutil.which", return_value="/usr/bin/claude"):
        decision = smart_router.route(
            task="Write a python function to compute fibonacci numbers",
            role="worker"
        )
        
    assert decision.provider_id == "cli:claude"
    assert "selected for coding/reasoning task" in decision.reason
