"""
Houdini Agent — Benchmark Suite

Measures and tracks:
  • Success rate across a standard task set
  • Average execution time per task
  • Vision strategy accuracy (which strategy resolved clicks)
  • Confidence model calibration quality

Usage:
    python -m src.benchmark                        # run all benchmarks
    python -m src.benchmark --tag smoke            # only tasks tagged "smoke"
    python -m src.benchmark --dry-run              # list tasks without executing
    python -m src.benchmark --output results.json  # persist to file

The standard task set is defined in BENCHMARK_TASKS below.
Extend it by appending to the list or loading from a JSON file via --tasks-file.
"""

import argparse
import json
import os
import sys
import time
import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is on sys.path so we can import src.*
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.utils.logging import logger

# ── Standard task set ────────────────────────────────────────────────

@dataclass
class BenchmarkTask:
    id: str
    description: str
    tags: List[str] = field(default_factory=list)
    expected_app: Optional[str] = None          # expected frontmost app after completion
    timeout_s: float = 120.0
    verify_hint: Optional[str] = None           # hint for automated verification


BENCHMARK_TASKS: List[BenchmarkTask] = [
    # ── Smoke tests (fast, deterministic) ──
    BenchmarkTask(
        id="smoke-spotlight",
        description="Open Spotlight search and close it",
        tags=["smoke", "hotkey"],
        expected_app=None,
        timeout_s=15,
        verify_hint="Spotlight search bar appeared and then disappeared; desktop is back to normal.",
    ),
    BenchmarkTask(
        id="smoke-textedit",
        description="Open TextEdit, type 'Hello World', then close without saving",
        tags=["smoke", "type", "app-launch"],
        expected_app="TextEdit",
        timeout_s=30,
        verify_hint="TextEdit window is closed and no save dialog remains; desktop is clean.",
    ),
    BenchmarkTask(
        id="smoke-safari-url",
        description="Open Safari and navigate to https://example.com",
        tags=["smoke", "browser", "navigation"],
        expected_app="Safari",
        timeout_s=40,
        verify_hint="Safari is frontmost and the address bar shows example.com loaded.",
    ),

    # ── App interaction ──
    BenchmarkTask(
        id="app-finder-new-folder",
        description="Open Finder, create a new folder on the Desktop called 'houdini-benchmark-test', then delete it",
        tags=["app", "finder", "file-ops"],
        expected_app="Finder",
        timeout_s=60,
        verify_hint="Finder is active and no folder named 'houdini-benchmark-test' remains on the Desktop.",
    ),
    BenchmarkTask(
        id="app-notes-create",
        description="Open Notes, create a new note with the text 'Benchmark test note', then delete it",
        tags=["app", "notes"],
        expected_app="Notes",
        timeout_s=60,
        verify_hint="Notes app is open and no note titled 'Benchmark test note' remains in the list.",
    ),

    # ── Vision-heavy tasks ──
    BenchmarkTask(
        id="vision-settings-wifi",
        description="Open System Settings and navigate to Wi-Fi",
        tags=["vision", "settings", "navigation"],
        expected_app="System Settings",
        timeout_s=60,
        verify_hint="System Settings window shows the Wi-Fi settings pane with Wi-Fi options visible.",
    ),
    BenchmarkTask(
        id="vision-safari-search",
        description="Open Safari, search Google for 'Houdini agent benchmark', and wait for results",
        tags=["vision", "browser", "search"],
        expected_app="Safari",
        timeout_s=60,
        verify_hint="Safari shows a Google search results page for the query 'Houdini agent benchmark'.",
    ),

    # ── Multi-step orchestration ──
    BenchmarkTask(
        id="multi-copy-paste",
        description="Open TextEdit, type 'benchmark payload', select all, copy, open a second TextEdit window, paste, then close both windows without saving",
        tags=["multi-step", "clipboard"],
        expected_app="TextEdit",
        timeout_s=90,
        verify_hint="No TextEdit windows remain open and no save dialogs are present.",
    ),
    BenchmarkTask(
        id="multi-screenshot",
        description="Take a screenshot using Cmd+Shift+3, wait 2 seconds, then open the screenshot in Preview from the Desktop",
        tags=["multi-step", "screenshot"],
        expected_app="Preview",
        timeout_s=60,
        verify_hint="Preview app is frontmost displaying a screenshot image.",
    ),

    # ── Browser-only tasks ──
    BenchmarkTask(
        id="browser-example-com",
        description="Open the browser and navigate to https://example.com",
        tags=["browser", "navigation"],
        expected_app=None,
        timeout_s=30,
        verify_hint="The browser page shows example.com with the 'Example Domain' heading visible.",
    ),
    BenchmarkTask(
        id="browser-search-houdini",
        description="Search Google for 'Houdini agent benchmark' and return the first result title",
        tags=["browser", "search"],
        expected_app=None,
        timeout_s=60,
        verify_hint="The browser shows Google search results for 'Houdini agent benchmark'.",
    ),
    BenchmarkTask(
        id="browser-form-fill",
        description="Open https://httpbin.org/forms/post and fill in the customer name field with 'Houdini'",
        tags=["browser", "form"],
        expected_app=None,
        timeout_s=45,
        verify_hint="The form on httpbin.org has the customer name field filled with 'Houdini'.",
    ),

    # ── Edge-case / robustness ──
    BenchmarkTask(
        id="edge-nonexistent-app",
        description="Open an application called 'ThisAppDoesNotExist123'",
        tags=["edge", "negative"],
        expected_app=None,
        timeout_s=20,
        verify_hint="The agent reports failure or an error dialog appears because the app does not exist.",
    ),
]


# ── Result structures ────────────────────────────────────────────────

@dataclass
class TaskResult:
    task_id: str
    description: str
    tags: List[str]
    success: bool
    error: Optional[str] = None
    duration_s: float = 0.0
    vision_strategy: Optional[str] = None
    confidence_scores: List[float] = field(default_factory=list)
    avg_confidence: float = 0.0
    judge_score: Optional[float] = None
    judge_reason: Optional[str] = None


@dataclass
class BenchmarkReport:
    run_id: str
    started_at: str
    completed_at: str = ""
    total_tasks: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    success_rate: float = 0.0
    avg_duration_s: float = 0.0
    median_duration_s: float = 0.0
    avg_confidence: float = 0.0
    results: List[Dict[str, Any]] = field(default_factory=list)
    tag_breakdown: Dict[str, Dict[str, Any]] = field(default_factory=dict)


# ── Benchmark runner ─────────────────────────────────────────────────

class BenchmarkRunner:
    def __init__(
        self,
        tasks: List[BenchmarkTask],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        architecture: str = "adaptive",
        cloud_endpoint: Optional[str] = None,
        verify_with_llm: bool = False,
        generate_skills_on_failure: bool = False,
    ):
        self.tasks = tasks
        self.provider = provider
        self.model = model
        self.architecture = architecture
        self.cloud_endpoint = cloud_endpoint
        self.verify_with_llm = verify_with_llm
        self.generate_skills_on_failure = generate_skills_on_failure

    def run(self, dry_run: bool = False) -> BenchmarkReport:
        import uuid
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        report = BenchmarkReport(
            run_id=run_id,
            started_at=datetime.now().isoformat(),
            total_tasks=len(self.tasks),
        )

        if dry_run:
            for t in self.tasks:
                report.results.append(asdict(TaskResult(
                    task_id=t.id, description=t.description, tags=t.tags,
                    success=False, error="dry-run",
                )))
                report.skipped += 1
            report.completed_at = datetime.now().isoformat()
            return report

        # Collect confidence scores from event bus
        confidence_scores: List[float] = []
        task_confidences: List[float] = []
        try:
            from src.utils.event_bus import event_bus
            def _on_conf(payload):
                s = payload.get("score")
                if s is not None:
                    task_confidences.append(float(s))
            event_bus.subscribe("confidence", _on_conf)
        except ImportError:
            event_bus = None

        for task in self.tasks:
            logger.info(f"\n{'='*60}")
            logger.info(f"BENCHMARK [{task.id}]: {task.description}")
            logger.info(f"{'='*60}")

            task_confidences.clear()
            result = self._run_single(task)

            # Attach captured confidences
            result.confidence_scores = list(task_confidences)
            if result.confidence_scores:
                result.avg_confidence = statistics.mean(result.confidence_scores)
            confidence_scores.extend(task_confidences)

            report.results.append(asdict(result))
            if result.success:
                report.passed += 1
            else:
                report.failed += 1
                if self.generate_skills_on_failure:
                    try:
                        self._generate_skill_from_failure(task, result)
                    except Exception as exc:
                        logger.warning(f"Could not generate skill for {task.id}: {exc}")

            logger.info(
                f"  → {'PASS' if result.success else 'FAIL'} "
                f"({result.duration_s:.1f}s, avg-conf={result.avg_confidence:.1f})"
            )

        # Unsubscribe
        if event_bus:
            try:
                event_bus.unsubscribe("confidence", _on_conf)
            except Exception:
                pass

        # Aggregate
        durations = [r["duration_s"] for r in report.results if r["success"]]
        report.success_rate = (report.passed / report.total_tasks * 100) if report.total_tasks else 0
        report.avg_duration_s = statistics.mean(durations) if durations else 0
        report.median_duration_s = statistics.median(durations) if durations else 0
        report.avg_confidence = statistics.mean(confidence_scores) if confidence_scores else 0
        report.completed_at = datetime.now().isoformat()
        report.tag_breakdown = self._compute_tag_breakdown(report.results)
        return report

    def _generate_skill_from_failure(self, task: BenchmarkTask, result: TaskResult) -> None:
        """Generate a skill from a failed benchmark result to improve future runs."""
        from src.skills.generator import generate_skill_from_failure

        error = result.error or "Task failed"
        generated = generate_skill_from_failure(
            task=task.description,
            error=error,
        )
        logger.info(
            f"  📝 Generated skill '{generated['skill_id']}' saved to {generated.get('path')}"
        )

    # ── Single task execution ────────────────────────────────────

    def _run_single(self, task: BenchmarkTask) -> TaskResult:
        from src.providers.registry import registry, get_default_provider

        start = time.time()
        try:
            provider_id = self.provider or os.environ.get("HOUDINI_DEFAULT_PROVIDER") or get_default_provider() or "ollama"
            # If provider looks like a model alias rather than a provider id,
            # fall back to auto-detected default provider.
            if "/" not in provider_id and provider_id not in registry.list_providers():
                provider_id = get_default_provider() or "ollama"

            client = registry.create(provider_id, model_name=self.model)

            if self.architecture == "langgraph":
                from src.loop.langgraph_coordinator import LangGraphCoordinator
                coordinator = LangGraphCoordinator(client=client, enable_thinking_window=False)
            elif self.architecture == "legacy":
                from src.loop.loop_coordinator import LoopCoordinator
                from src.planner.ollama_planner import OllamaPlanner
                from src.supervisor.ollama_supervisor import OllamaSupervisor
                coordinator = LoopCoordinator(
                    client=client,
                    planner=OllamaPlanner(client),
                    supervisor=OllamaSupervisor(client),
                    enable_supervisor=True,
                    supervisor_mode="background",
                    enable_thinking_window=False,
                )
            else:
                from src.loop.adaptive_coordinator import AdaptiveLoopCoordinator
                coordinator = AdaptiveLoopCoordinator(client=client, enable_thinking_window=False)

            result = coordinator.execute(task.description)
            duration = time.time() - start

            success = bool(result.get("success", False))
            error = result.get("error")

            # Optional LLM judge: verify the task outcome by asking a separate model.
            judge_score = None
            judge_reason = None
            if self.verify_with_llm and success and task.verify_hint:
                try:
                    judge_score, judge_reason = self._llm_judge(task, client)
                    # Override success if the judge strongly disagrees.
                    if judge_score is not None and judge_score < 0.5:
                        success = False
                        error = (error or "") + f" [LLM judge rejected: {judge_reason}]"
                except Exception as exc:
                    logger.warning(f"LLM judge failed for {task.id}: {exc}")

            return TaskResult(
                task_id=task.id,
                description=task.description,
                tags=task.tags,
                success=success,
                error=error,
                duration_s=round(duration, 2),
                vision_strategy=result.get("vision_strategy"),
                judge_score=judge_score,
                judge_reason=judge_reason,
            )
        except Exception as exc:
            return TaskResult(
                task_id=task.id,
                description=task.description,
                tags=task.tags,
                success=False,
                error=str(exc),
                duration_s=round(time.time() - start, 2),
            )

    def _llm_judge(self, task: BenchmarkTask, client) -> tuple:
        """Ask the configured provider whether the task outcome matches the intent.

        Returns a score in [0, 1] and a short reason. Uses a screenshot when the
        provider adapter supports image input.
        """
        from src.vision.screen_capture import capture_screen

        prompt = (
            f"You are evaluating whether a desktop automation task succeeded.\n\n"
            f"Task: {task.description}\n"
            f"Expected outcome hint: {task.verify_hint or 'No explicit hint'}\n\n"
            f"Look at the current screenshot and reply with STRICT JSON only:\n"
            f'{{"score": <float 0.0-1.0>, "reason": "<one sentence>"}}'
        )

        image = None
        try:
            image = capture_screen()
        except Exception as exc:
            logger.warning(f"Could not capture screenshot for judge: {exc}")

        if image is not None and hasattr(client, "generate"):
            raw = client.generate(prompt, images=[image])
        else:
            raw = client.generate(prompt)

        text = raw.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = text[:-3].strip()
        parsed = json.loads(text)
        score = float(parsed.get("score", 0.0))
        reason = str(parsed.get("reason", ""))
        return score, reason

    # ── Tag breakdown ────────────────────────────────────────────

    @staticmethod
    def _compute_tag_breakdown(results: List[Dict]) -> Dict[str, Dict[str, Any]]:
        tags: Dict[str, List[Dict]] = {}
        for r in results:
            for tag in r.get("tags", []):
                tags.setdefault(tag, []).append(r)
        breakdown = {}
        for tag, items in sorted(tags.items()):
            passed = sum(1 for i in items if i["success"])
            durations = [i["duration_s"] for i in items if i["success"]]
            breakdown[tag] = {
                "total": len(items),
                "passed": passed,
                "success_rate": round(passed / len(items) * 100, 1) if items else 0,
                "avg_duration_s": round(statistics.mean(durations), 2) if durations else 0,
            }
        return breakdown


# ── CLI ──────────────────────────────────────────────────────────────

def _print_report(report: BenchmarkReport):
    print(f"\n{'='*60}")
    print(f"  BENCHMARK REPORT  —  {report.run_id}")
    print(f"{'='*60}")
    print(f"  Total tasks     : {report.total_tasks}")
    print(f"  Passed          : {report.passed}")
    print(f"  Failed          : {report.failed}")
    print(f"  Skipped         : {report.skipped}")
    print(f"  Success rate    : {report.success_rate:.1f}%")
    print(f"  Avg duration    : {report.avg_duration_s:.1f}s")
    print(f"  Median duration : {report.median_duration_s:.1f}s")
    print(f"  Avg confidence  : {report.avg_confidence:.1f}/10")
    print()

    if report.tag_breakdown:
        print("  Tag breakdown:")
        for tag, info in report.tag_breakdown.items():
            print(f"    {tag:20s}  {info['passed']}/{info['total']} "
                  f"({info['success_rate']}%)  avg {info['avg_duration_s']:.1f}s")
        print()

    for r in report.results:
        status = "PASS" if r["success"] else "FAIL"
        err = f"  [{r['error'][:50]}]" if r.get("error") and not r["success"] else ""
        print(f"  [{status}] {r['task_id']:30s} {r['duration_s']:6.1f}s  conf={r.get('avg_confidence',0):.1f}{err}")

    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Houdini Agent Benchmark Suite")
    parser.add_argument("--tag", type=str, default=None, help="Only run tasks with this tag")
    parser.add_argument("--task-id", type=str, default=None, help="Run a single task by ID")
    parser.add_argument("--dry-run", action="store_true", help="List tasks without executing")
    parser.add_argument("--provider", type=str, default=None,
                        help="Provider id (openai, anthropic, gemini, ollama, ...)")
    parser.add_argument("--model", type=str, default=None, help="Model name/alias")
    parser.add_argument("--architecture", type=str, default="adaptive",
                        choices=["adaptive", "langgraph", "legacy"])
    parser.add_argument("--cloud-endpoint", type=str, default=None)
    parser.add_argument("--verify-with-llm", action="store_true",
                        help="Use an LLM judge with screenshots to verify task outcomes")
    parser.add_argument("--generate-skills-on-failure", action="store_true",
                        help="Generate a skill from each failed task to improve future runs")
    parser.add_argument("--output", type=str, default=None,
                        help="Write JSON report to this file")
    parser.add_argument("--tasks-file", type=str, default=None,
                        help="Load tasks from a JSON file instead of built-in set")
    args = parser.parse_args()

    # Load tasks
    if args.tasks_file:
        with open(args.tasks_file) as f:
            raw = json.load(f)
        tasks = [BenchmarkTask(**t) for t in raw]
    else:
        tasks = list(BENCHMARK_TASKS)

    # Filter
    if args.tag:
        tasks = [t for t in tasks if args.tag in t.tags]
    if args.task_id:
        tasks = [t for t in tasks if t.id == args.task_id]

    if not tasks:
        print("No matching tasks found.")
        sys.exit(1)

    runner = BenchmarkRunner(
        tasks=tasks,
        provider=args.provider,
        model=args.model,
        architecture=args.architecture,
        cloud_endpoint=args.cloud_endpoint,
        verify_with_llm=args.verify_with_llm,
        generate_skills_on_failure=args.generate_skills_on_failure,
    )

    report = runner.run(dry_run=args.dry_run)
    _print_report(report)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(asdict(report), f, indent=2, default=str)
        print(f"Report saved to {out_path}")


if __name__ == "__main__":
    main()
