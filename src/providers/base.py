"""Unified LLM provider abstraction layer for Houdini.

This module defines the common interface that all LLM adapters implement,
allowing planners, supervisors, and executors to swap providers without
hardcoding Ollama/Gemini specifics.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union


@dataclass
class ProviderUsage:
    """Lightweight usage/cost metadata returned by a generation call."""

    model: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    duration_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_openai_response(cls, response: Any, duration_ms: Optional[float] = None) -> "ProviderUsage":
        """Build a ProviderUsage from an OpenAI SDK chat completion response."""
        model = getattr(response, "model", None)
        usage_obj = getattr(response, "usage", None)
        input_tokens = None
        output_tokens = None
        total_tokens = None
        if usage_obj is not None:
            input_tokens = getattr(usage_obj, "prompt_tokens", None) or getattr(usage_obj, "input_tokens", None)
            output_tokens = getattr(usage_obj, "completion_tokens", None) or getattr(usage_obj, "output_tokens", None)
            total_tokens = getattr(usage_obj, "total_tokens", None)
        return cls(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
        )


@dataclass
class GenerateResult:
    """Structured result from a text generation call."""

    text: str
    usage: Optional[ProviderUsage] = None
    raw_response: Optional[Any] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None

    def __str__(self) -> str:
        return self.text


class LLMProvider(ABC):
    """Abstract base class for all LLM providers used by Houdini."""

    def __init__(self, model_name: Optional[str] = None, **kwargs):
        self.model_name = model_name or getattr(self, "DEFAULT_MODEL", None)
        self.config = kwargs

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Short unique identifier, e.g. 'ollama', 'openai', 'anthropic'."""
        ...

    @property
    @abstractmethod
    def supports_vision(self) -> bool:
        """Whether this provider can accept image inputs."""
        ...

    @property
    def supports_tool_calls(self) -> bool:
        """Whether this provider supports native tool/function calling."""
        return False

    @property
    def is_local(self) -> bool:
        """True if inference runs on the local machine (Ollama, WebLLM, etc.)."""
        return False

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs,
    ) -> GenerateResult:
        """Generate a text completion for the given prompt."""
        ...

    def generate_with_image(
        self,
        prompt: str,
        image: Union[str, bytes],
        *,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> GenerateResult:
        """Generate a completion using one or more images.

        image can be a file path or raw bytes. Subclasses that support vision
        should override this method; the default raises NotImplementedError.
        """
        raise NotImplementedError(
            f"Provider {self.provider_id} does not support vision inputs."
        )

    def generate_json(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate a JSON object, falling back to robust text extraction.

        Adapters with native JSON mode may override this for better reliability.
        """
        if "json" not in prompt.lower():
            prompt = f"{prompt}\n\nRespond with valid JSON only."

        result = self.generate(prompt, system_prompt=system_prompt, **kwargs)
        return self._extract_json(result.text)

    def tool_call(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        *,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> GenerateResult:
        """Call one or more tools/functions. Default raises NotImplementedError."""
        raise NotImplementedError(
            f"Provider {self.provider_id} does not support tool calls."
        )

    def list_models(self) -> List[str]:
        """Return a list of available model names."""
        return [self.model_name] if self.model_name else []

    def health_check(self) -> Dict[str, Any]:
        """Return a lightweight health/status dict."""
        return {
            "provider": self.provider_id,
            "model": self.model_name,
            "healthy": True,
            "supports_vision": self.supports_vision,
            "supports_tool_calls": self.supports_tool_calls,
        }

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """Extract JSON from a model response, handling markdown fences and noise."""
        import json
        import re

        # 1. Try ```json ... ``` blocks
        fence_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", text)
        if fence_match:
            candidate = fence_match.group(1).strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        # 2. Find outermost { ... } using brace counting
        depth = 0
        start = -1
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start != -1:
                    candidate = text[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        start = -1

        # 3. Last resort — try the entire text
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        raise ValueError(f"Could not extract JSON from response: {text[:300]}")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} provider={self.provider_id} model={self.model_name}>"
