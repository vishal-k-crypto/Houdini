"""
Vision Executor - Uses accessibility tree for smart element interaction.
Falls back to fast coordinate prediction when accessibility returns 0 elements.

NOW WITH PROBABILITY MODEL:
- Analyzes task completeness and uncertainty
- Adjusts match probability thresholds dynamically
- Handles partial/ambiguous task specifications (80-90% info)
- Uses flexible execution strategies based on task analysis
"""

import re
import time
from typing import Dict, Optional
from ..utils.logging import logger
from ..utils.accessibility_reader import (
    get_ui_tree, 
    format_ui_for_llm, 
    find_element_by_text,
    click_element
)

# Try to import probability model
try:
    from ..utils.probability_model import (
        get_probability_model,
        analyze_task_flexibility,
        get_flexible_execution_params
    )
    PROBABILITY_MODEL_AVAILABLE = True
except ImportError:
    PROBABILITY_MODEL_AVAILABLE = False
    logger.warning("Probability model not available")

# TinyClick - Samsung's Florence-2 fine-tuned model for fast click prediction
# This is the PRIMARY vision strategy (~250ms inference, 73.8% accuracy)
try:
    from ..utils.tinyclick_client import (
        predict_click_with_result,
        is_available as tinyclick_is_available,
        TINYCLICK_AVAILABLE
    )
    if TINYCLICK_AVAILABLE:
        logger.info("✅ TinyClick available (Samsung Florence-2)")
    else:
        logger.warning("❌ TinyClick venv not found - run: python3 -m venv .tinyclick-venv && .tinyclick-venv/bin/pip install transformers==4.48.0 torch pillow einops timm")
except ImportError as e:
    TINYCLICK_AVAILABLE = False
    logger.warning(f"TinyClick import failed: {e}")


def execute_vision_action(cli, action_description: str, max_attempts: int = 3,
                          context: Optional[Dict] = None,
                          execution_params: Optional[Dict] = None) -> Dict:
    """
    Execute a vision-based action using accessibility tree analysis.
    The executor analyzes the UI tree and determines where to click autonomously.
    
    NOW WITH PROBABILITY-AWARE EXECUTION:
    - Analyzes task completeness and uncertainty
    - Adjusts match probability thresholds dynamically
    - Uses flexible fallback strategies based on uncertainty
    
    Uses a multi-strategy approach:
    1. Smart heuristic analysis via accessibility API (fast, precise)
    2. Local Vision Localizer (Apple Vision + UI-TARS MLX) for non-accessible elements
    3. VLM screenshot analysis (universal, works for any app)
    4. LLM-guided targeting (text-based fallback)
    
    Args:
        cli: Gemini CLI (only for complex fallback cases)
        action_description: e.g., "click first search result"
        max_attempts: retry count
        context: Optional context for probability model
        execution_params: Pre-calculated execution parameters from TaskProbabilityModel.
                         If provided, these are used directly instead of recalculating.
    
    Returns: {"success": True/False, "error": "...", "method": "...", "match_probability": float, "flexibility": dict}
    """
    logger.info(f"👁️ Vision executor analyzing: {action_description}")
    
    # Use pre-calculated execution params if provided, otherwise calculate them
    exec_params = {}
    flexibility_info = {}
    
    if execution_params:
        # Use pre-calculated params from coordinator (avoids redundant calculation)
        exec_params = execution_params
        flexibility_info = {
            'strategy': exec_params.get('execution_strategy', 'standard'),
            'confidence': exec_params.get('confidence', 0.5),
            'intent': exec_params.get('primary_intent', 'unknown'),
            'predicted_info': exec_params.get('predicted_info', {}),
        }
        logger.info(f"  📊 Using pre-calculated execution params:")
        logger.info(f"     Strategy: {exec_params.get('execution_strategy', 'standard')}")
        logger.info(f"     Confidence: {exec_params.get('confidence', 0.5):.0%}")
        logger.info(f"     Min match: {exec_params.get('min_match_probability', 0.5):.0%}")
        logger.info(f"     Verification: {exec_params.get('verification_strictness', 'moderate')}")
    elif PROBABILITY_MODEL_AVAILABLE:
        exec_params = get_flexible_execution_params(action_description, context)
        flexibility_info = {
            'strategy': exec_params.get('execution_strategy', 'standard'),
            'confidence': exec_params.get('confidence', 0.5),
            'intent': exec_params.get('primary_intent', 'unknown'),
            'predicted_info': exec_params.get('predicted_info', {}),
        }
        
        logger.info(f"  📊 Probability analysis:")
        logger.info(f"     Strategy: {exec_params.get('execution_strategy')}")
        logger.info(f"     Confidence: {exec_params.get('confidence', 0):.0%}")
        logger.info(f"     Min match: {exec_params.get('min_match_probability', 0.5):.0%}")
        if exec_params.get('predicted_info'):
            logger.info(f"     Predicted: {exec_params.get('predicted_info')}")
    else:
        # Default params
        exec_params = {
            'min_match_probability': 0.5,
            'verification_strictness': 'moderate',
            'fallback_chain': ['infer_from_context', 'supervisor_guidance'],
            'exploration_enabled': False,
        }
    
    # Strategy 1: Smart heuristic analysis via accessibility (with Awareness & Exploration)
    result = _analyze_and_execute(action_description)
    
    if result.get("success"):
        result["method"] = "accessibility"
        result["match_probability"] = 1.0  # Accessibility matches are exact
        result["flexibility"] = flexibility_info
        return result

    # Get dynamic match threshold from probability model
    min_match_prob = exec_params.get('min_match_probability', 0.5)
    
    # Get app context for vision
    app_name = ""
    task_context = action_description
    try:
        from ..utils.accessibility_reader import get_frontmost_app
        app_info = get_frontmost_app()
        app_name = app_info.get("app", "")
        if app_name:
            task_context = f"App: {app_name} | Task: {action_description}"
    except:
        pass
    
    # Strategy 2: TinyClick (Samsung Florence-2) - Fast pixel-precise clicking
    # ~250ms inference, 73.8% accuracy on Screenspot benchmark
    # Use TinyClick when accessibility can't find the element
    if TINYCLICK_AVAILABLE and result.get("reason") in ["zero_elements", "no_match", "low_confidence"]:
        logger.info(f"  ⚡ Using TinyClick (threshold: {min_match_prob:.0%})...")
        tinyclick_result = _tinyclick_fallback(
            action_description, 
            min_match_prob,
            task_context=task_context
        )
        
        if tinyclick_result.get("success"):
            tinyclick_result["method"] = "tinyclick"
            tinyclick_result["flexibility"] = flexibility_info
            return tinyclick_result
        else:
            logger.warning(f"  TinyClick failed: {tinyclick_result.get('error')}")
    
    # No more fallbacks - TinyClick is our only vision strategy
    return {
        "success": False, 
        "error": "All strategies failed (accessibility + TinyClick)", 
        "method": "none",
        "flexibility": flexibility_info
    }


def _tinyclick_fallback(
    action_description: str,
    min_match_probability: float = 0.3,
    task_context: str = ""
) -> Dict:
    """
    Use TinyClick (Samsung's Florence-2 fine-tuned model) for fast click prediction.
    
    TinyClick Features:
    - ~250ms inference (160x faster than VLM cloud calls)
    - 0.27B parameters (lightweight, runs locally)
    - 73.8% accuracy on Screenspot benchmark
    - Pixel-precise coordinate prediction
    
    Args:
        action_description: What element to click, e.g., "first video thumbnail"
        min_match_probability: Minimum confidence threshold
        task_context: Additional context about the task
    
    Returns:
        {
            "success": bool,
            "coordinates": (x, y),
            "match_probability": float,
            "element": str,
            "error": str or None
        }
    """
    import pyautogui
    
    try:
        # Get prediction from TinyClick
        result = predict_click_with_result(
            action_description,
            screenshot_path=None,  # Will capture automatically
            task_context=task_context
        )
        
        if not result.get("success"):
            error_msg = result.get("error", "Prediction failed")
            logger.warning(f"  TinyClick: {error_msg}")
            return {
                "success": False,
                "match_probability": 0.0,
                "error": error_msg
            }
        
        x, y = result["x"], result["y"]
        confidence = result.get("confidence", 0.85)
        inference_ms = result.get("inference_ms", 0)
        
        logger.info(f"  TinyClick: Found element at ({x}, {y}) in {inference_ms:.0f}ms")
        logger.info(f"  Confidence: {confidence:.0%}")
        
        # Check confidence threshold
        if confidence < min_match_probability:
            logger.warning(f"  TinyClick confidence {confidence:.0%} below threshold {min_match_probability:.0%}")
            return {
                "success": False,
                "match_probability": confidence,
                "error": f"Confidence {confidence:.0%} below threshold"
            }
            
        # SAFETY CHECK: Protect against accidental address bar clicks (y < 110)
        # unless user explicitly asks for "address", "url", "browser", etc.
        action_lower = action_description.lower()
        explicit_nav_intent = any(w in action_lower for w in ['address', 'url', 'omnibox', 'browser', 'navigation'])
        
        if y < 110 and not explicit_nav_intent:
            logger.warning(f"  ⚠️ TinyClick result ({x}, {y}) is in browser chrome (likely address bar), but no explicit intent found.")
            return {
                "success": False,
                "match_probability": confidence,
                "is_address_bar_rejection": True,
                "error": "Safety check: Click target in browser chrome (address bar) rejected for non-navigation intent"
            }
        
        # Perform the click using human-like cursor movement
        try:
            from ..utils.cursor_controller import HumanCursor
            cursor = HumanCursor()
            cursor.move_to(x, y)
        except ImportError:
            # Fallback to pyautogui
            pyautogui.moveTo(x, y, duration=0.15)
        
        time.sleep(0.05)  # Brief pause before clicking
        pyautogui.click()
        
        logger.info(f"  ✅ TinyClick clicked at ({x}, {y})")
        
        return {
            "success": True,
            "coordinates": (x, y),
            "match_probability": confidence,
            "element": action_description,
            "inference_ms": inference_ms
        }
        
    except Exception as e:
        logger.error(f"  TinyClick error: {e}")
        return {"success": False, "error": str(e)}


def _analyze_and_execute(action_description: str) -> Dict:
    """
    Executor analyzes UI tree and determines click target.
    Uses direct text matching for reliability.
    """
    import pyautogui
    from ..utils.accessibility_reader import get_frontmost_app, get_ui_elements_applescript
    
    desc_lower = action_description.lower()
    
    # Extract search keywords from the action description
    keywords = []
    # Look for quoted text first
    import re
    quoted = re.findall(r'["\']([^"\']+)["\']', action_description)
    if quoted:
        keywords.extend([q.lower() for q in quoted])
    
    # Extract meaningful words from description
    skip_words = {'click', 'on', 'the', 'a', 'an', 'matching', 'element', 'find', 'locate'}
    words = [w.strip('.,!?') for w in desc_lower.split() 
             if w.strip('.,!?') and w.strip('.,!?') not in skip_words and len(w) > 2]
    keywords.extend(words)
    
    logger.info(f"  🔍 Looking for keywords: {keywords}")
    
    screen_width, screen_height = pyautogui.size()
    
    # Get UI elements
    elements = get_ui_elements_applescript(max_elements=150)
    
    if not elements:
        logger.warning("  ⚠️ Accessibility returned 0 elements")
        return {"success": False, "reason": "zero_elements"}
    
    # Score elements by keyword match and interactivity
    candidates = []
    for elem in elements:
        # Skip system bar (top 25px)
        if elem.y < 25:
            continue
            
        title = (elem.title or '').lower()
        value = (elem.value or '').lower()
        role = elem.role.lower() if elem.role else ''
        text = f"{title} {value}"
        
        score = 0.0
        matched_keywords = []
        
        # Keyword matching
        for kw in keywords:
            if kw in text:
                score += 0.4
                matched_keywords.append(kw)
        
        # Role bonus for interactive elements
        interactive_roles = ['button', 'link', 'menuitem', 'checkbox', 'radiobutton', 
                            'textfield', 'searchfield', 'combobox']
        if any(r in role for r in interactive_roles):
            score += 0.3
        
        # Penalty for headers/footers 
        if elem.y < screen_height * 0.08:  # Top 8%
            score -= 0.2
        
        if score > 0:
            candidates.append((score, elem, matched_keywords))
    
    # Sort by score
    candidates.sort(key=lambda x: -x[0])
    
    if not candidates:
        logger.info("  No matching candidates found")
        return {"success": False, "reason": "no_match"}
    
    # Check for explicit address bar intent
    explicit_nav_intent = any(w in desc_lower for w in ['address', 'url', 'omnibox', 'browser', 'navigation'])
    
    # Refine scores with address bar detection
    refined_candidates = []
    for score, elem, matched in candidates:
        # Heuristic for browser address bar/omnibox
        # 1. Top region of screen (usually top 110px)
        # 2. Text field or search field role
        # 3. Value looks like a URL
        is_top_region = elem.y < 110
        is_input_role = elem.role in ['textField', 'searchField', 'comboBox']
        val = (elem.value or '').strip()
        is_url_value = val.startswith('http') or val.startswith('www') or '://' in val or '.com' in val or '.org' in val or '.net' in val or '.io' in val
        
        is_likely_address_bar = is_top_region and is_input_role and is_url_value
        
        if is_likely_address_bar and not explicit_nav_intent:
            logger.info(f"  📉 Applying address bar penalty to '{elem.title or elem.value}' (is_likely_address_bar=True)")
            score -= 0.5
        
        if score > 0:
            refined_candidates.append((score, elem, matched))
            
    # Re-sort after penalties
    candidates = sorted(refined_candidates, key=lambda x: -x[0])
    
    if not candidates:
        logger.info("  No matching candidates after refinement")
        return {"success": False, "reason": "no_match_after_refinement"}
    
    # Log top candidates
    for i, (score, elem, matched) in enumerate(candidates[:3]):
        logger.info(f"  #{i+1} Score: {score:.2f} | '{elem.title or elem.value}' | {elem.role} | matched: {matched}")
    
    # Click best candidate if score is reasonable
    best_score, best_elem, best_matched = candidates[0]
    
    if best_score >= 0.3:  # Lower threshold for reliability
        return _perform_click(best_elem)
    else:
        logger.info(f"  Best score {best_score:.2f} too low, deferring to vision fallback")
        return {"success": False, "reason": "low_confidence"}


def _perform_click(target):
    import pyautogui
    import time
    
    logger.info(f"  Executor selected: {target.role} '{target.title or target.value}' at {target.center}")
    target_x, target_y = target.center
    
    pyautogui.moveTo(target_x, target_y, duration=0.3)
    time.sleep(0.05)
    pyautogui.click()
    
    logger.info(f"  ✅ Clicked: {target}")
    return {"success": True}


def smart_click(text_to_find: str) -> bool:
    """
    Find an element by text and click it.
    Fast, no LLM call needed.
    """
    element = find_element_by_text(text_to_find)
    if element:
        click_element(element)
        return True
    return False
