"""
App Knowledge Base - App-specific shortcuts, behaviors, and action patterns.

This module contains knowledge about how different macOS applications work,
their keyboard shortcuts, search mechanisms, and common pitfalls.

The agent uses this to:
1. Select correct shortcuts for each application
2. Verify the right app is focused before executing
3. Provide app-specific action alternatives
4. Learn from failures and update patterns
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import json
from datetime import datetime

from .logging import logger

APP_KNOWLEDGE_FILE = Path(__file__).parent.parent.parent / "data" / "app_knowledge.json"


@dataclass
class AppShortcut:
    """A keyboard shortcut for a specific action in an app."""
    action: str                      # What the shortcut does (e.g., "search")
    keys: List[str]                  # Key combination (e.g., ["command", "option", "f"])
    alternatives: List[List[str]] = field(default_factory=list)  # Alternative key combos
    requires_focus: bool = True      # Whether app must be focused
    notes: str = ""                  # Usage notes


@dataclass 
class AppProfile:
    """Complete profile of an application's behaviors and shortcuts."""
    name: str                        # App name (e.g., "Music")
    bundle_id: str                   # Bundle identifier (e.g., "com.apple.Music")
    
    # Shortcuts by action type
    shortcuts: Dict[str, AppShortcut] = field(default_factory=dict)
    
    # Common mistakes and corrections
    common_mistakes: Dict[str, str] = field(default_factory=dict)
    
    # Success rates for different action patterns
    action_success_rates: Dict[str, float] = field(default_factory=dict)
    
    # Wait times that work well for this app
    optimal_waits: Dict[str, float] = field(default_factory=dict)
    
    # Focus verification patterns (what to look for to confirm focus)
    focus_indicators: List[str] = field(default_factory=list)
    
    def get_shortcut(self, action: str) -> Optional[AppShortcut]:
        """Get the shortcut for an action."""
        return self.shortcuts.get(action)
    
    def get_keys(self, action: str) -> Optional[List[str]]:
        """Get just the key combination for an action."""
        shortcut = self.shortcuts.get(action)
        return shortcut.keys if shortcut else None


# ============================================================
# BUILT-IN APP PROFILES (hardcoded knowledge)
# ============================================================

BUILTIN_APP_PROFILES: Dict[str, AppProfile] = {
    # ---------------- Apple Music ----------------
    "Music": AppProfile(
        name="Music",
        bundle_id="com.apple.Music",
        shortcuts={
            "search": AppShortcut(
                action="search",
                keys=["command", "option", "f"],  # NOT Cmd+F!
                alternatives=[],  # Can also click search field
                notes="Cmd+F does NOT work for search in Music. Use Cmd+Option+F or click the search field."
            ),
            "play_pause": AppShortcut(
                action="play_pause",
                keys=["space"],
                notes="Space toggles play/pause when focus is on player, not search field"
            ),
            "next_track": AppShortcut(
                action="next_track",
                keys=["command", "right"],
            ),
            "previous_track": AppShortcut(
                action="previous_track", 
                keys=["command", "left"],
            ),
            "volume_up": AppShortcut(
                action="volume_up",
                keys=["command", "up"],
            ),
            "volume_down": AppShortcut(
                action="volume_down",
                keys=["command", "down"],
            ),
            "go_to_library": AppShortcut(
                action="go_to_library",
                keys=["command", "1"],
            ),
            "go_to_for_you": AppShortcut(
                action="go_to_for_you",
                keys=["command", "2"],
            ),
            "go_to_browse": AppShortcut(
                action="go_to_browse",
                keys=["command", "3"],
            ),
        },
        common_mistakes={
            "hotkey:command,f": "WRONG! Cmd+F doesn't search in Music. Use hotkey:command,option,f instead.",
            "key:enter": "After searching, use arrow keys to select result, then Enter to play.",
        },
        optimal_waits={
            "app_launch": 2.0,
            "search": 1.5,
            "play": 0.5,
        },
        focus_indicators=["Music", "Apple Music", "♫", "Now Playing"],
    ),
    
    # ---------------- Safari ----------------
    "Safari": AppProfile(
        name="Safari",
        bundle_id="com.apple.Safari",
        shortcuts={
            "search": AppShortcut(
                action="search",
                keys=["command", "l"],  # Focus address bar (also searches)
                alternatives=[["command", "k"]],  # Alternative for search
                notes="Cmd+L focuses address bar for URL or search. For WEBSITE search fields, use VISION."
            ),
            "new_tab": AppShortcut(
                action="new_tab",
                keys=["command", "t"],
            ),
            "close_tab": AppShortcut(
                action="close_tab",
                keys=["command", "w"],
            ),
            "back": AppShortcut(
                action="back",
                keys=["command", "["],
            ),
            "forward": AppShortcut(
                action="forward",
                keys=["command", "]"],
            ),
            "reload": AppShortcut(
                action="reload",
                keys=["command", "r"],
            ),
            "find_in_page": AppShortcut(
                action="find_in_page",
                keys=["command", "f"],  # Cmd+F is find in page, not search
                notes="Cmd+F finds text in the current page, not search the web"
            ),
        },
        common_mistakes={
            "hotkey:command,f": "Cmd+F is find-in-page, not web search. Use Cmd+L to focus address bar OR use VISION to click website search fields.",
            "hotkey:command,k": "For website search, use VISION to find and click the search field, not browser shortcuts.",
        },
        optimal_waits={
            "app_launch": 1.5,
            "page_load": 2.0,
            "search": 1.5,
        },
        focus_indicators=["Safari", "google.com", "webkit"],
    ),
    
    # ---------------- Google Chrome ----------------
    "Chrome": AppProfile(
        name="Chrome",
        bundle_id="com.google.Chrome",
        shortcuts={
            "search": AppShortcut(
                action="search",
                keys=["command", "l"],  # Focus address bar
                notes="Cmd+L focuses address bar. For WEBSITE search fields, use VISION."
            ),
            "new_tab": AppShortcut(
                action="new_tab",
                keys=["command", "t"],
            ),
            "close_tab": AppShortcut(
                action="close_tab",
                keys=["command", "w"],
            ),
            "back": AppShortcut(
                action="back",
                keys=["command", "["],
            ),
            "forward": AppShortcut(
                action="forward",
                keys=["command", "]"],
            ),
            "reload": AppShortcut(
                action="reload",
                keys=["command", "r"],
            ),
            "find_in_page": AppShortcut(
                action="find_in_page",
                keys=["command", "f"],
                notes="Cmd+F finds text in page, NOT for website search"
            ),
        },
        common_mistakes={
            "hotkey:command,f": "Cmd+F is find-in-page, NOT website search. Use VISION to click website search fields.",
            "hotkey:command,k": "Browser omnibox search. For website search fields, use VISION.",
        },
        optimal_waits={
            "app_launch": 1.5,
            "page_load": 2.0,
            "search": 1.5,
        },
        focus_indicators=["Chrome", "Google Chrome"],
    ),
    
    # ---------------- Firefox ----------------
    "Firefox": AppProfile(
        name="Firefox",
        bundle_id="org.mozilla.firefox",
        shortcuts={
            "search": AppShortcut(
                action="search",
                keys=["command", "l"],  # Focus address bar
                notes="Cmd+L focuses address bar. For WEBSITE search fields, use VISION."
            ),
            "new_tab": AppShortcut(
                action="new_tab",
                keys=["command", "t"],
            ),
            "close_tab": AppShortcut(
                action="close_tab",
                keys=["command", "w"],
            ),
            "find_in_page": AppShortcut(
                action="find_in_page",
                keys=["command", "f"],
                notes="Cmd+F finds text in page, NOT for website search"
            ),
        },
        common_mistakes={
            "hotkey:command,f": "Cmd+F is find-in-page. Use VISION for website search fields.",
        },
        optimal_waits={
            "app_launch": 1.5,
            "page_load": 2.0,
        },
        focus_indicators=["Firefox", "Mozilla Firefox"],
    ),
    
    # ---------------- Finder ----------------
    "Finder": AppProfile(
        name="Finder",
        bundle_id="com.apple.finder",
        shortcuts={
            "search": AppShortcut(
                action="search",
                keys=["command", "f"],  # In Finder, Cmd+F DOES search
                notes="Cmd+F opens search in Finder"
            ),
            "new_folder": AppShortcut(
                action="new_folder",
                keys=["command", "shift", "n"],
            ),
            "go_to_folder": AppShortcut(
                action="go_to_folder",
                keys=["command", "shift", "g"],
            ),
            "get_info": AppShortcut(
                action="get_info",
                keys=["command", "i"],
            ),
            "new_window": AppShortcut(
                action="new_window",
                keys=["command", "n"],
            ),
        },
        optimal_waits={
            "app_launch": 1.0,
            "folder_navigation": 0.5,
        },
        focus_indicators=["Finder", "Desktop", "Documents", "Downloads"],
    ),
    
    # ---------------- Spotify ----------------
    "Spotify": AppProfile(
        name="Spotify",
        bundle_id="com.spotify.client",
        shortcuts={
            "search": AppShortcut(
                action="search",
                keys=["command", "l"],  # Focus search bar
                alternatives=[["command", "k"]],
                notes="Cmd+L or Cmd+K focuses the search bar"
            ),
            "play_pause": AppShortcut(
                action="play_pause",
                keys=["space"],
            ),
            "next_track": AppShortcut(
                action="next_track",
                keys=["command", "right"],
            ),
            "previous_track": AppShortcut(
                action="previous_track",
                keys=["command", "left"],
            ),
        },
        common_mistakes={
            "hotkey:command,f": "Cmd+F is not search in Spotify. Use Cmd+L or Cmd+K.",
        },
        optimal_waits={
            "app_launch": 2.5,
            "search": 1.0,
        },
        focus_indicators=["Spotify"],
    ),
    
    # ---------------- WhatsApp ----------------
    "WhatsApp": AppProfile(
        name="WhatsApp",
        bundle_id="net.whatsapp.WhatsApp",
        shortcuts={
            "search": AppShortcut(
                action="search",
                keys=["command", "f"],  # Search in WhatsApp
                notes="Cmd+F opens the search bar for chats/contacts"
            ),
            "new_chat": AppShortcut(
                action="new_chat",
                keys=["command", "n"],
            ),
            "archive_chat": AppShortcut(
                action="archive_chat",
                keys=["command", "e"],
            ),
        },
        optimal_waits={
            "app_launch": 2.0,
            "search": 0.5,
        },
        focus_indicators=["WhatsApp"],
    ),
    
    # ---------------- Messages ----------------
    "Messages": AppProfile(
        name="Messages",
        bundle_id="com.apple.MobileSMS",
        shortcuts={
            "search": AppShortcut(
                action="search",
                keys=["command", "f"],
            ),
            "new_message": AppShortcut(
                action="new_message",
                keys=["command", "n"],
            ),
        },
        optimal_waits={
            "app_launch": 1.5,
            "search": 0.5,
        },
        focus_indicators=["Messages", "iMessage"],
    ),
    
    # ---------------- Notes ----------------
    "Notes": AppProfile(
        name="Notes",
        bundle_id="com.apple.Notes",
        shortcuts={
            "search": AppShortcut(
                action="search",
                keys=["command", "option", "f"],  # Search all notes
                alternatives=[["command", "f"]],   # Find in current note
                notes="Cmd+Option+F searches all notes, Cmd+F finds in current note"
            ),
            "new_note": AppShortcut(
                action="new_note",
                keys=["command", "n"],
            ),
        },
        optimal_waits={
            "app_launch": 1.5,
            "search": 0.5,
        },
        focus_indicators=["Notes"],
    ),
    
    # ---------------- Terminal ----------------
    "Terminal": AppProfile(
        name="Terminal",
        bundle_id="com.apple.Terminal",
        shortcuts={
            "search": AppShortcut(
                action="search",
                keys=["command", "f"],  # Find in terminal output
                notes="Cmd+F finds text in terminal output"
            ),
            "new_tab": AppShortcut(
                action="new_tab",
                keys=["command", "t"],
            ),
            "new_window": AppShortcut(
                action="new_window",
                keys=["command", "n"],
            ),
            "clear": AppShortcut(
                action="clear",
                keys=["command", "k"],
            ),
        },
        optimal_waits={
            "app_launch": 1.0,
            "command_execution": 0.5,
        },
        focus_indicators=["Terminal", "zsh", "bash", "~"],
    ),
    
    # ---------------- VS Code ----------------
    "Code": AppProfile(
        name="Code",
        bundle_id="com.microsoft.VSCode",
        shortcuts={
            "search": AppShortcut(
                action="search",
                keys=["command", "shift", "f"],  # Search in files
                notes="Cmd+Shift+F searches across all files"
            ),
            "find_in_file": AppShortcut(
                action="find_in_file",
                keys=["command", "f"],  # Find in current file
            ),
            "go_to_file": AppShortcut(
                action="go_to_file",
                keys=["command", "p"],
            ),
            "command_palette": AppShortcut(
                action="command_palette",
                keys=["command", "shift", "p"],
            ),
            "new_file": AppShortcut(
                action="new_file",
                keys=["command", "n"],
            ),
        },
        optimal_waits={
            "app_launch": 2.0,
            "search": 0.5,
        },
        focus_indicators=["Visual Studio Code", "Code", ".py", ".js", ".ts"],
    ),
}


class AppKnowledge:
    """
    Central knowledge base for app-specific behaviors.
    
    Combines built-in knowledge with learned patterns from execution history.
    """
    
    def __init__(self, knowledge_file: Path = APP_KNOWLEDGE_FILE):
        self.knowledge_file = knowledge_file
        self.profiles: Dict[str, AppProfile] = BUILTIN_APP_PROFILES.copy()
        self.learned_corrections: Dict[str, Dict] = {}  # App -> action -> correction
        self.action_history: List[Dict] = []  # Track actions for learning
        
        self._load_learned()
    
    def _load_learned(self):
        """Load learned corrections from disk."""
        try:
            if self.knowledge_file.exists():
                with open(self.knowledge_file, 'r') as f:
                    data = json.load(f)
                    self.learned_corrections = data.get("corrections", {})
                    
                    # Merge learned data into profiles
                    for app_name, app_data in data.get("app_updates", {}).items():
                        if app_name in self.profiles:
                            profile = self.profiles[app_name]
                            # Update success rates
                            profile.action_success_rates.update(
                                app_data.get("success_rates", {})
                            )
                            # Update optimal waits
                            profile.optimal_waits.update(
                                app_data.get("optimal_waits", {})
                            )
                    
                    logger.debug(f"Loaded learned app knowledge for {len(self.learned_corrections)} apps")
        except Exception as e:
            logger.warning(f"Could not load app knowledge: {e}")
    
    def _save_learned(self):
        """Save learned corrections to disk."""
        try:
            self.knowledge_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Prepare app updates from profiles
            app_updates = {}
            for name, profile in self.profiles.items():
                if profile.action_success_rates or profile.optimal_waits:
                    app_updates[name] = {
                        "success_rates": profile.action_success_rates,
                        "optimal_waits": profile.optimal_waits,
                    }
            
            data = {
                "corrections": self.learned_corrections,
                "app_updates": app_updates,
                "last_updated": datetime.now().isoformat(),
            }
            
            with open(self.knowledge_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Could not save app knowledge: {e}")
    
    def get_profile(self, app_name: str) -> Optional[AppProfile]:
        """Get the profile for an app by name."""
        # Try exact match first
        if app_name in self.profiles:
            return self.profiles[app_name]
        
        # Try case-insensitive match
        app_lower = app_name.lower()
        for name, profile in self.profiles.items():
            if name.lower() == app_lower:
                return profile
        
        return None
    
    def get_search_shortcut(self, app_name: str) -> Optional[List[str]]:
        """Get the correct search shortcut for an app."""
        profile = self.get_profile(app_name)
        if profile:
            return profile.get_keys("search")
        return None
    
    def validate_action(self, app_name: str, action: str) -> Tuple[bool, Optional[str]]:
        """
        Validate an action for an app and return correction if needed.
        
        Returns:
            (is_valid, correction_message)
        """
        profile = self.get_profile(app_name)
        if not profile:
            return True, None  # Can't validate unknown apps
        
        # Check for common mistakes
        for mistake_pattern, correction in profile.common_mistakes.items():
            if mistake_pattern in action:
                return False, correction
        
        # Check learned corrections
        if app_name in self.learned_corrections:
            for mistake_pattern, correction in self.learned_corrections[app_name].items():
                if mistake_pattern in action:
                    return False, correction
        
        return True, None
    
    def get_correct_action(self, app_name: str, intent: str, wrong_action: str) -> Optional[str]:
        """
        Get the correct action when a wrong action is detected.
        
        Args:
            app_name: Current app
            intent: What the user is trying to do (e.g., "search")
            wrong_action: The incorrect action that was planned
        
        Returns:
            Corrected action string or None
        """
        profile = self.get_profile(app_name)
        if not profile:
            return None
        
        # Map intent to shortcut
        intent_lower = intent.lower()
        shortcut = None
        
        if "search" in intent_lower:
            shortcut = profile.get_shortcut("search")
        elif "play" in intent_lower or "pause" in intent_lower:
            shortcut = profile.get_shortcut("play_pause")
        elif "next" in intent_lower:
            shortcut = profile.get_shortcut("next_track")
        elif "previous" in intent_lower or "back" in intent_lower:
            shortcut = profile.get_shortcut("previous_track")
        
        if shortcut:
            keys = ",".join(shortcut.keys)
            return f"hotkey:{keys}"
        
        return None
    
    def record_action_result(
        self,
        app_name: str,
        action: str,
        success: bool,
        error_type: Optional[str] = None,
        correction: Optional[str] = None
    ):
        """
        Record the result of an action for learning.
        
        This updates success rates and learns new corrections.
        """
        profile = self.get_profile(app_name)
        
        # Track in history
        self.action_history.append({
            "app": app_name,
            "action": action,
            "success": success,
            "error_type": error_type,
            "correction": correction,
            "timestamp": datetime.now().isoformat()
        })
        
        # Update profile if exists
        if profile:
            # Update success rate
            action_key = action.split(":")[0] if ":" in action else action
            current_rate = profile.action_success_rates.get(action_key, 0.5)
            # Exponential moving average
            alpha = 0.2
            new_rate = alpha * (1.0 if success else 0.0) + (1 - alpha) * current_rate
            profile.action_success_rates[action_key] = new_rate
        
        # Learn correction if provided
        if not success and correction:
            if app_name not in self.learned_corrections:
                self.learned_corrections[app_name] = {}
            self.learned_corrections[app_name][action] = correction
        
        # Periodically save
        if len(self.action_history) % 10 == 0:
            self._save_learned()
    
    def get_focus_verification_hints(self, app_name: str) -> List[str]:
        """Get hints for verifying an app has focus."""
        profile = self.get_profile(app_name)
        if profile:
            return profile.focus_indicators
        return [app_name]
    
    def get_optimal_wait(self, app_name: str, action_type: str) -> float:
        """Get the optimal wait time for an action in an app."""
        profile = self.get_profile(app_name)
        if profile and action_type in profile.optimal_waits:
            return profile.optimal_waits[action_type]
        
        # Default waits
        defaults = {
            "app_launch": 1.5,
            "search": 1.0,
            "page_load": 2.0,
            "keyboard_shortcut": 0.3,
        }
        return defaults.get(action_type, 0.5)
    
    def suggest_pre_action_verification(self, app_name: str, action: str) -> Optional[Dict]:
        """
        Suggest verification steps before executing an action.
        
        Returns dict with verification info or None if not needed.
        """
        profile = self.get_profile(app_name)
        if not profile:
            return None
        
        # High-risk actions that need verification
        high_risk_patterns = ["search", "delete", "send", "submit"]
        
        is_high_risk = any(p in action.lower() for p in high_risk_patterns)
        
        if is_high_risk:
            return {
                "should_verify": True,
                "expected_app": app_name,
                "focus_indicators": profile.focus_indicators,
                "message": f"Verify {app_name} is focused before: {action}"
            }
        
        return None


# Global instance
app_knowledge = AppKnowledge()
