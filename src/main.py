import argparse
import sys
import time
import io
import subprocess
from pathlib import Path

from .utils.logging import logger
from .utils.ollama_client import OllamaClient
from .planner.ollama_planner import OllamaPlanner
from .supervisor.ollama_supervisor import OllamaSupervisor
from .agents.blind_executor import execute_plan_fast, execute_blind_batch
from .agents.agent_s import AgentS

def capture_screen() -> bytes:
    """Capture screen for vision actions."""
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            temp_path = f.name
        
        if sys.platform == "linux":
            # Linux (Docker) - use scrot
            subprocess.run(["scrot", temp_path], capture_output=True, timeout=5)
        else:
            # macOS - use screencapture
            subprocess.run(["screencapture", "-x", "-C", temp_path], capture_output=True, timeout=5)
        
        if Path(temp_path).exists():
            with open(temp_path, 'rb') as f:
                data = f.read()
            Path(temp_path).unlink()
            if len(data) > 100:
                return data
    except:
        pass
    
    from PIL import Image
    img = Image.new('RGB', (1920, 1080), color='gray')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def run_loop_mode(args):
    """Execute task using the continuous loop system."""
    from .ui.thinking_window import start_thinking_window, stop_thinking_window
    
    # Start thinking window if enabled
    thinking_window_enabled = args.thinking_window
    if thinking_window_enabled:
        start_thinking_window()
        logger.info("💭 Thinking window started")
    
    try:
        # Initialize Ollama client
        client = OllamaClient(model_name=args.model, cloud_endpoint=getattr(args, 'cloud_endpoint', None))
        
        # Check if LangGraph mode is requested
        if getattr(args, 'use_langgraph', False):
            # NEW: LangGraph architecture with built-in state management and checkpointing
            from .loop.langgraph_coordinator import LangGraphCoordinator
            
            # Use SQLite checkpoint if path provided
            checkpoint_path = getattr(args, 'checkpoint_path', None)
            
            coordinator = LangGraphCoordinator(
                client=client,
                enable_thinking_window=thinking_window_enabled,
                max_iterations=100,
                checkpoint_path=checkpoint_path,
                enable_human_approval=getattr(args, 'human_approval', False),
            )
            
            logger.info("🔄 Using LANGGRAPH architecture (state machine with checkpointing)")
            
            # Check for resume
            thread_id = getattr(args, 'resume_thread', None)
            if thread_id:
                logger.info(f"🔄 Resuming from checkpoint: {thread_id}")
                result = coordinator.resume(thread_id)
            else:
                result = coordinator.execute(args.task)
        elif getattr(args, 'use_adaptive', True):
            # NEW: Adaptive architecture with macro/micro separation
            from .loop.adaptive_coordinator import AdaptiveLoopCoordinator
            
            coordinator = AdaptiveLoopCoordinator(
                client=client,
                enable_thinking_window=thinking_window_enabled,
                max_iterations=100
            )
            
            logger.info("🧠 Using ADAPTIVE architecture (macro planner → micro executor → adaptive supervisor)")
            result = coordinator.execute(args.task, is_training=getattr(args, 'train_mode', False))
        else:
            # Legacy: Original loop coordinator
            from .loop.loop_coordinator import LoopCoordinator
            planner = OllamaPlanner(client)
            supervisor = OllamaSupervisor(client)
            
            coordinator = LoopCoordinator(
                client=client,
                planner=planner,
                supervisor=supervisor,
                enable_supervisor=not args.no_supervisor,
                supervisor_mode=args.supervisor_mode,
                enable_thinking_window=thinking_window_enabled
            )
            
            logger.info("📋 Using LEGACY architecture")
            result = coordinator.execute(args.task)
    finally:
        # Keep window open for a bit to see final results
        if thinking_window_enabled:
            import time
            time.sleep(2)
    
    if result.get("success"):
        logger.info("✨ Task completed successfully!")
    else:
        logger.error(f"Task failed: {result.get('error', 'Unknown error')}")
    
    return result


def run_batch_mode(args):
    """Execute task using the batch execution system (legacy)."""
    client = OllamaClient(model_name=args.model, cloud_endpoint=getattr(args, 'cloud_endpoint', None))
    planner = OllamaPlanner(client)
    
    # Generate batched plan
    batches = planner.plan(args.task)
    
    logger.info(f"📋 Plan: {len(batches)} batches")
    for i, batch in enumerate(batches):
        btype = batch.get("type", "blind")
        desc = batch.get("description", "...")
        logger.info(f"  {i+1}. [{btype.upper()}] {desc}")

    # Execute batches
    for i, batch in enumerate(batches):
        batch_type = batch.get("type", "blind")
        description = batch.get("description", f"Batch {i+1}")
        
        logger.info(f"\n▶️ Executing: {description}")
        
        if batch_type == "blind":
            # Direct execution - no LLM calls needed!
            actions = batch.get("actions", [])
            if actions:
                result = execute_blind_batch(actions, use_enhanced=args.use_enhanced)
                if result["success"]:
                    logger.info(f"  ✅ Completed ({len(actions)} actions)")
                else:
                    logger.error(f"  ❌ Failed: {result['error']}")
            else:
                logger.warning(f"  No actions in batch")
            
            time.sleep(0.3)
            
        elif batch_type == "vision":
            # Vision action - uses accessibility tree (no screenshot!)
            action_desc = batch.get("action", description)
            logger.info(f"  👁️ Vision action: {action_desc}")
            
            from .agents.vision_executor import execute_vision_action
            result = execute_vision_action(client, action_desc, max_attempts=args.vision_steps)
            
            if result.get("success"):
                method = result.get("method", "unknown")
                duration = result.get("duration", 0)  # If available
                logger.info(f"  ✅ Vision action completed using {method.upper()}")
            else:
                logger.warning(f"  ⚠️ Vision action failed: {result.get('error', 'unknown')}")


def run_replay_mode(args):
    """Run the replay/time-travel debugging mode."""
    from .replay.replay_ui import run_replay, list_sessions
    
    if getattr(args, 'list_sessions', False):
        list_sessions()
    else:
        session_id = getattr(args, 'session_id', None)
        run_replay(session_id)


def run_debug_report_mode(args):
    """Generate AI-readable debug reports from execution sessions."""
    from .utils.debug_report_generator import get_debug_report_generator
    from .replay.execution_logger import get_execution_logger
    
    generator = get_debug_report_generator()
    exec_logger = get_execution_logger()
    
    # Generate report for specific session
    if getattr(args, 'debug_report_session', None):
        session_id = args.debug_report_session
        session = exec_logger.load_session_by_task_id(session_id)
        
        if session:
            output_path = generator.export_to_file(session)
            logger.info(f"📝 Debug report generated: {output_path}")
        else:
            logger.error(f"❌ Session not found: {session_id}")
        return
    
    # Generate reports for all failed sessions
    if getattr(args, 'debug_report_all', False):
        reports = generator.export_failed_sessions(limit=10)
        if reports:
            logger.info(f"📝 Generated {len(reports)} debug reports:")
            for path in reports:
                logger.info(f"   - {path}")
        else:
            logger.info("ℹ️ No failed sessions found")
        return
    
    # Default: generate report for latest session
    output_path = generator.export_latest_session()
    if output_path:
        logger.info(f"📝 Debug report generated: {output_path}")
        logger.info(f"   Share this file with an AI for root cause analysis!")
    else:
        logger.error("❌ No sessions found. Run some tasks first!")


def main():
    parser = argparse.ArgumentParser(description="Houdini Agent - Fast Batch Execution with Ollama Qwen 3 Coder")
    parser.add_argument("--task", "-t", required=False, help="Task description")
    parser.add_argument("--model", "-m", default=None, 
                        help="Ollama model for planning (default: from config or qwen3-coder:480b-cloud)")
    parser.add_argument("--cloud-endpoint", help="Ollama cloud endpoint URL (e.g., https://cloud.ollama.ai)")
    parser.add_argument("--vision-steps", type=int, default=3, help="Max steps for vision actions")
    
    # Supervisor arguments (enabled by default)
    parser.add_argument("--no-supervisor", action="store_true",
                        help="Disable supervisor monitoring (not recommended)")
    parser.add_argument("--supervisor-mode", default="background",
                        choices=["background", "checkpoint"],
                        help="Supervisor mode: background (parallel) or checkpoint (after batches)")
    parser.add_argument("--thinking-window", action="store_true", default=False,
                        help="Enable the floating thinking window (experimental)")
    
    # Architecture mode
    parser.add_argument("--use-adaptive", action="store_true", default=True,
                        help="Use new adaptive architecture with macro/micro separation (default: True)")
    parser.add_argument("--legacy", dest="use_adaptive", action="store_false",
                        help="Use legacy architecture instead of adaptive")
    
    # LangGraph mode (NEW!)
    parser.add_argument("--langgraph", dest="use_langgraph", action="store_true", default=False,
                        help="Use LangGraph-based architecture with built-in state management and checkpointing")
    parser.add_argument("--checkpoint-path", type=str, default=None,
                        help="SQLite path for persistent LangGraph checkpoints (e.g., data/checkpoints.db)")
    parser.add_argument("--resume-thread", type=str, default=None,
                        help="Resume a previous LangGraph execution by thread ID")
    parser.add_argument("--human-approval", action="store_true", default=False,
                        help="Enable human-in-the-loop approval points (LangGraph only)")
    
    # Enhanced executor arguments (NEW!)
    parser.add_argument("--use-enhanced", action="store_true", default=True,
                        help="Use enhanced executor with native accessibility (10-100x faster, default: True)")
    parser.add_argument("--no-enhanced", dest="use_enhanced", action="store_false",
                        help="Disable enhanced executor, use basic PyAutoGUI only")
    
    # Replay/Time Travel mode (NEW!)
    parser.add_argument("--replay", dest="replay_mode", action="store_true", default=False,
                        help="Enter replay mode to debug past executions with time travel")
    parser.add_argument("--replay-session", dest="session_id", type=str, default=None,
                        help="Replay a specific session by task ID or filepath")
    parser.add_argument("--replay-list", dest="list_sessions", action="store_true", default=False,
                        help="List all available replay sessions")
    
    # Debug Report mode (NEW!)
    parser.add_argument("--debug-report", dest="debug_report", action="store_true", default=False,
                        help="Generate AI-readable debug report for the latest session")
    parser.add_argument("--debug-report-session", dest="debug_report_session", type=str, default=None,
                        help="Generate debug report for a specific session by task ID")
    parser.add_argument("--debug-report-all", dest="debug_report_all", action="store_true", default=False,
                        help="Generate debug reports for all failed sessions")
    
    # Training Data Collection (NEW!)
    parser.add_argument("--train", dest="train_mode", action="store_true", default=False,
                        help="Run in training data collection mode (save full LLM logs to training_sessions)")
    
    # Health Check
    parser.add_argument("--health-check", dest="health_check", action="store_true", default=False,
                        help="Run health check to verify Ollama, permissions, models, and directories")
    
    args = parser.parse_args()
    
    # Handle health check mode
    if getattr(args, 'health_check', False):
        from .health_check import run_health_check
        success = run_health_check()
        sys.exit(0 if success else 1)
    
    # Handle debug report mode
    if getattr(args, 'debug_report', False) or getattr(args, 'debug_report_session', None) or getattr(args, 'debug_report_all', False):
        run_debug_report_mode(args)
        return
    
    # Handle replay mode
    if getattr(args, 'replay_mode', False) or getattr(args, 'list_sessions', False) or getattr(args, 'session_id', None):
        run_replay_mode(args)
        return
    
    # Task is required if not in replay mode
    if not args.task:
        parser.error("--task/-t is required unless using --replay mode")
    
    # Force loop mode (always enabled)
    args.loop = True
    
    # Log enhanced mode status
    if hasattr(args, 'use_enhanced'):
        if args.use_enhanced:
            logger.info("⚡ Enhanced executor ENABLED (native accessibility + human cursor)")
        else:
            logger.info("🐌 Enhanced executor DISABLED (using basic PyAutoGUI)")

    # ── Activate confidence & probability models ─────────────────
    # These are conditionally imported in coordinators; eagerly load them
    # here so failures are visible at startup, not buried in try/except.
    try:
        from .utils.execution_confidence import get_confidence_model
        _cm = get_confidence_model()
        logger.info(f"📊 Confidence model ACTIVE (calibration samples: {len(_cm.calibrator.calibration_data)})")
    except Exception as e:
        logger.warning(f"⚠️  Confidence model unavailable: {e}")

    try:
        from .utils.probability_model import get_probability_model
        _pm = get_probability_model()
        logger.info("🎲 Probability model ACTIVE (task flexibility + intent prediction)")
    except Exception as e:
        logger.warning(f"⚠️  Probability model unavailable: {e}")

    # Log architecture mode
    if getattr(args, 'use_langgraph', False):
        logger.info("🔄 LANGGRAPH architecture: State Machine with Checkpointing")
        if args.checkpoint_path:
            logger.info(f"   Checkpoint path: {args.checkpoint_path}")
        if args.resume_thread:
            logger.info(f"   Resuming thread: {args.resume_thread}")
    elif getattr(args, 'use_adaptive', True):
        logger.info("🧠 ADAPTIVE architecture: Macro Planner → Micro Executor → Adaptive Supervisor")
    else:
        logger.info("📋 LEGACY architecture: Planner → Executor → Supervisor")

    logger.info(f"🚀 Task: {args.task}")
    logger.info(f"🔄 Loop mode with supervisor {'DISABLED' if args.no_supervisor else 'ENABLED'}")
    start_time = time.time()

    # Always use loop mode
    run_loop_mode(args)
    
    elapsed = time.time() - start_time
    logger.info(f"\n🎉 Completed in {elapsed:.1f}s")


def run_task_internal(task_description: str, is_training: bool = True) -> dict:
    """
    Internal API for running tasks programmatically.
    Used by auto_collector.py for automated data collection.
    
    Args:
        task_description: The task to execute
        is_training: If True, enables training mode for excellent data quality
                    (captures screenshots before/after actions, saves to training_sessions)
        
    Returns:
        dict: Result with keys: success, error, session_id, duration
    """
    from .loop.adaptive_coordinator import AdaptiveLoopCoordinator
    from .utils.ollama_client import OllamaClient
    
    try:
        client = OllamaClient()
        coordinator = AdaptiveLoopCoordinator(
            client=client,
            enable_thinking_window=False,  # No GUI in Docker
            max_iterations=100
        )
        
        # Enable training mode for high-quality data collection
        result = coordinator.execute(task_description, is_training=is_training)
        
        return {
            "success": result.get("success", False),
            "error": result.get("error"),
            "session_id": result.get("session_id"),
        }
    except Exception as e:
        logger.error(f"Task execution failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "session_id": None,
        }


if __name__ == "__main__":
    main()
