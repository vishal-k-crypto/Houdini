"""
Semantic Checker - Lightweight validation without LLM calls.

This module provides fast semantic checking by comparing:
1. Expected state (from planner/macro step)
2. Actual state (from accessibility tree)

If there's a clear mismatch, it triggers an immediate interrupt
without needing expensive LLM inference.

This is the "Dual-Path Validation" approach:
- Fast path: Semantic rules + keyword matching (< 1ms)
- Slow path: Full LLM analysis (only when fast path is inconclusive)
"""

import re
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum

# Lazy imports for accessibility
_accessibility_reader = None


def _get_accessibility_reader():
    """Lazy import of accessibility reader."""
    global _accessibility_reader
    if _accessibility_reader is None:
        try:
            from ..utils.accessibility_reader import get_frontmost_app
            _accessibility_reader = get_frontmost_app
        except ImportError:
            _accessibility_reader = lambda: {"app": "Unknown", "window": ""}
    return _accessibility_reader


class SemanticMismatchType(str, Enum):
    """Types of semantic mismatches detected."""
    APP_MISMATCH = "app_mismatch"           # Wrong app is active
    WINDOW_MISMATCH = "window_mismatch"     # Wrong window/tab
    CONTEXT_MISMATCH = "context_mismatch"   # General context mismatch
    NONE = "none"                            # No mismatch detected


@dataclass
class SemanticCheckResult:
    """Result of a semantic check."""
    is_valid: bool
    mismatch_type: SemanticMismatchType
    expected: str
    actual: str
    confidence: float  # 0.0 to 1.0
    reason: str
    should_interrupt: bool  # True if execution should be interrupted
    
    def __bool__(self):
        return self.is_valid


# ============================================================
# APP NAME MAPPINGS
# Common app name variations and aliases
# ============================================================

APP_ALIASES: Dict[str, List[str]] = {
    # Browsers
    "safari": ["safari", "webkit"],
    "chrome": ["google chrome", "chrome", "chromium"],
    "firefox": ["firefox", "mozilla firefox"],
    "arc": ["arc", "arc browser"],
    "edge": ["microsoft edge", "edge"],
    "brave": ["brave browser", "brave"],
    
    # System apps
    "finder": ["finder"],
    "calculator": ["calculator", "calc"],
    "notes": ["notes"],
    "reminders": ["reminders"],
    "calendar": ["calendar", "ical"],
    "mail": ["mail", "apple mail"],
    "messages": ["messages", "imessage"],
    "facetime": ["facetime"],
    "photos": ["photos"],
    "music": ["music", "itunes", "apple music"],
    "settings": ["system settings", "system preferences", "settings"],
    "terminal": ["terminal", "iterm", "iterm2", "warp", "hyper"],
    
    # Productivity
    "vscode": ["visual studio code", "code", "vscode", "vs code"],
    "word": ["microsoft word", "word"],
    "excel": ["microsoft excel", "excel"],
    "powerpoint": ["microsoft powerpoint", "powerpoint"],
    "pages": ["pages"],
    "numbers": ["numbers"],
    "keynote": ["keynote"],
    
    # Communication
    "slack": ["slack"],
    "discord": ["discord"],
    "teams": ["microsoft teams", "teams"],
    "zoom": ["zoom", "zoom.us"],
    "whatsapp": ["whatsapp", "whatsapp web"],
    "telegram": ["telegram"],
    "signal": ["signal"],
    
    # Development
    "xcode": ["xcode"],
    "android studio": ["android studio"],
    "intellij": ["intellij idea", "intellij"],
    "pycharm": ["pycharm"],
    "sublime": ["sublime text", "sublime"],
    "atom": ["atom"],
    
    # Media
    "spotify": ["spotify"],
    "vlc": ["vlc", "vlc media player"],
    "quicktime": ["quicktime player", "quicktime"],
    
    # Utilities
    "spotlight": ["spotlight"],
    "launchpad": ["launchpad"],
    "activity monitor": ["activity monitor"],
}

# Reverse mapping: alias -> canonical name
ALIAS_TO_CANONICAL: Dict[str, str] = {}
for canonical, aliases in APP_ALIASES.items():
    for alias in aliases:
        ALIAS_TO_CANONICAL[alias.lower()] = canonical


def normalize_app_name(app_name: str) -> str:
    """Normalize app name to canonical form."""
    if not app_name:
        return ""
    name_lower = app_name.lower().strip()
    return ALIAS_TO_CANONICAL.get(name_lower, name_lower)


def apps_match(expected: str, actual: str) -> Tuple[bool, float]:
    """
    Check if two app names refer to the same application.
    
    Returns:
        (match: bool, confidence: float)
    """
    if not expected or not actual:
        return (False, 0.0)
    
    expected_norm = normalize_app_name(expected)
    actual_norm = normalize_app_name(actual)
    
    # Exact match after normalization
    if expected_norm == actual_norm:
        return (True, 1.0)
    
    # Partial match (one contains the other)
    if expected_norm in actual_norm or actual_norm in expected_norm:
        return (True, 0.9)
    
    # Check if both are browsers (browser is browser)
    browsers = {"safari", "chrome", "firefox", "arc", "edge", "brave"}
    if expected_norm in browsers and actual_norm in browsers:
        # Different browsers, but both are browsers - partial match
        return (True, 0.7)
    
    # Check if both are terminals
    terminals = {"terminal", "iterm", "iterm2", "warp", "hyper"}
    if expected_norm in terminals and actual_norm in terminals:
        return (True, 0.8)
    
    return (False, 0.0)


# ============================================================
# CONTEXT EXTRACTORS
# Extract expected app/context from macro steps
# ============================================================

# Words to strip from extracted app names
STRIP_WORDS = {"app", "application", "program", "to", "and", "the", "a", "an", "for", "with"}

# Patterns to extract app names from step descriptions
APP_EXTRACTION_PATTERNS = [
    r"open\s+(?:the\s+)?(\w+)",                      # "open Safari", "open the calculator"
    r"launch\s+(?:the\s+)?(\w+)",                    # "launch Chrome"
    r"switch\s+to\s+(?:the\s+)?(\w+)",               # "switch to Finder"
    r"go\s+to\s+(?:the\s+)?(\w+)",                   # "go to Safari"
    r"use\s+(\w+)",                                   # "use Calculator"
    r"in\s+(?:the\s+)?(\w+)",                        # "in Safari"
    r"navigate\s+to\s+(?:the\s+)?(\w+)",             # "navigate to Chrome"
]

# Keywords that indicate expected context in step descriptions
CONTEXT_KEYWORDS = {
    "browser": ["safari", "chrome", "firefox", "browser", "web", "url", "website"],
    "search": ["google", "bing", "duckduckgo", "query"],  # removed "search" - too generic
    "messaging": ["whatsapp", "message", "chat", "telegram", "signal", "slack"],
    "email": ["mail", "email", "outlook", "gmail"],
    "terminal": ["terminal", "command", "shell", "bash", "zsh"],
    "code": ["code", "vscode", "editor", "ide", "xcode"],
    "media": ["youtube", "video", "music", "spotify", "play"],
}


def extract_expected_app(step_description: str) -> Optional[str]:
    """
    Extract the expected app name from a macro step description.
    
    Examples:
        "Open Safari" -> "safari"
        "Navigate to Chrome" -> "chrome"
        "Use the Calculator" -> "calculator"
    """
    if not step_description:
        return None
    
    step_lower = step_description.lower()
    
    # First, check for known app names directly in the text (most reliable)
    for canonical, aliases in APP_ALIASES.items():
        for alias in aliases:
            # Use word boundaries to avoid partial matches
            if re.search(r'\b' + re.escape(alias.lower()) + r'\b', step_lower):
                return canonical
    
    # Try pattern matching for unknown apps
    for pattern in APP_EXTRACTION_PATTERNS:
        match = re.search(pattern, step_lower, re.IGNORECASE)
        if match:
            extracted = match.group(1).strip()
            # Skip common non-app words
            if extracted in STRIP_WORDS:
                continue
            # Validate it's a known app
            normalized = normalize_app_name(extracted)
            if normalized in APP_ALIASES or normalized in ALIAS_TO_CANONICAL:
                return normalized
            # Check it's not a generic word
            if extracted not in STRIP_WORDS and len(extracted) > 2:
                return extracted
    
    return None


def extract_expected_context(step_description: str, step_context: str = "") -> Dict[str, any]:
    """
    Extract expected context from step description and context hint.
    
    Returns:
        Dict with 'app', 'window_hint', 'domain', 'keywords'
    """
    combined = f"{step_description} {step_context}".lower()
    
    result = {
        "app": extract_expected_app(step_description),
        "window_hint": "",
        "domain": None,
        "keywords": [],
    }
    
    # Extract domain hints (e.g., "google.com", "youtube.com")
    domain_match = re.search(r'(?:go\s+to|visit|navigate\s+to|open)\s+(\w+\.(?:com|org|net|io|dev))', combined)
    if domain_match:
        result["domain"] = domain_match.group(1)
    
    # Extract context keywords
    for domain, keywords in CONTEXT_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                result["keywords"].append(kw)
                if not result["domain"]:
                    result["domain"] = domain
                break
    
    return result


# ============================================================
# MAIN SEMANTIC CHECKER
# ============================================================

class SemanticChecker:
    """
    Fast semantic validation using rules and keyword matching.
    
    This provides instant validation without LLM calls by:
    1. Comparing expected app (from plan) with actual app (from accessibility)
    2. Detecting obvious mismatches (e.g., expected Calculator, got Safari)
    3. Providing high-confidence interrupts for clear mismatches
    
    Usage:
        checker = SemanticChecker()
        result = checker.check_state_match(
            macro_step={"step": "Open Calculator", "context": "Calculator visible"},
            actual_app="Safari",
            actual_window="Google Search"
        )
        if result.should_interrupt:
            # Trigger immediate correction without LLM call
    """
    
    def __init__(self, strict_mode: bool = False):
        """
        Initialize the semantic checker.
        
        Args:
            strict_mode: If True, be more aggressive about detecting mismatches
        """
        self.strict_mode = strict_mode
        self._get_frontmost_app = _get_accessibility_reader()
    
    def get_current_state(self) -> Dict[str, str]:
        """Get current app/window state from accessibility tree."""
        try:
            return self._get_frontmost_app()
        except Exception:
            return {"app": "Unknown", "window": ""}
    
    def check_state_match(
        self,
        macro_step: Dict,
        actual_app: Optional[str] = None,
        actual_window: Optional[str] = None,
    ) -> SemanticCheckResult:
        """
        Check if the current state matches the expected state from the macro step.
        
        Args:
            macro_step: The current macro step dict with 'step' and 'context' keys
            actual_app: Current app name (if None, will be fetched from accessibility)
            actual_window: Current window title (if None, will be fetched from accessibility)
        
        Returns:
            SemanticCheckResult indicating if state is valid or needs interrupt
        """
        # Get actual state if not provided
        if actual_app is None or actual_window is None:
            state = self.get_current_state()
            actual_app = actual_app or state.get("app", "Unknown")
            actual_window = actual_window or state.get("window", "")
        
        step_desc = macro_step.get("step", "")
        step_context = macro_step.get("context", "")
        
        # Extract expected context from step
        expected = extract_expected_context(step_desc, step_context)
        expected_app = expected.get("app")
        
        # If no expected app can be extracted, we can't check
        if not expected_app:
            return SemanticCheckResult(
                is_valid=True,  # Can't determine, so don't interrupt
                mismatch_type=SemanticMismatchType.NONE,
                expected="(unknown)",
                actual=actual_app,
                confidence=0.0,
                reason="Could not extract expected app from step description",
                should_interrupt=False
            )
        
        # Check if apps match
        match, confidence = apps_match(expected_app, actual_app)
        
        if match:
            return SemanticCheckResult(
                is_valid=True,
                mismatch_type=SemanticMismatchType.NONE,
                expected=expected_app,
                actual=actual_app,
                confidence=confidence,
                reason=f"App matches: expected '{expected_app}', got '{actual_app}'",
                should_interrupt=False
            )
        
        # Mismatch detected!
        return SemanticCheckResult(
            is_valid=False,
            mismatch_type=SemanticMismatchType.APP_MISMATCH,
            expected=expected_app,
            actual=actual_app,
            confidence=1.0 - confidence,  # High confidence in mismatch
            reason=f"App mismatch: expected '{expected_app}' but active app is '{actual_app}'",
            should_interrupt=True
        )
    
    def check_action_context(
        self,
        intended_action: str,
        actual_app: Optional[str] = None,
        actual_window: Optional[str] = None,
    ) -> SemanticCheckResult:
        """
        Check if the current context is appropriate for an intended action.
        
        This is a simpler check that doesn't need a full macro step,
        just an action description.
        
        Args:
            intended_action: Description of intended action (e.g., "click search button")
            actual_app: Current app name
            actual_window: Current window title
        
        Returns:
            SemanticCheckResult
        """
        if actual_app is None:
            state = self.get_current_state()
            actual_app = state.get("app", "Unknown")
            actual_window = state.get("window", "")
        
        action_lower = intended_action.lower()
        actual_app_lower = actual_app.lower() if actual_app else ""
        actual_window_lower = actual_window.lower() if actual_window else ""
        
        # Check for obvious mismatches
        mismatches = []
        
        # Typing in URL bar but not in a browser
        if any(x in action_lower for x in ["url bar", "address bar", "url field"]):
            if not any(b in actual_app_lower for b in ["safari", "chrome", "firefox", "arc", "edge", "brave"]):
                mismatches.append(("browser", actual_app))
        
        # WhatsApp action but WhatsApp not active
        if "whatsapp" in action_lower and "whatsapp" not in actual_app_lower:
            mismatches.append(("whatsapp", actual_app))
        
        # Calculator action but Calculator not active
        if "calculator" in action_lower and "calculator" not in actual_app_lower:
            mismatches.append(("calculator", actual_app))
        
        # Search action in search engine
        if any(x in action_lower for x in ["search result", "search box", "google search"]):
            if not any(b in actual_app_lower for b in ["safari", "chrome", "firefox", "arc", "edge", "brave"]):
                mismatches.append(("browser for search", actual_app))
        
        if mismatches:
            expected, actual = mismatches[0]
            return SemanticCheckResult(
                is_valid=False,
                mismatch_type=SemanticMismatchType.CONTEXT_MISMATCH,
                expected=expected,
                actual=actual,
                confidence=0.9,
                reason=f"Context mismatch: action '{intended_action}' expects '{expected}' but active app is '{actual}'",
                should_interrupt=True
            )
        
        return SemanticCheckResult(
            is_valid=True,
            mismatch_type=SemanticMismatchType.NONE,
            expected="",
            actual=actual_app,
            confidence=0.5,  # Lower confidence as we're doing simpler checks
            reason="No obvious context mismatch detected",
            should_interrupt=False
        )
    
    def quick_app_check(self, expected_app: str) -> SemanticCheckResult:
        """
        Quick check if the expected app is currently active.
        
        This is the fastest possible check - just compares app names.
        
        Args:
            expected_app: Name of the app that should be active
        
        Returns:
            SemanticCheckResult
        """
        state = self.get_current_state()
        actual_app = state.get("app", "Unknown")
        
        match, confidence = apps_match(expected_app, actual_app)
        
        return SemanticCheckResult(
            is_valid=match,
            mismatch_type=SemanticMismatchType.NONE if match else SemanticMismatchType.APP_MISMATCH,
            expected=expected_app,
            actual=actual_app,
            confidence=confidence if match else (1.0 - confidence),
            reason=f"{'Match' if match else 'Mismatch'}: expected '{expected_app}', got '{actual_app}'",
            should_interrupt=not match
        )


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_semantic_checker: Optional[SemanticChecker] = None


def get_semantic_checker(strict_mode: bool = False) -> SemanticChecker:
    """Get the singleton SemanticChecker instance."""
    global _semantic_checker
    if _semantic_checker is None:
        _semantic_checker = SemanticChecker(strict_mode=strict_mode)
    return _semantic_checker


def quick_semantic_check(macro_step: Dict) -> SemanticCheckResult:
    """
    Convenience function for quick semantic checks.
    
    Example:
        result = quick_semantic_check({"step": "Open Calculator", "context": "Calculator visible"})
        if result.should_interrupt:
            print(f"Mismatch! {result.reason}")
    """
    checker = get_semantic_checker()
    return checker.check_state_match(macro_step)
