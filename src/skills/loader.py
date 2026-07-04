"""Load skill definitions from Markdown files with YAML frontmatter."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml


@dataclass
class Skill:
    """A single skill definition."""

    id: str
    name: str
    description: str
    triggers: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    instructions: str = ""
    source: Optional[Path] = None
    priority: int = 0
    metadata: Dict[str, any] = field(default_factory=dict)

    @property
    def prompt_fragment(self) -> str:
        """Return a system-prompt friendly fragment for this skill."""
        return (
            f"## Skill: {self.name}\n\n"
            f"{self.description}\n\n"
            f"{self.instructions}\n"
        )


def _parse_frontmatter(text: str) -> tuple[Dict[str, any], str]:
    """Split a Markdown file into YAML frontmatter and body."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                front = yaml.safe_load(parts[1]) or {}
            except Exception:
                front = {}
            body = parts[2].strip()
            return front, body
    return {}, text


def load_skill_file(path: Path) -> Skill:
    """Load a single skill from a Markdown file."""
    text = path.read_text(encoding="utf-8")
    front, body = _parse_frontmatter(text)

    skill_id = front.get("id") or path.stem
    name = front.get("name") or skill_id.replace("-", " ").title()

    return Skill(
        id=skill_id,
        name=name,
        description=front.get("description", ""),
        triggers=[t.lower() for t in front.get("triggers", [])],
        tags=[t.lower() for t in front.get("tags", [])],
        instructions=body,
        source=path,
        priority=int(front.get("priority", 0)),
        metadata=front.get("metadata", {}),
    )


def load_skills(
    directories: Optional[List[Path]] = None,
    pattern: str = "*.md",
) -> List[Skill]:
    """Load all skills from the given directories.

    Default search paths (in priority order):
      1. ./skills/
      2. ~/.config/houdini/skills/
      3. <package_dir>/builtin_skills/ (future)
    """
    if directories is None:
        directories = []
        project_skills = Path.cwd() / "skills"
        if project_skills.exists():
            directories.append(project_skills)
        user_skills = Path.home() / ".config" / "houdini" / "skills"
        if user_skills.exists():
            directories.append(user_skills)

    skills: List[Skill] = []
    seen_ids: set[str] = set()

    for directory in directories:
        if not directory.exists():
            continue
        for path in sorted(directory.glob(pattern)):
            try:
                skill = load_skill_file(path)
                if skill.id in seen_ids:
                    continue
                seen_ids.add(skill.id)
                skills.append(skill)
            except Exception as exc:
                # Be resilient: one bad skill shouldn't break the whole registry.
                import logging

                logging.getLogger(__name__).warning(f"Failed to load skill {path}: {exc}")

    # Higher priority skills sort first.
    skills.sort(key=lambda s: (-s.priority, s.id))
    return skills
