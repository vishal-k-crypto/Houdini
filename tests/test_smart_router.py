"""Tests for the SmartRouter task-aware routing layer."""
import pytest

import pytest

from src.providers.base import LLMProvider
from src.providers.registry import registry
from src.providers.smart_router import SmartRouter, TaskClassifier


class FakeProvider(LLMProvider):
    """In-memory provider for routing tests."""

    def __init__(self, model_name="fake", supports_vision=False, is_local=False, supports_tools=False, **kwargs):
        super().__init__(model_name=model_name, **kwargs)
        self._supports_vision = supports_vision
        self._is_local = is_local
        self._supports_tools = supports_tools
        self.calls = []

    @property
    def provider_id(self):
        return "fake"

    @property
    def supports_vision(self):
        return self._supports_vision

    @property
    def is_local(self):
        return self._is_local

    @property
    def supports_tool_calls(self):
        return self._supports_tools

    def _generate_text(self, prompt, **kwargs):
        self.calls.append(("text", prompt, kwargs))
        from src.providers.base import GenerateResult
        return GenerateResult(text="ok")


@pytest.fixture(autouse=True)
def _register_fake_providers():
    registry.register("fake-local", FakeProvider)
    registry.register("fake-cloud", FakeProvider)
    registry.register("fake-vision", FakeProvider)
    yield
    # Clean up registrations after test
    for pid in ("fake-local", "fake-cloud", "fake-vision"):
        registry._providers.pop(pid, None)


def test_task_classifier_simple():
    assert TaskClassifier.classify("click the OK button") == "simple"
    assert TaskClassifier.classify("open TextEdit") == "simple"


def test_task_classifier_medium():
    assert TaskClassifier.classify("Open Safari and navigate to example.com") == "medium"
    assert TaskClassifier.classify("search Google for Houdini and wait for results") == "medium"


def test_task_classifier_hard():
    assert TaskClassifier.classify("Debug why the build is failing and fix it") == "hard"
    assert TaskClassifier.classify("Write a multi-step benchmark that recovers from errors") == "hard"


def test_smart_router_prefers_preference():
    router = SmartRouter(
        preferences={"worker": "fake-cloud"},
        tiers={"worker": ["fake-local", "fake-vision"]},
    )
    decision = router.route("click the button", "worker")
    assert decision.provider_id == "fake-cloud"


def test_smart_router_falls_back_to_tiers():
    router = SmartRouter(
        tiers={"worker": ["fake-local"]},
    )
    decision = router.route("click the button", "worker")
    assert decision.provider_id == "fake-local"


def test_smart_router_raises_when_no_viable_provider():
    router = SmartRouter(
        tiers={"worker": ["definitely-not-a-provider"]},
    )
    with pytest.raises(RuntimeError):
        router.route("click the button", "worker")


def test_smart_router_usage_summary_empty():
    router = SmartRouter()
    summary = router.usage_summary()
    assert summary["total_calls"] == 0
    assert summary["successful"] == 0
    assert summary["total_cost_usd"] == 0.0


def test_smart_router_records_failed_call():
    router = SmartRouter()
    from src.providers.smart_router import RoutingDecision
    decision = RoutingDecision(
        role="worker",
        provider_id="fake",
        model="fake-model",
        reason="test",
        local=True,
    )
    router._record(decision, None, 100.0, success=False, error="boom")
    summary = router.usage_summary()
    assert summary["total_calls"] == 1
    assert summary["successful"] == 0
    assert summary["failed"] == 1
    assert summary["by_provider"]["fake"]["calls"] == 1


def test_smart_router_local_preference():
    router = SmartRouter(prefer_local=True)
    # Scoring logic should penalize non-local providers.
    score, reason = router._score("openai", FakeProvider(is_local=False), "worker", "simple", False)
    assert score < 1.0
    assert "not local" in reason


def test_smart_router_vision_requirement():
    router = SmartRouter()
    score, reason = router._score(
        "fake-local", FakeProvider(is_local=True, supports_vision=False), "vision", "medium", True
    )
    assert score < 0.8
    assert "no vision" in reason
