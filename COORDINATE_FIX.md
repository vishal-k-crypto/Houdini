# Coordinate System Fix - CRITICAL

## Problem
The agent was clicking in **wrong locations** because of a coordinate system mismatch:

- **macOS Accessibility API**: Uses **BOTTOM-LEFT origin** (y increases upward)
- **PyAutoGUI**: Uses **TOP-LEFT origin** (y increases downward)

## Solution
Added coordinate conversion function in `accessibility_reader.py`:

```python
def convert_macos_to_pyautogui_coords(x: int, y: int) -> Tuple[int, int]:
    """
    Convert macOS coordinates (bottom-left origin) to PyAutoGUI (top-left origin).
    
    macOS: (0, 0) = bottom-left, y increases upward
    PyAutoGUI: (0, 0) = top-left, y increases downward
    """
    screen_height = get_screen_height()
    converted_y = screen_height - y
    return (x, converted_y)
```

## Changes Made

### 1. `src/utils/accessibility_reader.py`
- Added `get_screen_height()` to cache screen dimensions
- Added `convert_macos_to_pyautogui_coords()` for coordinate conversion
- Updated `get_ui_elements_applescript()` to convert all coordinates
- Updated `UIElement` documentation to note coordinates are pre-converted

### 2. Verification
Created `test_coordinates.py` which validates:
- ✅ Top-left corner conversion
- ✅ Top-right corner conversion
- ✅ Bottom-left corner conversion
- ✅ Bottom-right corner conversion
- ✅ Center point conversion

All test cases passed successfully.

## Technical Details

### Coordinate Systems
```
macOS (Accessibility API):          PyAutoGUI:
(0, H) +---------+ (W, H)          (0, 0) +---------+ (W, 0)
       |         |                         |         |
       |         |                         |         |
(0, 0) +---------+ (W, 0)          (0, H) +---------+ (W, H)
```

### Conversion Formula
```
PyAutoGUI_Y = Screen_Height - macOS_Y
PyAutoGUI_X = macOS_X  (unchanged)
```

### Example
For screen size 1512x982:
- macOS (756, 491) → PyAutoGUI (756, 491)  [center remains center]
- macOS (0, 982) → PyAutoGUI (0, 0)  [bottom-left → top-left]
- macOS (0, 0) → PyAutoGUI (0, 982)  [top-left → bottom-left]

## Impact

### Before Fix
```python
# AppleScript returns: button at (100, 800) [macOS coords]
# PyAutoGUI clicks at: (100, 800) [wrong!]
# Actual screen position: (100, 182) [should have been here]
```

### After Fix
```python
# AppleScript returns: button at (100, 800) [macOS coords]
# Convert: (100, 982-800) = (100, 182) [PyAutoGUI coords]
# PyAutoGUI clicks at: (100, 182) [correct!]
```

## Testing

Run the test script:
```bash
cd /Users/letsfuck/Desktop/Houdini/houdini-agent
source .venv/bin/activate
python test_coordinates.py
```

Expected output:
```
✅ Top-Left        PyAutoGUI(   0,    0) <-> macOS(   0,  982) -> Converted(   0,    0)
✅ Top-Right       PyAutoGUI(1512,    0) <-> macOS(1512,  982) -> Converted(1512,    0)
✅ Bottom-Left     PyAutoGUI(   0,  982) <-> macOS(   0,    0) -> Converted(   0,  982)
✅ Bottom-Right    PyAutoGUI(1512,  982) <-> macOS(1512,    0) -> Converted(1512,  982)
✅ Center          PyAutoGUI( 756,  491) <-> macOS( 756,  491) -> Converted( 756,  491)
```

## Notes

1. **Retina Display**: The fix handles logical points correctly. Both macOS and PyAutoGUI use logical points (not physical pixels), so no additional scaling is needed for Retina displays.

2. **Screen Height Cache**: Screen height is cached to avoid repeated pyautogui.size() calls.

3. **All Click Operations**: The fix applies to:
   - Vision executor clicks
   - Accessibility-based clicks
   - LLM-guided element targeting
   - Recovery handler clicks

4. **Position-Based Clicks**: These already use percentages of screen size with PyAutoGUI, so they work correctly without conversion.

## Verification

After this fix, all click operations should hit their targets accurately. Run your task again to verify:

```bash
python -m src.main --task "open Safari and click the first search result" --loop
```

The agent should now click on the correct elements!
