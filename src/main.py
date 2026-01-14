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
    from .loop.loop_coordinator import LoopCoordinator
    from .ui.thinking_window import start_thinking_window, stop_thinking_window
    
    # Start thinking window if enabled
    thinking_window_enabled = not args.no_thinking_window
    if thinking_window_enabled:
        start_thinking_window()
        logger.info("💭 Thinking window started")
    
    try:
        # Initialize Ollama client and components
        client = OllamaClient(model_name=args.model, cloud_endpoint=getattr(args, 'cloud_endpoint', None))
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
                logger.info(f"  ✅ Vision action completed")
            else:
                logger.warning(f"  ⚠️ Vision action failed: {result.get('error', 'unknown')}")


def main():
    parser = argparse.ArgumentParser(description="Houdini Agent - Fast Batch Execution with Ollama Qwen 3 Coder")
    parser.add_argument("--task", "-t", required=True, help="Task description")
    parser.add_argument("--model", "-m", default="qwen2.5-coder:32b", 
                        help="Ollama model for planning (default: qwen2.5-coder:32b, use qwen3-coder:480b for cloud)")
    parser.add_argument("--cloud-endpoint", help="Ollama cloud endpoint URL (e.g., https://cloud.ollama.ai)")
    parser.add_argument("--vision-steps", type=int, default=3, help="Max steps for vision actions")
    
    # Loop mode arguments
    parser.add_argument("--loop", action="store_true", 
                        help="Use continuous loop mode (keeps model aware of state)")
    parser.add_argument("--no-supervisor", action="store_true",
                        help="Disable supervisor monitoring in loop mode")
    parser.add_argument("--supervisor-mode", default="background",
                        choices=["background", "checkpoint"],
                        help="Supervisor mode: background (parallel) or checkpoint (after batches)")
    parser.add_argument("--no-thinking-window", action="store_true",
                        help="Disable the floating thinking window")
    
    # Enhanced executor arguments (NEW!)
    parser.add_argument("--use-enhanced", action="store_true", default=True,
                        help="Use enhanced executor with native accessibility (10-100x faster, default: True)")
    parser.add_argument("--no-enhanced", dest="use_enhanced", action="store_false",
                        help="Disable enhanced executor, use basic PyAutoGUI only")
    
    args = parser.parse_args()
    
    # Log enhanced mode status
    if hasattr(args, 'use_enhanced'):
        if args.use_enhanced:
            logger.info("⚡ Enhanced executor ENABLED (native accessibility + human cursor)")
        else:
            logger.info("🐌 Enhanced executor DISABLED (using basic PyAutoGUI)")

    logger.info(f"🚀 Task: {args.task}")
    start_time = time.time()

    if args.loop:
        # New loop-based execution with continuous state awareness
        logger.info("🔄 Using continuous loop mode")
        run_loop_mode(args)
    else:
        # Legacy batch execution
        run_batch_mode(args)
    
    elapsed = time.time() - start_time
    logger.info(f"\n🎉 Completed in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
