"""Skill-as-file protocol for Houdini Agent.

Skills are reusable, versioned instruction files (Markdown + YAML frontmatter)
that teach the agent how to handle common task families. They are inspired by
Open Design's SKILL.md protocol and let the same runtime execute tasks more
reliably without re-planning from scratch every time.
"""
from .loader import load_skills, Skill
from .registry import SkillRegistry, skill_registry

__all__ = ["load_skills", "Skill", "SkillRegistry", "skill_registry"]
