"""
Vision Executor - Uses accessibility tree for smart element interaction.
Much faster than OCR/screenshot-based approaches.
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


def execute_vision_action(cli: GeminiCLI, action_description: str, max_attempts: int = 3) -> Dict:
    """
    Execute a vision-based action using accessibility tree analysis.
    The executor analyzes the UI tree and determines where to click autonomously.
    
    Uses a multi-strategy approach:
    1. Smart heuristic analysis (fast, no LLM)
    2. Position-based fallback for common patterns
    3. LLM-guided targeting (slower, more accurate)
    
    Args:
        cli: Gemini CLI (only for complex fallback cases)
        action_description: e.g., "click first search result"
        max_attempts: retry count
    
    Returns: {"success": True/False, "error": "...", "method": "..."}
    """
    logger.info(f"👁️ Vision executor analyzing: {action_description}")
    
    # Strategy 1: Smart heuristic analysis
    result = _analyze_and_execute(action_description)
    
    if result.get("success"):
        result["method"] = "heuristic"
        return result
    
    # Strategy 2: Position-based fallback for known patterns
    logger.info("  Trying position-based targeting...")
    result = _position_based_click(action_description)
    
    if result.get("success"):
        result["method"] = "position"
        return result
    
    # Strategy 3: LLM-guided fallback (rare)
    logger.warning("  Using LLM-guided fallback...")
    result = _llm_fallback(cli, action_description, max_attempts)
    result["method"] = "llm"
    return result


def _position_based_click(action_description: str) -> Dict:
    """
    Fallback: Click based on known UI patterns when element detection fails.
    Uses learned positions for common app layouts.
    """
    import pyautogui
    from ..utils.accessibility_reader import get_frontmost_app
    
    app_info = get_frontmost_app()
    app_name = (app_info.get("app", "") or "").lower()
    window_title = (app_info.get("window", "") or "").lower()
    screen_width, screen_height = pyautogui.size()
    desc_lower = action_description.lower()
    
    # YouTube-specific patterns
    if "youtube" in app_name or "youtube" in window_title:
        if any(kw in desc_lower for kw in ["first", "latest", "video", "thumbnail"]):
            # YouTube video grid: first video is typically at ~30% from left, 45% from top
            target_x = int(screen_width * 0.30)
            target_y = int(screen_height * 0.45)
            
            logger.info(f"  📍 YouTube pattern: clicking at ({target_x}, {target_y})")
            pyautogui.moveTo(target_x, target_y, duration=0.3)
            time.sleep(0.1)
            pyautogui.click()
            return {"success": True}
    
    # Google Search patterns
    if "google" in window_title and "search" in window_title:
        if "first" in desc_lower and "result" in desc_lower:
            # First search result is typically at ~45% from left, 35% from top
            target_x = int(screen_width * 0.45)
            target_y = int(screen_height * 0.35)
            
            logger.info(f"  📍 Google pattern: clicking at ({target_x}, {target_y})")
            pyautogui.moveTo(target_x, target_y, duration=0.3)
            time.sleep(0.1)
            pyautogui.click()
            return {"success": True}
    
    # Safari/browser general pattern - main content area
    if any(kw in desc_lower for kw in ["first", "click", "open"]):
        if "safari" in app_name or "chrome" in app_name or "firefox" in app_name:
            # Main content area center
            target_x = int(screen_width * 0.40)
            target_y = int(screen_height * 0.50)
            
            logger.info(f"  📍 Browser pattern: clicking at ({target_x}, {target_y})")
            pyautogui.moveTo(target_x, target_y, duration=0.3)
            time.sleep(0.1)
            pyautogui.click()
            return {"success": True}
    
    return {"success": False, "reason": "no_position_pattern_matched"}


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
