"""
Robust Action Parser — handles LLM formatting variations gracefully.

Parses action strings like:
    "hotkey:command,space"
    "Hotkey: command, space"
    "CLICK: search box"
    "type:Hello World"
    "wait:2.5"
    "scroll:down,3"
    "drag:100,200,300,400"
    "clipboard:copy"  /  "clipboard:paste"

Returns normalized MicroAction-compatible dicts.
"""

import re
from typing import Dict, List, Optional, Tuple


# Canonical action types
_ACTION_ALIASES = {
    "hotkey": "hotkey",
    "shortcut": "hotkey",
    "key_combo": "hotkey",
    "type": "type",
    "text": "type",
    "write": "type",
    "input": "type",
    "key": "key",
    "press": "key",
    "keypress": "key",
    "tap": "key",
    "wait": "wait",
    "sleep": "wait",
    "delay": "wait",
    "pause": "wait",
    "click": "click",
    "tap_element": "click",
    "find_and_click": "click",
    "scroll": "scroll",
    "scroll_to": "scroll",
    "drag": "drag",
    "drag_and_drop": "drag",
    "clipboard": "clipboard",
    "copy": "clipboard",
    "paste": "clipboard",
    "open_url": "open_url",
    "url": "open_url",
    "activate_app": "activate_app",
}

# Key name normalization
_KEY_ALIASES = {
    "cmd": "command",
    "meta": "command",
    "super": "command",
    "win": "command",
    "opt": "option",
    "alt": "option",
    "ctrl": "control",
    "ctl": "control",
    "ret": "return",
    "enter": "return",
    "cr": "return",
    "esc": "escape",
    "del": "delete",
    "bs": "backspace",
    "spc": "space",
    "pgup": "pageup",
    "pgdn": "pagedown",
    "pgdown": "pagedown",
}


def normalize_key(key: str) -> str:
    """Normalize a key name to pyautogui-compatible form."""
    k = key.strip().lower()
    return _KEY_ALIASES.get(k, k)


def parse_action(raw: str) -> Optional[Dict]:
    """
    Parse a single action string into a normalized dict.

    Handles: 'hotkey:command,space', 'CLICK: search box', 'type: hello',
             'wait:2', 'scroll:down,3', 'drag:100,200,300,400',
             'clipboard:paste'

    Returns dict with keys: type, params, description
    Returns None if the string cannot be parsed.
    """
    if not raw or not isinstance(raw, str):
        return None

    raw = raw.strip()

    # Split on first colon
    colon_idx = raw.find(":")
    if colon_idx == -1:
        # No colon — might be a bare key name like "return"
        return {
            "type": "key",
            "params": {"key": normalize_key(raw)},
            "description": f"Press {raw}",
        }

    action_raw = raw[:colon_idx].strip().lower().replace(" ", "_")
    value = raw[colon_idx + 1:].strip()

    # Resolve canonical type
    action_type = _ACTION_ALIASES.get(action_raw)
    if not action_type:
        # Try partial match
        for alias, canonical in _ACTION_ALIASES.items():
            if alias in action_raw or action_raw in alias:
                action_type = canonical
                break
    if not action_type:
        # Unknown — treat as click description
        action_type = "click"
        value = raw  # Use full string as element description

    # ── Build params per type ────────────────────────────────

    if action_type == "hotkey":
        keys = [normalize_key(k) for k in re.split(r"[,+\s]+", value) if k.strip()]
        return {
            "type": "hotkey",
            "params": {"keys": keys},
            "description": f"Press {'+'.join(keys)}",
        }

    if action_type == "type":
        return {
            "type": "type",
            "params": {"text": value},
            "description": f"Type: {value}",
        }

    if action_type == "key":
        return {
            "type": "key",
            "params": {"key": normalize_key(value)},
            "description": f"Press {value}",
        }

    if action_type == "wait":
        try:
            seconds = float(re.search(r"[\d.]+", value).group())
        except (AttributeError, ValueError):
            seconds = 1.0
        return {
            "type": "wait",
            "params": {"seconds": seconds},
            "description": f"Wait {seconds}s",
        }

    if action_type == "click":
        return {
            "type": "click",
            "params": {"element": value},
            "description": f"Click: {value}",
            "requires_screen": True,
        }

    if action_type == "scroll":
        # "down,3" or "up" or "down 5"
        parts = re.split(r"[,\s]+", value)
        direction = parts[0].lower() if parts else "down"
        amount = 3  # default
        if len(parts) > 1:
            try:
                amount = int(parts[1])
            except ValueError:
                pass
        return {
            "type": "scroll",
            "params": {"direction": direction, "amount": amount},
            "description": f"Scroll {direction} {amount}",
        }

    if action_type == "drag":
        # "100,200,300,400" or "from_element to_element"
        nums = re.findall(r"\d+", value)
        if len(nums) >= 4:
            return {
                "type": "drag",
                "params": {
                    "start_x": int(nums[0]),
                    "start_y": int(nums[1]),
                    "end_x": int(nums[2]),
                    "end_y": int(nums[3]),
                },
                "description": f"Drag ({nums[0]},{nums[1]}) → ({nums[2]},{nums[3]})",
            }
        return {
            "type": "drag",
            "params": {"description": value},
            "description": f"Drag: {value}",
        }

    if action_type == "clipboard":
        op = value.lower().strip()
        if op in ("copy", "cut", "paste", "select_all"):
            return {
                "type": "clipboard",
                "params": {"operation": op},
                "description": f"Clipboard: {op}",
            }
        # Default to paste
        return {
            "type": "clipboard",
            "params": {"operation": "paste"},
            "description": "Clipboard: paste",
        }

    if action_type == "open_url":
        return {
            "type": "open_url",
            "params": {"url": value},
            "description": f"Open URL: {value}",
        }

    if action_type == "activate_app":
        return {
            "type": "activate_app",
            "params": {"app": value},
            "description": f"Activate: {value}",
        }

    # Fallback
    return {
        "type": action_type,
        "params": {"raw": value},
        "description": raw,
    }


def parse_actions(raw_list: list) -> List[Dict]:
    """Parse a list of action strings, skipping unparseable ones."""
    results = []
    for item in raw_list:
        if isinstance(item, dict):
            # Already structured — normalize type
            t = item.get("type", "").strip().lower()
            item["type"] = _ACTION_ALIASES.get(t, t)
            results.append(item)
        elif isinstance(item, str):
            parsed = parse_action(item)
            if parsed:
                results.append(parsed)
    return results
