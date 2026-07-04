"""MCP (Model Context Protocol) server for Houdini Agent.

Exposes Houdini's core capabilities to coding agents such as Claude Code,
Codex CLI, Cursor, and any other MCP client:
  • run_task / get_task          — submit and monitor desktop tasks
  • list_providers                — discover available LLM providers
  • list_skills / match_skills    — browse reusable skill instructions
  • run_benchmark / get_benchmark — measure agent accuracy
  • get_health                    — server health and stats

Usage:
    python -m src.mcp_server              # start stdio MCP server
    python -m src.mcp_server --print-config claude
    python -m src.mcp_server --install claude

Requires the Houdini API server to be running:
    python -m src.api.server
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    Server = None  # type: ignore
    stdio_server = None  # type: ignore
    TextContent = Tool = None  # type: ignore

from src.utils.logging import logger


API_BASE = os.environ.get("HOUDINI_API_URL", "http://127.0.0.1:8420")


class HoudiniMCPClient:
    """Lightweight async HTTP client for the Houdini API."""

    def __init__(self, base_url: str = API_BASE):
        self.base_url = base_url.rstrip("/")

    async def _request(
        self,
        method: str,
        path: str,
        json_body: Dict[str, Any] | None = None,
        params: Dict[str, str] | None = None,
    ) -> Dict[str, Any]:
        import httpx
        async with httpx.AsyncClient(timeout=60.0) as client:
            url = f"{self.base_url}{path}"
            if method.upper() == "GET":
                response = await client.get(url, params=params)
            else:
                response = await client.post(url, json=json_body)
            response.raise_for_status()
            return response.json()

    async def health(self) -> Dict[str, Any]:
        return await self._request("GET", "/api/health")

    async def list_providers(self) -> Dict[str, Any]:
        return await self._request("GET", "/api/providers")

    async def list_skills(self, task: str | None = None) -> Dict[str, Any]:
        params = {"task": task} if task else None
        return await self._request("GET", "/api/skills", params=params)

    async def submit_task(self, task: str, **kwargs) -> Dict[str, Any]:
        body = {"task": task, **kwargs}
        return await self._request("POST", "/api/tasks", json_body=body)

    async def get_task(self, task_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/tasks/{task_id}")

    async def list_benchmark_tasks(self, tag: str | None = None) -> Dict[str, Any]:
        params = {"tag": tag} if tag else None
        return await self._request("GET", "/api/benchmarks/tasks", params=params)

    async def run_benchmark(self, **kwargs) -> Dict[str, Any]:
        return await self._request("POST", "/api/benchmarks/run", json_body=kwargs)

    async def get_benchmark_result(self, run_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/benchmarks/results/{run_id}")


# Tool schemas exposed to MCP clients
TOOLS: List[Dict[str, Any]] = [
    {
        "name": "houdini_get_health",
        "description": "Get Houdini API health, uptime, and task statistics.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "houdini_list_providers",
        "description": "List available LLM providers and which ones are currently usable.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "houdini_list_skills",
        "description": "List reusable skill instructions. Optionally pass a task to see which skills match.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Optional task description to rank skills by relevance"},
            },
        },
    },
    {
        "name": "houdini_run_task",
        "description": "Submit a desktop automation task to Houdini. Returns a task_id to poll with houdini_get_task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Natural language task description"},
                "provider": {"type": "string", "description": "Optional provider id (openai, anthropic, gemini, ollama, ...)"},
                "model": {"type": "string", "description": "Optional model name/alias"},
                "architecture": {"type": "string", "enum": ["adaptive", "langgraph", "legacy"], "description": "Coordinator architecture"},
                "use_enhanced": {"type": "boolean", "description": "Use enhanced executor"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "houdini_get_task",
        "description": "Get the status, events, and result of a submitted Houdini task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task id returned by houdini_run_task"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "houdini_list_benchmark_tasks",
        "description": "List available benchmark tasks, optionally filtered by tag.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tag": {"type": "string", "description": "Optional tag filter (e.g. smoke, vision)"},
            },
        },
    },
    {
        "name": "houdini_run_benchmark",
        "description": "Start a benchmark run. Returns a run_id to poll with houdini_get_benchmark_result.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tag": {"type": "string", "description": "Only run tasks with this tag"},
                "task_id": {"type": "string", "description": "Run a single task by id"},
                "provider": {"type": "string", "description": "Provider id to use"},
                "model": {"type": "string", "description": "Model name/alias"},
                "architecture": {"type": "string", "enum": ["adaptive", "langgraph", "legacy"]},
                "verify_with_llm": {"type": "boolean", "description": "Use LLM judge with screenshots"},
            },
        },
    },
    {
        "name": "houdini_get_benchmark_result",
        "description": "Poll for benchmark results by run_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Run id returned by houdini_run_benchmark"},
            },
            "required": ["run_id"],
        },
    },
]


class HoudiniMCPServer:
    """MCP server wrapping the Houdini HTTP API."""

    def __init__(self, api_base: str = API_BASE):
        if not MCP_AVAILABLE:
            raise RuntimeError("mcp package not installed. Run: pip install mcp>=1.0.0")
        self.api = HoudiniMCPClient(api_base)
        self.server = Server("houdini-agent")
        self._register_handlers()

    def _register_handlers(self):
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            return [Tool(**t) for t in TOOLS]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            try:
                result = await self._handle_tool(name, arguments or {})
                return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
            except Exception as exc:
                logger.error(f"MCP tool {name} failed: {exc}")
                return [TextContent(type="text", text=json.dumps({"error": str(exc)}, indent=2))]

    async def _handle_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name == "houdini_get_health":
            return await self.api.health()
        if name == "houdini_list_providers":
            return await self.api.list_providers()
        if name == "houdini_list_skills":
            return await self.api.list_skills(arguments.get("task"))
        if name == "houdini_run_task":
            body = {"task": arguments["task"]}
            for key in ("provider", "model", "architecture", "use_enhanced"):
                if key in arguments:
                    body[key] = arguments[key]
            return await self.api.submit_task(**body)
        if name == "houdini_get_task":
            return await self.api.get_task(arguments["task_id"])
        if name == "houdini_list_benchmark_tasks":
            return await self.api.list_benchmark_tasks(arguments.get("tag"))
        if name == "houdini_run_benchmark":
            body = {}
            for key in ("tag", "task_id", "provider", "model", "architecture", "verify_with_llm"):
                if key in arguments:
                    body[key] = arguments[key]
            return await self.api.run_benchmark(**body)
        if name == "houdini_get_benchmark_result":
            return await self.api.get_benchmark_result(arguments["run_id"])
        raise ValueError(f"Unknown tool: {name}")

    async def run(self):
        async with stdio_server(self.server.request_handlers) as (read_stream, write_stream):
            await self.server.run(read_stream, write_stream, self.server.create_initialization_options())


# ── CLI helpers ──────────────────────────────────────────────────────

AGENT_CONFIG_PATHS = {
    "claude": lambda: Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
    "claude-code": lambda: Path.home() / ".claude" / "mcp_config.json",
    "codex": lambda: Path.home() / ".codex" / "mcp_config.json",
    "cursor": lambda: Path.home() / ".cursor" / "mcp_config.json",
    "copilot": lambda: Path.home() / ".github" / "copilot" / "mcp_config.json",
}


def _build_server_command() -> List[str]:
    """Return the command array to launch this MCP server."""
    python = sys.executable
    script = Path(__file__).resolve()
    return [python, str(script)]


def _build_config() -> Dict[str, Any]:
    return {
        "mcpServers": {
            "houdini": {
                "command": _build_server_command()[0],
                "args": _build_server_command()[1:],
                "env": {
                    "HOUDINI_API_URL": API_BASE,
                },
            }
        }
    }


def _print_config(agent: str):
    print(json.dumps(_build_config(), indent=2))


def _install_config(agent: str):
    path_fn = AGENT_CONFIG_PATHS.get(agent)
    if path_fn is None:
        raise ValueError(f"Unknown agent: {agent}. Supported: {', '.join(AGENT_CONFIG_PATHS)}")

    config_path = path_fn()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    existing: Dict[str, Any] = {}
    if config_path.exists():
        with open(config_path) as f:
            existing = json.load(f)

    existing.setdefault("mcpServers", {}).update(_build_config()["mcpServers"])

    with open(config_path, "w") as f:
        json.dump(existing, f, indent=2)

    print(f"Installed Houdini MCP config to {config_path}")


def main():
    parser = argparse.ArgumentParser(description="Houdini Agent MCP Server")
    parser.add_argument("--print-config", metavar="AGENT", help="Print MCP config for an agent")
    parser.add_argument("--install", metavar="AGENT", help="Install MCP config for an agent")
    parser.add_argument("--api-url", default=API_BASE, help="Houdini API base URL")
    args = parser.parse_args()

    if args.print_config:
        _print_config(args.print_config)
        return
    if args.install:
        _install_config(args.install)
        return

    if not MCP_AVAILABLE:
        print("ERROR: mcp package not installed. Run: pip install mcp>=1.0.0", file=sys.stderr)
        sys.exit(1)

    server = HoudiniMCPServer(api_base=args.api_url)
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
