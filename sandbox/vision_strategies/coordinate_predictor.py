"""
Fast Coordinate Predictor using Qwen3-Coder
Predicts precise click coordinates based on UI layout reasoning.
Much faster than vision models.
"""

import time
from typing import Dict, Tuple, Optional
from .logging import logger
from .ollama_client import OllamaClient

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    logger.warning("pyautogui not available")


class CoordinatePredictor:
    """
    Uses Qwen3-Coder to reason about UI layouts and predict precise coordinates.
    Fast and works universally for any application.
    """
    
    def __init__(self, model_name: str = "qwen3-coder:480b-cloud"):
        """Initialize coordinate predictor."""
        self.model_name = model_name
        self.client = OllamaClient(model_name=model_name)
        self.screen_width, self.screen_height = self._get_screen_size()
    
    def _get_screen_size(self) -> Tuple[int, int]:
        """Get screen dimensions."""
        if PYAUTOGUI_AVAILABLE:
            return pyautogui.size()
        return (1920, 1080)  # Default fallback
    
    def predict_coordinates(
        self,
        element_description: str,
        app_name: str,
        window_title: str = "",
        context: str = ""
    ) -> Dict:
        """
        Predict precise coordinates for a UI element using fast reasoning.
        
        Args:
            element_description: What to find (e.g., "search field", "contact named kushal")
            app_name: Application name
            window_title: Window title
            context: Additional context
        
        Returns:
            {
                "found": True/False,
                "x": int,
                "y": int,
                "confidence": float (0-1),
                "match_probability": float (0-1),
                "element": str,
                "reasoning": str
            }
        """
        start_time = time.time()
        
        prompt = f"""You are an EXPERT UI coordinate calculator. Your predictions must be PIXEL-PERFECT.

## SCREEN INFO
- Size: {self.screen_width}x{self.screen_height} pixels
- Coordinate system: (0,0) = top-left corner
- Click target: CENTER of the element (middle of clickable area)

## APPLICATION
- App: {app_name}
- Window: {window_title}
- Context: {context}

## ELEMENT TO FIND
{element_description}

## CRITICAL: PRECISE COORDINATE CALCULATION

### WhatsApp Desktop Layout (measured precisely):
- **Window margins**: Left=0, Top=0 (fullscreen typically)
- **Sidebar width**: ~350-400px
- **Title bar height**: ~70px
- **Search bar**: 
  * Position: Top of left sidebar
  * X: 175px (middle of 350px sidebar)
  * Y: 85px (below 70px title bar, accounting for padding)
  * Size: ~320x40px
- **Contact list items**:
  * First contact: Y=150px
  * Each contact height: ~72px
  * Contact #2: Y=222px, Contact #3: Y=294px
  * X: 175px (middle of sidebar)
- **Message input**:
  * Position: Bottom of chat area
  * X: 50-60% of screen width (depends on window size)
  * Y: 90-95% of screen height
  * For {self.screen_height}px screen: Y≈{int(self.screen_height * 0.92)}px
- **New message/chat button**:
  * Position: Bottom-right or top of sidebar
  * Common: X≈90% of screen width, Y≈92% of screen height

### Safari/Chrome Browser Layout:
- **Address bar**: Y=40-50px, X=50% width
- **Tabs**: Y=10-25px
- **Bookmarks bar**: Y=70-85px

### General App Patterns:
- **Menu bar**: Y=0-25px
- **Toolbar**: Y=40-80px  
- **Sidebar**: X=0-350px
- **Main content**: Center of remaining space
- **Bottom bar**: Y=95-100% height

## CALCULATION METHOD
1. Identify the UI region (toolbar, sidebar, content, etc.)
2. Calculate exact pixel coordinates using measurements above
3. For {app_name}, use the specific patterns for that app
4. Return coordinates for the CLICKABLE CENTER of the element

## MATCH PROBABILITY RATING
Rate how confident you are this element exists and matches:
- 1.0 = Exact match expected (e.g., WhatsApp always has search bar)
- 0.9 = Very likely match (e.g., "kushal" found as "Kushal RU")  
- 0.8 = Probable match (similar name/element exists)
- 0.7 = Possible match (fuzzy match)
- 0.5 = Uncertain (might not exist)
- 0.0 = Won't find (element doesn't exist in this app)

## RESPONSE FORMAT
Return ONLY valid JSON (no markdown, no explanation):
{{
    "found": true,
    "x": <exact integer X coordinate - USE MEASUREMENTS ABOVE>,
    "y": <exact integer Y coordinate - USE MEASUREMENTS ABOVE>,
    "confidence": <0.85-1.0 for precise calculations, lower if estimating>,
    "match_probability": <0.0-1.0 element match likelihood>,
    "element": "what you found",
    "reasoning": "SHOW YOUR CALCULATION: e.g., 'Sidebar width 350px / 2 = 175px, Title 70px + padding 15px = 85px'"
}}

## EXAMPLES WITH CALCULATIONS

WhatsApp search bar on {self.screen_width}x{self.screen_height}:
{{"found": true, "x": 175, "y": 85, "confidence": 0.98, "match_probability": 1.0, "element": "search field", "reasoning": "Sidebar 350px/2=175px X, Title bar 70px + padding 15px = 85px Y"}}

WhatsApp first contact on {self.screen_width}x{self.screen_height}:
{{"found": true, "x": 175, "y": 150, "confidence": 0.95, "match_probability": 0.9, "element": "contact kushal", "reasoning": "Sidebar 350px/2=175px X, First contact below search at 150px Y"}}

WhatsApp second contact:
{{"found": true, "x": 175, "y": 222, "confidence": 0.95, "match_probability": 0.9, "element": "contact", "reasoning": "First contact 150px + 72px row height = 222px Y"}}

WhatsApp message input on {self.screen_width}x{self.screen_height}:
{{"found": true, "x": {int(self.screen_width * 0.6)}, "y": {int(self.screen_height * 0.92)}, "confidence": 0.93, "match_probability": 1.0, "element": "message input", "reasoning": "Chat area at 60% width={int(self.screen_width * 0.6)}px, Bottom at 92% height={int(self.screen_height * 0.92)}px"}}

REMEMBER: Use the EXACT measurements provided. Show your math in reasoning!
"""

        try:
            response = self.client.generate(prompt, temperature=0.2)
            duration = time.time() - start_time
            
            # Parse JSON from response
            result = self._parse_json_response(response)
            
            if result and result.get("found"):
                x = result.get("x")
                y = result.get("y")
                
                # Validate and bounds-check coordinates
                if x is not None and y is not None:
                    x = int(x)
                    y = int(y)
                    x = max(0, min(x, self.screen_width - 1))
                    y = max(0, min(y, self.screen_height - 1))
                    
                    confidence = result.get("confidence", 0.8)
                    match_prob = result.get("match_probability", 0.8)
                    element = result.get("element", "unknown")
                    reasoning = result.get("reasoning", "")
                    
                    logger.info(f"  ⚡ Fast prediction ({duration:.1f}s): ({x}, {y})")
                    logger.info(f"     Confidence: {confidence:.0%}, Match: {match_prob:.0%}")
                    logger.info(f"     Element: {element}")
                    logger.debug(f"     Reasoning: {reasoning}")
                    
                    return {
                        "found": True,
                        "x": x,
                        "y": y,
                        "confidence": confidence,
                        "match_probability": match_prob,
                        "element": element,
                        "reasoning": reasoning
                    }
            
            logger.warning(f"  Could not predict coordinates ({duration:.1f}s)")
            return {
                "found": False,
                "x": None,
                "y": None,
                "confidence": 0.0,
                "match_probability": 0.0,
                "element": None,
                "reasoning": result.get("reasoning", "unable to predict") if result else "no response"
            }
            
        except Exception as e:
            logger.error(f"Coordinate prediction error: {e}")
            return {
                "found": False,
                "x": None,
                "y": None,
                "confidence": 0.0,
                "match_probability": 0.0,
                "element": None,
                "reasoning": str(e)
            }
    
    def _parse_json_response(self, response: str) -> Optional[Dict]:
        """Extract and parse JSON from response."""
        import json
        import re
        
        try:
            # Remove markdown code blocks
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
            else:
                # Find JSON object
                start = response.find("{")
                end = response.rfind("}") + 1
                if start != -1 and end != 0:
                    json_str = response[start:end]
                else:
                    json_str = response
            
            return json.loads(json_str)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            logger.debug(f"Response was: {response[:500]}")
            return None
    
    def click_element(
        self,
        element_description: str,
        app_name: str,
        window_title: str = "",
        context: str = "",
        min_match_probability: float = 0.6,
        try_adjustments: bool = False
    ) -> Dict:
        """
        Predict coordinates and click element.
        
        Args:
            try_adjustments: If True, will try small position adjustments if needed
        
        Returns:
            {"success": True/False, "coordinates": (x,y), "match_probability": float, ...}
        """
        result = self.predict_coordinates(element_description, app_name, window_title, context)
        
        if not result.get("found"):
            return {
                "success": False,
                "coordinates": None,
                "match_probability": 0.0,
                "error": "Could not predict coordinates"
            }
        
        match_prob = result.get("match_probability", 0)
        
        if match_prob < min_match_probability:
            logger.warning(f"  Match probability {match_prob:.0%} below threshold {min_match_probability:.0%}")
            return {
                "success": False,
                "coordinates": (result["x"], result["y"]),
                "match_probability": match_prob,
                "confidence": result.get("confidence", 0),
                "element": result.get("element"),
                "error": f"Match probability too low: {match_prob:.0%}"
            }
        
        x, y = result["x"], result["y"]
        
        # Try main position first
        click_result = self._try_click(x, y, match_prob, result.get("element"))
        if click_result["success"]:
            return click_result
        
        # If adjustments enabled and confidence is not super high, try nearby positions
        if try_adjustments and result.get("confidence", 1.0) < 0.95:
            logger.info(f"  🔄 Trying position adjustments...")
            adjustments = [
                (0, -10),   # 10px up
                (0, 10),    # 10px down
                (-10, 0),   # 10px left
                (10, 0),    # 10px right
                (-5, -5),   # diagonal
                (5, 5),     # diagonal
            ]
            
            for dx, dy in adjustments:
                adj_x, adj_y = x + dx, y + dy
                # Bounds check
                if 0 <= adj_x < self.screen_width and 0 <= adj_y < self.screen_height:
                    logger.debug(f"  Trying adjusted position ({adj_x}, {adj_y})")
                    adj_result = self._try_click(adj_x, adj_y, match_prob, result.get("element"))
                    if adj_result.get("success"):
                        logger.info(f"  ✅ Success with adjustment ({dx:+d}, {dy:+d})")
                        return adj_result
            
            logger.warning(f"  All position adjustments failed")
        
        return click_result
    
    def _try_click(self, x: int, y: int, match_prob: float, element: str) -> Dict:
        """Try clicking at specific coordinates."""
        try:
            if PYAUTOGUI_AVAILABLE:
                # Move and click
                current_x, current_y = pyautogui.position()
                distance = ((x - current_x)**2 + (y - current_y)**2)**0.5
                duration = min(0.5, max(0.15, distance / 2000))
                
                logger.info(f"  🖱️ Moving to ({x}, {y})")
                pyautogui.moveTo(x, y, duration=duration)
                time.sleep(0.05)
                pyautogui.click()
                logger.info(f"  ✅ Clicked at ({x}, {y}) [match: {match_prob:.0%}]")
            
            return {
                "success": True,
                "coordinates": (x, y),
                "match_probability": match_prob,
                "confidence": 1.0,
                "element": element,
                "error": None
            }
        except Exception as e:
            logger.error(f"Click failed: {e}")
            return {
                "success": False,
                "coordinates": (x, y),
                "match_probability": match_prob,
                "error": str(e)
            }


# Global instance
_predictor = None


def get_predictor() -> CoordinatePredictor:
    """Get or create global predictor instance."""
    global _predictor
    if _predictor is None:
        _predictor = CoordinatePredictor()
    return _predictor


def predict_and_click(
    element_description: str,
    app_name: str,
    window_title: str = "",
    context: str = "",
    min_match_probability: float = 0.6
) -> Dict:
    """
    Convenience function to predict coordinates and click.
    
    Returns:
        {"success": True/False, "coordinates": (x,y), "match_probability": float, ...}
    """
    predictor = get_predictor()
    return predictor.click_element(
        element_description,
        app_name,
        window_title,
        context,
        min_match_probability
    )
