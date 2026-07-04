"""Generate new skills from task failures or user demonstrations.

The generator uses an LLM to turn a failed task description, error message,
and optional screenshot into a reusable skill Markdown file. Generated skills
are saved to the user's skill directory so they persist across upgrades and
can be edited by the user.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from ..utils.logging import logger


DEFAULT_USER_SKILLS_DIR = Path.home() / ".config" / "houdini" / "skills"


class SkillGenerator:
    """Generate skill files from failures or demonstrations."""

    SYSTEM_PROMPT = """You are a skill author for Houdini, a desktop automation agent.
Your job is to convert a failed task into a concise, reusable skill instruction file.

The file format is Markdown with YAML frontmatter:

---
id: unique-kebab-case-id
name: Short Human-Readable Name
description: One-line summary of what the skill covers.
triggers:
  - keyword or phrase that should activate this skill
  - another trigger
tags:
  - macos
  - category
priority: 10
---

Detailed step-by-step instructions for the agent. Be specific about:
- The exact keyboard shortcuts or clicks to use
- How to recover from common errors
- What to verify before considering the step complete

Rules:
- Keep instructions actionable and under 400 words.
- Use trigger phrases that would appear in the user's task.
- The id must be kebab-case, unique, and derived from the task.
- Do NOT include markdown code fences around the output.
- Output ONLY the skill file content.
"""

    def __init__(self, client=None):
        self.client = client

    def _get_client(self):
        if self.client is not None:
            return self.client
        # Lazy fallback: use the default provider
        from ..providers.router import get_provider
        return get_provider("planner")

    def generate(
        self,
        task: str,
        error: Optional[str] = None,
        screenshot: Optional[bytes] = None,
        existing_skills: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Generate a skill from a task failure.

        Returns a dict with 'skill_text', 'skill_id', and 'path' (if saved).
        """
        client = self._get_client()

        existing = ""
        if existing_skills:
            existing = "\nExisting skill ids to avoid:\n" + "\n".join(
                f"- {s.id}" for s in existing_skills
            )

        user_prompt = f"""Task that failed:
{task}

Error / reason for failure:
{error or 'No explicit error; the task did not complete as expected.'}

Write a skill that would help Houdini complete this task or recover from this failure next time.{existing}
"""

        kwargs = {"system_prompt": self.SYSTEM_PROMPT, "temperature": 0.3}
        if screenshot is not None and client.supports_vision:
            result = client.generate(user_prompt, images=[screenshot], **kwargs)
        else:
            result = client.generate(user_prompt, **kwargs)

        skill_text = result.text if hasattr(result, "text") else str(result)
        skill_text = self._clean(skill_text)

        front, body = self._parse_frontmatter(skill_text)
        skill_id = self._normalize_id(front.get("id")) or self._derive_id(task)

        # Merge a stable id if missing
        if "id" not in front:
            front["id"] = skill_id
        if "name" not in front:
            front["name"] = skill_id.replace("-", " ").title()
        if "description" not in front:
            front["description"] = f"Generated skill for: {task[:80]}"
        if "priority" not in front:
            front["priority"] = 10

        skill_text = self._render(front, body)
        return {"skill_id": skill_id, "skill_text": skill_text, "frontmatter": front, "body": body}

    def save(
        self,
        skill_text: str,
        skill_id: str,
        directory: Optional[Path] = None,
    ) -> Path:
        """Save a generated skill to disk and reload the registry."""
        directory = directory or DEFAULT_USER_SKILLS_DIR
        directory.mkdir(parents=True, exist_ok=True)

        path = directory / f"{skill_id}.md"
        counter = 1
        while path.exists():
            path = directory / f"{skill_id}-{counter}.md"
            counter += 1

        path.write_text(skill_text, encoding="utf-8")
        logger.info(f"Generated skill saved to {path}")

        # Reload registry so the new skill is immediately available
        try:
            from .registry import skill_registry
            skill_registry.reload()
        except Exception as exc:
            logger.warning(f"Failed to reload skill registry: {exc}")

        return path

    def generate_and_save(
        self,
        task: str,
        error: Optional[str] = None,
        screenshot: Optional[bytes] = None,
        directory: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Generate and persist a skill in one call."""
        from .registry import skill_registry

        result = self.generate(
            task,
            error=error,
            screenshot=screenshot,
            existing_skills=skill_registry.skills,
        )
        path = self.save(result["skill_text"], result["skill_id"], directory=directory)
        result["path"] = path
        return result

    @staticmethod
    def _clean(text: str) -> str:
        """Strip accidental markdown fences."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return text

    @staticmethod
    def _parse_frontmatter(text: str) -> tuple[Dict[str, Any], str]:
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

    @staticmethod
    def _render(front: Dict[str, Any], body: str) -> str:
        lines = ["---"]
        for key, value in front.items():
            if isinstance(value, list):
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {item}")
            else:
                lines.append(f"{key}: {value}")
        lines.append("---")
        lines.append("")
        lines.append(body.strip())
        return "\n".join(lines) + "\n"

    @staticmethod
    def _normalize_id(skill_id: Optional[str]) -> Optional[str]:
        if not skill_id:
            return None
        skill_id = re.sub(r"[^a-z0-9]+", "-", skill_id.lower()).strip("-")
        return skill_id or None

    @staticmethod
    def _derive_id(task: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", task.lower()).strip("-")
        base = base[:50].strip("-")
        timestamp = str(int(time.time()))[-6:]
        return f"{base}-{timestamp}" if base else f"generated-skill-{timestamp}"


def generate_skill_from_failure(
    task: str,
    error: Optional[str] = None,
    screenshot: Optional[bytes] = None,
    client=None,
) -> Dict[str, Any]:
    """Convenience function: generate and save a skill from a failure."""
    generator = SkillGenerator(client=client)
    return generator.generate_and_save(task, error=error, screenshot=screenshot)
