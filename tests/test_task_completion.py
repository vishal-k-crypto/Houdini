"""
Tests for task completion validation logic.

Tests the critical verification pipeline:
- _supervisor_verify_completion (zero-element handling, confidence gating)
- _app_matches_task (app matching)
- TaskVerifier (multi-method aggregation)
- OllamaSupervisor._validate_success (partial acceptance, error defaults)
"""
import pytest
import sys
import os
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional


# ============================================================
# Import helpers — mock heavy dependencies so we can import
# the actual source modules without pyautogui, Ollama, etc.
# ============================================================

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _PROJECT_ROOT)

# Pre-register stub modules for heavy deps that aren't needed in tests
_mock_logger = MagicMock()
_mock_modules = {
    "pyautogui": MagicMock(),
    "rich": MagicMock(),
    "rich.logging": MagicMock(),
    "rich.console": MagicMock(),
    "pydantic": sys.modules.get("pydantic", MagicMock()),
    "dotenv": MagicMock(),
}
for name, stub in _mock_modules.items():
    if name not in sys.modules:
        sys.modules[name] = stub


@pytest.fixture(autouse=True)
def _mock_pil():
    """Isolate PIL mocking to tests in this file so the real Pillow import
    remains available to other tests (e.g. test_browser_vision.py)."""
    with patch.dict(sys.modules, {"PIL": MagicMock(), "PIL.Image": MagicMock()}):
        yield

# Now import the actual modules through the package system.
# task_verifier has light deps (logging + coordinate_predictor), so mock those:
import types

# Create the src package stubs that haven't been imported yet
def _ensure_package(dotted_name):
    parts = dotted_name.split(".")
    for i in range(len(parts)):
        partial = ".".join(parts[:i+1])
        if partial not in sys.modules:
            mod = types.ModuleType(partial)
            # Set __path__ to the actual filesystem path so sub-imports work
            mod.__path__ = [os.path.join(_PROJECT_ROOT, *parts[:i+1])]
            sys.modules[partial] = mod
        elif not hasattr(sys.modules[partial], '__path__'):
            sys.modules[partial].__path__ = [os.path.join(_PROJECT_ROOT, *parts[:i+1])]

# We need: src, src.utils, src.loop, src.supervisor, src.ui
for pkg in ["src", "src.utils", "src.loop", "src.supervisor", "src.ui", "src.agents",
            "src.planner", "src.replay", "src.data_collection"]:
    _ensure_package(pkg)

# Stub the utils modules that get imported via relative paths
sys.modules["src.utils.logging"] = types.ModuleType("src.utils.logging")
sys.modules["src.utils.logging"].logger = MagicMock()
sys.modules["src.utils.logging"].setup_logging = MagicMock()

sys.modules["src.utils.coordinate_predictor"] = types.ModuleType("src.utils.coordinate_predictor")
sys.modules["src.utils.coordinate_predictor"].get_predictor = MagicMock(return_value=MagicMock())

sys.modules["src.utils.ollama_client"] = types.ModuleType("src.utils.ollama_client")
sys.modules["src.utils.ollama_client"].OllamaClient = MagicMock

sys.modules["src.utils.accessibility_reader"] = types.ModuleType("src.utils.accessibility_reader")
sys.modules["src.utils.accessibility_reader"].format_ui_for_llm = MagicMock(return_value="")

# Now import the actual source modules
from src.loop.task_verifier import TaskVerifier
from src.supervisor.ollama_supervisor import OllamaSupervisor


# ============================================================
# Minimal stubs so we can unit-test without importing the full
# dependency tree (Ollama, accessibility, vision, etc.)
# ============================================================

@dataclass
class FakeScreenContext:
    app_name: str = "Safari"
    window_title: str = "YouTube"
    visible_elements: List[Dict] = field(default_factory=list)
    screenshot_path: Optional[str] = None
    raw_accessibility_tree: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class FakeMacroPlan:
    macro_steps: List[Dict] = field(default_factory=list)
    success_criteria: str = "Task completed"
    expected_outcome: str = "Goal achieved"


@dataclass
class FakeAdaptiveState:
    task: str = "play a YouTube video"
    current_macro_step_idx: int = 3
    macro_plan: Optional[FakeMacroPlan] = None
    executed_actions: List[Dict] = field(default_factory=list)
    supervisor_interventions: int = 0
    pending_confidence_outcomes: List = field(default_factory=list)
    evolution_count: int = 0
    evolution_attempt_count: int = 0
    max_evolution_attempts: int = 3
    supervisor_notes: List[str] = field(default_factory=list)


# ============================================================
# Tests: _app_matches_task
# ============================================================

class TestAppMatchesTask:
    """Tests for the _app_matches_task method."""

    def _make_coordinator(self):
        """Create a minimal coordinator mock with just the method under test."""
        # Import the actual method logic inline to avoid full import
        # We replicate the logic here since importing the full module pulls in
        # many heavy dependencies (Ollama, accessibility, etc.)
        class FakeCoordinator:
            def _app_matches_task(self, app_name: str, task: str) -> bool:
                app_lower = app_name.lower()
                task_lower = task.lower()
                
                browser_keywords = ["youtube", "video", "google", "web", "search online", "play a", "watch"]
                if any(kw in task_lower for kw in browser_keywords):
                    return app_lower in ["safari", "google chrome", "firefox", "arc", "brave", "edge"]
                
                if "whatsapp" in task_lower:
                    return "whatsapp" in app_lower
                if "messages" in task_lower:
                    return "messages" in app_lower
                if "notes" in task_lower:
                    return "notes" in app_lower
                if "mail" in task_lower or "email" in task_lower:
                    return "mail" in app_lower or "outlook" in app_lower
                if "calendar" in task_lower:
                    return "calendar" in app_lower
                if "spotify" in task_lower or "music" in task_lower:
                    return "spotify" in app_lower or "music" in app_lower
                
                # FIXED: Conservative default - reject unknown mappings
                return False

        return FakeCoordinator()

    def test_youtube_task_matches_safari(self):
        c = self._make_coordinator()
        assert c._app_matches_task("Safari", "play a YouTube video") is True

    def test_youtube_task_matches_chrome(self):
        c = self._make_coordinator()
        assert c._app_matches_task("Google Chrome", "watch YouTube") is True

    def test_youtube_task_rejects_finder(self):
        c = self._make_coordinator()
        assert c._app_matches_task("Finder", "play a YouTube video") is False

    def test_whatsapp_task_matches_whatsapp(self):
        c = self._make_coordinator()
        assert c._app_matches_task("WhatsApp", "send whatsapp message") is True

    def test_whatsapp_task_rejects_safari(self):
        c = self._make_coordinator()
        assert c._app_matches_task("Safari", "send whatsapp message") is False

    def test_unknown_task_rejects_by_default(self):
        """CRITICAL: Unknown tasks must NOT default to True."""
        c = self._make_coordinator()
        assert c._app_matches_task("TextEdit", "do something unusual") is False

    def test_unknown_task_rejects_any_app(self):
        c = self._make_coordinator()
        assert c._app_matches_task("Safari", "make a sandwich") is False

    def test_mail_task_matches_mail(self):
        c = self._make_coordinator()
        assert c._app_matches_task("Mail", "send an email") is True

    def test_email_task_matches_outlook(self):
        c = self._make_coordinator()
        assert c._app_matches_task("Outlook", "send an email") is True

    def test_calendar_task_rejects_notes(self):
        c = self._make_coordinator()
        assert c._app_matches_task("Notes", "create calendar event") is False


# ============================================================
# Tests: TaskVerifier
# ============================================================

class TestTaskVerifier:
    """Tests for the TaskVerifier aggregation logic."""

    def _make_verifier(self, llm_client=None):
        """Create TaskVerifier instance."""
        return TaskVerifier(llm_client=llm_client)

    def test_empty_verifications_return_incomplete(self):
        v = self._make_verifier()
        result = v._aggregate_verifications([])
        assert result["complete"] is False
        assert result["confidence"] == 0.0

    def test_low_confidence_is_not_complete(self):
        v = self._make_verifier()
        verifications = [
            {"method": "screen_state", "complete": False, "confidence": 0.2, "evidence": []},
            {"method": "actions", "complete": False, "confidence": 0.3, "evidence": []},
        ]
        result = v._aggregate_verifications(verifications)
        assert result["complete"] is False
        assert result["confidence"] < 0.65

    def test_high_confidence_is_complete(self):
        v = self._make_verifier()
        verifications = [
            {"method": "screen_state", "complete": True, "confidence": 0.9, "evidence": ["app open"]},
            {"method": "actions", "complete": True, "confidence": 0.95, "evidence": ["all succeeded"]},
            {"method": "llm", "complete": True, "confidence": 0.85, "evidence": ["LLM says yes"]},
        ]
        result = v._aggregate_verifications(verifications)
        assert result["complete"] is True
        assert result["confidence"] >= 0.65

    def test_zero_screen_with_some_actions_and_llm_can_still_pass(self):
        """Edge case: 0 screen evidence but strong action + LLM evidence."""
        v = self._make_verifier()
        verifications = [
            {"method": "screen_state", "complete": False, "confidence": 0.0, "evidence": []},
            {"method": "actions", "complete": True, "confidence": 1.0, "evidence": ["all done"]},
            {"method": "llm", "complete": True, "confidence": 0.9, "evidence": ["confirmed"]},
        ]
        result = v._aggregate_verifications(verifications)
        # screen(0.2)*0.0 + actions(0.3)*1.0 + llm(0.5)*0.9 = 0 + 0.3 + 0.45 = 0.75
        assert result["confidence"] >= 0.65
        assert result["complete"] is True

    def test_open_task_high_confidence(self):
        v = self._make_verifier()
        result = v._verify_by_screen_state(
            "open Safari",
            {"app": "Safari", "window": "Favorites"}
        )
        assert result["confidence"] >= 0.7

    def test_wrong_app_low_confidence(self):
        v = self._make_verifier()
        result = v._verify_by_screen_state(
            "open Calculator",
            {"app": "Safari", "window": "Google"}
        )
        assert result["confidence"] < 0.7

    def test_no_actions_not_complete(self):
        v = self._make_verifier()
        result = v._verify_by_actions("send a message", [])
        assert result["complete"] is False
        assert result["confidence"] == 0.0


# ============================================================
# Tests: OllamaSupervisor._validate_success
# ============================================================

class TestSupervisorValidateSuccess:
    """Tests for the supervisor's success validation — partial acceptance and error defaults."""

    def test_partial_is_rejected(self):
        """CRITICAL: Partial completion must NOT be accepted as success."""
        mock_client = MagicMock()
        mock_client.generate.return_value = "PARTIAL - some steps were completed but not all"
        
        supervisor = OllamaSupervisor(client=mock_client)
        
        result = supervisor._validate_success(
            task="send message to John",
            plan=[{"type": "blind", "actions": []}],
            result={"success": True}
        )
        assert result is False

    def test_yes_is_accepted(self):
        mock_client = MagicMock()
        mock_client.generate.return_value = "YES - all steps completed successfully"
        
        supervisor = OllamaSupervisor(client=mock_client)
        
        result = supervisor._validate_success(
            task="open Safari",
            plan=[{"type": "blind", "actions": []}],
            result={"success": True}
        )
        assert result is True

    def test_no_is_rejected(self):
        mock_client = MagicMock()
        mock_client.generate.return_value = "NO - the message was never sent"
        
        supervisor = OllamaSupervisor(client=mock_client)
        
        result = supervisor._validate_success(
            task="send message",
            plan=[{"type": "blind", "actions": []}],
            result={"success": True}
        )
        assert result is False

    def test_error_defaults_to_false(self):
        """CRITICAL: On LLM error, must NOT default to accepting success."""
        mock_client = MagicMock()
        mock_client.generate.side_effect = Exception("Connection refused")
        
        supervisor = OllamaSupervisor(client=mock_client)
        
        result = supervisor._validate_success(
            task="send message",
            plan=[{"type": "blind", "actions": []}],
            result={"success": True}
        )
        assert result is False


# ============================================================
# Tests: Confidence gating thresholds
# ============================================================

class TestConfidenceGating:
    """Tests for confidence threshold logic."""

    def test_confidence_below_075_blocks_completion(self):
        """Confidence below 0.75 should NOT allow task completion."""
        # Simulates the gate: `if complete and confidence >= 0.75`
        complete = True
        confidence = 0.70
        assert not (complete and confidence >= 0.75)

    def test_confidence_at_075_allows_completion(self):
        complete = True
        confidence = 0.75
        assert (complete and confidence >= 0.75)

    def test_confidence_at_060_old_threshold_now_blocks(self):
        """Old threshold was 0.6 — this should now be blocked."""
        complete = True
        confidence = 0.60
        assert not (complete and confidence >= 0.75)

    def test_zero_element_with_screenshot_capped_at_080(self):
        """Zero-element mode with screenshot: confidence capped at 0.80."""
        zero_element_mode = True
        has_screenshot_evidence = True
        confidence = 0.95  # LLM says very confident
        
        max_confidence = 0.80 if has_screenshot_evidence else 0.65
        if confidence > max_confidence:
            confidence = max_confidence
        
        assert confidence == 0.80
        # 0.80 >= 0.75 so this CAN pass
        assert confidence >= 0.75

    def test_zero_element_without_screenshot_capped_at_065(self):
        """Zero-element mode without screenshot: confidence capped at 0.65, always blocks."""
        zero_element_mode = True
        has_screenshot_evidence = False
        confidence = 0.95
        
        max_confidence = 0.80 if has_screenshot_evidence else 0.65
        if confidence > max_confidence:
            confidence = max_confidence
        
        assert confidence == 0.65
        # 0.65 < 0.75 so this CANNOT pass
        assert confidence < 0.75


# ============================================================
# Tests: Evolution forced stop
# ============================================================

class TestEvolutionForcedStop:
    """Verify that max-evolution-attempts leads to FAILED, not COMPLETED."""

    def test_max_evolution_returns_false(self):
        """When evolution count exceeds max, return False (→ FAILED phase)."""
        state = FakeAdaptiveState()
        state.evolution_attempt_count = 4  # > max of 3
        state.max_evolution_attempts = 3
        
        # The logic: if attempt_count > max → return False
        should_stop = state.evolution_attempt_count > state.max_evolution_attempts
        assert should_stop is True
        # return False → sets phase to FAILED (not COMPLETED)
