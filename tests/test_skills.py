"""Tests for the skill-as-file protocol."""
from pathlib import Path

import pytest

from src.skills.loader import load_skill_file, load_skills
from src.skills.registry import SkillRegistry


@pytest.fixture
def sample_skill_dir(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    (skills_dir / "open-app.md").write_text(
        """---
id: open-app
name: Open an Application
description: Open an app via Spotlight.
triggers:
  - open
  - launch
tags:
  - macos
priority: 5
---

Use Cmd+Space to open Spotlight, type the app name, and press Enter.
""",
        encoding="utf-8",
    )

    (skills_dir / "save-file.md").write_text(
        """---
id: save-file
name: Save a File
description: Save a file to a folder.
triggers:
  - save
  - save as
tags:
  - file
priority: 2
---

Use Cmd+S, then Cmd+Shift+G to navigate to the folder.
""",
        encoding="utf-8",
    )

    # A file without frontmatter should be ignored by the loader if malformed,
    # but load_skill_file treats it as body-only.
    (skills_dir / "invalid.yaml").write_text("not markdown", encoding="utf-8")

    return skills_dir


def test_load_skill_file(sample_skill_dir: Path):
    skill = load_skill_file(sample_skill_dir / "open-app.md")
    assert skill.id == "open-app"
    assert skill.name == "Open an Application"
    assert "Spotlight" in skill.instructions
    assert skill.triggers == ["open", "launch"]
    assert skill.priority == 5


def test_load_skills_filters_by_extension(sample_skill_dir: Path):
    skills = load_skills([sample_skill_dir])
    ids = {s.id for s in skills}
    assert ids == {"open-app", "save-file"}


def test_skill_registry_match(sample_skill_dir: Path):
    registry = SkillRegistry.from_directories([sample_skill_dir])
    matches = registry.match("open Safari", top_k=2)
    assert len(matches) >= 1
    assert matches[0].id == "open-app"


def test_skill_registry_prompt_for_task(sample_skill_dir: Path):
    registry = SkillRegistry.from_directories([sample_skill_dir])
    prompt = registry.prompt_for_task("save the document to downloads")
    assert "Skill: Save a File" in prompt
    assert "Cmd+S" in prompt


def test_skill_registry_no_match_returns_empty_string(sample_skill_dir: Path):
    registry = SkillRegistry.from_directories([sample_skill_dir])
    prompt = registry.prompt_for_task("do something completely unrelated to anything")
    assert prompt == ""
