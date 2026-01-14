"""
Blind Executor - Runs keyboard/mouse actions without screen checks.
Much faster than vision-based execution.
"""

import time
from typing import List
from ..utils.logging import logger
from ..utils.prompt_evolution import prompt_evolution

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

# Try to import enhanced executor
try:
    from .enhanced_executor import EnhancedExecutor, execute_enhanced_batch, ENHANCED_AVAILABLE
except ImportError:
    ENHANCED_AVAILABLE = False
    logger.info("Enhanced executor not available, using basic PyAutoGUI")


def execute_blind_batch(actions: List[str], task: str = None, use_enhanced: bool = True) -> dict:
    """
    Execute a batch of blind actions directly.
    
    Args:
        actions: List of action strings
        task: Optional task description
        use_enhanced: Try to use enhanced executor (10-100x faster) if available
    
    Action format:
    - "hotkey:key1,key2" → pyautogui.hotkey(key1, key2)
    - "type:text" → pyautogui.write(text)
    - "key:keyname" → pyautogui.press(keyname)
    - "wait:seconds" → time.sleep(seconds)
    - "click:element_name" → Find and click element (enhanced only)
    - "type:field:text" → Find field and type (enhanced only)
    
    Returns: {"success": True/False, "error": "..."}
    """
    # Try enhanced executor first (much faster!)
    if use_enhanced and ENHANCED_AVAILABLE:
        logger.debug("Using enhanced executor (native accessibility + human cursor)")
        result = execute_enhanced_batch(actions, task, use_human_cursor=True)
        
        # If enhanced succeeded, return immediately
        if result["success"]:
            return {"success": True, "error": None, "method": "enhanced"}
        else:
            logger.warning(f"Enhanced executor failed: {result.get('error')}, falling back to basic")
    
    # Fallback to basic PyAutoGUI executor
    logger.debug("Using basic PyAutoGUI executor")
    if not PYAUTOGUI_AVAILABLE:
        error_msg = "pyautogui not available"
        if task:
            prompt_evolution.record_feedback(
                component="executor",
                task=task,
                success=False,
                error_type="dependency_missing",
                error_details=error_msg
            )
        return {"success": False, "error": error_msg}
    
    start_time = time.time()
    executed_actions = []
    
    for action in actions:
        try:
            executed_actions.append(action)
            
            if action.startswith("hotkey:"):
                keys = action[7:].split(",")
                keys = [k.strip() for k in keys]
                
                # Support macOS key name variations and aliases
                key_mapping = {
                    'cmd': 'command',
                    'opt': 'option',
                    'alt': 'option',
                    'ctrl': 'control',
                    'del': 'delete',
                    'ret': 'return',
                    'esc': 'escape',
                    'grave': '`',  # For Cmd+` window switching
                }
                
                keys = [key_mapping.get(k.lower(), k) for k in keys]
                pyautogui.hotkey(*keys)
                logger.info(f"  ↳ hotkey({', '.join(keys)})")
                
            elif action.startswith("type:"):
                text = action[5:]
                pyautogui.write(text, interval=0.02)
                logger.info(f"  ↳ type('{text}')")
                
            elif action.startswith("key:"):
                key = action[4:].strip()
                pyautogui.press(key)
                logger.info(f"  ↳ press({key})")
                
            elif action.startswith("wait:"):
                secs = float(action[5:])
                time.sleep(secs)
                
            elif action.startswith("click:"):
                # Blind click at coordinates x,y
                coords = action[6:].split(",")
                x, y = int(coords[0]), int(coords[1])
                pyautogui.click(x, y)
                logger.info(f"  ↳ click({x}, {y})")
                
            else:
                # Unknown format, try as raw text
                logger.warning(f"  Unknown action format: {action}")
            
            # Small delay between actions
            time.sleep(0.1)
            
        except Exception as e:
            logger.error(f"  ✗ Action failed: {action} - {e}")
            
            # Record execution failure
            if task:
                prompt_evolution.record_feedback(
                    component="executor",
                    task=task,
                    success=False,
                    error_type="action_execution_failed",
                    error_details=f"Action '{action}' failed: {str(e)}",
                    execution_time=time.time() - start_time,
                    actions_taken=executed_actions
                )
            
            return {"success": False, "error": str(e)}
    
    execution_time = time.time() - start_time
    
    # Record successful execution
    if task:
        prompt_evolution.record_feedback(
            component="executor",
            task=task,
            success=True,
            execution_time=execution_time,
            actions_taken=executed_actions
        )
    
    return {"success": True, "error": None}


def execute_plan_fast(batches: List[dict]) -> dict:
    """
    Execute a full plan with blind batches.
    
    Args:
        batches: [{"type": "blind"/"vision", "actions": [...], "description": "..."}]
    
    Returns results for each batch.
    """
    results = []
    
    for i, batch in enumerate(batches):
        batch_type = batch.get("type", "blind")
        description = batch.get("description", f"Batch {i+1}")
        
        logger.info(f"▶️ {description}")
        
        if batch_type == "blind":
            actions = batch.get("actions", [])
            result = execute_blind_batch(actions)
            results.append({"batch": i+1, "type": "blind", "result": result})
            
            if not result["success"]:
                logger.error(f"  Batch failed, stopping")
                break
            
            # Small wait after blind batch for UI to settle
            time.sleep(0.3)
            
        elif batch_type == "vision":
            # Vision actions need screen observation
            # Return early so caller can handle with worker
            logger.info(f"  ⏸️ Vision action needed - requires screen")
            results.append({"batch": i+1, "type": "vision", "action": batch.get("action", "")})
            # Don't break - let caller decide to continue
            
    return {"results": results, "completed": len(results)}
