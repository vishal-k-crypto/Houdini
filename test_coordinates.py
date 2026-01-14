"""
Test coordinate conversion between macOS and PyAutoGUI.
"""

import pyautogui
from src.utils.accessibility_reader import (
    convert_macos_to_pyautogui_coords,
    get_screen_height,
    get_ui_elements_applescript,
    get_frontmost_app
)

print("=" * 60)
print("COORDINATE SYSTEM TEST")
print("=" * 60)

# Get screen dimensions
screen_width, screen_height = pyautogui.size()
print(f"\nScreen Size: {screen_width}x{screen_height}")

# Get current mouse position
current_x, current_y = pyautogui.position()
print(f"\nCurrent Mouse Position (PyAutoGUI): ({current_x}, {current_y})")

# Test conversion
print("\n" + "-" * 60)
print("COORDINATE CONVERSION TEST")
print("-" * 60)

# Test corner conversions
test_cases = [
    ("Top-Left", 0, 0),
    ("Top-Right", screen_width, 0),
    ("Bottom-Left", 0, screen_height),
    ("Bottom-Right", screen_width, screen_height),
    ("Center", screen_width // 2, screen_height // 2),
]

for name, pyautogui_x, pyautogui_y in test_cases:
    # Convert PyAutoGUI to macOS (reverse operation)
    macos_x = pyautogui_x
    macos_y = screen_height - pyautogui_y
    
    # Convert back
    converted_x, converted_y = convert_macos_to_pyautogui_coords(macos_x, macos_y)
    
    match = "✅" if (converted_x == pyautogui_x and converted_y == pyautogui_y) else "❌"
    print(f"{match} {name:15} PyAutoGUI({pyautogui_x:4}, {pyautogui_y:4}) <-> macOS({macos_x:4}, {macos_y:4}) -> Converted({converted_x:4}, {converted_y:4})")

# Test with actual UI elements
print("\n" + "-" * 60)
print("ACTUAL UI ELEMENTS TEST")
print("-" * 60)

app_info = get_frontmost_app()
print(f"\nFrontmost App: {app_info['app']}")
print(f"Window: {app_info['window'][:50]}")

elements = get_ui_elements_applescript(max_elements=5)
print(f"\nFound {len(elements)} UI elements (showing first 5):")

for i, elem in enumerate(elements[:5], 1):
    cx, cy = elem.center
    print(f"\n{i}. {elem.role:12} '{elem.title[:30]:30}'")
    print(f"   Position: ({elem.x}, {elem.y})")
    print(f"   Size: {elem.width}x{elem.height}")
    print(f"   Center: ({cx}, {cy})")
    
    # Verify center is within screen bounds
    in_bounds = (0 <= cx <= screen_width and 0 <= cy <= screen_height)
    bounds_check = "✅" if in_bounds else "❌ OUT OF BOUNDS!"
    print(f"   {bounds_check}")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
print("\n⚠️  If any elements are OUT OF BOUNDS, coordinates are wrong!")
print("✅  All elements should have centers within screen dimensions")
