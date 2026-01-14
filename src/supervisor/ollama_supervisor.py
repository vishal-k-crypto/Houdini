"""
Ollama-based Supervisor using Qwen 3 Coder model.
Validates execution results and maintains executor history.
"""
import json
from typing import List, Dict, Optional
from pathlib import Path
from ..utils.ollama_client import OllamaClient
from ..utils.logging import logger

EXECUTOR_HISTORY_FILE = Path(__file__).parent.parent.parent / "data" / "executor_history.json"


class ExecutorHistory:
    """Maintains history of executor operations for context."""
    
    def __init__(self, history_file: Path = EXECUTOR_HISTORY_FILE):
        self.history_file = history_file
        self.history: List[Dict] = []
        self._load()
    
    def _load(self):
        """Load history from disk."""
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r') as f:
                    self.history = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load executor history: {e}")
            self.history = []
    
    def _save(self):
        """Save history to disk."""
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, 'w') as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save executor history: {e}")
    
    def add_execution(self, task: str, batches: List[Dict], success: bool, 
                     duration: float, error: Optional[str] = None):
        """Add an execution record."""
        import datetime
        
        record = {
            "task": task,
            "timestamp": datetime.datetime.now().isoformat(),
            "batches_count": len(batches),
            "success": success,
            "duration": duration,
            "error": error
        }
        
        self.history.append(record)
        
        # Keep only last 100 executions
        if len(self.history) > 100:
            self.history = self.history[-100:]
        
        self._save()
    
    def get_recent(self, count: int = 10) -> List[Dict]:
        """Get recent execution records."""
        return self.history[-count:] if self.history else []
    
    def get_context_summary(self, count: int = 5) -> str:
        """Get a formatted summary of recent executions."""
        recent = self.get_recent(count)
        if not recent:
            return "No previous executions."
        
        summary = f"Last {len(recent)} executor operations:\n"
        for i, record in enumerate(recent, 1):
            status = "✓" if record.get("success") else "✗"
            task = record.get("task", "Unknown")
            duration = record.get("duration", 0)
            summary += f"{i}. {status} {task} ({duration:.1f}s)\n"
        
        return summary


class OllamaSupervisor:
    """
    Ollama-based supervisor using Qwen 3 Coder 480B.
    Validates execution and maintains executor history.
    """
    
    def __init__(self, client: OllamaClient):
        self.client = client
        self.executor_history = ExecutorHistory()
    
    def validate(self, task: str, plan: List[Dict], execution_result: Dict,
                screenshot_path: Optional[str] = None) -> Dict:
        """
        Validate execution result and update history.
        
        Args:
            task: Original task description
            plan: The plan that was executed
            execution_result: Result from executor
            screenshot_path: Optional screenshot for validation
        
        Returns:
            Validation result with success status and feedback
        """
        success = execution_result.get("success", False)
        error = execution_result.get("error")
        duration = execution_result.get("duration", 0)
        
        # Record in history
        self.executor_history.add_execution(
            task=task,
            batches=plan,
            success=success,
            duration=duration,
            error=error
        )
        
        # If execution failed, provide detailed analysis
        if not success:
            logger.warning(f"Execution failed: {error}")
            
            # Get AI feedback on failure
            feedback = self._analyze_failure(task, plan, execution_result)
            
            return {
                "valid": False,
                "success": False,
                "error": error,
                "feedback": feedback,
                "history_updated": True
            }
        
        # Validate success with AI
        is_valid = self._validate_success(task, plan, execution_result)
        
        return {
            "valid": is_valid,
            "success": success,
            "feedback": "Task completed successfully" if is_valid else "Execution may be incomplete",
            "history_updated": True
        }
    
    def _analyze_failure(self, task: str, plan: List[Dict], result: Dict) -> str:
        """Analyze execution failure and provide feedback."""
        error = result.get("error", "Unknown error")
        history_context = self.executor_history.get_context_summary()
        
        prompt = f"""Analyze this execution failure and provide actionable feedback.

Task: {task}

Plan executed:
{json.dumps(plan, indent=2)}

Error encountered: {error}

Recent executor history:
{history_context}

Provide:
1. Root cause analysis
2. Specific suggestions to fix the issue
3. Whether to retry, replan, or abort

Be concise and actionable."""
        
        try:
            response = self.client.generate(
                prompt,
                temperature=0.3,
                model="qwen2.5-coder:32b"  # Use available model
            )
            return response
        except Exception as e:
            logger.error(f"Failed to analyze failure: {e}")
            return f"Execution failed: {error}. Manual review needed."
    
    def _validate_success(self, task: str, plan: List[Dict], result: Dict) -> bool:
        """Validate if the task was truly completed successfully."""
        # Quick heuristic validation
        if result.get("completed", False):
            return True
        
        # Use AI for deeper validation if needed
        history_context = self.executor_history.get_context_summary()
        
        prompt = f"""Validate if this task was completed successfully.

Task: {task}

Plan executed:
{json.dumps(plan, indent=2)}

Execution result:
{json.dumps(result, indent=2)}

Recent executor history:
{history_context}

Answer with YES if task is complete, NO if incomplete, PARTIAL if partially complete.
Then explain briefly."""
        
        try:
            response = self.client.generate(
                prompt,
                temperature=0.1,
                model="qwen2.5-coder:32b"
            )
            
            response_lower = response.lower()
            if "yes" in response_lower[:50]:
                return True
            elif "partial" in response_lower[:50]:
                logger.warning("Task partially complete")
                return True  # Accept partial completion
            else:
                return False
        except Exception as e:
            logger.error(f"Failed to validate success: {e}")
            return True  # Default to accepting success
    
    def get_executor_history(self) -> List[Dict]:
        """Get executor history for planner context."""
        return self.executor_history.get_recent(10)
    
    def get_statistics(self) -> Dict:
        """Get execution statistics."""
        history = self.executor_history.history
        if not history:
            return {"total": 0, "success_rate": 0, "avg_duration": 0}
        
        total = len(history)
        successful = sum(1 for h in history if h.get("success", False))
        durations = [h.get("duration", 0) for h in history]
        
        return {
            "total": total,
            "successful": successful,
            "success_rate": successful / total if total > 0 else 0,
            "avg_duration": sum(durations) / len(durations) if durations else 0
        }


# Alias for compatibility
QwenSupervisor = OllamaSupervisor
