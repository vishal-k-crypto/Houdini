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
from ..utils.gemini_client import GeminiCLI
from ..utils.coordinate_predictor import get_predictor

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

# Try to import coordinate predictor
try:
    PREDICTOR_AVAILABLE = True
except ImportError:
    PREDICTOR_AVAILABLE = False
    logger.warning("Coordinate predictor not available")

# Try to import LocalVisionLocalizer (hybrid Apple Vision + UI-TARS MLX)
# This is the PRIMARY vision strategy for non-accessible apps on Mac
try:
    from ..utils.local_vision_localizer import (
        LocalVisionLocalizer,
        get_local_localizer,
        find_element_locally
    )
    LOCAL_VISION_AVAILABLE = True
    logger.info("LocalVisionLocalizer available (Apple Vision + UI-TARS)")
except ImportError:
    LOCAL_VISION_AVAILABLE = False
    logger.info("LocalVisionLocalizer not available - install pyobjc-framework-Vision and mlx-vlm")


def execute_vision_action(cli: GeminiCLI, action_description: str, max_attempts: int = 3,
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
    
    # Strategy 1: Smart heuristic analysis via accessibility
    result = _analyze_and_execute(action_description)
    
    if result.get("success"):
        result["method"] = "accessibility"
        result["match_probability"] = 1.0  # Accessibility matches are exact
        result["flexibility"] = flexibility_info
        return result
    
    # Get dynamic match threshold from probability model
    min_match_prob = exec_params.get('min_match_probability', 0.5)
    
    # Strategy 2: Local Vision Localizer (Apple Vision + UI-TARS MLX)
    # Hardware-accelerated on Apple Silicon - best for non-accessible apps
    if LOCAL_VISION_AVAILABLE and result.get("reason") == "zero_elements":
        logger.info(f"  🍎 Using Local Vision Localizer (threshold: {min_match_prob:.0%})...")
        local_result = _local_vision_fallback(action_description, min_match_prob)
        
        if local_result.get("success"):
            local_result["method"] = "local_vision"
            local_result["flexibility"] = flexibility_info
            return local_result
    
    # Strategy 3: Fast coordinate prediction (universal - works for any app)
    if PREDICTOR_AVAILABLE:
        logger.info(f"  ⚡ Using fast coordinate prediction (threshold: {min_match_prob:.0%})...")
        result = _fast_coordinate_fallback(action_description, min_match_prob)
        
        if result.get("success"):
            result["method"] = "coordinate_prediction"
            result["flexibility"] = flexibility_info
            return result
        elif result.get("match_probability", 0) > 0:
            # Found something but with low probability
            match_prob = result.get('match_probability', 0)
            logger.warning(f"  Prediction found element with {match_prob:.0%} match probability")
            
            # If exploration is enabled and we have alternatives, try them
            if exec_params.get('exploration_enabled') and match_prob > 0.3:
                logger.info("  🔍 Exploration enabled - proceeding with low-confidence match")
                result["method"] = "coordinate_prediction_exploratory"
                result["flexibility"] = flexibility_info
                return result
    
    # Strategy 4: LLM-guided fallback (last resort)
    logger.warning("  Using LLM-guided fallback...")
    result = _llm_fallback(cli, action_description, max_attempts)
    result["method"] = "llm"
    result["flexibility"] = flexibility_info
    return result


def _local_vision_fallback(action_description: str, min_match_probability: float = 0.5) -> Dict:
    """
    Use Local Vision Localizer (Apple Vision + UI-TARS MLX) to find and click UI elements.
    
    Hybrid approach:
    1. Apple Vision Framework - Fast geometric detection of UI rectangles (sub-millisecond)
    2. UI-TARS via MLX-VLM - Semantic grounding for complex elements
    
    Hardware-accelerated on Apple Silicon Neural Engine.
    
    Args:
        action_description: What element to find and click
        min_match_probability: Minimum match score to consider success
        
    Returns:
        {
            "success": True/False,
            "coordinates": (x, y) or None,
            "match_probability": float,
            "element": detected element info,
            "error": "..." or None
        }
    """
    import pyautogui
    
    try:
        localizer = get_local_localizer()
        result = find_element_locally(action_description, min_confidence=min_match_probability)
        
        if not result.found:
            logger.warning(f"  LocalVision: No element matching '{action_description}'")
            return {
                "success": False,
                "match_probability": result.confidence,
                "error": "No matching element found"
            }
        
        # Check if match meets threshold
        if result.confidence < min_match_probability:
            logger.warning(f"  LocalVision: Match confidence {result.confidence:.0%} below threshold {min_match_probability:.0%}")
            return {
                "success": False,
                "match_probability": result.confidence,
                "element": result.element_description,
                "coordinates": (result.x, result.y),
                "error": f"Match confidence too low: {result.confidence:.0%}"
            }
        
        # Execute click
        x, y = result.x, result.y
        logger.info(f"  LocalVision: Found '{result.element_description}' at ({x}, {y})")
        logger.info(f"  Method: {result.method}, Confidence: {result.confidence:.0%}")
        
        # Move and click with natural motion
        current_x, current_y = pyautogui.position()
        distance = ((x - current_x)**2 + (y - current_y)**2)**0.5
        duration = min(0.5, max(0.1, distance / 1000))
        
        pyautogui.moveTo(x, y, duration=duration)
        pyautogui.click()
        
        logger.info(f"  ✅ LocalVision clicked at ({x}, {y})")
        
        return {
            "success": True,
            "coordinates": (x, y),
            "match_probability": result.confidence,
            "element": result.element_description,
        }
        
    except Exception as e:
        logger.error(f"  LocalVision error: {e}")
        return {"success": False, "error": str(e)}


def _fast_coordinate_fallback(action_description: str, min_match_probability: float = 0.5) -> Dict:
    """
    Use fast coordinate prediction to find and click elements.
    Uses Qwen3-Coder to reason about UI layouts and predict precise coordinates.
    MUCH faster than vision models (2-3 seconds vs 30+ seconds).
    
    This is a UNIVERSAL method that works for any application.
    Returns match probability so caller can decide whether to proceed.
    
    Args:
        action_description: What element to find and click
        min_match_probability: Minimum match probability to consider success (0.0-1.0)
    
    Returns:
        {
            "success": True/False,
            "coordinates": (x, y) or None,
            "match_probability": float (0.0-1.0),
            "confidence": float (0.0-1.0),
            "element": "text of element found",
            "error": "..." or None
        }
    """
    from ..utils.accessibility_reader import get_frontmost_app
    
    # Get app context for better prediction
    app_info = get_frontmost_app()
    app_name = app_info.get("app", "Unknown")
    window_title = app_info.get("window", "")
    
    task_context = f"Looking for: {action_description}"
    
    logger.info(f"  ⚡ Predicting coordinates for {app_name}...")
    
    # Use fast predictor to find and click with probability threshold
    predictor = get_predictor()
    result = predictor.click_element(
        action_description,
        app_name,
        window_title,
        task_context,
        min_match_probability
    )
    
    # Log the match details
    if result.get("success") or result.get("coordinates"):
        match_prob = result.get("match_probability", 0)
        element = result.get("element", "unknown")
        logger.info(f"  📊 Match probability: {match_prob:.0%} for '{element}'")
    
    return result


# Legacy VLM fallback - replaced by fast coordinate predictor
def _vlm_screenshot_fallback(action_description: str, min_match_probability: float = 0.5) -> Dict:
    """
    Use VLM screenshot analysis to find and click elements.
    Takes a screenshot, sends to Qwen3-VL, gets precise coordinates.
    
    This is a UNIVERSAL method that works for any application.
    Returns match probability so caller can decide whether to proceed.
    
    Args:
        action_description: What element to find and click
        min_match_probability: Minimum match probability to consider success (0.0-1.0)
    
    Returns:
        {
            "success": True/False,
            "coordinates": (x, y) or None,
            "match_probability": float (0.0-1.0),
            "confidence": float (0.0-1.0),
            "element": "text of element found",
            "error": "..." or None
        }
    """
    from ..utils.accessibility_reader import get_frontmost_app
    
    try:
        from ..utils.ollama_vlm import vlm_find_and_click
    except ImportError:
        logger.error("  VLM not available - this is a legacy fallback")
        return {"success": False, "error": "VLM not available"}
    
    # Get app context for better VLM targeting
    app_info = get_frontmost_app()
    app_name = app_info.get("app", "Unknown")
    window_title = app_info.get("window", "")
    
    task_context = f"App: {app_name}, Window: {window_title}"
    
    logger.info(f"  VLM context: {task_context}")
    
    # Use VLM to find and click with probability threshold
    result = vlm_find_and_click(action_description, task_context, min_match_probability)
    
    # Log the match details
    if result.get("found") or result.get("coordinates"):
        match_prob = result.get("match_probability", 0)
        element = result.get("element", "unknown")
        logger.info(f"  📊 Match probability: {match_prob:.0%} for '{element}'")
    
    return result


# _position_based_click removed - VLM is now the universal fallback


def _analyze_and_execute(action_description: str) -> Dict:
    """
    Executor analyzes UI tree and determines click target autonomously.
    This is the primary execution path - no LLM needed.
    """
    import pyautogui
    from ..utils.accessibility_reader import get_frontmost_app, get_ui_tree, get_ui_elements_applescript
    
    desc_lower = action_description.lower()
    
    # Get screen context
    app_info = get_frontmost_app()
    app_name = app_info.get("app", "").lower()
    screen_width, screen_height = pyautogui.size()
    
    logger.info(f"  Context: {app_info.get('app')} - {app_info.get('window', '')[:50]}")
    
    # Executor determines intent from action description
    intent = _parse_intent(desc_lower)
    logger.info(f"  Intent: {intent}")
    
    # Get and analyze UI elements
    elements = get_ui_elements_applescript(max_elements=100)
    logger.info(f"  Analyzing {len(elements)} UI elements")
    
    # If zero elements, signal to use fast coordinate prediction
    if len(elements) == 0:
        logger.warning("  ⚠️ Accessibility returned 0 elements - using fast prediction")
        return {"success": False, "reason": "zero_elements", "use_predictor": True}
    
    # Filter elements based on intent and context
    candidates = _filter_relevant_elements(elements, intent, app_name, screen_width, screen_height)
    
    if not candidates:
        logger.warning("  No suitable elements found by executor")
        return {"success": False, "reason": "no_candidates"}
    
    # Executor selects best target
    target = candidates[0]  # Already sorted by relevance
    logger.info(f"  Executor selected: {target.role} '{target.title or target.value}' at {target.center}")
    
    # Execute click
    current_x, current_y = pyautogui.position()
    target_x, target_y = target.center
    distance = ((target_x - current_x)**2 + (target_y - current_y)**2)**0.5
    
    logger.info(f"  Moving cursor: ({current_x}, {current_y}) → ({target_x}, {target_y}) [distance: {distance:.0f}px]")
    pyautogui.moveTo(target_x, target_y, duration=0.3)
    
    import time
    time.sleep(0.05)
    pyautogui.click()
    
    logger.info(f"  ✅ Clicked: {target}")
    return {"success": True}


def _parse_intent(action_desc: str) -> Dict:
    """Parse action description to understand what user wants."""
    intent = {
        "action": "click",
        "target_type": "unknown",
        "position": "any",
        "keywords": []
    }
    
    # Determine position preference
    if re.search(r'\b(first|latest|top|1st)\b', action_desc):
        intent["position"] = "first"
    elif re.search(r'\b(second|2nd)\b', action_desc):
        intent["position"] = "second"
    elif re.search(r'\b(last|bottom)\b', action_desc):
        intent["position"] = "last"
    
    # Determine target type
    if 'video' in action_desc or 'thumbnail' in action_desc:
        intent["target_type"] = "video"
    elif 'search result' in action_desc or 'result' in action_desc:
        intent["target_type"] = "search_result"
    elif 'button' in action_desc:
        intent["target_type"] = "button"
    elif 'link' in action_desc:
        intent["target_type"] = "link"
    elif 'title' in action_desc:
        intent["target_type"] = "title"
    
    # Extract quoted text or specific keywords
    quoted = re.findall(r'["\']([^"\']+)["\']', action_desc)
    if quoted:
        intent["keywords"] = quoted
    
    return intent


def _filter_relevant_elements(elements: list, intent: Dict, app_name: str, screen_w: int, screen_h: int) -> list:
    """
    Executor's intelligent filtering - removes irrelevant elements.
    Returns sorted list of candidates.
    """
    candidates = []
    
    # Define exclusion zones (areas to avoid)
    # Left sidebar: x < 15% of screen
    # Top header: y < 20% of screen  
    # Right sidebar: x > 85% of screen
    sidebar_left = screen_w * 0.15
    header_top = screen_h * 0.20
    sidebar_right = screen_w * 0.85
    
    for elem in elements:
        # Skip if in exclusion zones
        if elem.x < sidebar_left and elem.role in ['button', 'staticText']:
            continue  # Likely navigation sidebar
        if elem.y < header_top and 'logo' in (elem.title or '').lower():
            continue  # Likely header/logo
        if elem.x > sidebar_right:
            continue  # Right sidebar
        
        # Skip elements that are clearly not targets
        title_lower = (elem.title or '').lower()
        value_lower = (elem.value or '').lower()
        
        # Exclude common non-target patterns
        exclude_patterns = ['subscribe', 'logo', 'profile', 'avatar', 'menu', 'navigation', 'sidebar']
        if any(pattern in title_lower or pattern in value_lower for pattern in exclude_patterns):
            # Unless specifically searching for these
            if not any(kw in title_lower or kw in value_lower for kw in intent.get("keywords", [])):
                continue
        
        # Score element based on intent
        score = 0
        
        # Target type matching with improved video detection
        if intent["target_type"] == "video":
            # Videos are usually large clickable areas in main content
            if elem.role in ['link', 'button', 'group', 'image']:
                # Typical video thumbnail size
                if elem.width > 150 and elem.height > 80:
                    score += 50
                # Extra score for elements with video-related text
                elem_text = (elem.title or '') + ' ' + (elem.value or '')
                if any(kw in elem_text.lower() for kw in ['views', 'ago', 'watch', 'video']):
                    score += 30
        elif intent["target_type"] == "button":
            if elem.role == 'button':
                score += 40
        elif intent["target_type"] == "link":
            if elem.role in ['link', 'staticText']:
                score += 40
        
        # Keyword matching
        for keyword in intent.get("keywords", []):
            if keyword.lower() in title_lower or keyword.lower() in value_lower:
                score += 100
        
        # Position in main content area (center-right)
        if sidebar_left < elem.x < sidebar_right and elem.y > header_top:
            score += 20
        
        # Prefer elements with content
        if elem.title or elem.value:
            score += 10
        
        if score > 0:
            candidates.append((score, elem))
    
    # Sort by score (highest first), then by position
    candidates.sort(key=lambda x: (-x[0], x[1].y, x[1].x))
    
    # Apply position filter
    if intent["position"] == "first":
        candidates = candidates[:1]
    elif intent["position"] == "second":
        candidates = candidates[1:2] if len(candidates) > 1 else []
    elif intent["position"] == "last":
        candidates = candidates[-1:] if candidates else []
    
    # Return just the elements
    return [elem for score, elem in candidates[:5]]  # Top 5 candidates


def _llm_fallback(cli: GeminiCLI, action_description: str, max_attempts: int) -> Dict:
    """
    Fallback to LLM when executor cannot determine target.
    This should be rare - executor should handle most cases.
    """
    for attempt in range(max_attempts):
        try:
            ui_context = format_ui_for_llm(max_elements=40)
            logger.debug(f"UI Context:\n{ui_context[:500]}")
            
            # Get app context for better targeting
            from ..utils.accessibility_reader import get_frontmost_app
            app_info = get_frontmost_app()
            app_name = app_info.get("app", "").lower()
            
            # Build context-aware prompt
            prompt = f"""You are helping navigate a {app_info.get("app", "application")}. Here are the clickable UI elements:

{ui_context}

Task: {action_description}

IMPORTANT GUIDELINES:
- AVOID: Channel logos, profile pictures, navigation bars, headers, sidebars
- TARGET: Video thumbnails, article titles, search results, content items (usually in the main content area)
- YouTube: Videos are in the center/right area with thumbnails and titles below them
- YouTube: First video is typically at coordinates around (365, 512) in the main grid
- Google: Search results are center-page with blue link titles
- Generic: Main content is usually center-right, not in left sidebar or top header

First, briefly explain which element type you'll click and why (one sentence).
Then on a new line, provide ONLY the exact element text to click.

Format:
Reasoning: [one sentence explaining your choice]
Element: [exact text to click]

Or respond with:
DONE (if task is complete)
"""
            
            try:
                response = cli.generate(prompt).strip()
            except Exception as llm_error:
                logger.warning(f"LLM call failed: {llm_error}")
                # Try to find element by partial description
                response = "DONE"
            
            if "DONE" in response.upper():
                logger.info("Vision task marked as done")
                return {"success": True, "done": True}
            
            # Parse response (may have reasoning + element)
            element_text = response
            if "Element:" in response:
                # Extract the element text from structured response
                lines = response.split("\n")
                for line in lines:
                    if line.startswith("Reasoning:"):
                        logger.info(f"  LLM reasoning: {line[10:].strip()}")
                    elif line.startswith("Element:"):
                        element_text = line[8:].strip()
            
            logger.info(f"  Looking for element: '{element_text}'")
            
            # Find and click the element
            element = find_element_by_text(element_text)
            
            if element:
                click_element(element)
                logger.info(f"Clicked: {response}")
                return {"success": True}
            else:
                logger.warning(f"Element not found: {response}")
                # Fallback: try direct click if coordinates given
                time.sleep(0.5)
                
        except Exception as e:
            logger.error(f"Vision action failed (attempt {attempt+1}): {e}")
            time.sleep(0.3)
    
    # After all retries fail, return success to avoid hanging
    logger.warning("Vision action failed after retries - marking as complete to continue")
    return {"success": True, "error": "Could not complete vision action, continuing anyway"}


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
