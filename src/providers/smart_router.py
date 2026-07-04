"""Task-aware smart routing for Houdini.

The SmartRouter extends ProviderRouter with dynamic model selection based on:
  • Task complexity (heuristic + optional LLM classifier)
  • Required capabilities (vision, tool calls, long context, coding)
  • User constraints (local-only, budget cap, latency preference)
  • Provider health / availability

This lets Houdini use cheap, fast models for simple actions while reserving
frontier models for high-stakes planning and error recovery.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .base import GenerateResult, LLMProvider
from .registry import get_default_provider, registry
from .router import ProviderRouter


@dataclass
class RoutingDecision:
    """Result of a routing decision."""

    role: str
    provider_id: str
    model: Optional[str]
    reason: str
    estimated_cost_usd: Optional[float] = None
    estimated_latency_ms: Optional[float] = None
    local: bool = False
    supports_vision: bool = False


@dataclass
class RoutedCall:
    """Record of a routed generation call."""

    role: str
    provider_id: str
    model: Optional[str]
    prompt_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    duration_ms: Optional[float] = None
    success: bool = True
    error: Optional[str] = None


class TaskClassifier:
    """Lightweight rule-based task complexity classifier.

    Complexity levels:
      simple  - single action, known pattern, short horizon
      medium  - multi-step, some reasoning, app interaction
      hard    - long horizon, error recovery, reasoning, novel task
    """

    HARD_INDICATORS = [
        "debug", "refactor", "complex", "multi-step", "orchestrate",
        "error", "recover", "if.*fail", "loop", "iterate", "compare",
        "research", "find.*and.*then", "write.*test", "benchmark",
        "install", "configure", "deploy",
    ]
    MEDIUM_INDICATORS = [
        "open.*and.*then", "create.*and.*delete", "copy.*paste",
        "search.*for", "navigate", "switch", "select", "save.*as",
    ]
    SIMPLE_INDICATORS = [
        "click", "type", "press", "close", "open.*app", "screenshot",
        "spotlight", "launch",
    ]

    @classmethod
    def classify(cls, task: str) -> str:
        task_l = task.lower()
        if any(re.search(p, task_l) for p in cls.HARD_INDICATORS):
            return "hard"
        words = len(task.split())
        steps = task.count(",") + task.count("and") + task.count("then") + task.count(";")
        if words > 25 or steps >= 2:
            return "medium"
        if any(re.search(p, task_l) for p in cls.MEDIUM_INDICATORS):
            return "medium"
        return "simple"


class SmartRouter(ProviderRouter):
    """Dynamic provider/model selection for Houdini sub-tasks."""

    # Cost estimates per 1M input tokens (approximate, updated periodically)
    COST_PER_1M_INPUT: Dict[str, float] = {
        "openai": 2.50,
        "anthropic": 3.00,
        "gemini": 0.50,
        "ollama": 0.0,
        "webllm": 0.0,
        "cli:claude": 0.0,
        "cli:codex": 0.0,
    }

    # Latency estimates for a short prompt (ms)
    LATENCY_ESTIMATE_MS: Dict[str, float] = {
        "ollama": 800.0,
        "webllm": 600.0,
        "gemini": 400.0,
        "openai": 500.0,
        "anthropic": 600.0,
        "cli:claude": 3000.0,
        "cli:codex": 5000.0,
    }

    def __init__(
        self,
        preferences: Optional[Dict[str, str]] = None,
        tiers: Optional[Dict[str, List[str]]] = None,
        budget_cap_usd: Optional[float] = None,
        prefer_local: bool = False,
        latency_budget_ms: Optional[float] = None,
        classifier: Optional[Callable[[str], str]] = None,
    ):
        super().__init__(
            preferences=preferences,
            tiers=tiers,
            budget_cap_usd=budget_cap_usd,
        )
        self.prefer_local = prefer_local
        self.latency_budget_ms = latency_budget_ms
        self.classifier = classifier or TaskClassifier.classify
        self.history: List[RoutedCall] = []
        self._spent_usd = 0.0

    def route(
        self,
        task: str,
        role: str = "worker",
        *,
        require_vision: bool = False,
        require_tools: bool = False,
        require_local: bool = False,
    ) -> RoutingDecision:
        """Pick the best provider/model for a task/role combination."""
        complexity = self.classifier(task)
        preferred = self.preferences.get(role)

        candidates = []
        if preferred:
            candidates.append(preferred)
        candidates.extend(self.tiers.get(role, []))

        # Filter by capability and availability
        viable: List[Tuple[str, LLMProvider]] = []
        for provider_id in candidates:
            provider = self._try_create(
                provider_id,
                prefer_vision=require_vision,
                require_local=require_local or self.prefer_local,
            )
            if provider is None:
                continue
            if require_tools and not provider.supports_tool_calls:
                continue
            viable.append((provider_id, provider))

        if not viable:
            # Relax local constraint if nothing is available
            for provider_id in candidates:
                provider = self._try_create(
                    provider_id, prefer_vision=require_vision, require_local=False
                )
                if provider is None:
                    continue
                if require_tools and not provider.supports_tool_calls:
                    continue
                viable.append((provider_id, provider))

        if not viable:
            raise RuntimeError(
                f"No viable provider for role={role} task={task[:80]!r}"
            )

        # Score viable candidates
        scored = []
        for provider_id, provider in viable:
            score, reason = self._score(
                provider_id, provider, role, complexity, require_vision
            )
            scored.append((score, provider_id, provider, reason))

        scored.sort(key=lambda x: x[0], reverse=True)
        _score, provider_id, provider, reason = scored[0]

        return RoutingDecision(
            role=role,
            provider_id=provider_id,
            model=provider.model_name,
            reason=reason,
            estimated_cost_usd=self._estimate_cost(provider_id),
            estimated_latency_ms=self.LATENCY_ESTIMATE_MS.get(provider_id),
            local=provider.is_local,
            supports_vision=provider.supports_vision,
        )

    def generate_for(
        self,
        task: str,
        prompt: str,
        role: str = "worker",
        *,
        require_vision: bool = False,
        require_tools: bool = False,
        require_local: bool = False,
        fallback: bool = True,
        **generate_kwargs,
    ) -> GenerateResult:
        """Route and execute a generation call, with optional fallback chain."""
        decision = self.route(
            task,
            role,
            require_vision=require_vision,
            require_tools=require_tools,
            require_local=require_local,
        )
        provider = self._create(
            decision.provider_id,
            prefer_vision=require_vision,
            require_local=require_local,
        )

        start = time.time()
        try:
            if require_vision:
                # Vision prompts are expected to supply image via generate_kwargs
                result = provider.generate(prompt, **generate_kwargs)
            else:
                result = provider.generate(prompt, **generate_kwargs)
            duration_ms = (time.time() - start) * 1000
            self._record(decision, result, duration_ms, success=True)
            return result
        except Exception as exc:
            duration_ms = (time.time() - start) * 1000
            self._record(decision, None, duration_ms, success=False, error=str(exc))
            if not fallback:
                raise

            # Fallback: try next viable providers
            candidates = self._fallback_candidates(
                task, role, decision.provider_id, require_vision, require_tools, require_local
            )
            for provider_id in candidates:
                provider = self._try_create(
                    provider_id,
                    prefer_vision=require_vision,
                    require_local=require_local,
                )
                if provider is None:
                    continue
                try:
                    result = provider.generate(prompt, **generate_kwargs)
                    duration_ms = (time.time() - start) * 1000
                    self._record(
                        RoutingDecision(
                            role=role,
                            provider_id=provider_id,
                            model=provider.model_name,
                            reason="fallback",
                            local=provider.is_local,
                            supports_vision=provider.supports_vision,
                        ),
                        result,
                        duration_ms,
                        success=True,
                    )
                    return result
                except Exception as fallback_exc:
                    self._record(
                        RoutingDecision(
                            role=role,
                            provider_id=provider_id,
                            model=provider.model_name,
                            reason="fallback failed",
                            local=provider.is_local,
                            supports_vision=provider.supports_vision,
                        ),
                        None,
                        (time.time() - start) * 1000,
                        success=False,
                        error=str(fallback_exc),
                    )
            raise RuntimeError(f"All providers failed for role={role}: {exc}")

    def _score(
        self,
        provider_id: str,
        provider: LLMProvider,
        role: str,
        complexity: str,
        require_vision: bool,
    ) -> Tuple[float, str]:
        """Return a score [0,1] and human-readable reason for this provider."""
        score = 1.0
        reasons = []

        # Local preference
        if self.prefer_local and not provider.is_local:
            score -= 0.3
            reasons.append("not local")
        elif provider.is_local:
            score += 0.1
            reasons.append("local")

        # Complexity fit: frontier APIs for hard tasks, local for simple
        if complexity == "hard" and provider.is_local:
            score -= 0.25
            reasons.append("local may struggle with hard task")
        elif complexity == "simple" and not provider.is_local:
            score -= 0.15
            reasons.append("overkill for simple task")
        else:
            reasons.append(f"fits {complexity} complexity")

        # Vision
        if require_vision and provider.supports_vision:
            score += 0.15
            reasons.append("vision capable")
        elif require_vision:
            score -= 0.5
            reasons.append("no vision")

        # Latency budget
        latency = self.LATENCY_ESTIMATE_MS.get(provider_id, 1000.0)
        if self.latency_budget_ms and latency > self.latency_budget_ms:
            score -= 0.2
            reasons.append("too slow")

        # Budget cap
        cost = self._estimate_cost(provider_id)
        if self.budget_cap_usd is not None and self._spent_usd + cost > self.budget_cap_usd:
            score -= 0.5
            reasons.append("near budget cap")

        # Prefer gemini for cost-effective vision
        if require_vision and provider_id == "gemini":
            score += 0.05

        reason = f"{provider_id} ({complexity})"
        if reasons:
            reason += f" — {', '.join(reasons)}"
        return max(0.0, score), reason

    def _fallback_candidates(
        self,
        task: str,
        role: str,
        exclude: str,
        require_vision: bool,
        require_tools: bool,
        require_local: bool,
    ) -> List[str]:
        """Return fallback provider ids excluding the one that just failed."""
        seen = {exclude}
        candidates = []
        for pid in self.tiers.get(role, []):
            if pid in seen:
                continue
            seen.add(pid)
            candidates.append(pid)
        return candidates

    def _estimate_cost(self, provider_id: str) -> float:
        return self.COST_PER_1M_INPUT.get(provider_id, 0.0)

    def _record(
        self,
        decision: RoutingDecision,
        result: Optional[GenerateResult],
        duration_ms: float,
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        usage = result.usage if result else None
        cost = usage.cost_usd if usage else None
        if cost is not None:
            self._spent_usd += cost
        self.history.append(
            RoutedCall(
                role=decision.role,
                provider_id=decision.provider_id,
                model=decision.model,
                prompt_tokens=usage.input_tokens if usage else None,
                output_tokens=usage.output_tokens if usage else None,
                cost_usd=cost,
                duration_ms=duration_ms,
                success=success,
                error=error,
            )
        )

    def usage_summary(self) -> Dict[str, Any]:
        """Return aggregate routing/cost summary."""
        total_calls = len(self.history)
        successful = sum(1 for h in self.history if h.success)
        total_cost = sum(h.cost_usd or 0.0 for h in self.history)
        total_duration = sum(h.duration_ms or 0.0 for h in self.history)
        by_provider: Dict[str, Dict[str, Any]] = {}
        for h in self.history:
            entry = by_provider.setdefault(
                h.provider_id,
                {"calls": 0, "success": 0, "cost_usd": 0.0, "duration_ms": 0.0},
            )
            entry["calls"] += 1
            entry["success"] += int(h.success)
            entry["cost_usd"] += h.cost_usd or 0.0
            entry["duration_ms"] += h.duration_ms or 0.0
        return {
            "total_calls": total_calls,
            "successful": successful,
            "failed": total_calls - successful,
            "total_cost_usd": total_cost,
            "total_duration_ms": total_duration,
            "budget_cap_usd": self.budget_cap_usd,
            "spent_usd": self._spent_usd,
            "by_provider": by_provider,
        }


# Global smart router instance
smart_router = SmartRouter()


def configure_from_env() -> None:
    """Load smart-router preferences from environment."""
    for role in SmartRouter.ROLES:
        env_value = os.environ.get(f"HOUDINI_{role.upper()}_PROVIDER")
        if env_value:
            smart_router.set_preference(role, env_value)

    budget = os.environ.get("HOUDINI_BUDGET_CAP_USD")
    if budget:
        try:
            smart_router.budget_cap_usd = float(budget)
        except ValueError:
            pass

    if os.environ.get("HOUDINI_PREFER_LOCAL", "").lower() in ("true", "1", "yes"):
        smart_router.prefer_local = True

    latency = os.environ.get("HOUDINI_LATENCY_BUDGET_MS")
    if latency:
        try:
            smart_router.latency_budget_ms = float(latency)
        except ValueError:
            pass


configure_from_env()
