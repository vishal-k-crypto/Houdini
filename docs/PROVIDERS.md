# Houdini Agent — Provider Abstraction Guide

Houdini uses a unified adapter layer in `src/providers/` so planners, supervisors, and executors can work with any LLM provider without hardcoding Ollama, OpenAI, Gemini, etc.

---

## Supported Providers

| Provider ID | Type | Required Key / Detection | Notes |
|-------------|------|--------------------------|-------|
| `ollama` | Local API | `OLLAMA_ENDPOINT` (optional) | Default provider; runs on your machine |
| `openai` | Cloud API | `OPENAI_API_KEY` | OpenAI-compatible SDK |
| `anthropic` | Cloud API | `ANTHROPIC_API_KEY` | Claude family |
| `gemini` | Cloud API | `GEMINI_API_KEY` | Google Gemini |
| `deepseek` | Cloud API | `DEEPSEEK_API_KEY` | OpenAI-compatible endpoint |
| `openrouter` | Cloud API | `OPENROUTER_API_KEY` | OpenAI-compatible gateway |
| `grok` | Cloud API | `XAI_API_KEY` | xAI / Grok models |
| `webllm` | Browser | None | Runs via the frontend; see [FRONTEND.md](FRONTEND.md) |
| `claude-code` | CLI | `claude` in PATH | Anthropic terminal agent |
| `codex` | CLI | `codex` in PATH | OpenAI terminal agent |
| `opencode` | CLI | `opencode` in PATH | OpenAI terminal agent |
| `kimi` | CLI | `kimi` in PATH | Moonshot terminal agent |
| `gemini-cli` | CLI | `gemini` in PATH | Google terminal agent |
| `agy` / `antigravity` | CLI | `agy` in PATH | Terminal agent |
| `qwen` | CLI | `qwen` in PATH | Alibaba terminal agent |

---

## How to Add a New Provider Adapter

### 1. Create a New Adapter Module

Add a file under `src/providers/adapters/` named `<provider>_adapter.py`.

### 2. Subclass `LLMProvider`

Implement the required properties and methods:

```python
from typing import Any, Dict, List, Optional
from ..base import GenerateResult, LLMProvider, ProviderUsage

class MyProvider(LLMProvider):
    """Adapter for MyProvider."""

    DEFAULT_MODEL: str = "my-model"
    ENV_KEY: str = "MY_API_KEY"

    def __init__(self, model_name: Optional[str] = None, *, api_key: Optional[str] = None, **kwargs):
        super().__init__(model_name=model_name or self.DEFAULT_MODEL, **kwargs)
        self.api_key = api_key or os.environ.get(self.ENV_KEY)

    @property
    def provider_id(self) -> str:
        return "myprovider"

    @property
    def supports_vision(self) -> bool:
        return True  # or False

    @classmethod
    def detect(cls) -> Dict[str, Any]:
        available = bool(os.environ.get(self.ENV_KEY))
        return {"available": available, "requires_api_key": True}

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
        # ... implement generation
        return GenerateResult(text="...", usage=ProviderUsage())

__provider_id__ = "myprovider"
__provider_class__ = MyProvider
```

### 3. Register the Adapter

Registration happens automatically via `ProviderRegistry.auto_load("src.providers.adapters")` as long as the module defines `__provider_id__` and `__provider_class__`.

To add aliases, call `register_alias` at the bottom of the module:

```python
from ..registry import registry
registry.register_alias("mp", "myprovider")
```

### 4. Add Environment Variables

Add the required key(s) to `.env.example` so users know how to configure it:

```bash
# ----- MyProvider -----
MY_API_KEY=your_myprovider_key_here
MY_BASE_URL=https://api.myprovider.com/v1
```

### 5. Update Settings (if needed)

If the provider needs a default model or base URL, add it to `config/settings.py` or keep it in the adapter.

---

## Environment Variables and CLI Detection

### Detection Order

`ProviderRegistry.detect_available()` checks each adapter in this order:

1. If the adapter defines a `detect()` class method, it is called first.
2. Otherwise, the registry checks for `ENV_KEY` in the environment.

### CLI Detection

For CLI agents, adapters should use `shutil.which()` to check for the binary in PATH:

```python
import shutil

@classmethod
def detect(cls) -> Dict[str, Any]:
    binary = shutil.which("claude")
    return {
        "available": bool(binary),
        "type": "cli",
        "binary": binary,
    }
```

### Common Environment Variables

See `.env.example` for the full list. Key variables:

| Variable | Provider | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | OpenAI | API key |
| `ANTHROPIC_API_KEY` | Anthropic | API key |
| `GEMINI_API_KEY` | Gemini | API key |
| `DEEPSEEK_API_KEY` | DeepSeek | API key |
| `OPENROUTER_API_KEY` | OpenRouter | API key |
| `XAI_API_KEY` | Grok / xAI | API key |
| `OLLAMA_ENDPOINT` | Ollama | Custom Ollama URL |
| `OLLAMA_DEFAULT_MODEL` | Ollama | Default model name |

---

## Fallback and Routing Logic

### Default Provider Selection

`get_default_provider()` picks the first available provider in this priority order:

1. `ollama` (if running)
2. `gemini` (if `GEMINI_API_KEY` set)
3. `openai` (if `OPENAI_API_KEY` set)
4. `anthropic` (if `ANTHROPIC_API_KEY` set)

### Model Selection

Models can be selected via:

- CLI: `--model <provider>/<model>` or `--model <model>`
- Environment: `OLLAMA_DEFAULT_MODEL`, `GEMINI_MODEL`, etc.
- Config: `HoudiniSettings`

If a model is prefixed with a provider ID (e.g., `openai/gpt-4o`), the registry creates the appropriate adapter.

### Fallback Chain

A higher-level provider router can be implemented in `src/providers/router.py` (planned) to:

- Try the preferred provider first.
- Fall back to local Ollama if the cloud provider fails.
- Rate-limit and retry gracefully.
- Track cost per provider.

### Runtime Usage

```python
from src.providers.registry import registry

provider = registry.create("openai", model_name="gpt-4o")
result = provider.generate("Plan a desktop task.")
print(result.text)
```

---

## WebLLM

WebLLM is a special browser-only provider. It is not implemented as a Python adapter. Instead, the frontend handles model loading, inference, and message passing. The frontend can send generated plans to the Houdini daemon over HTTP/WebSocket.

See [FRONTEND.md](FRONTEND.md) for WebLLM integration details.

---

## Testing Adapters

Add a test in `tests/` that mocks the provider API and verifies:

- `generate()` returns a `GenerateResult`.
- `detect()` correctly reports availability.
- `health_check()` returns a valid dict.

Example:

```python
def test_openai_adapter_detects_without_key():
    from src.providers.adapters.openai_adapter import OpenAICompatibleProvider
    info = OpenAICompatibleProvider.detect()
    assert "available" in info
    assert "requires_api_key" in info
```

---

## Summary

- Adapters live in `src/providers/adapters/`.
- Subclass `LLMProvider` and define `__provider_id__`/`__provider_class__`.
- Use `ENV_KEY` or a custom `detect()` for auto-discovery.
- Update `.env.example` and [README.md](../README.md) for new providers.
- WebLLM is handled by the frontend, not a Python adapter.
