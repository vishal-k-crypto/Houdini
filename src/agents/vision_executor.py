"""
Vision Executor - Uses accessibility tree for smart element interaction.
Much faster than OCR/screenshot-based approaches.
"""

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
    Execute a vision-based action using accessibility tree (no screenshots).
    
    Args:
        cli: Gemini CLI for LLM queries
        action_description: e.g., "click first search result"
        max_attempts: retry count
    
    Returns: {"success": True/False, "error": "..."}
    """
    for attempt in range(max_attempts):
        try:
            # Get UI tree (fast, no screenshot)
            ui_context = format_ui_for_llm(max_elements=40)
            logger.debug(f"UI Context:\n{ui_context[:500]}")
            
            # Ask LLM to identify what to click
            prompt = f"""You have access to the current screen elements.

{ui_context}

Task: {action_description}

Which element should I interact with? 
Respond with ONLY the element text to click, e.g.: "First Result"
Or respond with: DONE (if task is complete)
"""
            
            response = cli.generate(prompt).strip()
            
            if "DONE" in response.upper():
                logger.info("Vision task marked as done")
                return {"success": True, "done": True}
            
            # Find and click the element
            element = find_element_by_text(response)
            
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
    
    return {"success": False, "error": "Could not complete vision action"}


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
