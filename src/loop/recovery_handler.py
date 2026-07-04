"""
RecoveryRouter - Failure classification and strategy selection for Houdini Agent.

Extends the existing RecoveryHandler with a classification layer that maps a
failure signature to one of the canonical failure categories and then selects the
appropriate recovery strategy. This makes recovery faster, less reliant on LLM
round-trips, and easier to tune.

Categories:
- network          : connection / website unreachable / WARP-related issues
- vision           : cannot locate element, OCR/vision model failure
- permission       : permission dialogs, accessibility denied, system prompts
- ui_changed       : UI element moved, app changed, unexpected screen state
- model_timeout    : LLM call timed out or failed to respond
- unknown          : everything else
"""

from __future__ import annotations

import time
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from .loop_state import LoopState, LoopStatus
from ..utils.logging import logger

# Import existing recovery handler base if available
try:
    from .recovery_handler import RecoveryHandler, StuckCondition
    BASE_HANDLER = RecoveryHandler
except ImportError:
    BASE_HANDLER = object  # type: ignore


try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False


class FailureCategory(str, Enum):
    NETWORK = "network"
    VISION = "vision"
    PERMISSION = "permission"
    UI_CHANGED = "ui_changed"
    MODEL_TIMEOUT = "model_timeout"
    UNKNOWN = "unknown"


class RecoveryStrategy(str, Enum):
    DISMISS_AND_RETRY = "dismiss_and_retry"
    WAIT_AND_RETRY = "wait_and_retry"
    ESCAPE_DIALOG = "escape_dialog"
    CLICK_ALLOW = "click_allow"
    SKIP_STEP = "skip_step"
    ROLLBACK_CHECKPOINT = "rollback_checkpoint"
    LLM_GUIDANCE = "llm_guidance"
    RESTART_APP = "restart_app"
    TOGGLE_WARP = "toggle_warp"
    ABORT = "abort"


@dataclass
class FailureSignature:
    """Structured failure description."""
    category: FailureCategory
    reason: str
    confidence: float = 0.5
    context: Dict[str, Any] = field(default_factory=dict)
    suggested_strategy: Optional[RecoveryStrategy] = None


class RecoveryRouter:
    """
    Classifies failures and routes them to a recovery strategy.

    Can be used standalone or injected into the existing RecoveryHandler.
    """

    # Regex patterns for classification (error text, window titles, etc.)
    NETWORK_PATTERNS = [
        r"can'?t be reached",
        r"no internet",
        r"connection error",
        r"timeout",
        r"timed out",
        r"network",
        r"unreachable",
        r"ERR_",
        r"dns",
        r"warp",
    ]
    VISION_PATTERNS = [
        r"element not found",
        r"cannot locate",
        r"no matching element",
        r"vision",
        r"ocr",
        r"not found on screen",
        r"click failed",
        r"coordinate",
    ]
    PERMISSION_PATTERNS = [
        r"permission",
        r"accessibility",
        r"allow",
        r"deny",
        r"do you want",
        r"are you sure",
        r"authenticate",
        r"password",
        r"system dialog",
    ]
    UI_CHANGED_PATTERNS = [
        r"ui changed",
        r"unexpected screen",
        r"wrong app",
        r"window changed",
        r"element moved",
        r"state mismatch",
        r"does not match",
    ]
    MODEL_TIMEOUT_PATTERNS = [
        r"llm error",
        r"model timeout",
        r"generate_json",
        r"client error",
        r"no response",
        r"empty response",
        r"json decode",
        r"model",
    ]

    def __init__(
        self,
        state: Optional[LoopState] = None,
        llm_guidance_fn: Optional[Callable[..., Dict[str, Any]]] = None,
        max_recovery_attempts: int = 3,
    ):
        self.state = state
        self.llm_guidance_fn = llm_guidance_fn
        self.max_recovery_attempts = max_recovery_attempts
        self._attempts: Dict[str, int] = {}
        self._history: List[Dict[str, Any]] = []

    # --------------------------------------------------------
    # Classification
    # --------------------------------------------------------

    def classify(
        self,
        error_text: Optional[str] = None,
        window_title: Optional[str] = None,
        action_type: Optional[str] = None,
        exception: Optional[Exception] = None,
    ) -> FailureSignature:
        """Classify a failure based on available signals."""
        text = " ".join(
            str(x).lower()
            for x in [error_text, window_title, exception]
            if x is not None
        )

        if self._matches(text, self.NETWORK_PATTERNS):
            return FailureSignature(
                category=FailureCategory.NETWORK,
                reason="Network/connection failure detected",
                confidence=0.8,
                suggested_strategy=RecoveryStrategy.TOGGLE_WARP,
            )
        if self._matches(text, self.VISION_PATTERNS) or action_type == "vision":
            return FailureSignature(
                category=FailureCategory.VISION,
                reason="Vision/element location failure",
                confidence=0.8,
                suggested_strategy=RecoveryStrategy.WAIT_AND_RETRY,
            )
        if self._matches(text, self.PERMISSION_PATTERNS):
            return FailureSignature(
                category=FailureCategory.PERMISSION,
                reason="Permission or system dialog",
                confidence=0.85,
                suggested_strategy=RecoveryStrategy.CLICK_ALLOW,
            )
        if self._matches(text, self.UI_CHANGED_PATTERNS):
            return FailureSignature(
                category=FailureCategory.UI_CHANGED,
                reason="UI changed or unexpected screen state",
                confidence=0.75,
                suggested_strategy=RecoveryStrategy.WAIT_AND_RETRY,
            )
        if self._matches(text, self.MODEL_TIMEOUT_PATTERNS):
            return FailureSignature(
                category=FailureCategory.MODEL_TIMEOUT,
                reason="LLM/model timeout or generation failure",
                confidence=0.7,
                suggested_strategy=RecoveryStrategy.WAIT_AND_RETRY,
            )

        return FailureSignature(
            category=FailureCategory.UNKNOWN,
            reason="Unclassified failure",
            confidence=0.3,
            suggested_strategy=RecoveryStrategy.LLM_GUIDANCE,
        )

    @staticmethod
    def _matches(text: str, patterns: List[str]) -> bool:
        for p in patterns:
            if re.search(p, text):
                return True
        return False

    # --------------------------------------------------------
    # Strategy selection
    # --------------------------------------------------------

    def select_strategy(self, signature: FailureSignature) -> RecoveryStrategy:
        """Pick the best strategy for a classified failure."""
        category = signature.category
        if category == FailureCategory.PERMISSION:
            return RecoveryStrategy.CLICK_ALLOW
        if category == FailureCategory.NETWORK:
            return RecoveryStrategy.TOGGLE_WARP
        if category == FailureCategory.VISION:
            return RecoveryStrategy.WAIT_AND_RETRY
        if category == FailureCategory.UI_CHANGED:
            return RecoveryStrategy.WAIT_AND_RETRY
        if category == FailureCategory.MODEL_TIMEOUT:
            return RecoveryStrategy.WAIT_AND_RETRY
        return signature.suggested_strategy or RecoveryStrategy.LLM_GUIDANCE

    # --------------------------------------------------------
    # Execution
    # --------------------------------------------------------

    def recover(
        self,
        error_text: Optional[str] = None,
        window_title: Optional[str] = None,
        action_type: Optional[str] = None,
        exception: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Classify a failure and execute the selected recovery strategy.
        Returns a result dict with keys: success, action, reason, category.
        """
        signature = self.classify(error_text, window_title, action_type, exception)
        strategy = self.select_strategy(signature)

        key = f"{signature.category}:{strategy}"
        self._attempts[key] = self._attempts.get(key, 0) + 1

        if self._attempts[key] > self.max_recovery_attempts:
            return {
                "success": False,
                "action": "abort",
                "reason": f"Max recovery attempts for {signature.category.value}",
                "category": signature.category.value,
                "strategy": strategy.value,
            }

        logger.warning(
            f"🩹 RecoveryRouter: {signature.category.value} -> {strategy.value} "
            f"(attempt {self._attempts[key]}/{self.max_recovery_attempts})"
        )

        result = self._execute_strategy(strategy, signature, context)
        self._history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "category": signature.category.value,
                "strategy": strategy.value,
                "success": result.get("success", False),
                "reason": result.get("reason", ""),
            }
        )
        return result

    def _execute_strategy(
        self,
        strategy: RecoveryStrategy,
        signature: FailureSignature,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a recovery strategy."""
        if not PYAUTOGUI_AVAILABLE:
            return {"success": False, "action": "abort", "reason": "pyautogui unavailable"}

        try:
            if strategy == RecoveryStrategy.ESCAPE_DIALOG:
                pyautogui.press("escape")
                time.sleep(0.3)
                return {"success": True, "action": "escape", "reason": "Pressed escape"}

            if strategy == RecoveryStrategy.CLICK_ALLOW:
                # Try common permission dialog buttons
                pyautogui.press("return")
                time.sleep(0.3)
                return {"success": True, "action": "click_allow", "reason": "Pressed return to accept"}

            if strategy == RecoveryStrategy.WAIT_AND_RETRY:
                wait_seconds = 1.5
                if signature.category == FailureCategory.MODEL_TIMEOUT:
                    wait_seconds = 3.0
                time.sleep(wait_seconds)
                return {
                    "success": True,
                    "action": "wait_and_retry",
                    "reason": f"Waited {wait_seconds}s before retry",
                }

            if strategy == RecoveryStrategy.DISMISS_AND_RETRY:
                pyautogui.press("escape")
                time.sleep(0.3)
                return {"success": True, "action": "dismiss_and_retry", "reason": "Dismissed dialog"}

            if strategy == RecoveryStrategy.TOGGLE_WARP:
                # WARP toggle: command-shift-R is a common WARP shortcut
                pyautogui.keyDown("command")
                pyautogui.keyDown("shift")
                pyautogui.keyDown("r")
                pyautogui.keyUp("r")
                pyautogui.keyUp("shift")
                pyautogui.keyUp("command")
                time.sleep(2.0)
                return {
                    "success": True,
                    "action": "toggle_warp",
                    "reason": "Toggled WARP VPN and waited",
                }

            if strategy == RecoveryStrategy.SKIP_STEP:
                if self.state:
                    self.state.advance_batch()
                return {"success": True, "action": "skip_step", "reason": "Skipped problematic step"}

            if strategy == RecoveryStrategy.ROLLBACK_CHECKPOINT:
                if self.state and self.state.checkpoints:
                    last = self.state.checkpoints[-1]
                    self.state.rollback_to(last.checkpoint_id)
                    return {
                        "success": True,
                        "action": "rollback",
                        "reason": f"Rolled back to checkpoint {last.checkpoint_id}",
                    }
                return {"success": False, "action": "rollback", "reason": "No checkpoint available"}

            if strategy == RecoveryStrategy.LLM_GUIDANCE:
                if self.llm_guidance_fn:
                    return self.llm_guidance_fn(signature=signature, context=context)
                return {
                    "success": False,
                    "action": "llm_guidance",
                    "reason": "No LLM guidance function provided",
                }

            if strategy == RecoveryStrategy.ABORT:
                if self.state:
                    self.state.status = LoopStatus.FAILED
                return {"success": False, "action": "abort", "reason": "Aborted by strategy"}

        except Exception as e:
            logger.error(f"RecoveryRouter strategy {strategy.value} failed: {e}")
            return {
                "success": False,
                "action": strategy.value,
                "reason": f"Strategy execution error: {e}",
            }

        return {
            "success": False,
            "action": strategy.value,
            "reason": "Unhandled strategy",
        }

    # --------------------------------------------------------
    # Utilities
    # --------------------------------------------------------

    def get_history(self) -> List[Dict[str, Any]]:
        return self._history

    def reset(self):
        self._attempts.clear()
        self._history.clear()


# ============================================================
# Extended RecoveryHandler that uses the router
# ============================================================

class RecoveryHandlerWithRouter(BASE_HANDLER):  # type: ignore
    """
    Drop-in replacement for RecoveryHandler that uses RecoveryRouter.
    Keeps all existing RecoveryHandler methods and adds router-based fast path.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.router = RecoveryRouter(
            state=kwargs.get("state") or (args[1] if len(args) > 1 else None),
            llm_guidance_fn=self._llm_guidance_wrapper,
            max_recovery_attempts=kwargs.get("max_recovery_attempts", 3),
        )

    def _llm_guidance_wrapper(self, signature, context=None):
        # Fallback to original LLM recovery
        stuck = StuckCondition(
            detected_at=datetime.now(),
            reason=signature.reason,
            screen_context=context.get("screen_context", "") if context else "",
            loop_count=0,
            last_actions=context.get("last_actions", []) if context else [],
        )
        return self._get_llm_recovery(stuck)

    def classify_and_recover(
        self,
        error_text: Optional[str] = None,
        window_title: Optional[str] = None,
        action_type: Optional[str] = None,
        exception: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Fast classification + recovery; falls back to legacy check_and_recover."""
        result = self.router.recover(
            error_text=error_text,
            window_title=window_title,
            action_type=action_type,
            exception=exception,
            context=context,
        )
        if result.get("success"):
            return result
        # Fallback to legacy behavior
        return self.check_and_recover() or {
            "success": False,
            "action": "none",
            "reason": "RecoveryHandler did not detect stuck condition",
        }
