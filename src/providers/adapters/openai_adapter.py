"""OpenAI-compatible adapter for Houdini.

Supports OpenAI, OpenRouter, DeepSeek, Grok, and any other OpenAI-compatible
endpoint. BYOK via the OPENAI_API_KEY / OPENROUTER_API_KEY / DEEPSEEK_API_KEY
environment variables or via explicit api_key.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Union

from ..base import GenerateResult, LLMProvider, ProviderUsage


def _model_alias(provider: str, model: str) -> str:
    """Return the full OpenRouter model id if needed."""
    if provider == "openrouter" and "/" not in model:
        return f"openrouter/{model}"
    if provider == "deepseek" and model == "default":
        return "deepseek-chat"
    return model


class OpenAICompatibleProvider(LLMProvider):
    """Adapter for OpenAI-compatible APIs."""

    DEFAULT_MODEL: str = "gpt-4o"
    ENV_KEY: str = "OPENAI_API_KEY"
    BASE_URLS: Dict[str, str] = {
        "openai": "https://api.openai.com/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "grok": "https://api.x.ai/v1",
    }

    def __init__(
        self,
        model_name: Optional[str] = None,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        provider: Optional[str] = None,
        **kwargs,
    ):
        # Determine provider flavor: explicit > environment > openai default
        self._provider = provider or self._infer_provider(model_name)
        super().__init__(
            model_name=model_name or self.DEFAULT_MODEL,
            api_key=api_key,
            base_url=base_url,
            provider=self._provider,
            **kwargs,
        )
        self.api_key = api_key or os.environ.get(self.ENV_KEY)
        if self._provider in ("openrouter",):
            self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY") or self.api_key
        if self._provider == "deepseek":
            self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY") or self.api_key
        if self._provider == "grok":
            self.api_key = api_key or os.environ.get("XAI_API_KEY") or os.environ.get("GROK_API_KEY") or self.api_key

        self.base_url = (
            base_url
            or os.environ.get(f"{self._provider.upper()}_BASE_URL")
            or self.BASE_URLS.get(self._provider, self.BASE_URLS["openai"])
        )

        self._client: Optional[Any] = None
        self._ensure_client()

    @property
    def provider_id(self) -> str:
        return self._provider

    @property
    def supports_vision(self) -> bool:
        # Conservative default; override by specific model families
        vision_models = {"gpt-4o", "gpt-4-turbo", "gpt-4-vision"}
        model = (self.model_name or "").lower()
        return any(v in model for v in vision_models) or "vision" in model

    @property
    def supports_tool_calls(self) -> bool:
        # Most OpenAI-compatible providers support tools
        return True

    @classmethod
    def detect(cls) -> Dict[str, Any]:
        available = bool(
            os.environ.get("OPENAI_API_KEY")
            or os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("XAI_API_KEY")
            or os.environ.get("GROK_API_KEY")
        )
        return {"available": available, "requires_api_key": True}

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        try:
            import openai
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI SDK not installed. Install with: pip install openai"
            ) from exc

        if not self.api_key:
            raise RuntimeError(
                f"API key required for {self._provider}. Set {self.ENV_KEY} or pass api_key."
            )

        self._client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)

    def _infer_provider(self, model_name: Optional[str]) -> str:
        if model_name and model_name.startswith("openrouter/"):
            return "openrouter"
        if model_name and model_name.startswith("deepseek/"):
            return "deepseek"
        if model_name and model_name.startswith("grok/"):
            return "grok"
        # Environment hints
        for flavor in ("openrouter", "deepseek", "grok", "openai"):
            if os.environ.get(f"{flavor.upper()}_API_KEY"):
                return flavor
        return "openai"

    def _build_messages(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

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
        self._ensure_client()
        temperature = temperature if temperature is not None else 0.7
        messages = self._build_messages(prompt, system_prompt)
        request: Dict[str, Any] = {
            "model": _model_alias(self._provider, self.model_name or self.DEFAULT_MODEL),
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            request["max_tokens"] = max_tokens
        if stop:
            request["stop"] = stop

        start = time.time()
        response = self._client.chat.completions.create(**request)  # type: ignore
        duration_ms = (time.time() - start) * 1000

        text = response.choices[0].message.content or ""
        usage = ProviderUsage.from_openai_response(response, duration_ms)
        return GenerateResult(text=text, usage=usage, raw_response=response)

    def generate_with_image(
        self,
        prompt: str,
        image: Any,
        *,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> GenerateResult:
        if not self.supports_vision:
            raise RuntimeError(f"Model {self.model_name} may not support vision.")
        self._ensure_client()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        image_content = self._normalize_image(image)
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_content}},
                ],
            }
        )

        start = time.time()
        response = self._client.chat.completions.create(  # type: ignore
            model=_model_alias(self._provider, self.model_name or self.DEFAULT_MODEL),
            messages=messages,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens"),
        )
        duration_ms = (time.time() - start) * 1000

        text = response.choices[0].message.content or ""
        usage = ProviderUsage.from_openai_response(response, duration_ms)
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
        messages = self._build_messages(prompt, system_prompt)
        response = self._client.chat.completions.create(  # type: ignore
            model=_model_alias(self._provider, self.model_name or self.DEFAULT_MODEL),
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens"),
        )
        message = response.choices[0].message
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(
                    {
                        "id": tc.id,
                        "function": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                )
        return GenerateResult(
            text=message.content or "",
            raw_response=response,
            tool_calls=tool_calls or None,
        )

    def _normalize_image(self, image: Any) -> str:
        """Return a data URI or URL for an image input."""
        import base64

        if isinstance(image, str):
            if image.startswith("http://") or image.startswith("https://") or image.startswith("data:"):
                return image
            with open(image, "rb") as f:
                data = f.read()
            encoded = base64.b64encode(data).decode("utf-8")
            return f"data:image/png;base64,{encoded}"
        if isinstance(image, bytes):
            encoded = base64.b64encode(image).decode("utf-8")
            return f"data:image/png;base64,{encoded}"
        raise TypeError(f"Unsupported image type: {type(image)}")


__provider_id__ = "openai"
__provider_class__ = OpenAICompatibleProvider
