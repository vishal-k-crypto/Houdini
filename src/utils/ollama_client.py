"""
Ollama Client — uses the Ollama HTTP REST API directly.

Replaces the previous subprocess-based approach (ollama run / curl) with
direct HTTP calls for lower latency, proper message formatting, and
reliable JSON handling.
"""
import json
import re
import time
import urllib.request
import urllib.error
from typing import Optional, List, Dict
from .logging import logger

try:
    from ..replay.execution_logger import log_llm_interaction
except ImportError:
    def log_llm_interaction(*args, **kwargs): pass

try:
    from config.settings import settings as _settings
except ImportError:
    _settings = None


def _cfg(attr: str, fallback):
    if _settings is not None:
        return getattr(_settings, attr, fallback)
    return fallback


class OllamaClient:
    """
    Client for Ollama models via the HTTP REST API.

    Uses /api/chat (preferred) for proper role-based messaging and
    /api/generate as fallback.  No subprocess spawning — all calls go
    through urllib so there is zero process-creation overhead.
    """

    def __init__(self, model_name: str = None, cloud_endpoint: Optional[str] = None):
        self.model_name = model_name or _cfg("ollama_default_model", "qwen3-coder:480b-cloud")
        import os
        self.base_url = (
            cloud_endpoint
            or os.getenv("OLLAMA_ENDPOINT")
            or _cfg("ollama_endpoint", None)
            or "http://localhost:11434"
        )
        # Strip trailing slash
        self.base_url = self.base_url.rstrip("/")
        self._timeout = _cfg("ollama_generate_timeout", 120)
        self._verify_installation()

    # ── helpers ──────────────────────────────────────────────────

    def _http_post(self, path: str, payload: dict, timeout: Optional[float] = None) -> dict:
        """Low-level HTTP POST returning parsed JSON."""
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=timeout or self._timeout)
        body = resp.read().decode()
        return json.loads(body)

    def _http_get(self, path: str, timeout: float = 10) -> dict:
        url = f"{self.base_url}{path}"
        resp = urllib.request.urlopen(url, timeout=timeout)
        return json.loads(resp.read().decode())

    def _verify_installation(self):
        """Ping the Ollama API to confirm it's reachable."""
        try:
            tags = self._http_get("/api/tags", timeout=10)
            names = [m.get("name", "") for m in tags.get("models", [])][:5]
            logger.info(f"Ollama API reachable. Models: {', '.join(names) or '(none pulled)'}")
        except Exception as e:
            logger.warning(f"Ollama API check failed ({self.base_url}): {e}")

    # ── main generation ─────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[List[Dict]] = None,
        retry_count: int = None,
        temperature: float = None,
        model: Optional[str] = None,
        images: Optional[List[str]] = None,
    ) -> str:
        """
        Generate text using the Ollama /api/chat endpoint.

        Uses proper role-based messages so the model's native chat template
        is applied server-side (no more hardcoded <|system|> tags).
        """
        if retry_count is None:
            retry_count = _cfg("ollama_retry_count", 3)
        if temperature is None:
            temperature = _cfg("ollama_default_temperature", 0.7)

        model_to_use = model or self.model_name

        # Build messages array for /api/chat
        messages: List[Dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Inject conversation context if provided as message dicts
        if context and isinstance(context, list):
            for msg in context:
                if isinstance(msg, dict) and "role" in msg:
                    messages.append(msg)

        user_msg: Dict = {"role": "user", "content": prompt}
        if images:
            user_msg["images"] = images
        messages.append(user_msg)

        payload = {
            "model": model_to_use,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": _cfg("ollama_max_tokens", 4096),
            },
        }

        for attempt in range(retry_count):
            try:
                start_time = time.time()
                resp = self._http_post("/api/chat", payload)
                duration = time.time() - start_time

                output = (resp.get("message") or {}).get("content", "").strip()

                if not output:
                    # Fallback: try /api/generate for older Ollama versions
                    gen_payload = {
                        "model": model_to_use,
                        "prompt": prompt,
                        "system": system_prompt or "",
                        "stream": False,
                        "options": payload["options"],
                    }
                    if images:
                        gen_payload["images"] = images
                    resp = self._http_post("/api/generate", gen_payload)
                    duration = time.time() - start_time
                    output = resp.get("response", "").strip()

                if output:
                    logger.debug(f"Ollama ({model_to_use}) response: {duration:.1f}s, {len(output)} chars")
                    log_llm_interaction(
                        component="ollama_client",
                        prompt=prompt,
                        response=output,
                        model=model_to_use,
                        duration_ms=duration * 1000,
                    )
                    return output

                logger.warning(f"Empty Ollama response (attempt {attempt+1}/{retry_count})")

            except urllib.error.URLError as e:
                logger.error(f"Ollama network error (attempt {attempt+1}/{retry_count}): {e}")
            except json.JSONDecodeError as e:
                logger.error(f"Ollama JSON error (attempt {attempt+1}/{retry_count}): {e}")
            except Exception as e:
                logger.error(f"Ollama error (attempt {attempt+1}/{retry_count}): {e}")

            if attempt < retry_count - 1:
                time.sleep(2 ** attempt)

        raise RuntimeError(f"Failed to get response from Ollama after {retry_count} attempts")

    def generate_with_history(
        self,
        prompt: str,
        history: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Generate with conversation history passed as proper chat messages."""
        # Pass history as context — generate() injects them as messages
        recent = history[-5:] if history else []
        return self.generate(
            prompt,
            system_prompt=system_prompt,
            context=recent,
            **kwargs,
        )

    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> dict:
        """Generate and parse a JSON response with robust extraction."""
        if "json" not in prompt.lower():
            prompt += "\n\nRespond with valid JSON only."

        response = self.generate(prompt, system_prompt=system_prompt, **kwargs)
        return self._extract_json(response)

    # ── JSON extraction (robust, handles nested fences) ─────────

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Extract JSON from LLM response handling markdown fences and noise."""
        # 1. Try ```json ... ``` blocks
        fence_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", text)
        if fence_match:
            candidate = fence_match.group(1).strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        # 2. Find outermost { ... } using brace counting (handles nested objects)
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
                        start = -1  # try next top-level object

        # 3. Last resort — try entire text
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        raise ValueError(f"Could not extract JSON from Ollama response: {text[:300]}")


# Alias for backward compatibility
QwenClient = OllamaClient
