"""
Choice Tracker - Track user choices and preferences for smarter automation.

This module records user decisions, learns preferences over time, and provides
recommendations based on historical choice patterns.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict

from .logging import logger

CHOICES_FILE = Path(__file__).parent.parent.parent / "data" / "choices.json"


@dataclass
class ChoiceRecord:
    """Record of a single choice made during execution."""
    id: str
    context: str                        # Situation that triggered the choice
    context_type: str                   # Type of context (app_selection, element_click, etc.)
    options: List[str]                  # Available options
    chosen: str                         # What was selected
    outcome: str                        # success/failure/partial
    app_context: Optional[str] = None   # Which app was active
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "context": self.context,
            "context_type": self.context_type,
            "options": self.options,
            "chosen": self.chosen,
            "outcome": self.outcome,
            "app_context": self.app_context,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ChoiceRecord":
        return cls(**data)


@dataclass
class AppPreferences:
    """Learned preferences for a specific application."""
    app_name: str
    preferred_shortcuts: Dict[str, str] = field(default_factory=dict)  # action -> shortcut
    preferred_waits: Dict[str, float] = field(default_factory=dict)    # action_type -> wait_time
    common_actions: List[str] = field(default_factory=list)           # Frequently used actions
    success_patterns: List[str] = field(default_factory=list)         # Action patterns that work well
    
    def to_dict(self) -> Dict:
        return {
            "app_name": self.app_name,
            "preferred_shortcuts": self.preferred_shortcuts,
            "preferred_waits": self.preferred_waits,
            "common_actions": self.common_actions,
            "success_patterns": self.success_patterns
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "AppPreferences":
        return cls(
            app_name=data["app_name"],
            preferred_shortcuts=data.get("preferred_shortcuts", {}),
            preferred_waits=data.get("preferred_waits", {}),
            common_actions=data.get("common_actions", []),
            success_patterns=data.get("success_patterns", [])
        )


class ChoiceTracker:
    """
    Track and learn from user choices to build preference models.
    
    Features:
    - Record choices made during task execution
    - Build per-app preference profiles
    - Suggest likely choices based on history
    - Track environmental patterns
    """
    
    def __init__(self, choices_file: Path = CHOICES_FILE):
        self.choices_file = choices_file
        self.choices: List[ChoiceRecord] = []
        self.app_preferences: Dict[str, AppPreferences] = {}
        self.global_preferences: Dict[str, Any] = {
            "default_browser": None,
            "default_search_engine": "google",
            "keyboard_style": "standard",  # standard, vim, etc.
            "typing_speed": "normal",      # slow, normal, fast
            "confirmation_preference": "auto"  # auto, always_confirm, never_confirm
        }
        self._load()
    
    def _load(self):
        """Load choices and preferences from disk."""
        try:
            if self.choices_file.exists():
                with open(self.choices_file, 'r') as f:
                    data = json.load(f)
                
                # Load choices
                for choice_data in data.get("choices", []):
                    self.choices.append(ChoiceRecord.from_dict(choice_data))
                
                # Load app preferences
                for app_data in data.get("app_preferences", []):
                    prefs = AppPreferences.from_dict(app_data)
                    self.app_preferences[prefs.app_name] = prefs
                
                # Load global preferences
                self.global_preferences.update(data.get("global_preferences", {}))
                
                logger.debug(f"Loaded {len(self.choices)} choices from {self.choices_file}")
        except Exception as e:
            logger.warning(f"Could not load choices: {e}")
    
    def _save(self):
        """Save choices and preferences to disk."""
        try:
            self.choices_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "choices": [c.to_dict() for c in self.choices[-1000:]],  # Keep last 1000
                "app_preferences": [p.to_dict() for p in self.app_preferences.values()],
                "global_preferences": self.global_preferences,
                "last_updated": datetime.now().isoformat()
            }
            with open(self.choices_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save choices: {e}")
    
    def record_choice(
        self,
        context: str,
        context_type: str,
        options: List[str],
        chosen: str,
        outcome: str = "success",
        app_context: Optional[str] = None
    ):
        """
        Record a choice made during execution.
        
        Args:
            context: Description of the situation
            context_type: Type (app_selection, element_click, action_choice, etc.)
            options: Available options
            chosen: What was selected
            outcome: success/failure/partial
            app_context: Which application was active
        """
        choice_id = f"c_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(self.choices)}"
        
        record = ChoiceRecord(
            id=choice_id,
            context=context,
            context_type=context_type,
            options=options,
            chosen=chosen,
            outcome=outcome,
            app_context=app_context
        )
        
        self.choices.append(record)
        
        # Update preferences based on this choice
        self._update_preferences(record)
        
        self._save()
        logger.debug(f"Recorded choice: {chosen} in context '{context[:50]}...'")
    
    def _update_preferences(self, choice: ChoiceRecord):
        """Update preference models based on a new choice."""
        # Update app-specific preferences
        if choice.app_context:
            if choice.app_context not in self.app_preferences:
                self.app_preferences[choice.app_context] = AppPreferences(
                    app_name=choice.app_context
                )
            prefs = self.app_preferences[choice.app_context]
            
            # Track common actions for this app
            if choice.chosen not in prefs.common_actions:
                prefs.common_actions.append(choice.chosen)
                if len(prefs.common_actions) > 20:  # Keep top 20
                    prefs.common_actions = prefs.common_actions[-20:]
            
            # Track successful patterns
            if choice.outcome == "success":
                pattern = f"{choice.context_type}:{choice.chosen}"
                if pattern not in prefs.success_patterns:
                    prefs.success_patterns.append(pattern)
                    if len(prefs.success_patterns) > 50:
                        prefs.success_patterns = prefs.success_patterns[-50:]
        
        # Update global preferences
        if choice.context_type == "browser_selection" and choice.outcome == "success":
            self.global_preferences["default_browser"] = choice.chosen
        
        if choice.context_type == "search_engine" and choice.outcome == "success":
            self.global_preferences["default_search_engine"] = choice.chosen
    
    def get_likely_choice(
        self,
        context: str,
        context_type: str,
        options: List[str],
        app_context: Optional[str] = None
    ) -> Optional[str]:
        """
        Get the most likely choice based on historical patterns.
        
        Returns:
            The most likely choice, or None if no strong preference
        """
        # Find similar past choices
        relevant_choices = [
            c for c in self.choices
            if c.context_type == context_type and c.outcome == "success"
        ]
        
        # Filter by app context if provided
        if app_context:
            app_choices = [c for c in relevant_choices if c.app_context == app_context]
            if app_choices:
                relevant_choices = app_choices
        
        if not relevant_choices:
            return None
        
        # Count successful choices for each option
        choice_counts = defaultdict(int)
        for c in relevant_choices:
            if c.chosen in options:
                choice_counts[c.chosen] += 1
        
        if not choice_counts:
            return None
        
        # Return the most common successful choice
        best_choice = max(choice_counts.items(), key=lambda x: x[1])
        
        # Only return if we have enough confidence (multiple occurrences)
        if best_choice[1] >= 2:
            return best_choice[0]
        
        return None
    
    def get_app_preferences(self, app_name: str) -> Optional[AppPreferences]:
        """Get learned preferences for a specific app."""
        return self.app_preferences.get(app_name)
    
    def get_preferred_wait_time(self, app_name: str, action_type: str) -> Optional[float]:
        """Get the preferred wait time for an action type in a specific app."""
        prefs = self.app_preferences.get(app_name)
        if prefs:
            return prefs.preferred_waits.get(action_type)
        return None
    
    def update_wait_preference(self, app_name: str, action_type: str, wait_time: float, success: bool):
        """Update wait time preference based on execution outcome."""
        if app_name not in self.app_preferences:
            self.app_preferences[app_name] = AppPreferences(app_name=app_name)
        
        prefs = self.app_preferences[app_name]
        
        if success:
            # Successful execution - this wait time works
            if action_type in prefs.preferred_waits:
                # Running average, weighted toward successful times
                old = prefs.preferred_waits[action_type]
                prefs.preferred_waits[action_type] = (old * 0.7 + wait_time * 0.3)
            else:
                prefs.preferred_waits[action_type] = wait_time
        else:
            # Failed - maybe need more wait time
            if action_type in prefs.preferred_waits:
                # Increase wait time slightly
                prefs.preferred_waits[action_type] *= 1.2
        
        self._save()
    
    def get_global_preference(self, key: str) -> Any:
        """Get a global preference value."""
        return self.global_preferences.get(key)
    
    def set_global_preference(self, key: str, value: Any):
        """Set a global preference value."""
        self.global_preferences[key] = value
        self._save()
    
    def get_browser_preference(self) -> str:
        """Get the preferred browser."""
        browser = self.global_preferences.get("default_browser")
        if browser:
            return browser
        
        # Infer from recent choices
        browser_choices = [
            c.chosen for c in self.choices
            if c.context_type == "browser_selection" and c.outcome == "success"
        ]
        
        if browser_choices:
            # Return most common
            counts = defaultdict(int)
            for b in browser_choices:
                counts[b] += 1
            return max(counts.items(), key=lambda x: x[1])[0]
        
        return "Safari"  # macOS default
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about tracked choices."""
        if not self.choices:
            return {"total_choices": 0}
        
        context_types = defaultdict(int)
        outcomes = defaultdict(int)
        apps = defaultdict(int)
        
        for c in self.choices:
            context_types[c.context_type] += 1
            outcomes[c.outcome] += 1
            if c.app_context:
                apps[c.app_context] += 1
        
        return {
            "total_choices": len(self.choices),
            "context_types": dict(context_types),
            "outcomes": dict(outcomes),
            "apps_tracked": len(self.app_preferences),
            "top_apps": dict(sorted(apps.items(), key=lambda x: x[1], reverse=True)[:5]),
            "global_preferences": self.global_preferences
        }
    
    def get_recent_choices(self, count: int = 10, context_type: Optional[str] = None) -> List[ChoiceRecord]:
        """Get recent choices, optionally filtered by type."""
        choices = self.choices
        if context_type:
            choices = [c for c in choices if c.context_type == context_type]
        return choices[-count:]


# Global instance
choice_tracker = ChoiceTracker()
