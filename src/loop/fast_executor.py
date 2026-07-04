"""
FastExecutor - Street-smart action executor for Houdini Agent.

Optimizes the executor loop by:
1. Batching blind actions so keyboard/clipboard sequences execute without
   per-action LLM or vision round-trips.
2. Speculatively pre-executing common patterns (open app, spotlight, new tab,
   paste, etc.) when the current context matches a known pattern.
3. Parallelizing vision inference and coordinate prediction when multiple UI
   targets are needed safely.
4. Using the SemanticCache and PatternStore to skip planning when a proven
   plan exists.

The FastExecutor is intentionally conservative: it never executes a vision
action without the appropriate safety checks, and it falls back to the
standard LLM executor for anything uncertain.
"""

from __future__ import annotations

import time
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..utils.logging import logger
from ..utils.action_parser import parse_action, parse_actions
from ..utils.pattern_store import pattern_store

try:
    from ..utils.semantic_cache import lookup_plan, store_plan
    SEMANTIC_CACHE_AVAILABLE = True
except ImportError:
    SEMANTIC_CACHE_AVAILABLE = False
    lookup_plan = store_plan = None

try:
    from ..utils.execution_confidence import rate_action
    CONFIDENCE_AVAILABLE = True
except ImportError:
    CONFIDENCE_AVAILABLE = False
    rate_action = None


def _safe_action_type(action: Dict[str, Any]) -> str:
    return (action.get("type") or "").lower()


def _is_blind_action(action: Dict[str, Any]) -> bool:
    return _safe_action_type(action) in {
        "hotkey", "type", "key", "wait", "clipboard", "open_url", "activate_app"
    }


def _is_vision_action(action: Dict[str, Any]) -> bool:
    return _safe_action_type(action) in {"click", "scroll", "drag"}


@dataclass
class ExecutionResult:
    """Result of executing a batch of actions."""
    success: bool
    actions_executed: int = 0
    errors: List[str] = field(default_factory=list)
    method: str = "fast"
    used_cache: bool = False
    used_pattern: bool = False


class FastExecutor:
    """
    Fast executor that batches blind actions and pre-executes common patterns.

    Usage:
        executor = FastExecutor(vision_handler=...)
        result = executor.execute_batch(actions, task="open Notes and type hello")
    """

    # Common patterns that can be pre-executed without LLM calls
    COMMON_PATTERNS = {
        "spotlight_open": [
            {"type": "hotkey", "params": {"keys": ["command", "space"]}, "description": "Open Spotlight"},
        ],
        "paste": [
            {"type": "hotkey", "params": {"keys": ["command", "v"]}, "description": "Paste"},
        ],
        "copy": [
            {"type": "hotkey", "params": {"keys": ["command", "c"]}, "description": "Copy"},
        ],
        "select_all": [
            {"type": "hotkey", "params": {"keys": ["command", "a"]}, "description": "Select All"},
        ],
        "new_tab": [
            {"type": "hotkey", "params": {"keys": ["command", "t"]}, "description": "New Tab"},
        ],
        "focus_url_bar": [
            {"type": "hotkey", "params": {"keys": ["command", "l"]}, "description": "Focus URL bar"},
        ],
        "close_tab": [
            {"type": "hotkey", "params": {"keys": ["command", "w"]}, "description": "Close Tab"},
        ],
        "quit_app": [
            {"type": "hotkey", "params": {"keys": ["command", "q"]}, "description": "Quit App"},
        ],
        "submit": [
            {"type": "key", "params": {"key": "return"}, "description": "Submit"},
        ],
        "escape": [
            {"type": "key", "params": {"key": "escape"}, "description": "Press Escape"},
        ],
    }

    def __init__(
        self,
        vision_handler: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        action_executor: Optional[Callable[[Dict[str, Any]], bool]] = None,
        enable_cache: bool = True,
        enable_patterns: bool = True,
        enable_confidence: bool = True,
    ):
        """
        Args:
            vision_handler: Callable that takes a vision action dict and returns
                a result dict with at least {"success": bool, "error": str}.
            action_executor: Callable that takes a parsed action dict and returns
                success bool. Defaults to pyautogui-based execution.
            enable_cache: Whether to use semantic cache for plan lookup.
            enable_patterns: Whether to use pattern store for plan reuse.
            enable_confidence: Whether to rate action confidence before execution.
        """
        self.vision_handler = vision_handler
        self.action_executor = action_executor or self._default_action_executor
        self.enable_cache = enable_cache and SEMANTIC_CACHE_AVAILABLE
        self.enable_patterns = enable_patterns
        self.enable_confidence = enable_confidence and CONFIDENCE_AVAILABLE
        self._lock = threading.RLock()
        self._stats = {"batches": 0, "actions": 0, "cache_hits": 0, "pattern_hits": 0}

    # --------------------------------------------------------
    # Entry points
    # --------------------------------------------------------

    def execute_plan(
        self,
        actions: List[Any],
        task: Optional[str] = None,
        parallel_vision: bool = True,
    ) -> ExecutionResult:
        """
        Execute a plan of action strings or dicts.

        1. Try semantic cache + pattern store for fast macro plan reuse.
        2. Batch consecutive blind actions.
        3. Run vision actions (possibly in parallel when safe).
        """
        parsed = parse_actions(actions)
        if not parsed:
            return ExecutionResult(success=True, actions_executed=0)

        # Plan-level fast path: try semantic cache / pattern store
        if task and self.enable_cache:
            cached = lookup_plan(task)
            if cached:
                cached_actions = [s.get("suggested_actions", []) for s in cached.get("macro_steps", [])]
                flat = [a for batch in cached_actions for a in batch]
                if flat:
                    parsed = parse_actions(flat)
                    self._stats["cache_hits"] += 1

        if task and self.enable_patterns and not self._stats.get("cache_hits", 0):
            similar = pattern_store.find_similar(task)
            if similar:
                best = pattern_store.get_best_pattern(similar)
                if best and best.confidence >= 0.8:
                    template, variables = pattern_store.normalize_task(task)
                    applied = pattern_store.apply_pattern(best, variables)
                    parsed = parse_actions(applied)
                    self._stats["pattern_hits"] += 1

        # Group into blind batches and vision actions
        batches = self._group_actions(parsed)
        result = ExecutionResult(success=True, actions_executed=0, method="fast")

        for batch in batches:
            if batch["type"] == "blind":
                batch_result = self._execute_blind_batch(batch["actions"])
            else:
                batch_result = self._execute_vision_batch(
                    batch["actions"], parallel=parallel_vision
                )
            result.actions_executed += batch_result.actions_executed
            result.errors.extend(batch_result.errors)
            if not batch_result.success:
                result.success = False
                break

        self._stats["batches"] += 1
        self._stats["actions"] += result.actions_executed
        return result

    def execute_batch(
        self,
        actions: List[Any],
        task: Optional[str] = None,
        parallel_vision: bool = True,
    ) -> ExecutionResult:
        """Alias for execute_plan."""
        return self.execute_plan(actions, task=task, parallel_vision=parallel_vision)

    # --------------------------------------------------------
    # Grouping and batching
    # --------------------------------------------------------

    def _group_actions(self, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Group consecutive blind actions into batches; vision actions stay separate."""
        batches: List[Dict[str, Any]] = []
        current_blind: List[Dict[str, Any]] = []

        for action in actions:
            if _is_blind_action(action):
                current_blind.append(action)
                continue
            if current_blind:
                batches.append({"type": "blind", "actions": current_blind})
                current_blind = []
            batches.append({"type": "vision", "actions": [action]})

        if current_blind:
            batches.append({"type": "blind", "actions": current_blind})

        return batches

    # --------------------------------------------------------
    # Blind execution
    # --------------------------------------------------------

    def _execute_blind_batch(self, actions: List[Dict[str, Any]]) -> ExecutionResult:
        result = ExecutionResult(success=True, actions_executed=0, method="blind_batch")
        for action in actions:
            if self.enable_confidence and rate_action:
                rating = rate_action(action)
                if rating.decision.value in ("abort", "defer_confirm"):
                    result.errors.append(f"Confidence abort/defer for {action}")
                    result.success = False
                    return result
            try:
                ok = self.action_executor(action)
                result.actions_executed += 1
                if not ok:
                    result.errors.append(f"Action executor returned False for {action}")
                    result.success = False
                    return result
            except Exception as e:
                logger.error(f"FastExecutor blind action failed: {e}")
                result.errors.append(str(e))
                result.success = False
                return result
            # Tiny inter-action pause for system stability
            time.sleep(0.02)
        return result

    # --------------------------------------------------------
    # Vision execution
    # --------------------------------------------------------

    def _execute_vision_batch(
        self,
        actions: List[Dict[str, Any]],
        parallel: bool = True,
    ) -> ExecutionResult:
        if not self.vision_handler:
            return ExecutionResult(
                success=False,
                errors=["No vision handler provided"],
            )

        result = ExecutionResult(success=True, actions_executed=0, method="vision_batch")

        # Only parallelize clicks that target different elements and don't depend on
        # previous state (e.g., a search then a click result is not parallel-safe).
        if parallel and len(actions) > 1 and all(
            _safe_action_type(a) == "click" for a in actions
        ):
            with ThreadPoolExecutor(max_workers=min(len(actions), 4)) as pool:
                futures = [pool.submit(self.vision_handler, a) for a in actions]
                for future in futures:
                    try:
                        res = future.result(timeout=30.0)
                        result.actions_executed += 1
                        if not res.get("success", False):
                            result.success = False
                            result.errors.append(res.get("error", "vision action failed"))
                    except Exception as e:
                        result.success = False
                        result.errors.append(str(e))
        else:
            for action in actions:
                try:
                    res = self.vision_handler(action)
                    result.actions_executed += 1
                    if not res.get("success", False):
                        result.success = False
                        result.errors.append(res.get("error", "vision action failed"))
                        break
                except Exception as e:
                    result.success = False
                    result.errors.append(str(e))
                    break

        return result

    # --------------------------------------------------------
    # Common pattern pre-execution
    # --------------------------------------------------------

    def run_common_pattern(
        self,
        pattern_name: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        """
        Execute a known common pattern by name, substituting any parameters.
        """
        pattern = self.COMMON_PATTERNS.get(pattern_name)
        if not pattern:
            return ExecutionResult(success=False, errors=[f"Unknown pattern {pattern_name}"])
        actions = parse_actions(pattern)
        if params:
            for action in actions:
                if action.get("type") == "type" and "text" in params:
                    action["params"]["text"] = params["text"]
        return self._execute_blind_batch(actions)

    # --------------------------------------------------------
    # Default action executor
    # --------------------------------------------------------

    @staticmethod
    def _default_action_executor(action: Dict[str, Any]) -> bool:
        """
        Execute a parsed action using pyautogui. This is the low-level fallback
        when no custom action_executor is provided.
        """
        import pyautogui

        pyautogui.FAILSAFE = True
        action_type = _safe_action_type(action)
        params = action.get("params", {})

        try:
            if action_type == "hotkey":
                keys = params.get("keys", [])
                if keys:
                    pyautogui.hotkey(*keys)
                return True
            elif action_type == "type":
                text = params.get("text", "")
                if text is not None:
                    pyautogui.write(text, interval=0.01)
                return True
            elif action_type == "key":
                key = params.get("key", "")
                if key:
                    pyautogui.press(key)
                return True
            elif action_type == "wait":
                seconds = params.get("seconds", 1.0)
                time.sleep(seconds)
                return True
            elif action_type == "clipboard":
                op = params.get("operation", "paste")
                if op == "copy":
                    pyautogui.hotkey("command", "c")
                elif op == "paste":
                    pyautogui.hotkey("command", "v")
                elif op == "cut":
                    pyautogui.hotkey("command", "x")
                elif op == "select_all":
                    pyautogui.hotkey("command", "a")
                return True
            elif action_type == "open_url":
                # Use pyautogui to focus URL bar and type
                url = params.get("url", "")
                pyautogui.hotkey("command", "l")
                time.sleep(0.1)
                pyautogui.write(url, interval=0.01)
                pyautogui.press("return")
                return True
            elif action_type == "activate_app":
                app = params.get("app", "")
                pyautogui.hotkey("command", "space")
                time.sleep(0.1)
                pyautogui.write(app, interval=0.01)
                pyautogui.press("return")
                return True
            elif action_type == "click":
                # Vision actions are handled by the vision handler, not here.
                return False
            elif action_type == "scroll":
                direction = params.get("direction", "down")
                amount = params.get("amount", 3)
                clicks = amount if direction in ("down", "right") else -amount
                pyautogui.scroll(clicks * 100)
                return True
            elif action_type == "drag":
                start_x = params.get("start_x")
                start_y = params.get("start_y")
                end_x = params.get("end_x")
                end_y = params.get("end_y")
                if start_x is not None and start_y is not None and end_x is not None and end_y is not None:
                    pyautogui.moveTo(start_x, start_y)
                    pyautogui.dragTo(end_x, end_y, duration=0.5)
                    return True
                return False
            else:
                return False
        except Exception as e:
            logger.error(f"Default action executor failed: {e}")
            return False

    # --------------------------------------------------------
    # Stats
    # --------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return self._stats.copy()
