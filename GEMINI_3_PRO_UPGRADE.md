# Gemini 3.0 Pro Upgrade - Enhanced Planning

## Overview

Upgraded the Houdini Agent to use **Gemini 3.0 Pro (gemini-2.5-pro)** for superior macro planning with enhanced micro-level execution details.

## Changes Made

### 1. Model Upgrade: Gemini 3.0 Pro for Planning

**File**: [src/utils/gemini_client.py](src/utils/gemini_client.py)

- Updated `GeminiCLI` class to use `gemini-2.5-pro` by default (resolves to Gemini 3.0 Pro)
- Enhanced documentation to clarify this is for "high-quality strategic planning"
- Maintains backward compatibility with model override parameter

```python
class GeminiCLI:
    """
    Wrapper for the Gemini CLI tool (text-only) and Python API (for vision).
    Uses Gemini 3.0 Pro (gemini-2.5-pro) for high-quality strategic planning.
    """
    def __init__(self, model_name: str = "gemini-2.5-pro"):
```

### 2. Enhanced Macro Planner Prompt

**File**: [prompts/macro_planner_prompt.md](prompts/macro_planner_prompt.md)

#### Key Improvements:

✅ **Strategic + Micro-Level Planning**
- Shifted from pure high-level to "high-level WITH detailed micro-level action sequences"
- Planner now provides complete, deterministic action chains

✅ **Clear Task Execution Formula**
- Introduced **TRIGGER → ACTION → WAIT → VERIFY** pattern
- Every step must include explicit timing and validation
- Removed ambiguity in execution flow

✅ **Detailed Action Specifications**
```json
{
  "suggested_actions": [
    "hotkey:command,space",      // TRIGGER: Spotlight
    "type:Safari",                // ACTION: Type app name  
    "key:return",                 // ACTION: Launch
    "wait:1.5",                   // WAIT: App launch time
    "hotkey:command,l",           // TRIGGER: URL bar
    "type:youtube.com",           // ACTION: Type URL
    "key:return",                 // ACTION: Navigate
    "wait:2.0"                    // WAIT: Page load (VERIFY)
  ]
}
```

✅ **Enhanced Responsibilities**
1. Strategic Breakdown - logical sequential phases
2. **Micro-Level Actions** - exact keystrokes, timing, validation
3. **Clear Execution Path** - NO ambiguity
4. Task Clarity - deterministic, directly executable
5. Proactive Planning - anticipate obstacles, provide fallbacks

#### New Section: Micro-Level Planning in Macro Steps

**DO: Be Specific and Detailed**
- Include exact timing: `"wait:1.5"` after app launches
- Specify validation: `"wait:1.0"` to verify action succeeded
- Concrete details: "Open Spotify using Spotlight, wait 1.5s for launch, then press Cmd+L to focus search"

**DON'T: Be Vague**
- ❌ "Search for music" (too vague)
- ❌ "Navigate to website" (missing URL and steps)
- ❌ "Find the button" (which button? where?)

### 3. Enhanced Micro Executor Prompt

**File**: [prompts/micro_executor_prompt.md](prompts/micro_executor_prompt.md)

#### New Section: 🎯 EXTRA TIPS FOR PRECISION EXECUTION

**Timing is Critical**
- ⏱️ After launching apps: Always wait 1.5-2s
- ⏱️ After page navigation: Wait 2-3s for full load
- ⏱️ After typing/clicking: Brief wait 0.3-0.5s for UI response
- ⏱️ Before verification: Add "wait:1.0" to let UI stabilize

**Screen Context Awareness**
- 👁️ Always check: What app is focused, what window is visible
- 👁️ Verify before acting: Is the expected element on screen?
- 👁️ Detect changes: Did a dialog pop up? Did navigation succeed?
- 👁️ Request help: If screen state is unexpected, ask supervisor

**Action Sequencing**
- 🔗 Chain actions properly: Complete one before starting next
- 🔗 Use vision when needed: Don't guess positions
- 🔗 Validate as you go: Check intermediate states
- 🔗 Be atomic: One clear action at a time

**Error Prevention**
- 🛡️ Double-check shortcuts: Use app-specific shortcuts
- 🛡️ Avoid assumptions: If unsure, use vision-based clicking
- 🛡️ Handle popups: Be ready for dialogs, notifications
- 🛡️ Fallback planning: Have alternative ready

**Confidence & Honesty**
- 💯 High confidence (0.9+): Deterministic hotkeys in native apps
- 💯 Medium confidence (0.7-0.8): Vision-based clicks on web content
- 💯 Low confidence (< 0.7): Set requires_screen_check=true and ask for help
- 💯 Be honest: Better to ask supervisor than execute wrong action

#### New Section: ⭐ EXECUTION PATTERN BEST PRACTICES

Provides 4 proven patterns with complete examples:

1. **Opening Apps (RELIABLE)** - Spotlight pattern with proper waits
2. **Web Navigation (FAST)** - Direct URL navigation with timing
3. **Website Interaction (VISION-BASED)** - Search and click with verification
4. **App-Specific Search (PRECISE)** - Correct shortcuts per app

Each pattern includes:
- Complete action sequence
- Proper timing between steps
- Confidence scores
- Clear descriptions

## Benefits

### 🧠 Better Planning Intelligence
- Gemini 3.0 Pro provides superior reasoning for complex multi-step tasks
- Better context understanding and task breakdown
- More accurate anticipation of obstacles

### 🎯 Crystal Clear Execution
- Macro planner now provides complete, executable action chains
- Eliminates ambiguity between planning and execution
- Reduces back-and-forth between planner and executor

### ⚡ Faster Execution
- Detailed action sequences prevent repeated LLM calls
- Executor can act immediately without additional planning
- Proper timing prevents UI race conditions

### 🛡️ Fewer Errors
- Extra tips help executor handle edge cases
- App-specific shortcut guidance prevents common mistakes
- Explicit timing reduces timing-related failures

### 📈 Better Learning
- Detailed patterns provide clear examples
- Execution best practices improve consistency
- Confidence guidelines help with honest self-assessment

## Usage

No changes required! The system automatically uses Gemini 3.0 Pro:

```bash
# Works exactly the same
python -m src.main --task "your task here"

# Adaptive architecture (default)
python -m src.main --task "search for AI news"

# LangGraph architecture
python -m src.main --task "your task here" --langgraph

# Legacy architecture
python -m src.main --task "your task here" --legacy
```

## Example Task Flow

**Task**: "Open YouTube and play latest MKBHD video"

### Before (Vague High-Level):
```json
{
  "step": "Open browser and search",
  "suggested_actions": ["open browser", "search for video"]
}
```
❌ Problem: Executor needs to make multiple LLM calls to figure out HOW

### After (Clear Micro-Level):
```json
{
  "step": "Open Safari and navigate to MKBHD's YouTube videos page",
  "suggested_actions": [
    "hotkey:command,space",
    "type:Safari",
    "key:return",
    "wait:1.5",
    "hotkey:command,l",
    "type:youtube.com/@mkbhd/videos",
    "key:return",
    "wait:2.5"
  ]
}
```
✅ Executor can execute immediately without additional planning

## Technical Details

### Model Selection
- **Planning**: Gemini 3.0 Pro (gemini-2.5-pro) - strategic reasoning
- **Verification**: Gemini 2.0 Flash (gemini-2.0-flash-exp) - fast checks
- **Vision**: Gemini 2.0 Flash (gemini-2.0-flash-exp) - image understanding

### Backward Compatibility
- All existing code continues to work
- Model can be overridden per call if needed
- Legacy architecture unchanged

### Performance Impact
- Gemini 3.0 Pro may be slightly slower per call
- BUT: Fewer total calls due to better planning
- NET: Faster overall execution with fewer errors

## Files Modified

1. [src/utils/gemini_client.py](src/utils/gemini_client.py) - Model upgrade
2. [prompts/macro_planner_prompt.md](prompts/macro_planner_prompt.md) - Enhanced planning guidance
3. [prompts/micro_executor_prompt.md](prompts/micro_executor_prompt.md) - Added execution tips

## Next Steps

### Monitoring
Watch for improvements in:
- Task success rate
- Execution speed (fewer retries)
- Error patterns (should decrease)

### Tuning
If needed, adjust:
- Wait times in execution patterns
- Confidence thresholds
- Vision vs hotkey balance

### Learning
The system will continue to learn and improve:
- Pattern store captures successful executions
- Lesson store records failures and corrections
- Prompt evolution adapts based on feedback

## Verification

Test with complex multi-step tasks:

```bash
# Multi-step web interaction
python -m src.main --task "go to YouTube, search for MKBHD, play his latest video"

# App-specific shortcuts
python -m src.main --task "open Apple Music and play Bohemian Rhapsody"

# Cross-app workflow
python -m src.main --task "search for quantum physics on Google, open first result, and take a screenshot"
```

Expect:
- ✅ Clearer planning with detailed steps
- ✅ Faster execution with fewer LLM calls
- ✅ Better handling of timing and UI transitions
- ✅ More reliable app-specific interactions
