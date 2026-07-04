"""Structured observation from a browser page."""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class BrowserObservation:
    """A snapshot of the browser state at one timestep."""

    url: str
    title: str
    screenshot_b64: str
    accessibility_tree: Dict[str, Any]
    interactive_elements: List[Dict[str, Any]] = field(default_factory=list)
    clean_text: str = ""
    action_history: List[str] = field(default_factory=list)

    @property
    def screenshot_bytes(self) -> bytes:
        return base64.b64decode(self.screenshot_b64)

    def to_text_context(self, max_chars: int = 3000) -> str:
        parts = [
            f"URL: {self.url}",
            f"Title: {self.title}",
            "Page text:",
            self.clean_text[:max_chars],
        ]
        return "\n".join(parts)
