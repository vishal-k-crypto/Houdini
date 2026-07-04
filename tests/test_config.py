"""Tests for config/settings.py — verify defaults load correctly."""
import pytest
import sys
import os

# Ensure project root is on path
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _PROJECT_ROOT)


class TestSettings:
    """Verify the centralized config loads with sane defaults."""

    def test_settings_import(self):
        from config.settings import settings
        assert settings is not None

    def test_default_model(self):
        from config.settings import settings
        assert settings.ollama_default_model == "qwen3-coder:480b-cloud"

    def test_confidence_thresholds_sane(self):
        from config.settings import settings
        assert 0.5 <= settings.completion_confidence_threshold <= 1.0
        assert 0.5 <= settings.task_verifier_confidence_threshold <= 1.0
        assert settings.zero_element_no_screenshot_cap < settings.completion_confidence_threshold

    def test_zero_element_caps_ordered(self):
        from config.settings import settings
        # Without screenshot should be stricter than with screenshot
        assert settings.zero_element_no_screenshot_cap < settings.zero_element_screenshot_cap

    def test_execution_limits_positive(self):
        from config.settings import settings
        assert settings.max_iterations > 0
        assert settings.max_step_attempts > 0
        assert settings.max_evolution_attempts > 0

    def test_timeouts_positive(self):
        from config.settings import settings
        assert settings.ollama_generate_timeout > 0
        assert settings.screen_capture_timeout > 0
        assert settings.ui_settle_wait >= 0

    def test_data_paths_defined(self):
        from config.settings import settings
        assert settings.data_dir
        assert settings.executor_history_file
        assert settings.replay_sessions_dir

    def test_env_override(self, monkeypatch):
        """Environment variables should override defaults."""
        monkeypatch.setenv("OLLAMA_DEFAULT_MODEL", "test-model:latest")
        # Need to re-instantiate since settings is frozen
        from config.settings import HoudiniSettings
        fresh = HoudiniSettings()
        assert fresh.ollama_default_model == "test-model:latest"

    def test_frozen_immutable(self):
        from config.settings import settings
        with pytest.raises(AttributeError):
            settings.ollama_default_model = "should-fail"
