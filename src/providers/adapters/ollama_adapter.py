"""Ollama adapter for Houdini.

Wraps the existing src.utils.ollama_client.OllamaClient as a unified LLMProvider
so planners and supervisors can use it through the common abstraction without
rewriting the low-level HTTP logic.
"""
from __future__ import annotations

import os
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

from ..base import GenerateResult, LLMProvider, ProviderUsage


class OllamaProvider(LLMProvider):
    """Adapter for Ollama local models via the HTTP REST API."""

    DEFAULT_MODEL: str = "qwen3-coder:480b-cloud"

    def __init__(
        self,
        model_name: Optional[str] = None,
        *,
        cloud_endpoint: Optional[str] = None,
        timeout: Optional[int] = None,
        **kwargs,
    ):
        super().__init__(model_name=model_name or self.DEFAULT_MODEL, **kwargs)
        self.base_url = (
            cloud_endpoint
            or os.environ.get("OLLAMA_ENDPOINT")
            or "http://localhost:11434"
        ).rstrip("/")
        self.timeout = timeout or 120

    @property
    def provider_id(self) -> str:
        return "ollama"

    @property
    def supports_vision(self) -> bool:
        # Ollama supports vision for LLaVA-based models; conservative default
        model = (self.model_name or "").lower()
        return "llava" in model or "vision" in model

    @property
    def is_local(self) -> bool:
        return True

    @classmethod
    def detect(cls) -> Dict[str, Any]:
        try:
            url = f"{(os.environ.get('OLLAMA_ENDPOINT') or 'http://localhost:11434').rstrip('/')}/api/tags"
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = resp.read().decode()
                import json

                models = json.loads(data).get("models", [])
                return {
                    "available": True,
                    "local": True,
                    "models": [m.get("name") for m in models][:20],
                }
        except Exception:
            return {"available": False, "local": True}

    def _http_post(self, path: str, payload: dict, timeout: Optional[float] = None) -> dict:
        url = f"{self.base_url}{path}"
        import json

        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=timeout or self.timeout)
        body = resp.read().decode()
        return json.loads(body)

    def _http_get(self, path: str, timeout: float = 10) -> dict:
        import json

        url = f"{self.base_url}{path}"
        resp = urllib.request.urlopen(url, timeout=timeout)
        return json.loads(resp.read().decode())

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        context: Optional[List[Dict[str, str]]] = None,
        **kwargs,
    ) -> GenerateResult:
        import json

        temperature = temperature if temperature is not None else 0.7
        model_to_use = self.model_name or self.DEFAULT_MODEL

        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if context and isinstance(context, list):
            for msg in context:
                if isinstance(msg, dict) and "role" in msg:
                    messages.append(msg)
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model_to_use,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens or 4096,
            },
        }
        if stop:
            payload["options"]["stop"] = stop

        start = time.time()
        try:
            resp = self._http_post("/api/chat", payload)
            output = (resp.get("message") or {}).get("content", "").strip()
        except Exception as first_exc:
            # Fallback to /api/generate for older Ollama versions
            try:
                gen_payload = {
                    "model": model_to_use,
                    "prompt": prompt,
                    "system": system_prompt or "",
                    "stream": False,
                    "options": payload["options"],
                }
                resp = self._http_post("/api/generate", gen_payload)
                output = resp.get("response", "").strip()
            except Exception:
                raise first_exc
        duration_ms = (time.time() - start) * 1000

        return GenerateResult(
            text=output,
            usage=ProviderUsage(model=model_to_use, duration_ms=duration_ms),
            raw_response=resp,
        )

    def generate_with_image(
        self,
        prompt: str,
        image: Any,
        *,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> GenerateResult:
        import base64

        if not self.supports_vision:
            raise RuntimeError(f"Model {self.model_name} may not support vision via Ollama.")

        image_b64 = self._normalize_image(image)
        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt, "images": [image_b64]})

        payload = {
            "model": self.model_name or self.DEFAULT_MODEL,
            "messages": messages,
            "stream": False,
            "options": {"temperature": kwargs.get("temperature", 0.7)},
        }
        start = time.time()
        resp = self._http_post("/api/chat", payload)
        duration_ms = (time.time() - start) * 1000
        output = (resp.get("message") or {}).get("content", "").strip()
        return GenerateResult(
            text=output,
            usage=ProviderUsage(model=self.model_name, duration_ms=duration_ms),
            raw_response=resp,
        )

    def _normalize_image(self, image: Any) -> str:
        import base64

        if isinstance(image, str):
            with open(image, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        if isinstance(image, bytes):
            return base64.b64encode(image).decode("utf-8")
        raise TypeError(f"Unsupported image type: {type(image)}")

    def list_models(self) -> List[str]:
        try:
            tags = self._http_get("/api/tags")
            return [m.get("name", "") for m in tags.get("models", [])]
        except Exception:
            return []

    def health_check(self) -> Dict[str, Any]:
        try:
            tags = self._http_get("/api/tags")
            models = [m.get("name", "") for m in tags.get("models", [])]
            return {
                "provider": self.provider_id,
                "model": self.model_name,
                "healthy": True,
                "supports_vision": self.supports_vision,
                "base_url": self.base_url,
                "models": models,
            }
        except Exception as e:
            return {
                "provider": self.provider_id,
                "model": self.model_name,
                "healthy": False,
                "error": str(e),
                "base_url": self.base_url,
            }


__provider_id__ = "ollama"
__provider_class__ = OllamaProvider
