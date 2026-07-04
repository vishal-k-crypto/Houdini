"""
Prompt Evolution System - Automatically improve prompts based on failures and learnings.

This system tracks execution patterns, analyzes failures, and evolves the internal
prompts for Planner, Executor, and Supervisor to improve performance over time.
"""

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from .logging import logger

# Lazy import to avoid circular dependency
_lesson_store = None

def _get_lesson_store():
    """Get the lesson store instance (lazy loading to avoid circular imports)."""
    global _lesson_store
    if _lesson_store is None:
        from .lesson_store import lesson_store
        _lesson_store = lesson_store
    return _lesson_store

PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
EVOLUTION_LOG = Path(__file__).parent.parent.parent / "data" / "prompt_evolution_log.json"
FEEDBACK_LOG = Path(__file__).parent.parent.parent / "data" / "feedback_log.json"


class PromptEvolution:
    """
    Manages prompt evolution based on task execution feedback.
    
    Features:
    - Tracks failures and successes
    - Analyzes patterns in failures
    - Generates prompt improvements
    - Manages prompt versioning
    - A/B testing of prompt variations
    """
    
    def __init__(self):
        self.prompts_dir = PROMPTS_DIR
        self.evolution_log_path = EVOLUTION_LOG
        self.feedback_log_path = FEEDBACK_LOG
        
        # Ensure directories exist
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        self.evolution_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.evolution_history = self._load_evolution_history()
        self.feedback_data = self._load_feedback_data()
        # NEW: A/B variant registry
        self.variant_registry = self._load_variant_registry()
    
    def _load_evolution_history(self) -> List[Dict]:
        """Load prompt evolution history."""
        try:
            if self.evolution_log_path.exists():
                with open(self.evolution_log_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load evolution history: {e}")
        return []
    
    def _save_evolution_history(self):
        """Save prompt evolution history."""
        try:
            with open(self.evolution_log_path, 'w') as f:
                json.dump(self.evolution_history, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save evolution history: {e}")
    
    def _load_feedback_data(self) -> List[Dict]:
        """Load feedback from task executions."""
        try:
            if self.feedback_log_path.exists():
                with open(self.feedback_log_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load feedback data: {e}")
        return []
    
    def _save_feedback_data(self):
        """Save feedback data."""
        try:
            with open(self.feedback_log_path, 'w') as f:
                json.dump(self.feedback_data, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save feedback data: {e}")
    
    def record_feedback(
        self,
        component: str,  # "planner", "executor", "supervisor"
        task: str,
        success: bool,
        error_type: Optional[str] = None,
        error_details: Optional[str] = None,
        execution_time: Optional[float] = None,
        actions_taken: Optional[List[str]] = None,
        suggestion: Optional[str] = None
    ):
        """
        Record feedback from a task execution.
        
        Args:
            component: Which component (planner/executor/supervisor)
            task: The task description
            success: Whether execution succeeded
            error_type: Category of error (if failed)
            error_details: Detailed error information
            execution_time: Time taken to execute
            actions_taken: List of actions executed
            suggestion: Suggested improvement
        """
        feedback_entry = {
            "timestamp": datetime.now().isoformat(),
            "component": component,
            "task": task,
            "success": success,
            "error_type": error_type,
            "error_details": error_details,
            "execution_time": execution_time,
            "actions_taken": actions_taken,
            "suggestion": suggestion
        }
        
        self.feedback_data.append(feedback_entry)
        self._save_feedback_data()
        
        # Trigger evolution if we have enough failures
        if not success:
            self._check_evolution_trigger(component, error_type)
    
    def _check_evolution_trigger(self, component: str, error_type: Optional[str]):
        """Check if we should trigger prompt evolution."""
        # Count recent failures for this component
        recent_failures = [
            f for f in self.feedback_data[-100:]  # Last 100 executions
            if f["component"] == component and not f["success"]
        ]
        
        # Trigger evolution if >20% failure rate
        if len(recent_failures) >= 5:
            recent_total = len([f for f in self.feedback_data[-100:] if f["component"] == component])
            failure_rate = len(recent_failures) / max(recent_total, 1)
            
            if failure_rate > 0.2:
                logger.warning(f"⚠️ High failure rate for {component}: {failure_rate:.1%}")
                logger.info(f"🧬 Triggering prompt evolution for {component}")
                self.evolve_prompt(component, recent_failures)
    
    def analyze_failures(self, component: str, failures: List[Dict]) -> Dict[str, Any]:
        """Analyze failure patterns to generate insights."""
        if not failures:
            return {}
        
        analysis = {
            "total_failures": len(failures),
            "error_types": {},
            "common_tasks": {},
            "timing_issues": [],
            "patterns": []
        }
        
        # Categorize errors
        for failure in failures:
            error_type = failure.get("error_type", "unknown")
            analysis["error_types"][error_type] = analysis["error_types"].get(error_type, 0) + 1
            
            # Track common failing tasks
            task = failure.get("task", "")[:50]  # Truncate
            analysis["common_tasks"][task] = analysis["common_tasks"].get(task, 0) + 1
            
            # Identify timing issues
            if "timeout" in str(failure.get("error_details", "")).lower():
                analysis["timing_issues"].append(failure)
        
        # Identify patterns
        if analysis["error_types"].get("element_not_found", 0) > 3:
            analysis["patterns"].append("frequent_element_not_found")
        
        if len(analysis["timing_issues"]) > 3:
            analysis["patterns"].append("timing_issues")
        
        if analysis["error_types"].get("invalid_action", 0) > 2:
            analysis["patterns"].append("action_format_issues")
        
        return analysis
    
    def generate_prompt_improvement(self, component: str, analysis: Dict) -> Optional[str]:
        """
        Generate a prompt improvement section based on failure analysis.
        
        Returns:
            A markdown section to append to the prompt, or None if no improvement needed.
        """
        if not analysis.get("patterns"):
            return None
        
        improvements = []
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        improvements.append(f"\n\n## Evolution Update - {timestamp}\n")
        improvements.append(f"**Failure Analysis**: {analysis['total_failures']} failures analyzed\n")
        
        patterns = analysis.get("patterns", [])
        
        # Pattern-specific improvements
        if "frequent_element_not_found" in patterns:
            improvements.append("\n### Learned Pattern: Element Not Found Issues\n")
            improvements.append("**Observation**: High rate of element not found errors.\n")
            improvements.append("**Improvement**:\n")
            if component == "planner":
                improvements.append("- Add more wait time before vision actions\n")
                improvements.append("- Use more specific element descriptions\n")
                improvements.append("- Consider adding retry logic to plans\n")
            elif component == "executor":
                improvements.append("- Retry element lookup with broader search criteria\n")
                improvements.append("- Wait for page/UI stabilization before searching\n")
                improvements.append("- Use fallback selectors (role, label, position)\n")
        
        if "timing_issues" in patterns:
            improvements.append("\n### Learned Pattern: Timing Issues\n")
            improvements.append("**Observation**: Multiple timeout/premature action errors.\n")
            improvements.append("**Improvement**:\n")
            if component == "planner":
                improvements.append("- Increase default wait times by 50%\n")
                improvements.append("- Add explicit wait steps after state changes\n")
                improvements.append("- Consider application/network latency\n")
            elif component == "executor":
                improvements.append("- Implement adaptive wait times\n")
                improvements.append("- Poll for element availability instead of fixed waits\n")
                improvements.append("- Add timeout safeguards (max 10s)\n")
        
        if "action_format_issues" in patterns:
            improvements.append("\n### Learned Pattern: Action Format Issues\n")
            improvements.append("**Observation**: Invalid action formats being generated.\n")
            improvements.append("**Improvement**:\n")
            if component == "planner":
                improvements.append("- Strictly follow action format specifications\n")
                improvements.append("- Validate action format before including in plan\n")
                improvements.append("- Use examples from documentation\n")
        
        # Add most common errors
        if analysis.get("error_types"):
            top_errors = sorted(analysis["error_types"].items(), key=lambda x: x[1], reverse=True)[:3]
            improvements.append(f"\n**Top Error Types**: {', '.join([f'{e[0]} ({e[1]}x)' for e in top_errors])}\n")
        
        return "".join(improvements)
    
    def evolve_prompt(self, component: str, recent_failures: List[Dict]):
        """
        Evolve a component's prompt based on failure analysis.
        
        NEW: Instead of appending markdown to prompt files (causing context bloat),
        we now store failures as lessons in the LessonStore vector database.
        These are retrieved via RAG when needed, keeping prompts lean.
        
        Args:
            component: "planner", "executor", or "supervisor"
            recent_failures: List of recent failure feedback entries
        """
        # Get lesson store
        lesson_store = _get_lesson_store()
        
        # Analyze failures for insights
        analysis = self.analyze_failures(component, recent_failures)
        
        if not analysis.get("patterns"):
            logger.info(f"No patterns detected for {component}")
            return
        
        # Store each failure as a lesson in the vector database
        lessons_added = 0
        for failure in recent_failures:
            error_type = failure.get("error_type", "unknown")
            error_details = failure.get("error_details", "")
            task = failure.get("task", "")
            suggestion = failure.get("suggestion")
            
            # Generate solution based on patterns detected
            if not suggestion:
                suggestion = self._generate_solution_from_analysis(component, analysis, error_type)
            
            # Record in lesson store
            lesson = lesson_store.record_failure(
                component=component,
                task=task,
                error_type=error_type,
                error_details=error_details,
                suggestion=suggestion
            )
            
            if lesson:
                lessons_added += 1
        
        # Record evolution in history
        evolution_entry = {
            "timestamp": datetime.now().isoformat(),
            "component": component,
            "analysis": analysis,
            "lessons_added": lessons_added,
            "failure_count": len(recent_failures),
            "method": "lesson_store"  # New field to indicate RAG-based storage
        }
        self.evolution_history.append(evolution_entry)
        self._save_evolution_history()
        
        logger.info(f"✨ Stored {lessons_added} lessons for {component} in vector DB")
        logger.info(f"📚 Lessons will be retrieved via RAG when similar tasks are planned")
    
    def _generate_solution_from_analysis(
        self, 
        component: str, 
        analysis: Dict, 
        error_type: str
    ) -> str:
        """
        Generate a solution suggestion based on failure analysis patterns.
        """
        patterns = analysis.get("patterns", [])
        solutions = []
        
        if "frequent_element_not_found" in patterns and error_type == "element_not_found":
            if component == "planner":
                solutions.append("Add more wait time before vision actions")
                solutions.append("Use more specific element descriptions")
            elif component == "executor":
                solutions.append("Retry element lookup with broader search criteria")
                solutions.append("Wait for page/UI stabilization")
        
        if "timing_issues" in patterns and error_type in ("timeout", "timing"):
            if component == "planner":
                solutions.append("Increase default wait times by 50%")
                solutions.append("Add explicit wait steps after state changes")
            elif component == "executor":
                solutions.append("Implement adaptive wait times")
                solutions.append("Poll for element availability instead of fixed waits")
        
        if "action_format_issues" in patterns:
            solutions.append("Strictly follow action format specifications")
            solutions.append("Validate action format before execution")
        
        return "; ".join(solutions) if solutions else f"Investigate and handle: {error_type}"
    
    def get_prompt_version(self, component: str) -> int:
        """Get the current version number of a component's prompt."""
        evolutions = [e for e in self.evolution_history if e["component"] == component]
        return len(evolutions)
    
    def get_recent_learnings(self, component: str, count: int = 5) -> List[Dict]:
        """Get recent evolution learnings for a component."""
        evolutions = [e for e in self.evolution_history if e["component"] == component]
        return evolutions[-count:]

    def reset_prompt(self, component: str):
        """Reset a prompt to its original version (removes all evolutions)."""
        # This would require storing original prompts separately
        # For now, manual restoration is needed
        logger.warning(f"Prompt reset not implemented. Manually restore {component}_prompt.md")

    def get_success_rate(self, component: str, window: int = 100) -> float:
        """Calculate success rate for a component over recent executions."""
        recent = [f for f in self.feedback_data[-window:] if f["component"] == component]
        if not recent:
            return 1.0
        successes = sum(1 for f in recent if f["success"])
        return successes / len(recent)

    # ============================================================
    # A/B MUTATION TRACKING (NEW)
    # ============================================================

    def create_variant(
        self,
        component: str,
        base_prompt: str,
        mutation_name: str,
        mutated_prompt: str,
    ) -> str:
        """
        Register a new A/B prompt variant.

        Returns a variant_id that should be passed to record_feedback so outcomes
        can be attributed to the variant.
        """
        variant_id = self._variant_id(component, mutation_name)
        entry = {
            "variant_id": variant_id,
            "component": component,
            "mutation_name": mutation_name,
            "created_at": datetime.now().isoformat(),
            "base_prompt_hash": self._hash(base_prompt),
            "mutated_prompt_hash": self._hash(mutated_prompt),
        }
        self.variant_registry[variant_id] = entry
        self._save_variant_registry()
        logger.info(f"🧬 Created prompt variant {variant_id} for {component}: {mutation_name}")
        return variant_id

    def _variant_id(self, component: str, mutation_name: str) -> str:
        return hashlib.md5(f"{component}:{mutation_name}".encode()).hexdigest()[:12]

    def _hash(self, text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()[:12]

    def _save_variant_registry(self):
        try:
            self.evolution_log_path.parent.mkdir(parents=True, exist_ok=True)
            path = self.evolution_log_path.parent / "prompt_variant_registry.json"
            with open(path, "w") as f:
                json.dump(list(self.variant_registry.values()), f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save variant registry: {e}")

    def _load_variant_registry(self) -> Dict[str, Dict]:
        try:
            path = self.evolution_log_path.parent / "prompt_variant_registry.json"
            if path.exists():
                with open(path, "r") as f:
                    data = json.load(f)
                return {entry["variant_id"]: entry for entry in data}
        except Exception as e:
            logger.warning(f"Could not load variant registry: {e}")
        return {}

    def record_variant_outcome(
        self,
        variant_id: str,
        success: bool,
        execution_time: Optional[float] = None,
    ):
        """Record the outcome of an execution that used a specific variant."""
        if variant_id not in self.variant_registry:
            logger.debug(f"Unknown variant_id {variant_id}; ignoring outcome")
            return
        entry = self.variant_registry[variant_id]
        if "outcomes" not in entry:
            entry["outcomes"] = []
        entry["outcomes"].append(
            {
                "timestamp": datetime.now().isoformat(),
                "success": success,
                "execution_time": execution_time,
            }
        )
        self._save_variant_registry()

    def get_best_variant(self, component: str) -> Optional[Dict[str, Any]]:
        """Return the variant with the highest empirical success rate for a component."""
        candidates = [
            v for v in self.variant_registry.values() if v["component"] == component
        ]
        if not candidates:
            return None

        def score(variant: Dict) -> float:
            outcomes = variant.get("outcomes", [])
            if not outcomes:
                return 0.0
            successes = sum(1 for o in outcomes if o["success"])
            # Laplace smoothing
            return (successes + 1) / (len(outcomes) + 2)

        best = max(candidates, key=score)
        outcomes = best.get("outcomes", [])
        successes = sum(1 for o in outcomes if o["success"])
        return {
            "variant_id": best["variant_id"],
            "mutation_name": best["mutation_name"],
            "success_rate": successes / max(len(outcomes), 1),
            "smoothed_score": score(best),
            "executions": len(outcomes),
            "successes": successes,
        }

    def get_variant_statistics(self, component: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get performance statistics for all variants, optionally filtered by component."""
        variants = self.variant_registry.values()
        if component:
            variants = [v for v in variants if v["component"] == component]
        stats = []
        for v in variants:
            outcomes = v.get("outcomes", [])
            successes = sum(1 for o in outcomes if o["success"])
            stats.append(
                {
                    "variant_id": v["variant_id"],
                    "component": v["component"],
                    "mutation_name": v["mutation_name"],
                    "executions": len(outcomes),
                    "successes": successes,
                    "success_rate": successes / max(len(outcomes), 1),
                }
            )
        return stats

    # ============================================================
    # LIFECYCLE
    # ============================================================

    def __init__(self):
        self.prompts_dir = PROMPTS_DIR
        self.evolution_log_path = EVOLUTION_LOG
        self.feedback_log_path = FEEDBACK_LOG

        # Ensure directories exist
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        self.evolution_log_path.parent.mkdir(parents=True, exist_ok=True)

        self.evolution_history = self._load_evolution_history()
        self.feedback_data = self._load_feedback_data()
        # NEW: A/B variant registry
        self.variant_registry = self._load_variant_registry()

    def get_statistics(self) -> Dict[str, Any]:
        """Get overall system statistics."""
        stats = {
            "total_executions": len(self.feedback_data),
            "total_evolutions": len(self.evolution_history),
            "components": {},
            "best_variants": {},
        }

        for component in ["planner", "executor", "supervisor"]:
            component_data = [f for f in self.feedback_data if f["component"] == component]
            stats["components"][component] = {
                "executions": len(component_data),
                "success_rate": self.get_success_rate(component),
                "prompt_version": self.get_prompt_version(component),
                "failures": sum(1 for f in component_data if not f["success"])
            }
            best = self.get_best_variant(component)
            if best:
                stats["best_variants"][component] = best

        return stats


# Global instance
prompt_evolution = PromptEvolution()
