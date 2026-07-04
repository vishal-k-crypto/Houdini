"""Tests for the skill generator."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.providers.base import GenerateResult
from src.skills.generator import SkillGenerator


def test_normalize_id():
    assert SkillGenerator._normalize_id("Open Safari!!") == "open-safari"
    assert SkillGenerator._normalize_id("") is None
    assert SkillGenerator._normalize_id("---") is None


def test_derive_id():
    task = "Open System Settings and navigate to Wi-Fi"
    sid = SkillGenerator._derive_id(task)
    assert sid.startswith("open-system-settings-and-navigate-to-wi-fi")


def test_clean_strips_fences():
    raw = "```markdown\n---\nid: x\n---\nbody\n```"
    cleaned = SkillGenerator._clean(raw)
    assert "```" not in cleaned
    assert "id: x" in cleaned


def test_render_roundtrip():
    front = {"id": "test-skill", "name": "Test", "triggers": ["open", "launch"], "priority": 10}
    body = "Do this and that."
    text = SkillGenerator._render(front, body)
    assert text.startswith("---\nid: test-skill")
    assert "- open" in text
    assert "- launch" in text
    assert body in text


def test_generate_with_mock_client(tmp_path):
    fake_skill = """---
id: open-safari-search
triggers:
  - safari
  - search
tags:
  - browser
priority: 10
---

1. Open Safari.
2. Search for the query.
3. Wait for results.
"""
    client = MagicMock()
    client.supports_vision = False
    client.generate.return_value = GenerateResult(text=fake_skill)

    gen = SkillGenerator(client=client)
    result = gen.generate("Open Safari and search Google for Houdini", error="Could not find search box")

    assert result["skill_id"] == "open-safari-search"
    assert "Open Safari" in result["skill_text"]
    client.generate.assert_called_once()


def test_generate_and_save(tmp_path):
    fake_skill = """---
id: save-notes
name: Save Notes
triggers:
  - save note
tags:
  - notes
priority: 10
---
Press Cmd+S.
"""
    client = MagicMock()
    client.supports_vision = False
    client.generate.return_value = GenerateResult(text=fake_skill)

    gen = SkillGenerator(client=client)
    result = gen.generate_and_save("Save a note in Notes", error="Nothing happened", directory=tmp_path)

    assert "path" in result
    assert result["path"].exists()
    assert "save-notes" in result["path"].name


def test_generate_fills_missing_frontmatter(tmp_path):
    body_only = "When the user asks to create a folder, use Cmd+Shift+N in Finder."
    client = MagicMock()
    client.supports_vision = False
    client.generate.return_value = GenerateResult(text=body_only)

    gen = SkillGenerator(client=client)
    result = gen.generate("Create a new folder in Finder", error="Wrong shortcut used")

    assert result["skill_text"].startswith("---")
    assert "id:" in result["skill_text"]
    assert "priority:" in result["skill_text"]
    assert body_only in result["skill_text"]
