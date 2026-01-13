"""
LoopCoordinator - Manages both ExecutorLoop and SupervisorLoop together.
Handles initialization, coordination, and cleanup.
"""

import time
from datetime import datetime
from typing import Dict, Optional, Callable

from .loop_state import LoopState, LoopStatus
from .executor_loop import ExecutorLoop
from .supervisor_loop import SupervisorLoop
from ..utils.logging import logger
from ..utils.gemini_client import GeminiCLI
from ..planner.gemini_planner import GeminiPlanner


class LoopCoordinator:
    """
    Coordinates the ExecutorLoop and SupervisorLoop.
    
    Workflow:
    1. Plan task using GeminiPlanner
    2. Initialize shared LoopState
    3. Start SupervisorLoop in background (optional)
    4. Run ExecutorLoop in main thread
    5. Handle completion and cleanup
    """
    
    def __init__(self, 
                 cli: GeminiCLI,
                 planner: GeminiPlanner,
                 enable_supervisor: bool = True,
                 supervisor_mode: str = "background",  # "background" or "checkpoint"
                 vision_handler: Optional[Callable] = None):
        """
        Args:
            cli: Gemini client for LLM calls
            planner: Task planner
            enable_supervisor: Whether to run supervisor
            supervisor_mode: "background" (parallel) or "checkpoint" (after batches)
            vision_handler: Callback for vision actions
        """
        self.cli = cli
        self.planner = planner
        self.enable_supervisor = enable_supervisor
        self.supervisor_mode = supervisor_mode
        self.vision_handler = vision_handler
        
        # Components (created per-task)
        self.state: Optional[LoopState] = None
        self.executor_loop: Optional[ExecutorLoop] = None
        self.supervisor_loop: Optional[SupervisorLoop] = None
    
    def execute(self, task: str) -> Dict:
        """
        Execute a task using the loop system.
        
        Args:
            task: Natural language task description
            
        Returns:
            Execution summary dict
        """
        start_time = time.time()
        
        logger.info(f"🎯 LoopCoordinator starting task: {task}")
        
        try:
            # 1. Generate plan
            logger.info("📋 Generating execution plan...")
            batches = self.planner.plan(task)
            
            if not batches:
                logger.error("❌ No batches generated")
                return {"success": False, "error": "Planning failed"}
            
            logger.info(f"   Plan has {len(batches)} batches")
            for i, b in enumerate(batches):
                btype = b.get("type", "?").upper()
                desc = b.get("description", "...")[:50]
                logger.info(f"   {i+1}. [{btype}] {desc}")
            
            # 2. Initialize shared state
            self.state = LoopState(
                task_description=task,
                batches=batches
            )
            
            # 3. Create vision handler wrapper
            vision_callback = self._create_vision_handler()
            
            # 4. Create loops
            self.executor_loop = ExecutorLoop(
                state=self.state,
                on_vision_needed=vision_callback,
                action_delay=0.1
            )
            
            if self.enable_supervisor:
                self.supervisor_loop = SupervisorLoop(
                    state=self.state,
                    check_interval=0.5
                )
            
            # 5. Start supervisor if background mode
            if self.enable_supervisor and self.supervisor_mode == "background":
                self.supervisor_loop.start_background()
            
            # 6. Run executor (blocking)
            logger.info("\n" + "="*50)
            logger.info("🚀 Starting execution loop")
            logger.info("="*50 + "\n")
            
            result = self.executor_loop.run()
            
            # 7. Stop supervisor
            if self.supervisor_loop:
                self.supervisor_loop.stop()
            
            # 8. Generate final report
            elapsed = time.time() - start_time
            
            logger.info("\n" + "="*50)
            logger.info("📊 Execution Complete")
            logger.info("="*50)
            logger.info(f"   Status: {result['status']}")
            logger.info(f"   Time: {elapsed:.1f}s")
            logger.info(f"   Actions: {result['actions_successful']}/{result['actions_total']} successful")
            logger.info(f"   Batches: {result['batches_completed']}/{result['batches_total']} completed")
            if result['interventions'] > 0:
                logger.info(f"   Interventions: {result['interventions']}")
            
            return {
                "success": result["status"] == "completed",
                "summary": result,
                "elapsed": elapsed,
                "context": self.state.get_context_prompt() if self.state else None
            }
            
        except Exception as e:
            logger.error(f"❌ Coordinator error: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
        
        finally:
            self._cleanup()
    
    def _create_vision_handler(self) -> Callable:
        """Create vision action handler."""
        if self.vision_handler:
            return self.vision_handler
        
        # Default: use vision executor
        def default_vision_handler(action_description: str) -> Dict:
            try:
                from ..agents.vision_executor import execute_vision_action
                return execute_vision_action(self.cli, action_description, max_attempts=3)
            except Exception as e:
                logger.error(f"Vision handler error: {e}")
                return {"success": False, "error": str(e)}
        
        return default_vision_handler
    
    def _cleanup(self):
        """Cleanup after execution."""
        if self.supervisor_loop and self.supervisor_loop.running:
            self.supervisor_loop.stop()
        
        # Log final state context (for debugging)
        if self.state:
            logger.debug(f"\nFinal state:\n{self.state.get_context_prompt()}")
    
    def get_state_context(self) -> str:
        """Get current state context for external use."""
        if self.state:
            return self.state.get_context_prompt()
        return "No active state"
    
    def pause(self, reason: str = "Manual pause"):
        """Pause execution."""
        if self.executor_loop:
            self.executor_loop.pause(reason)
    
    def resume(self):
        """Resume execution."""
        if self.executor_loop:
            self.executor_loop.resume()
    
    def stop(self):
        """Stop execution completely."""
        if self.executor_loop:
            self.executor_loop.stop()
        if self.supervisor_loop:
            self.supervisor_loop.stop()


def run_with_loop(task: str, 
                  model: str = "gemini-2.5-pro",
                  enable_supervisor: bool = True,
                  supervisor_mode: str = "background") -> Dict:
    """
    Convenience function to run a task with the loop system.
    
    Args:
        task: Natural language task description
        model: Gemini model to use
        enable_supervisor: Whether to enable supervisor monitoring
        supervisor_mode: "background" or "checkpoint"
    
    Returns:
        Execution result dict
    """
    cli = GeminiCLI(model_name=model)
    planner = GeminiPlanner(cli)
    
    coordinator = LoopCoordinator(
        cli=cli,
        planner=planner,
        enable_supervisor=enable_supervisor,
        supervisor_mode=supervisor_mode
    )
    
    return coordinator.execute(task)
