"""
Action Optimizer - Optimize action sequences based on learned patterns.

This module uses historical execution data to optimize action sequences,
adjust timing, batch actions intelligently, and remove redundancies.
"""

import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from .pattern_store import PatternStore, pattern_store
from .choice_tracker import ChoiceTracker, choice_tracker
from .logging import logger


@dataclass
class OptimizationResult:
    """Result of an optimization pass."""
    original_actions: List[str]
    optimized_actions: List[str]
    changes_made: List[str]
    estimated_time_saved: float


class ActionOptimizer:
    """
    Optimize action sequences based on learned patterns and historical data.
    
    Features:
    - Wait time optimization based on historical success data
    - Action batching for efficiency  
    - Redundancy removal
    - App-specific optimizations
    """
    
    # Default wait times by action type
    DEFAULT_WAITS = {
        "app_launch": 1.0,
        "page_load": 1.5,
        "keyboard_shortcut": 0.3,
        "typing": 0.1,
        "click": 0.2,
        "generic": 0.5
    }
    
    # Actions that typically don't need waits after them
    NO_WAIT_ACTIONS = [
        "type:",
        "key:tab",
    ]
    
    # Actions that need waits after them
    WAIT_AFTER_ACTIONS = [
        ("key:enter", 0.8),
        ("hotkey:command,space", 0.5),  # Spotlight
        ("hotkey:command,t", 0.3),      # New tab
        ("hotkey:command,l", 0.2),      # Focus URL bar
        ("hotkey:command,n", 0.5),      # New window
        ("hotkey:command,w", 0.3),      # Close window
    ]
    
    def __init__(
        self,
        pattern_store: PatternStore = None,
        choice_tracker: ChoiceTracker = None
    ):
        self.pattern_store = pattern_store or globals()["pattern_store"]
        self.choice_tracker = choice_tracker or globals()["choice_tracker"]
    
    def optimize_sequence(
        self,
        actions: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> OptimizationResult:
        """
        Apply all optimizations to an action sequence.
        
        Args:
            actions: List of action strings
            context: Optional context (app_name, task_type, etc.)
        
        Returns:
            OptimizationResult with optimized actions and changes made
        """
        original = actions.copy()
        optimized = actions.copy()
        changes = []
        time_saved = 0.0
        
        # 1. Optimize wait times
        optimized, wait_changes, wait_saved = self._optimize_waits(optimized, context)
        changes.extend(wait_changes)
        time_saved += wait_saved
        
        # 2. Remove redundant waits
        optimized, redundant_changes, redundant_saved = self._remove_redundant_waits(optimized)
        changes.extend(redundant_changes)
        time_saved += redundant_saved
        
        # 3. Merge consecutive typing actions
        optimized, merge_changes = self._merge_typing(optimized)
        changes.extend(merge_changes)
        
        # 4. Insert missing waits after critical actions
        optimized, insert_changes = self._insert_necessary_waits(optimized, context)
        changes.extend(insert_changes)
        
        return OptimizationResult(
            original_actions=original,
            optimized_actions=optimized,
            changes_made=changes,
            estimated_time_saved=time_saved
        )
    
    def _optimize_waits(
        self,
        actions: List[str],
        context: Optional[Dict] = None
    ) -> Tuple[List[str], List[str], float]:
        """
        Optimize wait times based on historical success data.
        
        Returns:
            (optimized_actions, changes_list, time_saved)
        """
        optimized = []
        changes = []
        time_saved = 0.0
        
        app_name = context.get("app_name") if context else None
        
        for i, action in enumerate(actions):
            if action.startswith("wait:"):
                try:
                    current_wait = float(action.split(":")[1])
                    
                    # Get optimized wait from choice tracker (app-specific)
                    optimal_wait = None
                    if app_name:
                        # Determine action type from previous action
                        if i > 0:
                            prev_action = actions[i - 1]
                            action_type = self._classify_action(prev_action)
                            optimal_wait = self.choice_tracker.get_preferred_wait_time(
                                app_name, action_type
                            )
                    
                    if optimal_wait is None:
                        # Use pattern store for optimization
                        similar_patterns = self.pattern_store.find_similar(
                            context.get("task", "") if context else ""
                        )
                        if similar_patterns:
                            best_pattern = similar_patterns[0][0]
                            idx_key = str(i)
                            optimal_wait = best_pattern.optimized_waits.get(idx_key)
                    
                    if optimal_wait is not None and optimal_wait != current_wait:
                        # Use the learned optimal wait (but don't go below 0.1s)
                        new_wait = max(optimal_wait, 0.1)
                        optimized.append(f"wait:{new_wait:.1f}")
                        diff = current_wait - new_wait
                        if diff > 0:
                            time_saved += diff
                            changes.append(f"Reduced wait at #{i} from {current_wait}s to {new_wait}s")
                        else:
                            changes.append(f"Increased wait at #{i} from {current_wait}s to {new_wait}s (learned)")
                    else:
                        optimized.append(action)
                except:
                    optimized.append(action)
            else:
                optimized.append(action)
        
        return optimized, changes, time_saved
    
    def _remove_redundant_waits(self, actions: List[str]) -> Tuple[List[str], List[str], float]:
        """
        Remove redundant or excessive waits.
        
        Returns:
            (optimized_actions, changes_list, time_saved)
        """
        optimized = []
        changes = []
        time_saved = 0.0
        
        prev_was_wait = False
        accumulated_wait = 0.0
        
        for i, action in enumerate(actions):
            if action.startswith("wait:"):
                try:
                    wait_time = float(action.split(":")[1])
                    
                    if prev_was_wait:
                        # Merge consecutive waits
                        accumulated_wait += wait_time
                        changes.append(f"Merged consecutive wait at #{i}")
                    else:
                        if accumulated_wait > 0:
                            # Output the accumulated wait
                            optimized.append(f"wait:{accumulated_wait:.1f}")
                        accumulated_wait = wait_time
                        prev_was_wait = True
                except:
                    optimized.append(action)
                    prev_was_wait = False
            else:
                if accumulated_wait > 0:
                    # Cap excessive waits at 3 seconds
                    if accumulated_wait > 3.0:
                        time_saved += accumulated_wait - 3.0
                        changes.append(f"Capped excessive wait from {accumulated_wait}s to 3.0s")
                        accumulated_wait = 3.0
                    optimized.append(f"wait:{accumulated_wait:.1f}")
                    accumulated_wait = 0.0
                
                optimized.append(action)
                prev_was_wait = False
        
        # Handle trailing wait
        if accumulated_wait > 0:
            if accumulated_wait > 3.0:
                time_saved += accumulated_wait - 3.0
                accumulated_wait = 3.0
            optimized.append(f"wait:{accumulated_wait:.1f}")
        
        return optimized, changes, time_saved
    
    def _merge_typing(self, actions: List[str]) -> Tuple[List[str], List[str]]:
        """
        Merge consecutive type actions into one.
        
        Returns:
            (optimized_actions, changes_list)
        """
        optimized = []
        changes = []
        
        i = 0
        while i < len(actions):
            action = actions[i]
            
            if action.startswith("type:"):
                # Collect consecutive type actions
                text_parts = [action.split(":", 1)[1]]
                j = i + 1
                
                while j < len(actions) and actions[j].startswith("type:"):
                    text_parts.append(actions[j].split(":", 1)[1])
                    j += 1
                
                if len(text_parts) > 1:
                    merged_text = "".join(text_parts)
                    optimized.append(f"type:{merged_text}")
                    changes.append(f"Merged {len(text_parts)} type actions into one")
                    i = j
                    continue
            
            optimized.append(action)
            i += 1
        
        return optimized, changes
    
    def _insert_necessary_waits(
        self,
        actions: List[str],
        context: Optional[Dict] = None
    ) -> Tuple[List[str], List[str]]:
        """
        Insert necessary waits after critical actions if missing.
        
        Returns:
            (optimized_actions, changes_list)
        """
        optimized = []
        changes = []
        
        for i, action in enumerate(actions):
            optimized.append(action)
            
            # Check if this action needs a wait after it
            for pattern, wait_time in self.WAIT_AFTER_ACTIONS:
                if pattern in action:
                    # Check if next action is already a wait
                    if i + 1 < len(actions) and actions[i + 1].startswith("wait:"):
                        continue  # Already has a wait
                    
                    # Check if it's the last action (no wait needed)
                    if i + 1 >= len(actions):
                        continue
                    
                    # Get app-specific wait if available
                    app_name = context.get("app_name") if context else None
                    if app_name:
                        action_type = self._classify_action(action)
                        learned_wait = self.choice_tracker.get_preferred_wait_time(
                            app_name, action_type
                        )
                        if learned_wait:
                            wait_time = learned_wait
                    
                    optimized.append(f"wait:{wait_time}")
                    changes.append(f"Inserted wait after '{action}' ({wait_time}s)")
                    break
        
        return optimized, changes
    
    def _classify_action(self, action: str) -> str:
        """Classify an action for wait time lookup."""
        if "command,space" in action:
            return "app_launch"
        elif "command,l" in action or "command,t" in action:
            return "keyboard_shortcut"
        elif action.startswith("type:"):
            return "typing"
        elif action.startswith("click:"):
            return "click"
        elif "enter" in action:
            return "page_load"
        else:
            return "generic"
    
    def suggest_wait_times(
        self,
        actions: List[str],
        context: Optional[Dict] = None
    ) -> List[Tuple[int, float]]:
        """
        Suggest optimal wait times for actions based on historical data.
        
        Returns:
            List of (action_index, suggested_wait) tuples
        """
        suggestions = []
        app_name = context.get("app_name") if context else None
        
        for i, action in enumerate(actions):
            if action.startswith("wait:"):
                continue
            
            action_type = self._classify_action(action)
            
            # Get learned wait time
            suggested_wait = None
            
            if app_name:
                suggested_wait = self.choice_tracker.get_preferred_wait_time(
                    app_name, action_type
                )
            
            if suggested_wait is None:
                suggested_wait = self.DEFAULT_WAITS.get(action_type, 0.3)
            
            # Only suggest if this action typically needs a wait
            needs_wait = any(pattern in action for pattern, _ in self.WAIT_AFTER_ACTIONS)
            if needs_wait:
                suggestions.append((i, suggested_wait))
        
        return suggestions
    
    def batch_actions(
        self,
        actions: List[str],
        max_batch_size: int = 10
    ) -> List[Dict]:
        """
        Intelligently batch actions based on learned patterns.
        
        Returns:
            List of batch dicts with type, actions, and description
        """
        batches = []
        current_batch = []
        current_type = "blind"
        
        for action in actions:
            # Determine if this action requires vision
            requires_vision = self._requires_vision(action)
            action_type = "vision" if requires_vision else "blind"
            
            if action_type != current_type and current_batch:
                # Close current batch
                batches.append({
                    "type": current_type,
                    "actions": current_batch.copy() if current_type == "blind" else [],
                    "action": current_batch[0] if current_type == "vision" else "",
                    "description": self._generate_batch_description(current_batch)
                })
                current_batch = []
            
            current_batch.append(action)
            current_type = action_type
            
            # Check batch size limit
            if len(current_batch) >= max_batch_size and current_type == "blind":
                batches.append({
                    "type": "blind",
                    "actions": current_batch.copy(),
                    "description": self._generate_batch_description(current_batch)
                })
                current_batch = []
        
        # Close final batch
        if current_batch:
            batches.append({
                "type": current_type,
                "actions": current_batch if current_type == "blind" else [],
                "action": current_batch[0] if current_type == "vision" else "",
                "description": self._generate_batch_description(current_batch)
            })
        
        return batches
    
    def _requires_vision(self, action: str) -> bool:
        """Check if an action requires vision/screen observation."""
        # Vision-requiring patterns
        vision_keywords = ["click on", "find", "locate", "select", "choose", "look for"]
        action_lower = action.lower()
        
        return any(kw in action_lower for kw in vision_keywords)
    
    def _generate_batch_description(self, actions: List[str]) -> str:
        """Generate a human-readable description for a batch of actions."""
        if not actions:
            return "Empty batch"
        
        if len(actions) == 1:
            return actions[0]
        
        # Summarize the actions
        action_types = []
        for action in actions:
            if action.startswith("hotkey:"):
                action_types.append("shortcut")
            elif action.startswith("type:"):
                text = action.split(":", 1)[1]
                action_types.append(f"type '{text[:20]}..'" if len(text) > 20 else f"type '{text}'")
            elif action.startswith("key:"):
                action_types.append(action.split(":")[1])
            elif action.startswith("wait:"):
                continue  # Skip waits in description
            else:
                action_types.append(action[:30])
        
        if len(action_types) <= 3:
            return " → ".join(action_types)
        else:
            return f"{action_types[0]} → ... → {action_types[-1]} ({len(actions)} actions)"
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        """Get statistics about optimizations performed."""
        pattern_stats = self.pattern_store.get_statistics()
        choice_stats = self.choice_tracker.get_statistics()
        
        return {
            "patterns_learned": pattern_stats.get("total_patterns", 0),
            "choices_tracked": choice_stats.get("total_choices", 0),
            "apps_with_preferences": choice_stats.get("apps_tracked", 0),
            "high_confidence_patterns": pattern_stats.get("high_confidence_count", 0)
        }


# Global instance
action_optimizer = ActionOptimizer()
