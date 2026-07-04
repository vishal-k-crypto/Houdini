"""WebLLM adapter placeholder for Houdini.

WebLLM runs inside the browser via WebGPU; the Python backend cannot drive it
directly. This adapter provides a stub API surface that the daemon can expose
to the frontend and that the frontend can replace with real `@mlc-ai/web-llm`
calls.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..base import GenerateResult, LLMProvider


class WebLLMProvider(LLMProvider):
    """Placeholder adapter for in-browser WebLLM inference."""

    DEFAULT_MODEL: str = "Llama-3.2-1B-Instruct-q4f32_1-MLC"

    def __init__(self, model_name: Optional[str] = None, **kwargs):
        super().__init__(model_name=model_name or self.DEFAULT_MODEL, **kwargs)

    @property
    def provider_id(self) -> str:
        return "webllm"

    @property
    def supports_vision(self) -> bool:
        return False

    @property
    def is_local(self) -> bool:
        return True

    @classmethod
    def detect(cls) -> Dict[str, Any]:
        # WebLLM is always available in the sense that the frontend can use it.
        return {"available": False, "frontend_only": True, "local": True}

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
        raise NotImplementedError(
            "WebLLM generation is handled in the browser. "
            "Use the frontend WebLLM client."
        )

    def health_check(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_id,
            "model": self.model_name,
            "healthy": True,
            "frontend_only": True,
        }


__provider_id__ = "webllm"
__provider_class__ = WebLLMProvider
