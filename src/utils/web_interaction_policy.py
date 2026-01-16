"""
Web Interaction Policy
Defines rules for interacting with web browsers and websites.

KEY PRINCIPLE:
    When inside a web page (YouTube, Google, etc.), NEVER rely on keyboard
    shortcuts. Websites have custom behavior and shortcuts don't work reliably.
    
    Instead: Take screenshot → Find element visually → Move cursor → Click → Type
    
    This is how humans interact with websites, and it's the most reliable method.
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class InteractionMode(Enum):
    """How to interact with the application."""
    HOTKEYS = "hotkeys"  # Use keyboard shortcuts (native apps)
    VISION = "vision"  # Use vision-based cursor control (websites)
    HYBRID = "hybrid"  # Mix of both depending on context


@dataclass
class WebInteractionRule:
    """Rule for how to interact with a specific context."""
    context: str  # "browser", "youtube", "google", etc.
    mode: InteractionMode
    reasoning: str
    forbidden_hotkeys: List[str]  # Hotkeys that should never be used
    vision_actions: List[str]  # Actions that require vision


# Browser applications
BROWSER_APPS = [
    "Safari",
    "Google Chrome",
    "Chrome",
    "Firefox",
    "Microsoft Edge",
    "Edge",
    "Arc",
    "Brave"
]


# Websites that require vision-based interaction
VISION_FIRST_DOMAINS = [
    "youtube.com",
    "google.com",
    "facebook.com",
    "twitter.com",
    "instagram.com",
    "reddit.com",
    "amazon.com",
    "netflix.com",
    "github.com",
    "stackoverflow.com",
    "linkedin.com",
    "medium.com",
    "notion.so",
    "figma.com",
    "canva.com",
    "spotify.com/browse",  # Web player
    "mail.google.com",  # Gmail
    "docs.google.com",  # Google Docs
    "drive.google.com",  # Google Drive
    # Add more as needed - basically ANY website content
]


# Actions that MUST use vision when in browser
BROWSER_VISION_REQUIRED_ACTIONS = [
    "search on website",
    "search for video",
    "search for product",
    "click video",
    "click link",
    "click button on page",
    "fill form",
    "type in field",
    "select dropdown",
    "play video",
    "submit form",
    "like post",
    "comment",
    "share",
    "scroll to element",
    "find and click",
]


# Hotkeys that should NEVER be used for website interaction
FORBIDDEN_WEBSITE_HOTKEYS = [
    "command,f",  # Find in page - NOT for search on website!
    "ctrl,f",  # Find in page
    "command,k",  # Browser command bar, not website search
    "command,option,f",  # Not applicable to websites
]


# Only these hotkeys are safe for browser control (not website content)
SAFE_BROWSER_HOTKEYS = {
    "command,l": "Focus URL bar",
    "command,t": "New tab",
    "command,w": "Close tab",
    "command,shift,t": "Reopen closed tab",
    "command,r": "Refresh page",
    "command,left": "Back",
    "command,right": "Forward",
    "command,+": "Zoom in",
    "command,-": "Zoom out",
    "command,0": "Reset zoom",
    "command,shift,]": "Next tab",
    "command,shift,[": "Previous tab",
}


class WebInteractionPolicy:
    """
    Policy engine that determines how to interact with browsers and websites.
    """
    
    def __init__(self):
        self.rules: Dict[str, WebInteractionRule] = self._build_rules()
    
    def _build_rules(self) -> Dict[str, WebInteractionRule]:
        """Build interaction rules for different contexts."""
        return {
            "browser_chrome": WebInteractionRule(
                context="browser_chrome",
                mode=InteractionMode.HYBRID,
                reasoning="Chrome hotkeys work for browser control, but website content requires vision",
                forbidden_hotkeys=FORBIDDEN_WEBSITE_HOTKEYS,
                vision_actions=BROWSER_VISION_REQUIRED_ACTIONS
            ),
            "browser_safari": WebInteractionRule(
                context="browser_safari",
                mode=InteractionMode.HYBRID,
                reasoning="Safari hotkeys work for browser control, but website content requires vision",
                forbidden_hotkeys=FORBIDDEN_WEBSITE_HOTKEYS,
                vision_actions=BROWSER_VISION_REQUIRED_ACTIONS
            ),
            "browser_firefox": WebInteractionRule(
                context="browser_firefox",
                mode=InteractionMode.HYBRID,
                reasoning="Firefox hotkeys work for browser control, but website content requires vision",
                forbidden_hotkeys=FORBIDDEN_WEBSITE_HOTKEYS,
                vision_actions=BROWSER_VISION_REQUIRED_ACTIONS
            ),
            "website_youtube": WebInteractionRule(
                context="website_youtube",
                mode=InteractionMode.VISION,
                reasoning="YouTube has custom UI - search field, video thumbnails must be found visually",
                forbidden_hotkeys=FORBIDDEN_WEBSITE_HOTKEYS + ["command,k", "slash"],
                vision_actions=["search", "click video", "play", "pause", "like", "comment"]
            ),
            "website_google": WebInteractionRule(
                context="website_google",
                mode=InteractionMode.VISION,
                reasoning="Google search results are dynamic - must click links visually",
                forbidden_hotkeys=FORBIDDEN_WEBSITE_HOTKEYS,
                vision_actions=["search", "click result", "next page"]
            ),
            "website_generic": WebInteractionRule(
                context="website_generic",
                mode=InteractionMode.VISION,
                reasoning="Unknown website - always use vision for reliability",
                forbidden_hotkeys=FORBIDDEN_WEBSITE_HOTKEYS,
                vision_actions=BROWSER_VISION_REQUIRED_ACTIONS
            ),
        }
    
    def is_browser_app(self, app_name: str) -> bool:
        """Check if app is a web browser."""
        return any(browser.lower() in app_name.lower() for browser in BROWSER_APPS)
    
    def is_website_action(self, action_description: str) -> bool:
        """
        Check if action is targeting website content (not browser chrome).
        
        Website actions include:
        - Search on website
        - Click elements on page
        - Fill forms
        - Watch videos
        - etc.
        """
        action_lower = action_description.lower()
        
        # Keywords that indicate website interaction
        website_keywords = [
            "search for",
            "click video",
            "click link",
            "click button",
            "click result",
            "click the first",
            "click the",
            "click on",
            "play video",
            "watch",
            "type in field",
            "fill form",
            "submit",
            "like",
            "comment",
            "share",
            "add to cart",
            "checkout",
            "sign in on page",
            "login on site",
            "find and click",
            "locate and click",
            "select result",
            "first result",
            "open result",
            "thumbnail",
            "search box",
            "search field",
        ]
        
        return any(kw in action_lower for kw in website_keywords)
    
    def requires_vision(
        self,
        app_name: str,
        action_description: str,
        window_title: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Determine if an action requires vision-based interaction.
        
        Returns:
            (requires_vision: bool, reason: str)
        """
        # Check if it's a browser app
        if not self.is_browser_app(app_name):
            return False, "Not a browser application"
        
        # Check if it's a website action
        if self.is_website_action(action_description):
            return True, "Website content interaction requires vision (no reliable hotkeys)"
        
        # Check window title for domain
        if window_title:
            for domain in VISION_FIRST_DOMAINS:
                if domain in window_title.lower():
                    return True, f"Known website ({domain}) requires vision-based interaction"
        
        # Default for browsers: if action mentions clicking/finding elements, use vision
        action_lower = action_description.lower()
        if any(word in action_lower for word in ["click", "find", "locate", "search on", "type in"]):
            return True, "Action involves finding elements on page - use vision"
        
        return False, "Browser control action (not website content) can use hotkeys"
    
    def is_hotkey_forbidden(
        self,
        app_name: str,
        hotkey: str,
        action_context: str = ""
    ) -> Tuple[bool, str]:
        """
        Check if a hotkey is forbidden in current context.
        
        Args:
            app_name: Application name
            hotkey: Hotkey string (e.g., "command,f")
            action_context: What the action is trying to accomplish
            
        Returns:
            (is_forbidden: bool, reason: str)
        """
        if not self.is_browser_app(app_name):
            return False, "Not a browser app"
        
        # Normalize hotkey
        hotkey_normalized = hotkey.lower().replace("+", ",")
        
        # Check if it's a forbidden website hotkey
        if hotkey_normalized in [h.lower() for h in FORBIDDEN_WEBSITE_HOTKEYS]:
            return True, f"{hotkey} doesn't work reliably on websites - use vision instead"
        
        # Check if action context indicates website interaction
        if self.is_website_action(action_context):
            # Only safe browser hotkeys allowed
            if hotkey_normalized not in [h.lower() for h in SAFE_BROWSER_HOTKEYS.keys()]:
                return True, f"Website interaction - {hotkey} may not work as expected, use vision"
        
        return False, "Hotkey is safe for this context"
    
    def convert_to_vision_action(
        self,
        action_description: str,
        app_name: str,
        window_title: Optional[str] = None
    ) -> Optional[str]:
        """
        Convert a hotkey-based action to a vision-based action.
        
        Example:
            "Press Cmd+F to search" → "Take screenshot, find search field, click it, then type search query"
        
        Returns:
            Vision-based action description, or None if conversion not possible
        """
        action_lower = action_description.lower()
        
        # Common patterns
        if "search" in action_lower or "find" in action_lower:
            return "Take screenshot, locate the search field on the page, move cursor and click it to focus"
        
        if "play" in action_lower and "video" in action_lower:
            return "Take screenshot, find the video thumbnail or play button, move cursor and click it"
        
        if "click" in action_lower and any(w in action_lower for w in ["button", "link", "video", "result"]):
            # Already a click action - just emphasize vision
            return f"Take screenshot, visually locate and click the target element: {action_description}"
        
        if "type" in action_lower or "enter" in action_lower:
            return "Take screenshot, find the input field, move cursor to click it, then type the text"
        
        # Generic conversion
        return f"Use vision to: {action_description}"
    
    def get_recommended_approach(
        self,
        app_name: str,
        goal: str,
        window_title: Optional[str] = None
    ) -> str:
        """
        Get recommended approach for accomplishing a goal.
        
        Returns:
            Human-readable recommendation
        """
        requires_vision, reason = self.requires_vision(app_name, goal, window_title)
        
        if requires_vision:
            return f"""
🔍 VISION-BASED APPROACH REQUIRED

Reason: {reason}

Steps:
1. Take screenshot of current page
2. Visually locate the target element (search field, button, link, etc.)
3. Get precise cursor coordinates for the element
4. Move cursor to the element naturally (like a human)
5. Click the element
6. Type any required text
7. Wait for page response
8. Take another screenshot to verify

DO NOT use keyboard shortcuts like Cmd+F, Cmd+K, etc. on websites.
They are unreliable and often don't work as expected.
"""
        else:
            return f"""
⌨️ HOTKEY APPROACH ACCEPTABLE

Reason: {reason}

You may use browser control hotkeys like:
- Cmd+L (focus URL bar)
- Cmd+T (new tab)
- Cmd+R (refresh)
- Cmd+W (close tab)

But if you need to interact with page content, switch to vision-based approach.
"""


# Global instance
_policy = None


def get_policy() -> WebInteractionPolicy:
    """Get global policy instance."""
    global _policy
    if _policy is None:
        _policy = WebInteractionPolicy()
    return _policy


def check_action_requires_vision(
    app_name: str,
    action: str,
    window_title: Optional[str] = None
) -> Tuple[bool, str]:
    """Quick check if action requires vision."""
    return get_policy().requires_vision(app_name, action, window_title)


def validate_hotkey_for_web(
    app_name: str,
    hotkey: str,
    action_context: str = ""
) -> Tuple[bool, str]:
    """Quick validation of hotkey for web context."""
    policy = get_policy()
    is_forbidden, reason = policy.is_hotkey_forbidden(app_name, hotkey, action_context)
    return not is_forbidden, reason
