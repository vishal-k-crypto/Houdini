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
from ..utils.ollama_client import OllamaClient
from ..planner.ollama_planner import OllamaPlanner
from ..supervisor.ollama_supervisor import OllamaSupervisor
from ..ui.thinking_window import (
    show_planner_thinking,
    show_executor_thinking,
    show_supervisor_thinking,
    show_thinking,
    set_window_status
)


class LoopCoordinator:
    """
    Coordinates the ExecutorLoop and SupervisorLoop.
    
    Workflow:
    1. Plan task using OllamaPlanner with executor history context
    2. Initialize shared LoopState
    3. Start SupervisorLoop in background (optional)
    4. Run ExecutorLoop in main thread
    5. Handle completion and cleanup
    6. Update executor history via supervisor
    """
    
    def __init__(self, 
                 client: OllamaClient,
                 planner: OllamaPlanner,
                 supervisor: OllamaSupervisor,
                 enable_supervisor: bool = True,
                 supervisor_mode: str = "background",  # "background" or "checkpoint"
                 vision_handler: Optional[Callable] = None,
                 enable_thinking_window: bool = True):
        """
        Args:
            client: Ollama client for LLM calls
            planner: Task planner (Ollama-based)
            supervisor: Task supervisor (Ollama-based) with history tracking
            enable_supervisor: Whether to run supervisor
            supervisor_mode: "background" (parallel) or "checkpoint" (after batches)
            vision_handler: Callback for vision actions
            enable_thinking_window: Whether to show thinking window
        """
        self.client = client
        self.planner = planner
        self.supervisor = supervisor
        self.enable_supervisor = enable_supervisor
        self.supervisor_mode = supervisor_mode
        self.vision_handler = vision_handler
        self.enable_thinking_window = enable_thinking_window
        
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
        
        # Update thinking window
        if self.enable_thinking_window:
            set_window_status(f"Planning: {task[:40]}...")
            show_thinking("system", f"Task received: {task}", "info")
        
        try:
            # 1. Get executor history for context
            executor_history = self.supervisor.get_executor_history() if self.enable_supervisor else None
            
            # 2. Generate plan with history context
            logger.info("📋 Generating execution plan with Ollama Qwen 3 Coder...")
            if self.enable_thinking_window:
                show_planner_thinking(f"Analyzing task with executor history: '{task}'")
            batches = self.planner.plan(task, executor_history=executor_history)
            
            if not batches:
                logger.error("❌ No batches generated")
                return {"success": False, "error": "Planning failed"}
            
            logger.info(f"   Plan has {len(batches)} batches")
            if self.enable_thinking_window:
                show_planner_thinking(f"Generated {len(batches)} execution batches")
            for i, b in enumerate(batches):
                btype = b.get("type", "?").upper()
                desc = b.get("description", "...")[:50]
                logger.info(f"   {i+1}. [{btype}] {desc}")
                if self.enable_thinking_window:
                    show_planner_thinking(f"Batch {i+1}: [{btype}] {desc}")
            
            # 2. Initialize shared state
            self.state = LoopState(
                task_description=task,
                batches=batches
            )
            
            # 3. Create vision handler wrapper
            vision_callback = self._create_vision_handler()
            
            # 4. Create loops - pass CLI for recovery handling
            self.executor_loop = ExecutorLoop(
                state=self.state,
                on_vision_needed=vision_callback,
                action_delay=0.1,
                cli=self.cli  # Enable recovery with LLM guidance
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
            
            if self.enable_thinking_window:
                set_window_status("Executing...")
                show_executor_thinking("Starting execution loop")
            
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
            
            # Update thinking window
            if self.enable_thinking_window:
                if result["status"] == "completed":
                    set_window_status("✅ Completed")
                    show_thinking("system", f"Task completed in {elapsed:.1f}s", "success")
                else:
                    set_window_status("❌ Failed")
                    show_thinking("system", f"Task failed: {result.get('status')}", "error")
            
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

                # Generate context from current state
                context_prompt = None
                if self.state:
                    context_prompt = self.state.get_context_prompt()

                # Reduce max_attempts to 1 since we have heuristics now
                return execute_vision_action(
                    self.cli,
                    action_description,
                    max_attempts=1,
                    context_prompt=context_prompt
                )
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
                  model: str = "qwen2.5-coder:32b",
                  cloud_endpoint: Optional[str] = None,
                  enable_supervisor: bool = True,
                  supervisor_mode: str = "background",
                  enable_thinking_window: bool = True) -> Dict:
    """
    Convenience function to run a task with the loop system using Ollama.
    
    Args:
        task: Natural language task description
        model: Ollama model to use (default: qwen2.5-coder:32b, or qwen3-coder:480b for cloud)
        cloud_endpoint: Optional Ollama cloud endpoint URL
        enable_supervisor: Whether to enable supervisor monitoring
        supervisor_mode: "background" or "checkpoint"
        enable_thinking_window: Whether to show thinking window
    
    Returns:
        Execution result dict
    """
    client = OllamaClient(model_name=model, cloud_endpoint=cloud_endpoint)
    planner = OllamaPlanner(client)
    supervisor = OllamaSupervisor(client)
    
    coordinator = LoopCoordinator(
        client=client,
        planner=planner,
        supervisor=supervisor,
        planner=planner,
        enable_supervisor=enable_supervisor,
        supervisor_mode=supervisor_mode,
        enable_thinking_window=enable_thinking_window
    )
    
    return coordinator.execute(task)
