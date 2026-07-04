"""Tests for the /api/settings endpoint mapping."""
import os
import sys
from unittest.mock import patch

import pytest

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _PROJECT_ROOT)


def test_flat_settings_mapping():
    """Frontend sends flat settings; backend maps them to env vars."""
    from fastapi.testclient import TestClient
    from src.api.server import app

    client = TestClient(app)
    with patch.dict(os.environ, {}, clear=False):
        res = client.post("/api/settings", json={
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-test",
            "api_base": "https://api.openai.com/v1",
            "smart_router_enabled": True,
            "smart_router_prefer_local": False,
            "smart_router_budget_cap_usd": "5.00",
            "smart_router_latency_budget_ms": "2000",
        })
        assert res.status_code == 200
        assert os.environ.get("HOUDINI_DEFAULT_PROVIDER") == "openai"
        assert os.environ.get("OPENAI_API_KEY") == "sk-test"
        assert os.environ.get("HOUDINI_OPENAI_MODEL") == "gpt-4o"
        assert os.environ.get("HOUDINI_OPENAI_BASE_URL") == "https://api.openai.com/v1"
        assert os.environ.get("HOUDINI_SMART_ROUTER_ENABLED") == "true"
        assert os.environ.get("HOUDINI_PREFER_LOCAL") == "false"


def test_structured_provider_keys():
    """Structured provider_keys are applied directly."""
    from fastapi.testclient import TestClient
    from src.api.server import app

    client = TestClient(app)
    with patch.dict(os.environ, {}, clear=False):
        res = client.post("/api/settings", json={
            "default_provider": "anthropic",
            "provider_keys": {"ANTHROPIC_API_KEY": "sk-ant-test"},
            "provider_models": {"anthropic": "claude-sonnet-4"},
        })
        assert res.status_code == 200
        assert os.environ.get("HOUDINI_DEFAULT_PROVIDER") == "anthropic"
        assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-test"
        assert os.environ.get("HOUDINI_ANTHROPIC_MODEL") == "claude-sonnet-4"


def test_get_settings_includes_defaults():
    """GET /api/settings returns current non-sensitive settings."""
    from fastapi.testclient import TestClient
    from src.api.server import app

    client = TestClient(app)
    with patch.dict(os.environ, {"HOUDINI_DEFAULT_PROVIDER": "ollama"}, clear=False):
        res = client.get("/api/settings")
        assert res.status_code == 200
        data = res.json()
        assert data["default_provider"] == "ollama"
        assert "available_providers" in data
        assert "smart_router" in data


def test_browser_vision_setting():
    """Toggle use_browser_vision via /api/settings."""
    from fastapi.testclient import TestClient
    from src.api.server import app

    client = TestClient(app)
    with patch.dict(os.environ, {}, clear=False):
        res = client.post("/api/settings", json={"use_browser_vision": True})
        assert res.status_code == 200
        assert os.environ.get("HOUDINI_USE_BROWSER_VISION") == "true"

        res = client.get("/api/settings")
        assert res.status_code == 200
        assert res.json()["use_browser_vision"] is True

        res = client.post("/api/settings", json={"use_browser_vision": False})
        assert res.status_code == 200
        assert os.environ.get("HOUDINI_USE_BROWSER_VISION") == "false"
