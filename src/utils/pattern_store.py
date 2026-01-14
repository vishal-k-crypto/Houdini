"""
Pattern Store - Learn and store repeating behavior patterns for efficient automation.

This module tracks successful action sequences, learns patterns from task executions,
and provides pattern matching to reuse learned behaviors for similar tasks.
"""

import json
import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from collections import defaultdict

from .logging import logger

PATTERNS_FILE = Path(__file__).parent.parent.parent / "data" / "patterns.json"


@dataclass
class Pattern:
    """A learned pattern from successful executions."""
    id: str
    task_template: str                      # Normalized task pattern (e.g., "open {app} and search {query}")
    original_tasks: List[str]               # Original task strings that matched this pattern
    action_sequence: List[str]              # Successful action sequence
    variables: Dict[str, List[str]]         # Variable values seen (e.g., {"app": ["Safari", "Chrome"]})
    success_count: int = 0
    fail_count: int = 0
    total_duration: float = 0.0
    context_tags: List[str] = field(default_factory=list)
    optimized_waits: Dict[str, float] = field(default_factory=dict)  # action_idx -> optimal wait time
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_used: str = field(default_factory=lambda: datetime.now().isoformat())
    
    @property
    def avg_duration(self) -> float:
        total = self.success_count + self.fail_count
        return self.total_duration / max(total, 1)
    
    @property
    def success_rate(self) -> float:
        total = self.success_count + self.fail_count
        return self.success_count / max(total, 1)
    
    @property
    def confidence(self) -> float:
        """Confidence score based on success rate and usage count."""
        usage = self.success_count + self.fail_count
        # More usage = more confident (up to a point)
        usage_factor = min(usage / 20, 1.0)  # Max confidence at 20 uses
        return self.success_rate * usage_factor
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "task_template": self.task_template,
            "original_tasks": self.original_tasks,
            "action_sequence": self.action_sequence,
            "variables": self.variables,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "total_duration": self.total_duration,
            "context_tags": self.context_tags,
            "optimized_waits": self.optimized_waits,
            "created_at": self.created_at,
            "last_used": self.last_used
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Pattern":
        return cls(
            id=data["id"],
            task_template=data["task_template"],
            original_tasks=data.get("original_tasks", []),
            action_sequence=data["action_sequence"],
            variables=data.get("variables", {}),
            success_count=data.get("success_count", 0),
            fail_count=data.get("fail_count", 0),
            total_duration=data.get("total_duration", 0.0),
            context_tags=data.get("context_tags", []),
            optimized_waits=data.get("optimized_waits", {}),
            created_at=data.get("created_at", datetime.now().isoformat()),
            last_used=data.get("last_used", datetime.now().isoformat())
        )


class PatternStore:
    """
    Store and retrieve learned patterns from task executions.
    
    Features:
    - Pattern normalization (extract templates from specific tasks)
    - Similarity matching for finding relevant patterns
    - Pattern merging and optimization
    - Persistence to JSON file
    """
    
    # Common patterns for task normalization
    VARIABLE_PATTERNS = [
        # App names
        (r'\b(Safari|Chrome|Firefox|Opera|Edge|Brave)\b', '{browser}'),
        (r'\b(Finder|Notes|Calendar|Messages|Mail|Terminal|Calculator|Preview|Photos)\b', '{app}'),
        # Search queries - capture quoted or unquoted text after "search for" or "search"
        (r'search(?:\s+for)?\s+["\']?([^"\']+)["\']?$', 'search for {query}'),
        # URLs
        (r'(?:go to|open|visit)\s+(https?://\S+|www\.\S+|\w+\.\w+)', 'go to {url}'),
        # File/folder names
        (r'(?:file|folder|document)\s+(?:named|called)\s+["\']?(\w+)["\']?', 'folder named {name}'),
    ]
    
    def __init__(self, patterns_file: Path = PATTERNS_FILE):
        self.patterns_file = patterns_file
        self.patterns: Dict[str, Pattern] = {}
        self._load()
    
    def _load(self):
        """Load patterns from disk."""
        try:
            if self.patterns_file.exists():
                with open(self.patterns_file, 'r') as f:
                    data = json.load(f)
                    for pattern_data in data.get("patterns", []):
                        pattern = Pattern.from_dict(pattern_data)
                        self.patterns[pattern.id] = pattern
                logger.debug(f"Loaded {len(self.patterns)} patterns from {self.patterns_file}")
        except Exception as e:
            logger.warning(f"Could not load patterns: {e}")
            self.patterns = {}
    
    def _save(self):
        """Save patterns to disk."""
        try:
            self.patterns_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "patterns": [p.to_dict() for p in self.patterns.values()],
                "last_updated": datetime.now().isoformat()
            }
            with open(self.patterns_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save patterns: {e}")
    
    def normalize_task(self, task: str) -> Tuple[str, Dict[str, str]]:
        """
        Convert a specific task into a template with variables.
        
        Returns:
            Tuple of (template, variables_dict)
            e.g., ("open {browser} and search for {query}", {"browser": "Safari", "query": "weather"})
        """
        template = task.lower().strip()
        variables = {}
        
        # Extract browser names
        browser_match = re.search(r'\b(safari|chrome|firefox|opera|edge|brave)\b', template, re.IGNORECASE)
        if browser_match:
            variables["browser"] = browser_match.group(1).title()
            template = re.sub(r'\b(safari|chrome|firefox|opera|edge|brave)\b', '{browser}', template, flags=re.IGNORECASE)
        
        # Extract app names
        app_match = re.search(r'\b(finder|notes|calendar|messages|mail|terminal|calculator|preview|photos|whatsapp|spotify|slack|discord)\b', template, re.IGNORECASE)
        if app_match and "browser" not in variables:
            variables["app"] = app_match.group(1).title()
            template = re.sub(r'\b(finder|notes|calendar|messages|mail|terminal|calculator|preview|photos|whatsapp|spotify|slack|discord)\b', '{app}', template, flags=re.IGNORECASE)
        
        # Extract search queries - match text after "search for" or "search"
        search_match = re.search(r'search(?:\s+for)?\s+(.+?)(?:\s+on|\s+in|\s+and|$)', template)
        if search_match:
            query = search_match.group(1).strip()
            if query and '{' not in query:  # Not already a variable
                variables["query"] = query
                template = re.sub(re.escape(query), '{query}', template)
        
        # Extract URLs
        url_match = re.search(r'(?:go to|open|visit)\s+(https?://\S+|www\.\S+|[\w-]+\.(?:com|org|net|io)\S*)', template)
        if url_match:
            url = url_match.group(1)
            variables["url"] = url
            template = template.replace(url, '{url}')
        
        return template, variables
    
    def _generate_pattern_id(self, template: str) -> str:
        """Generate a unique ID for a pattern template."""
        return hashlib.md5(template.encode()).hexdigest()[:12]
    
    def find_similar(self, task: str, threshold: float = 0.6) -> List[Tuple[Pattern, float]]:
        """
        Find patterns similar to the given task.
        
        Returns:
            List of (pattern, similarity_score) tuples, sorted by score descending
        """
        template, variables = self.normalize_task(task)
        results = []
        
        for pattern in self.patterns.values():
            similarity = self._calculate_similarity(template, pattern.task_template)
            if similarity >= threshold:
                results.append((pattern, similarity))
        
        # Sort by similarity, then by confidence
        results.sort(key=lambda x: (x[1], x[0].confidence), reverse=True)
        return results
    
    def _calculate_similarity(self, template1: str, template2: str) -> float:
        """
        Calculate similarity between two templates using token-based matching.
        """
        # Tokenize
        tokens1 = set(re.findall(r'\w+|\{[^}]+\}', template1))
        tokens2 = set(re.findall(r'\w+|\{[^}]+\}', template2))
        
        if not tokens1 or not tokens2:
            return 0.0
        
        # Jaccard similarity
        intersection = tokens1 & tokens2
        union = tokens1 | tokens2
        
        # Boost score if variable placeholders match
        var_tokens1 = {t for t in tokens1 if t.startswith('{')}
        var_tokens2 = {t for t in tokens2 if t.startswith('{')}
        var_match_bonus = 0.1 if var_tokens1 == var_tokens2 else 0.0
        
        return len(intersection) / len(union) + var_match_bonus
    
    def get_best_pattern(self, similar_patterns: List[Tuple[Pattern, float]]) -> Optional[Pattern]:
        """
        Get the best pattern from a list of similar patterns.
        Considers both similarity and confidence.
        """
        if not similar_patterns:
            return None
        
        # Score = similarity * 0.4 + confidence * 0.6
        def score(item):
            pattern, similarity = item
            return similarity * 0.4 + pattern.confidence * 0.6
        
        best = max(similar_patterns, key=score)
        return best[0] if score(best) > 0.5 else None
    
    def record_execution(
        self,
        task: str,
        actions: List[Dict],
        success: bool,
        duration: float = 0.0
    ):
        """
        Record a task execution to learn patterns.
        
        Args:
            task: The original task string
            actions: List of action dicts with {action, success, duration}
            success: Whether the overall execution succeeded
            duration: Total execution duration
        """
        template, variables = self.normalize_task(task)
        pattern_id = self._generate_pattern_id(template)
        
        # Extract action strings
        action_sequence = [a.get("action", str(a)) if isinstance(a, dict) else str(a) for a in actions]
        
        if pattern_id in self.patterns:
            # Update existing pattern
            pattern = self.patterns[pattern_id]
            if success:
                pattern.success_count += 1
            else:
                pattern.fail_count += 1
            pattern.total_duration += duration
            pattern.last_used = datetime.now().isoformat()
            
            # Track original tasks
            if task not in pattern.original_tasks:
                pattern.original_tasks.append(task)
                if len(pattern.original_tasks) > 10:  # Keep last 10
                    pattern.original_tasks = pattern.original_tasks[-10:]
            
            # Update variables
            for var_name, var_value in variables.items():
                if var_name not in pattern.variables:
                    pattern.variables[var_name] = []
                if var_value not in pattern.variables[var_name]:
                    pattern.variables[var_name].append(var_value)
            
            # Learn optimal wait times from successful executions
            if success:
                self._learn_wait_times(pattern, actions)
            
            logger.debug(f"Updated pattern '{pattern_id}': {pattern.success_count} successes, {pattern.fail_count} failures")
        else:
            # Create new pattern
            context_tags = self._extract_context_tags(task, action_sequence)
            pattern = Pattern(
                id=pattern_id,
                task_template=template,
                original_tasks=[task],
                action_sequence=action_sequence,
                variables=variables,
                success_count=1 if success else 0,
                fail_count=0 if success else 1,
                total_duration=duration,
                context_tags=context_tags
            )
            self.patterns[pattern_id] = pattern
            logger.info(f"📚 Learned new pattern: '{template}'")
        
        self._save()
    
    def _learn_wait_times(self, pattern: Pattern, actions: List[Dict]):
        """Learn optimal wait times from action execution data."""
        for i, action in enumerate(actions):
            if isinstance(action, dict) and action.get("success"):
                action_str = action.get("action", "")
                if action_str.startswith("wait:"):
                    try:
                        wait_time = float(action_str.split(":")[1])
                        idx_key = str(i)
                        if idx_key in pattern.optimized_waits:
                            # Running average
                            old_avg = pattern.optimized_waits[idx_key]
                            pattern.optimized_waits[idx_key] = (old_avg + wait_time) / 2
                        else:
                            pattern.optimized_waits[idx_key] = wait_time
                    except:
                        pass
    
    def _extract_context_tags(self, task: str, actions: List[str]) -> List[str]:
        """Extract context tags from task and actions."""
        tags = []
        task_lower = task.lower()
        
        # App/browser tags
        if any(b in task_lower for b in ['safari', 'chrome', 'firefox', 'browser']):
            tags.append("browser")
        if 'search' in task_lower:
            tags.append("search")
        if any(a in task_lower for a in ['open', 'launch', 'start']):
            tags.append("launch")
        if 'click' in task_lower:
            tags.append("click")
        if 'type' in task_lower or 'write' in task_lower:
            tags.append("typing")
        
        # Action-based tags
        for action in actions:
            if 'hotkey' in str(action) or 'key' in str(action):
                if "keyboard" not in tags:
                    tags.append("keyboard")
            if 'type:' in str(action):
                if "typing" not in tags:
                    tags.append("typing")
        
        return tags
    
    def get_pattern_by_id(self, pattern_id: str) -> Optional[Pattern]:
        """Get a pattern by its ID."""
        return self.patterns.get(pattern_id)
    
    def get_high_confidence_patterns(self, min_confidence: float = 0.8) -> List[Pattern]:
        """Get all patterns with high confidence scores."""
        return [p for p in self.patterns.values() if p.confidence >= min_confidence]
    
    def get_patterns_by_tag(self, tag: str) -> List[Pattern]:
        """Get all patterns with a specific context tag."""
        return [p for p in self.patterns.values() if tag in p.context_tags]
    
    def apply_pattern(self, pattern: Pattern, variables: Dict[str, str]) -> List[str]:
        """
        Apply a pattern with specific variable values.
        
        Args:
            pattern: The pattern to apply
            variables: Dict of variable name -> value (e.g., {"browser": "Chrome", "query": "weather"})
        
        Returns:
            List of action strings with variables substituted
        """
        actions = []
        for action in pattern.action_sequence:
            new_action = action
            for var_name, var_value in variables.items():
                placeholder = f"{{{var_name}}}"
                new_action = new_action.replace(placeholder, var_value)
            actions.append(new_action)
        return actions
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about stored patterns."""
        if not self.patterns:
            return {"total_patterns": 0}
        
        total = len(self.patterns)
        success_rates = [p.success_rate for p in self.patterns.values()]
        confidences = [p.confidence for p in self.patterns.values()]
        
        return {
            "total_patterns": total,
            "avg_success_rate": sum(success_rates) / total,
            "avg_confidence": sum(confidences) / total,
            "high_confidence_count": len([c for c in confidences if c >= 0.8]),
            "total_executions": sum(p.success_count + p.fail_count for p in self.patterns.values()),
            "context_tags": list(set(tag for p in self.patterns.values() for tag in p.context_tags))
        }
    
    def cleanup_low_confidence(self, min_confidence: float = 0.3, min_uses: int = 5):
        """Remove patterns with low confidence and sufficient usage (failed too much)."""
        to_remove = []
        for pattern_id, pattern in self.patterns.items():
            total_uses = pattern.success_count + pattern.fail_count
            if total_uses >= min_uses and pattern.confidence < min_confidence:
                to_remove.append(pattern_id)
        
        for pid in to_remove:
            del self.patterns[pid]
            logger.info(f"🗑️ Removed low-confidence pattern: {pid}")
        
        if to_remove:
            self._save()


# Global instance
pattern_store = PatternStore()
