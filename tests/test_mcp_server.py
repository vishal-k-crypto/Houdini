"""Tests for the Houdini MCP server."""
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.mcp_server import (
    HoudiniMCPClient,
    HoudiniMCPServer,
    TOOLS,
    _build_config,
    _build_server_command,
)


@pytest.fixture
def client():
    return HoudiniMCPClient(base_url="http://localhost:9999")


def test_tools_have_required_schemas():
    names = {t["name"] for t in TOOLS}
    expected = {
        "houdini_get_health",
        "houdini_list_providers",
        "houdini_list_skills",
        "houdini_run_task",
        "houdini_get_task",
        "houdini_list_benchmark_tasks",
        "houdini_run_benchmark",
        "houdini_get_benchmark_result",
    }
    assert names == expected
    for tool in TOOLS:
        assert "description" in tool
        assert "inputSchema" in tool


def test_build_config():
    cfg = _build_config()
    assert "mcpServers" in cfg
    assert "houdini" in cfg["mcpServers"]
    assert cfg["mcpServers"]["houdini"]["command"]
    assert cfg["mcpServers"]["houdini"]["args"]


def test_build_server_command():
    cmd = _build_server_command()
    assert len(cmd) >= 2
    assert "python" in cmd[0] or "Python" in cmd[0]
    assert "mcp_server.py" in cmd[-1]


@pytest.mark.asyncio
async def test_client_health(client):
    with patch("httpx.AsyncClient") as mock_client_cls:
        from unittest.mock import MagicMock
        mock_response = AsyncMock()
        mock_response.json = MagicMock(return_value={"status": "ok"})
        mock_response.raise_for_status = lambda: None
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await client.health()
        assert result["status"] == "ok"
        mock_client.get.assert_called_once_with("http://localhost:9999/api/health", params=None)


@pytest.mark.asyncio
async def test_mcp_server_handles_unknown_tool():
    server = HoudiniMCPServer(api_base="http://localhost:9999")
    with pytest.raises(ValueError, match="Unknown tool"):
        await server._handle_tool("unknown_tool", {})


@pytest.mark.asyncio
async def test_mcp_server_run_task_builds_body():
    server = HoudiniMCPServer(api_base="http://localhost:9999")
    with patch.object(server.api, "submit_task", new=AsyncMock(return_value={"task_id": "abc123"})) as mock_submit:
        result = await server._handle_tool("houdini_run_task", {"task": "open Safari", "provider": "openai"})
        assert result["task_id"] == "abc123"
        mock_submit.assert_awaited_once_with(task="open Safari", provider="openai")


@pytest.mark.asyncio
async def test_mcp_server_get_task():
    server = HoudiniMCPServer(api_base="http://localhost:9999")
    with patch.object(server.api, "get_task", new=AsyncMock(return_value={"task_id": "abc", "status": "completed"})) as mock_get:
        result = await server._handle_tool("houdini_get_task", {"task_id": "abc"})
        assert result["status"] == "completed"
        mock_get.assert_awaited_once_with("abc")





def test_print_config_cli(capsys):
    from src.mcp_server import _print_config
    _print_config("claude")
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "houdini" in data["mcpServers"]


def test_install_config_writes_file(tmp_path):
    from src.mcp_server import _install_config
    config_path = tmp_path / "mcp_config.json"
    with patch("src.mcp_server.AGENT_CONFIG_PATHS", {"test": lambda: config_path}):
        _install_config("test")
    assert config_path.exists()
    data = json.loads(config_path.read_text())
    assert "houdini" in data.get("mcpServers", {})
