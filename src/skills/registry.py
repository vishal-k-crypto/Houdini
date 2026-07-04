"""Skill registry for matching tasks to reusable skill instructions."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from .loader import Skill, load_skills


class SkillRegistry:
    """Maintains a loaded set of skills and matches them to task descriptions."""

    def __init__(self, skills: Optional[List[Skill]] = None):
        self._skills: List[Skill] = skills or []
        self._index: Dict[str, Skill] = {s.id: s for s in self._skills}

    @classmethod
    def from_directories(cls, directories: Optional[List[Path]] = None) -> "SkillRegistry":
        return cls(load_skills(directories))

    @property
    def skills(self) -> List[Skill]:
        return list(self._skills)

    def reload(self, directories: Optional[List[Path]] = None) -> None:
        """Reload skills from disk."""
        self._skills = load_skills(directories)
        self._index = {s.id: s for s in self._skills}

    def get(self, skill_id: str) -> Optional[Skill]:
        return self._index.get(skill_id)

    def match(self, task: str, top_k: int = 3, min_score: float = 0.0) -> List[Skill]:
        """Return skills that appear relevant to the task.

        Matching is intentionally lightweight: keyword overlap on triggers, tags,
        name, and description. More sophisticated matching (embeddings) can be
        layered on later.
        """
        task_lower = task.lower()
        task_tokens = set(_tokenize(task_lower))
        scored: List[tuple[float, Skill]] = []

        for skill in self._skills:
            score = _score_skill(skill, task_lower, task_tokens)
            if score > min_score:
                scored.append((score, skill))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [skill for _, skill in scored[:top_k]]

    def prompt_for_task(self, task: str, top_k: int = 2) -> str:
        """Build a system-prompt fragment containing relevant skills."""
        matches = self.match(task, top_k=top_k)
        if not matches:
            return ""
        parts = ["# Reusable Skills for This Task\n"]
        for skill in matches:
            parts.append(skill.prompt_fragment)
        return "\n".join(parts)


def _tokenize(text: str) -> List[str]:
    """Simple whitespace/punctuation tokenizer."""
    return [t for t in re.split(r"[^a-z0-9]+", text) if len(t) > 2]


def _score_skill(skill: Skill, task_lower: str, task_tokens: set[str]) -> float:
    """Compute a simple relevance score between a skill and a task."""
    score = 0.0

    # Exact trigger match is strongest.
    for trigger in skill.triggers:
        if trigger in task_lower:
            score += 2.0
            # Bonus if trigger appears at the start.
            if task_lower.startswith(trigger):
                score += 1.0

    # Token overlap on name/description/tags.
    haystack = " ".join(
        [skill.name, skill.description, " ".join(skill.tags), " ".join(skill.triggers)]
    ).lower()
    haystack_tokens = set(_tokenize(haystack))
    overlap = task_tokens & haystack_tokens
    if haystack_tokens:
        score += 1.5 * len(overlap) / max(len(haystack_tokens), len(task_tokens))

    # Priority boost.
    score += skill.priority * 0.1

    return score


# Module-level singleton
skill_registry = SkillRegistry.from_directories()
