"""
Platform-specific configuration for Docker/Linux vs macOS environments.
"""

import os
import platform
from typing import Dict

# Detect if running in Docker
IS_DOCKER = os.path.exists('/.dockerenv') or os.getenv('DOCKER_CONTAINER') == 'true'
IS_LINUX = platform.system() == 'Linux'
IS_MACOS = platform.system() == 'Darwin'

# Platform-specific defaults
if IS_DOCKER or IS_LINUX:
    # Docker/Linux configuration
    DEFAULT_BROWSER = "Chromium"
    BROWSER_OPEN_SEQUENCE = ["chromium", "--no-sandbox"]  # Direct command
    BROWSER_HOTKEY = None  # No Spotlight on Linux
    APP_LAUNCHER = "xdotool"  # Use xdotool for launching
    
    # Hotkey overrides (Linux doesn't use Command, uses Control)
    HOTKEY_MODIFIER = "ctrl"  # Instead of "command"
    HOTKEY_URL_BAR = ["ctrl", "l"]
    HOTKEY_NEW_TAB = ["ctrl", "t"]
    HOTKEY_CLOSE_TAB = ["ctrl", "w"]
    HOTKEY_COPY = ["ctrl", "c"]
    HOTKEY_PASTE = ["ctrl", "v"]
    HOTKEY_SPOTLIGHT = None  # No spotlight on Linux
    
    # Linux app names
    BROWSER_NAMES = ["chromium", "chromium-browser", "google-chrome", "firefox"]
    TEXT_EDITOR = "gedit"
    OFFICE_SUITE = "libreoffice"
else:
    # macOS configuration
    DEFAULT_BROWSER = "Safari"
    BROWSER_OPEN_SEQUENCE = None  # Use Spotlight
    BROWSER_HOTKEY = ["command", "space"]  # Spotlight
    APP_LAUNCHER = "spotlight"
    
    # macOS hotkeys
    HOTKEY_MODIFIER = "command"
    HOTKEY_URL_BAR = ["command", "l"]
    HOTKEY_NEW_TAB = ["command", "t"]
    HOTKEY_CLOSE_TAB = ["command", "w"]
    HOTKEY_COPY = ["command", "c"]
    HOTKEY_PASTE = ["command", "v"]
    HOTKEY_SPOTLIGHT = ["command", "space"]
    
    # macOS app names
    BROWSER_NAMES = ["Safari", "Google Chrome", "Firefox", "Arc"]
    TEXT_EDITOR = "TextEdit"
    OFFICE_SUITE = "LibreOffice"


def get_browser_open_actions() -> list:
    """Get the action sequence to open the default browser."""
    if IS_DOCKER or IS_LINUX:
        # Linux/Docker: Use keyboard shortcut or direct command
        return [
            f"key:super",  # Open app menu
            "wait:0.5",
            f"type:{DEFAULT_BROWSER}",
            "key:return",
            "wait:2"
        ]
    else:
        # macOS: Use Spotlight
        return [
            "hotkey:command,space",
            f"type:{DEFAULT_BROWSER}",
            "key:return",
            "wait:2"
        ]


def get_url_navigation_actions(url: str) -> list:
    """Get actions to navigate to a URL in the current browser."""
    if IS_DOCKER or IS_LINUX:
        return [
            "hotkey:ctrl,l",
            f"type:{url}",
            "key:return",
            "wait:3"
        ]
    else:
        return [
            "hotkey:command,l",
            f"type:{url}",
            "key:return",
            "wait:3"
        ]


def get_platform_prompt_context() -> str:
    """Get platform-specific context for LLM prompts."""
    if IS_DOCKER or IS_LINUX:
        return """
## PLATFORM: Linux/Docker
- Browser: Use Chromium (NOT Safari - Safari is macOS only)
- Hotkeys: Use Ctrl instead of Command (e.g., Ctrl+L for URL bar, Ctrl+C for copy)
- App launching: Type app name and press Enter (no Spotlight)
- Available apps: Chromium, LibreOffice Impress, Text Editor

## Linux-specific action examples:
- Open browser: ["type:chromium", "key:return", "wait:2"] 
- URL bar: ["hotkey:ctrl,l"] (NOT command,l)
- New tab: ["hotkey:ctrl,t"] (NOT command,t)
- Copy: ["hotkey:ctrl,c"] (NOT command,c)
"""
    else:
        return """
## PLATFORM: macOS
- Browser: Safari (or Chrome/Firefox if specified)
- Hotkeys: Use Command as primary modifier
- App launching: Cmd+Space → type app name → Enter

## macOS-specific action examples:
- Open browser: ["hotkey:command,space", "type:Safari", "key:return", "wait:2"]
- URL bar: ["hotkey:command,l"]
- New tab: ["hotkey:command,t"]
- Copy: ["hotkey:command,c"]
"""


def translate_hotkey(hotkey: str) -> str:
    """Translate a hotkey string between platforms."""
    if IS_DOCKER or IS_LINUX:
        # Convert macOS hotkeys to Linux
        return hotkey.replace("command", "ctrl").replace("option", "alt")
    return hotkey


# Export key config values
PLATFORM_CONFIG = {
    "is_docker": IS_DOCKER,
    "is_linux": IS_LINUX,
    "is_macos": IS_MACOS,
    "default_browser": DEFAULT_BROWSER,
    "hotkey_modifier": HOTKEY_MODIFIER,
    "platform_name": "Docker/Linux" if (IS_DOCKER or IS_LINUX) else "macOS",
}


def get_step_type_rules() -> str:
    """Get platform-specific step type rules."""
    if IS_DOCKER or IS_LINUX:
        return """
### step_type: "blind" (keyboard-only, no vision needed):
- Opening browser: ["type:chromium", "key:return", "wait:2"]
- URL navigation: ["hotkey:ctrl,l", "type:google.com", "key:return", "wait:2"]
- Keyboard shortcuts: ["hotkey:ctrl,c"], ["hotkey:ctrl,v"]
- Typing after click: ["type:search query", "key:return"]

IMPORTANT: On Linux/Docker:
- Use "ctrl" NOT "command" for hotkeys
- Use "chromium" NOT "Safari" for browser
- No Spotlight (command+space) - just type app name directly
"""
    else:
        return """
### step_type: "blind" (keyboard-only, no vision needed):
- Opening apps: ["hotkey:command,space", "type:Safari", "key:return", "wait:2"]
- URL navigation: ["hotkey:command,l", "type:google.com", "key:return", "wait:2"]
- Keyboard shortcuts: ["hotkey:command,c"], ["hotkey:command,v"]
- Typing after click: ["type:search query", "key:return"]
"""


def get_example_prompts() -> str:
    """Get platform-specific example prompts for LLM."""
    if IS_DOCKER or IS_LINUX:
        return """
## COMPLETE EXAMPLES (Linux/Docker):

### Task: "Open YouTube and search for Python tutorials"
{{
  "macro_steps": [
    {{"step": "Launch Chromium browser", "step_type": "blind", "context": "Browser window visible", "suggested_actions": ["type:chromium", "key:return", "wait:3"]}},
    {{"step": "Navigate to YouTube", "step_type": "blind", "context": "YouTube homepage loaded", "suggested_actions": ["hotkey:ctrl,l", "type:youtube.com", "key:return", "wait:3"]}},
    {{"step": "Click the YouTube search box", "step_type": "vision", "context": "Search box focused", "suggested_actions": ["click:search input box at top of YouTube page"]}},
    {{"step": "Type search query", "step_type": "blind", "context": "Search results displayed", "suggested_actions": ["type:Python tutorials", "key:return", "wait:2"]}},
    {{"step": "Click first video", "step_type": "vision", "context": "Video playing", "suggested_actions": ["click:first video thumbnail in search results"]}}
  ],
  "expected_outcome": "Python tutorials video is playing on YouTube",
  "success_criteria": "Video player is visible and video is playing"
}}

### Task: "Research climate change and save notes"
{{
  "macro_steps": [
    {{"step": "Open Chromium browser", "step_type": "blind", "context": "Browser window visible", "suggested_actions": ["type:chromium", "key:return", "wait:3"]}},
    {{"step": "Search for climate change on Google", "step_type": "blind", "context": "Search results visible", "suggested_actions": ["hotkey:ctrl,l", "type:google.com", "key:return", "wait:2", "type:climate change facts", "key:return", "wait:2"]}},
    {{"step": "Click on a reliable source", "step_type": "vision", "context": "Article page open", "suggested_actions": ["click:first result from a .gov or .edu domain"]}},
    {{"step": "Copy key information", "step_type": "blind", "context": "Text selected and copied", "suggested_actions": ["hotkey:ctrl,a", "hotkey:ctrl,c"]}}
  ],
  "expected_outcome": "Key climate change information copied to clipboard",
  "success_criteria": "Clipboard contains relevant text"
}}
"""
    else:
        return """
## COMPLETE EXAMPLES (macOS):

### Task: "Open YouTube and search for Python tutorials"
{{
  "macro_steps": [
    {{"step": "Launch Safari browser", "step_type": "blind", "context": "Safari window visible", "suggested_actions": ["hotkey:command,space", "type:Safari", "key:return", "wait:2"]}},
    {{"step": "Navigate to YouTube", "step_type": "blind", "context": "YouTube homepage loaded", "suggested_actions": ["hotkey:command,l", "type:youtube.com", "key:return", "wait:3"]}},
    {{"step": "Click the YouTube search box", "step_type": "vision", "context": "Search box focused", "suggested_actions": ["click:search input box at top of YouTube page"]}},
    {{"step": "Type search query", "step_type": "blind", "context": "Search results displayed", "suggested_actions": ["type:Python tutorials", "key:return", "wait:2"]}},
    {{"step": "Click first video", "step_type": "vision", "context": "Video playing", "suggested_actions": ["click:first video thumbnail in search results"]}}
  ],
  "expected_outcome": "Python tutorials video is playing on YouTube",
  "success_criteria": "Video player is visible and video is playing"
}}

### Task: "Send a WhatsApp message to John saying hello"
{{
  "macro_steps": [
    {{"step": "Open WhatsApp", "step_type": "blind", "context": "WhatsApp window visible", "suggested_actions": ["hotkey:command,space", "type:WhatsApp", "key:return", "wait:2"]}},
    {{"step": "Search for John contact", "step_type": "blind", "context": "Search results visible", "suggested_actions": ["hotkey:command,f", "type:John", "wait:0.5"]}},
    {{"step": "Click John's chat", "step_type": "vision", "context": "John's chat open", "suggested_actions": ["click:John in the contact/chat list"]}},
    {{"step": "Type and send message", "step_type": "blind", "context": "Message sent", "suggested_actions": ["type:hello", "key:return"]}}
  ],
  "expected_outcome": "Message 'hello' sent to John in WhatsApp",
  "success_criteria": "Message appears in chat with sent checkmark"
}}
"""
