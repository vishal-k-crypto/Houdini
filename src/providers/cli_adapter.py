"""CLI-agent adapter for installed coding agents.

Wraps popular command-line AI agents by invoking them as subprocesses. Each CLI
agent is described by a command template and an optional prompt-injection
convention. Examples: Claude Code (`claude`), Codex (`codex`), OpenCode
(`od`), Kimi (`kimi`), Gemini CLI (`gemini`), agy (`agy`), Qwen CLI (`qwen`).

Because these agents are interactive coding assistants, the adapter:
- Creates a temporary workspace containing the user prompt.
- Invokes the CLI with a non-interactive / no-approval flag when available.
- Captures stdout/stderr and returns the generated response text.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .base import GenerateResult, LLMProvider, ProviderUsage


@dataclass
class CLIAgentSpec:
    """Description of how to invoke a CLI coding agent."""

    command: str
    args: List[str]
    prompt_template: str = "{prompt}"
    supports_vision: bool = False
    supports_tool_calls: bool = False
    env_vars: Optional[Dict[str, str]] = None
    description: str = ""

    def build_command(self, prompt: str, workspace: str) -> List[str]:
        rendered = self.prompt_template.format(
            prompt=prompt, workspace=workspace, cwd=os.getcwd()
        )
        return [self.command, *self.args, rendered]


# Known CLI agents. Flags are best-effort; many agents will still prompt for
# approval or login on first run.
_CLI_AGENTS: Dict[str, CLIAgentSpec] = {
    "claude": CLIAgentSpec(
        command="claude",
        args=["--no-intro", "-p"],
        prompt_template="{prompt}",
        supports_vision=False,
        supports_tool_calls=True,
        description="Anthropic Claude Code",
    ),
    "codex": CLIAgentSpec(
        command="codex",
        args=["--no-approval", "-q"],
        prompt_template="{prompt}",
        supports_vision=False,
        supports_tool_calls=True,
        description="OpenAI Codex CLI",
    ),
    "opencode": CLIAgentSpec(
        command="od",
        args=["--non-interactive"],
        prompt_template="{prompt}",
        supports_vision=False,
        supports_tool_calls=False,
        description="OpenCode CLI (od)",
    ),
    "kimi": CLIAgentSpec(
        command="kimi",
        args=["--non-interactive", "-p"],
        prompt_template="{prompt}",
        supports_vision=False,
        supports_tool_calls=False,
        description="Kimi CLI",
    ),
    "gemini": CLIAgentSpec(
        command="gemini",
        args=["-m", "gemini-2.5-pro", "-o", "text"],
        prompt_template="{prompt}",
        supports_vision=False,
        supports_tool_calls=False,
        description="Google Gemini CLI",
    ),
    "agy": CLIAgentSpec(
        command="agy",
        args=["--non-interactive"],
        prompt_template="{prompt}",
        supports_vision=False,
        supports_tool_calls=False,
        description="Antigravity (agy) CLI",
    ),
    "qwen": CLIAgentSpec(
        command="qwen",
        args=["--non-interactive"],
        prompt_template="{prompt}",
        supports_vision=False,
        supports_tool_calls=False,
        description="Qwen CLI",
    ),
}


class CLIAgentProvider(LLMProvider):
    """Adapter that wraps an installed command-line AI agent."""

    DEFAULT_MODEL: str = "cli-agent"

    def __init__(
        self,
        model_name: Optional[str] = None,
        *,
        agent: Optional[str] = None,
        timeout: int = 120,
        extra_args: Optional[List[str]] = None,
        **kwargs,
    ):
        # model_name can be used as the agent id if `agent` is not supplied
        resolved_agent = agent or model_name or "claude"
        if resolved_agent not in _CLI_AGENTS:
            raise ValueError(
                f"Unknown CLI agent '{resolved_agent}'. "
                f"Supported: {', '.join(_CLI_AGENTS.keys())}"
            )
        super().__init__(model_name=resolved_agent, **kwargs)
        self.agent = resolved_agent
        self.spec = _CLI_AGENTS[resolved_agent]
        self.timeout = timeout
        self.extra_args = extra_args or []

    @property
    def provider_id(self) -> str:
        return f"cli:{self.agent}"

    @property
    def supports_vision(self) -> bool:
        return self.spec.supports_vision

    @property
    def supports_tool_calls(self) -> bool:
        return self.spec.supports_tool_calls

    @classmethod
    def detect(cls) -> Dict[str, Any]:
        available = {}
        for name, spec in _CLI_AGENTS.items():
            if shutil.which(spec.command):
                available[name] = {
                    "available": True,
                    "command": spec.command,
                    "description": spec.description,
                }
        return {
            "available": bool(available),
            "agents": available,
        }

    def _generate_text(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs,
    ) -> GenerateResult:
        # Render full prompt with optional system prompt
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{full_prompt}"

        # Optionally write prompt to a temp file for CLI agents that prefer files
        with tempfile.TemporaryDirectory() as workspace:
            prompt_file = os.path.join(workspace, "prompt.txt")
            with open(prompt_file, "w", encoding="utf-8") as f:
                f.write(full_prompt)

            cmd = self.spec.build_command(full_prompt, workspace)
            if self.extra_args:
                cmd[1:1] = self.extra_args

            env = os.environ.copy()
            if self.spec.env_vars:
                env.update(self.spec.env_vars)

            start = time.time()
            try:
                result = subprocess.run(
                    cmd,
                    cwd=workspace,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
            except FileNotFoundError as exc:
                raise RuntimeError(
                    f"CLI agent '{self.agent}' not found in PATH."
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    f"CLI agent '{self.agent}' timed out after {self.timeout}s."
                ) from exc
            duration_ms = (time.time() - start) * 1000

            output = result.stdout.strip()
            if not output and result.stderr:
                output = result.stderr.strip()
            if result.returncode != 0 and not output:
                raise RuntimeError(
                    f"CLI agent '{self.agent}' exited with code {result.returncode}: {result.stderr}"
                )

            return GenerateResult(
                text=output,
                usage=ProviderUsage(
                    model=self.agent, duration_ms=duration_ms
                ),
            )

    def tool_call(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        *,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> GenerateResult:
        # CLI agents cannot reliably return structured tool calls, so we fall back
        # to a text request and expect the agent to act inside its workspace.
        tool_instructions = (
            "\n\nYou may use the following tools by creating/editing files in this workspace: "
            + ", ".join(t.get("name", t.get("function", "tool")) for t in tools)
        )
        return self.generate(
            prompt + tool_instructions,
            system_prompt=system_prompt,
            **kwargs,
        )

    def health_check(self) -> Dict[str, Any]:
        available = shutil.which(self.spec.command) is not None
        return {
            "provider": self.provider_id,
            "agent": self.agent,
            "command": self.spec.command,
            "healthy": available,
            "supports_vision": self.supports_vision,
            "supports_tool_calls": self.supports_tool_calls,
        }


def list_available_cli_agents() -> List[str]:
    """Return the list of CLI agents found on PATH."""
    return [
        name
        for name, spec in _CLI_AGENTS.items()
        if shutil.which(spec.command)
    ]


__provider_id__ = "cli"
__provider_class__ = CLIAgentProvider
