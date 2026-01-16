"""
Enhanced Reinforcement Learning Module for Action Selection

This module extends the basic Q-learning with:
1. App-aware state representation (app + action type = state)
2. Failure-specific learning (learn what NOT to do)
3. Priority Experience Replay (remember important transitions)
4. Contextual Bandits for action selection

Designed to quickly learn from failures like using Cmd+F in Apple Music.
"""

import json
import math
import hashlib
from typing import Dict, List, Optional, Tuple, Any, NamedTuple
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from collections import defaultdict, deque
import numpy as np
import random

from .logging import logger

RL_DATA_FILE = Path(__file__).parent.parent.parent / "data" / "enhanced_rl.json"


class Experience(NamedTuple):
    """A single experience tuple for replay."""
    state: str
    action: str
    reward: float
    next_state: Optional[str]
    done: bool
    priority: float
    timestamp: str


@dataclass
class AppActionStats:
    """Statistics for a specific action in a specific app."""
    app: str
    action: str
    successes: int = 0
    failures: int = 0
    total_reward: float = 0.0
    last_outcome: Optional[bool] = None
    failure_contexts: List[str] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        total = self.successes + self.failures
        if total == 0:
            return 0.5  # Prior
        return self.successes / total
    
    @property
    def confidence(self) -> float:
        """Bayesian confidence with uncertainty."""
        # Beta distribution: mean = (a) / (a + b)
        # With prior of 1, 1 (uniform)
        alpha = self.successes + 1
        beta = self.failures + 1
        return alpha / (alpha + beta)
    
    def update(self, success: bool, context: str = ""):
        if success:
            self.successes += 1
            self.total_reward += 1.0
        else:
            self.failures += 1
            self.total_reward -= 1.0
            if context and context not in self.failure_contexts:
                self.failure_contexts.append(context)
                # Keep only last 10 failure contexts
                self.failure_contexts = self.failure_contexts[-10:]
        self.last_outcome = success


class EnhancedRLAgent:
    """
    Enhanced Reinforcement Learning agent with:
    - App-specific Q-tables
    - Failure memory (remember what failed)
    - Priority experience replay
    - Action veto (prevent known-bad actions)
    """
    
    def __init__(
        self,
        data_path: Path = RL_DATA_FILE,
        learning_rate: float = 0.15,
        discount_factor: float = 0.9,
        exploration_rate: float = 0.1,
        replay_buffer_size: int = 1000
    ):
        self.data_path = data_path
        self.alpha = learning_rate
        self.gamma = discount_factor
        self.epsilon = exploration_rate
        
        # App-specific Q-tables: app_name -> action -> Q-value
        self.app_q_tables: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        
        # Global Q-table for unknown apps
        self.global_q_table: Dict[str, float] = defaultdict(float)
        
        # App-action statistics for detailed tracking
        self.app_action_stats: Dict[str, Dict[str, AppActionStats]] = defaultdict(dict)
        
        # Priority experience replay buffer
        self.replay_buffer: deque = deque(maxlen=replay_buffer_size)
        
        # Action veto list: (app, action) pairs that consistently fail
        self.vetoed_actions: Dict[str, List[str]] = defaultdict(list)
        
        # Shortcut corrections learned from failures
        self.learned_corrections: Dict[str, Dict[str, str]] = defaultdict(dict)
        
        self._load_data()
    
    def get_state_key(self, app_name: str, context: Optional[Dict] = None) -> str:
        """Create a state key from app and context."""
        # Primary state is just the app name for simplicity
        # This makes learning faster as we have fewer states
        return app_name.lower() if app_name else "unknown"
    
    def get_action_key(self, action: str) -> str:
        """Normalize action to a key for Q-table lookup."""
        # Extract the action type and key combination
        action_lower = action.lower().strip()
        
        if action_lower.startswith("hotkey:"):
            # For hotkeys, include the key combo
            return action_lower
        elif action_lower.startswith("type:"):
            return "type"  # Group all typing together
        elif action_lower.startswith("click:"):
            return "click"
        elif action_lower.startswith("wait:"):
            return "wait"
        elif action_lower.startswith("key:"):
            return action_lower
        else:
            return action_lower
    
    def get_q_value(self, app_name: str, action: str) -> float:
        """Get Q-value for an action in an app context."""
        state = self.get_state_key(app_name)
        action_key = self.get_action_key(action)
        
        # Check app-specific Q-table first
        if state in self.app_q_tables and action_key in self.app_q_tables[state]:
            return self.app_q_tables[state][action_key]
        
        # Fall back to global Q-table
        return self.global_q_table.get(action_key, 0.0)
    
    def get_confidence(self, app_name: str, action: str) -> float:
        """
        Get confidence score for an action in an app.
        Returns value between 0 and 1.
        """
        q_value = self.get_q_value(app_name, action)
        
        # Also check action stats if available
        state = self.get_state_key(app_name)
        action_key = self.get_action_key(action)
        
        if state in self.app_action_stats and action_key in self.app_action_stats[state]:
            stats = self.app_action_stats[state][action_key]
            # Blend Q-value confidence with stats confidence
            q_conf = 1.0 / (1.0 + math.exp(-2 * q_value))
            stats_conf = stats.confidence
            return 0.6 * stats_conf + 0.4 * q_conf
        
        # Just use Q-value
        try:
            return 1.0 / (1.0 + math.exp(-2 * q_value))
        except OverflowError:
            return 1.0 if q_value > 0 else 0.0
    
    def is_action_vetoed(self, app_name: str, action: str) -> Tuple[bool, Optional[str]]:
        """
        Check if an action is vetoed for an app.
        
        Returns:
            (is_vetoed, reason_or_alternative)
        """
        state = self.get_state_key(app_name)
        action_key = self.get_action_key(action)
        
        # Check explicit veto list
        if action_key in self.vetoed_actions.get(state, []):
            # Check if we have a learned correction
            if state in self.learned_corrections and action_key in self.learned_corrections[state]:
                alternative = self.learned_corrections[state][action_key]
                return True, f"Use {alternative} instead"
            return True, "This action consistently fails in this app"
        
        # Check if stats show very low success rate
        if state in self.app_action_stats and action_key in self.app_action_stats[state]:
            stats = self.app_action_stats[state][action_key]
            if stats.failures >= 3 and stats.success_rate < 0.2:
                return True, f"Low success rate ({stats.success_rate:.0%})"
        
        return False, None
    
    def select_action(
        self,
        app_name: str,
        available_actions: List[str],
        context: Optional[Dict] = None,
        use_exploration: bool = True
    ) -> Tuple[str, float, bool]:
        """
        Select the best action using epsilon-greedy with veto.
        
        Returns:
            (selected_action, confidence, was_exploratory)
        """
        # Filter out vetoed actions
        valid_actions = []
        for action in available_actions:
            is_vetoed, _ = self.is_action_vetoed(app_name, action)
            if not is_vetoed:
                valid_actions.append(action)
        
        if not valid_actions:
            # All actions vetoed, use the least-bad one
            valid_actions = available_actions
            logger.warning(f"All actions vetoed for {app_name}, using fallback")
        
        # Epsilon-greedy selection
        if use_exploration and random.random() < self.epsilon:
            # Explore: random action
            selected = random.choice(valid_actions)
            confidence = self.get_confidence(app_name, selected)
            return selected, confidence, True
        
        # Exploit: best action by Q-value
        best_action = None
        best_q = float('-inf')
        
        for action in valid_actions:
            q = self.get_q_value(app_name, action)
            if q > best_q:
                best_q = q
                best_action = action
        
        if best_action is None:
            best_action = valid_actions[0]
        
        confidence = self.get_confidence(app_name, best_action)
        return best_action, confidence, False
    
    def record_outcome(
        self,
        app_name: str,
        action: str,
        success: bool,
        context: Optional[Dict] = None,
        error_type: Optional[str] = None,
        correction: Optional[str] = None
    ):
        """
        Record the outcome of an action for learning.
        
        This is the main learning entry point.
        """
        state = self.get_state_key(app_name)
        action_key = self.get_action_key(action)
        reward = 1.0 if success else -1.0
        
        # 1. Update Q-value
        old_q = self.app_q_tables[state][action_key]
        new_q = old_q + self.alpha * (reward - old_q)
        self.app_q_tables[state][action_key] = new_q
        
        # Also update global Q-table (slower learning rate)
        old_global_q = self.global_q_table[action_key]
        self.global_q_table[action_key] = old_global_q + 0.05 * (reward - old_global_q)
        
        # 2. Update action stats
        if action_key not in self.app_action_stats[state]:
            self.app_action_stats[state][action_key] = AppActionStats(
                app=app_name, action=action_key
            )
        
        error_context = error_type or ""
        self.app_action_stats[state][action_key].update(success, error_context)
        
        # 3. Add to replay buffer (with priority based on TD error)
        td_error = abs(reward - old_q)
        priority = td_error + 0.1  # Small bonus to ensure non-zero priority
        
        experience = Experience(
            state=state,
            action=action_key,
            reward=reward,
            next_state=None,
            done=True,
            priority=priority,
            timestamp=datetime.now().isoformat()
        )
        self.replay_buffer.append(experience)
        
        # 4. Handle failures specially
        if not success:
            self._handle_failure(app_name, action, error_type, correction)
        
        # 5. Periodic replay learning
        if len(self.replay_buffer) > 20 and random.random() < 0.3:
            self._replay_learning()
        
        # 6. Save periodically
        if len(self.replay_buffer) % 10 == 0:
            self._save_data()
    
    def _handle_failure(
        self,
        app_name: str,
        action: str,
        error_type: Optional[str],
        correction: Optional[str]
    ):
        """Special handling for failures to accelerate learning."""
        state = self.get_state_key(app_name)
        action_key = self.get_action_key(action)
        
        # Check if this action has failed multiple times
        if state in self.app_action_stats and action_key in self.app_action_stats[state]:
            stats = self.app_action_stats[state][action_key]
            
            if stats.failures >= 2 and stats.success_rate < 0.3:
                # Add to veto list
                if action_key not in self.vetoed_actions[state]:
                    self.vetoed_actions[state].append(action_key)
                    logger.info(f"🚫 Vetoed action: {action_key} in {app_name} "
                               f"(success rate: {stats.success_rate:.0%})")
        
        # Learn correction if provided
        if correction:
            correction_key = self.get_action_key(correction)
            self.learned_corrections[state][action_key] = correction_key
            logger.info(f"📚 Learned correction for {app_name}: {action_key} → {correction_key}")
    
    def _replay_learning(self, batch_size: int = 8):
        """Learn from prioritized replay buffer."""
        if len(self.replay_buffer) < batch_size:
            return
        
        # Priority sampling (higher priority = more likely to sample)
        experiences = list(self.replay_buffer)
        priorities = np.array([e.priority for e in experiences])
        probs = priorities / priorities.sum()
        
        indices = np.random.choice(len(experiences), size=batch_size, p=probs, replace=False)
        
        for idx in indices:
            exp = experiences[idx]
            
            # Q-learning update
            old_q = self.app_q_tables[exp.state][exp.action]
            target_q = exp.reward  # Terminal state, no next state value
            new_q = old_q + self.alpha * 0.5 * (target_q - old_q)  # Half learning rate for replay
            self.app_q_tables[exp.state][exp.action] = new_q
    
    def get_suggested_action(self, app_name: str, intent: str) -> Optional[str]:
        """
        Get a suggested action for an intent in an app.
        Uses learned corrections and best-performing actions.
        """
        state = self.get_state_key(app_name)
        
        # Check for known corrections
        for wrong_action, correct_action in self.learned_corrections.get(state, {}).items():
            if intent.lower() in wrong_action:
                return correct_action
        
        # Find best action for this app
        if state in self.app_q_tables:
            actions = self.app_q_tables[state]
            if actions:
                best_action = max(actions.items(), key=lambda x: x[1])[0]
                return best_action
        
        return None
    
    def get_stats(self, app_name: Optional[str] = None) -> Dict[str, Any]:
        """Get learning statistics."""
        if app_name:
            state = self.get_state_key(app_name)
            return {
                "app": app_name,
                "q_values": dict(self.app_q_tables.get(state, {})),
                "vetoed_actions": self.vetoed_actions.get(state, []),
                "corrections": self.learned_corrections.get(state, {}),
                "action_stats": {
                    k: {"success_rate": v.success_rate, "confidence": v.confidence}
                    for k, v in self.app_action_stats.get(state, {}).items()
                }
            }
        else:
            return {
                "total_experiences": len(self.replay_buffer),
                "apps_tracked": list(self.app_q_tables.keys()),
                "total_vetoed": sum(len(v) for v in self.vetoed_actions.values()),
                "total_corrections": sum(len(v) for v in self.learned_corrections.values()),
            }
    
    def _load_data(self):
        """Load saved RL data."""
        try:
            if self.data_path.exists():
                with open(self.data_path, 'r') as f:
                    data = json.load(f)
                
                # Load Q-tables
                for app, actions in data.get("app_q_tables", {}).items():
                    for action, q_val in actions.items():
                        self.app_q_tables[app][action] = q_val
                
                self.global_q_table = defaultdict(float, data.get("global_q_table", {}))
                
                # Load vetoed actions
                self.vetoed_actions = defaultdict(list, data.get("vetoed_actions", {}))
                
                # Load corrections
                self.learned_corrections = defaultdict(dict, data.get("learned_corrections", {}))
                
                # Load action stats
                for app, actions in data.get("app_action_stats", {}).items():
                    for action, stats in actions.items():
                        self.app_action_stats[app][action] = AppActionStats(
                            app=app,
                            action=action,
                            successes=stats.get("successes", 0),
                            failures=stats.get("failures", 0),
                            total_reward=stats.get("total_reward", 0.0),
                            failure_contexts=stats.get("failure_contexts", [])
                        )
                
                logger.info(f"📊 Loaded RL data: {len(self.app_q_tables)} apps, "
                           f"{sum(len(v) for v in self.vetoed_actions.values())} vetoed actions")
        except Exception as e:
            logger.debug(f"Could not load RL data: {e}")
    
    def _save_data(self):
        """Save RL data."""
        try:
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert to serializable format
            app_action_stats_dict = {}
            for app, actions in self.app_action_stats.items():
                app_action_stats_dict[app] = {}
                for action, stats in actions.items():
                    app_action_stats_dict[app][action] = {
                        "successes": stats.successes,
                        "failures": stats.failures,
                        "total_reward": stats.total_reward,
                        "failure_contexts": stats.failure_contexts
                    }
            
            data = {
                "app_q_tables": {k: dict(v) for k, v in self.app_q_tables.items()},
                "global_q_table": dict(self.global_q_table),
                "vetoed_actions": dict(self.vetoed_actions),
                "learned_corrections": dict(self.learned_corrections),
                "app_action_stats": app_action_stats_dict,
                "last_updated": datetime.now().isoformat()
            }
            
            with open(self.data_path, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Could not save RL data: {e}")


# Global instance
enhanced_rl_agent = EnhancedRLAgent()
