"""Google Gemini adapter for Houdini.

Wraps the official google-genai SDK (when available) and falls back to the
Gemini CLI for text-only generation. BYOK via GEMINI_API_KEY / GOOGLE_API_KEY.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional, Union

from ..base import GenerateResult, LLMProvider, ProviderUsage


class GeminiProvider(LLMProvider):
    """Adapter for Google Gemini (SDK + CLI fallback)."""

    DEFAULT_MODEL: str = "gemini-2.0-flash-exp"
    ENV_KEYS: List[str] = ["GEMINI_API_KEY", "GOOGLE_API_KEY"]

    def __init__(
        self,
        model_name: Optional[str] = None,
        *,
        api_key: Optional[str] = None,
        use_cli: Optional[bool] = None,
        cli_timeout: int = 30,
        **kwargs,
    ):
        super().__init__(model_name=model_name or self.DEFAULT_MODEL, **kwargs)
        self.api_key = api_key
        for key in self.ENV_KEYS:
            self.api_key = self.api_key or os.environ.get(key)
        self._client: Optional[Any] = None
        self._use_cli = use_cli
        self._cli_timeout = cli_timeout
        self._sdk_available = self._check_sdk()
        self._cli_available = self._check_cli()

    @property
    def provider_id(self) -> str:
        return "gemini"

    @property
    def supports_vision(self) -> bool:
        return self._sdk_available

    @property
    def supports_tool_calls(self) -> bool:
        return self._sdk_available

    @classmethod
    def detect(cls) -> Dict[str, Any]:
        sdk = cls._check_sdk_static()
        cli = cls._check_cli_static()
        return {
            "available": sdk or cli or bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
            "sdk": sdk,
            "cli": cli,
            "requires_api_key": not cli,
        }

    def _check_sdk(self) -> bool:
        return self._check_sdk_static()

    @staticmethod
    def _check_sdk_static() -> bool:
        try:
            import google.genai  # noqa: F401
            return True
        except Exception:
            return False

    def _check_cli(self) -> bool:
        return self._check_cli_static()

    @staticmethod
    def _check_cli_static() -> bool:
        try:
            result = subprocess.run(
                ["gemini", "--version"], capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        if not self._sdk_available:
            raise RuntimeError("google-genai SDK not available for Gemini vision/tool use")
        from google import genai

        if self.api_key:
            self._client = genai.Client(api_key=self.api_key)
        else:
            self._client = genai.Client()  # uses ADC / env

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
        if self._use_cli is True or (self._use_cli is None and self._cli_available and not self._sdk_available):
            return self._generate_cli(prompt, system_prompt=system_prompt, **kwargs)

        self._ensure_client()
        temperature = temperature if temperature is not None else 0.7
        config_kwargs: Dict[str, Any] = {"temperature": temperature}
        if max_tokens:
            config_kwargs["max_output_tokens"] = max_tokens
        if stop:
            config_kwargs["stop_sequences"] = stop

        start = time.time()
        response = self._client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=config_kwargs if config_kwargs else None,
        )
        duration_ms = (time.time() - start) * 1000

        text = response.text or ""
        usage = ProviderUsage(
            model=self.model_name,
            input_tokens=getattr(response.usage_metadata, "prompt_token_count", None),
            output_tokens=getattr(response.usage_metadata, "candidates_token_count", None),
            total_tokens=getattr(response.usage_metadata, "total_token_count", None),
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
        from PIL import Image
        import io

        if isinstance(image, str):
            pil_image = Image.open(image)
        elif isinstance(image, bytes):
            pil_image = Image.open(io.BytesIO(image))
        else:
            raise TypeError(f"Unsupported image type: {type(image)}")

        contents = [prompt, pil_image]
        start = time.time()
        response = self._client.models.generate_content(
            model=self.model_name,
            contents=contents,
            config={"temperature": kwargs.get("temperature", 0.7)},
        )
        duration_ms = (time.time() - start) * 1000
        text = response.text or ""
        return GenerateResult(
            text=text,
            usage=ProviderUsage(
                model=self.model_name,
                duration_ms=duration_ms,
            ),
            raw_response=response,
        )

    def _generate_cli(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> GenerateResult:
        if not self._cli_available:
            raise RuntimeError("Gemini CLI not available")

        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        cmd = ["gemini", "-m", self.model_name, "-o", "text"]
        start = time.time()
        try:
            result = subprocess.run(
                cmd,
                input=full_prompt,
                capture_output=True,
                text=True,
                timeout=self._cli_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Gemini CLI timed out") from exc
        duration_ms = (time.time() - start) * 1000

        if result.returncode != 0:
            raise RuntimeError(f"Gemini CLI failed: {result.stderr}")

        return GenerateResult(
            text=result.stdout.strip(),
            usage=ProviderUsage(model=self.model_name, duration_ms=duration_ms),
        )


__provider_id__ = "gemini"
__provider_class__ = GeminiProvider
