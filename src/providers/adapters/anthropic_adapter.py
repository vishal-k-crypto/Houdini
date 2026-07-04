"""Anthropic Claude adapter for Houdini.

Supports text and vision generation via the Anthropic Messages API. BYOK via
ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import base64
import os
import time
from typing import Any, Dict, List, Optional, Union

from ..base import GenerateResult, LLMProvider, ProviderUsage


class AnthropicProvider(LLMProvider):
    """Adapter for Anthropic's Claude API."""

    DEFAULT_MODEL: str = "claude-sonnet-4-20250514"
    ENV_KEY: str = "ANTHROPIC_API_KEY"

    def __init__(
        self,
        model_name: Optional[str] = None,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(model_name=model_name or self.DEFAULT_MODEL, **kwargs)
        self.api_key = api_key or os.environ.get(self.ENV_KEY)
        self.base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL")
        self._client: Optional[Any] = None
        self._ensure_client()

    @property
    def provider_id(self) -> str:
        return "anthropic"

    @property
    def supports_vision(self) -> bool:
        return True

    @property
    def supports_tool_calls(self) -> bool:
        return True

    @classmethod
    def detect(cls) -> Dict[str, Any]:
        return {
            "available": bool(os.environ.get(cls.ENV_KEY)),
            "requires_api_key": True,
        }

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError(
                "Anthropic SDK not installed. Install with: pip install anthropic"
            ) from exc

        if not self.api_key:
            raise RuntimeError(
                f"API key required for Anthropic. Set {self.ENV_KEY} or pass api_key."
            )

        client_kwargs: Dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        self._client = anthropic.Anthropic(**client_kwargs)

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
        self._ensure_client()
        temperature = temperature if temperature is not None else 0.7
        max_tokens = max_tokens or 4096

        request: Dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            request["system"] = system_prompt
        if stop:
            request["stop_sequences"] = stop

        start = time.time()
        response = self._client.messages.create(**request)  # type: ignore
        duration_ms = (time.time() - start) * 1000

        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text

        usage = ProviderUsage(
            model=self.model_name,
            input_tokens=getattr(response.usage, "input_tokens", None),
            output_tokens=getattr(response.usage, "output_tokens", None),
            total_tokens=getattr(response.usage, "input_tokens", 0)
            + getattr(response.usage, "output_tokens", 0),
            duration_ms=duration_ms,
        )
        return GenerateResult(text=text, usage=usage, raw_response=response)

    def generate_with_image(
        self,
        prompt: str,
        image: Union[str, bytes],
        *,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> GenerateResult:
        self._ensure_client()
        image_content = self._normalize_image(image)
        content: List[Dict[str, Any]] = [
            {"type": "text", "text": prompt},
            {"type": "image", "source": image_content},
        ]
        request: Dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", 0.7),
            "messages": [{"role": "user", "content": content}],
        }
        if system_prompt:
            request["system"] = system_prompt

        start = time.time()
        response = self._client.messages.create(**request)  # type: ignore
        duration_ms = (time.time() - start) * 1000

        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text

        usage = ProviderUsage(
            model=self.model_name,
            input_tokens=getattr(response.usage, "input_tokens", None),
            output_tokens=getattr(response.usage, "output_tokens", None),
            total_tokens=getattr(response.usage, "input_tokens", 0)
            + getattr(response.usage, "output_tokens", 0),
            duration_ms=duration_ms,
        )
        return GenerateResult(text=text, usage=usage, raw_response=response)

    def tool_call(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        *,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> GenerateResult:
        self._ensure_client()
        request: Dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", 0.7),
            "messages": [{"role": "user", "content": prompt}],
            "tools": tools,
        }
        if system_prompt:
            request["system"] = system_prompt

        response = self._client.messages.create(**request)  # type: ignore
        text = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    {
                        "id": block.id,
                        "function": block.name,
                        "arguments": block.input,
                    }
                )
        return GenerateResult(text=text, raw_response=response, tool_calls=tool_calls or None)

    def _normalize_image(self, image: Union[str, bytes]) -> Dict[str, Any]:
        """Return an Anthropic-compatible image source dict."""
        if isinstance(image, str):
            if image.startswith("http://") or image.startswith("https://"):
                raise ValueError("Anthropic adapter does not support remote image URLs")
            with open(image, "rb") as f:
                data = f.read()
            media_type = self._guess_media_type(image)
            return {
                "type": "base64",
                "media_type": media_type,
                "data": base64.b64encode(data).decode("utf-8"),
            }
        if isinstance(image, bytes):
            return {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.b64encode(image).decode("utf-8"),
            }
        raise TypeError(f"Unsupported image type: {type(image)}")

    @staticmethod
    def _guess_media_type(path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        mapping = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return mapping.get(ext, "image/png")


__provider_id__ = "anthropic"
__provider_class__ = AnthropicProvider
