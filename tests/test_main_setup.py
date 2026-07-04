"""Tests for the CLI setup/discovery helpers in src.main."""
import os
import sys
from unittest.mock import patch, MagicMock
from io import StringIO

import pytest

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _PROJECT_ROOT)


class Args:
    def __init__(self, export=False):
        self.export = export


def test_run_setup_mode_detects_providers():
    from src.main import run_setup_mode

    fake_registry = {
        "ollama": {"available": True, "local": True, "models": ["qwen3-coder"]},
        "openai": {"available": False},
    }
    with patch("src.main.registry.detect_available", return_value=fake_registry), \
         patch("src.providers.cli_adapter.list_available_cli_agents", return_value=["claude"]), \
         patch("src.main.get_default_provider", return_value="ollama"), \
         patch("sys.stdout", new_callable=StringIO) as stdout:
        run_setup_mode(Args())
        output = stdout.getvalue()

    assert "Houdini Agent — Provider Setup" in output
    assert "ollama" in output
    assert "claude" in output
    assert "Recommended default provider: ollama" in output


def test_run_setup_mode_export():
    from src.main import run_setup_mode

    fake_registry = {"openai": {"available": True}}
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}), \
         patch("src.main.registry.detect_available", return_value=fake_registry), \
         patch("src.providers.cli_adapter.list_available_cli_agents", return_value=[]), \
         patch("src.main.get_default_provider", return_value="openai"), \
         patch("sys.stdout", new_callable=StringIO) as stdout:
        run_setup_mode(Args(export=True))
        output = stdout.getvalue()

    assert "export HOUDINI_DEFAULT_PROVIDER=openai" in output
    assert "export OPENAI_API_KEY=sk-test" in output
