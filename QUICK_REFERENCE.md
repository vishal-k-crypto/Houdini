# Quick Reference - Prompt Evolution System

## 🚀 Quick Start

### Run a Task (Evolution Happens Automatically)
```bash
# With thinking window (default)
python -m src.main --task "your task here" --loop

# Without thinking window
python -m src.main --task "your task here" --loop --no-thinking-window

# Demo the thinking window
python demo_thinking_window.py
```

## 💭 Thinking Window

**Real-time AI reasoning display** - see what the agent is thinking!

- **Planner** (Teal): Task analysis and planning
- **Executor** (Orange): Action execution
- **Supervisor** (Purple): Validation and monitoring
- **Draggable**: Click header to move
- **Collapsible**: Click - / + button
- **Clear**: Click 🗑 to clear messages

See [THINKING_WINDOW.md](THINKING_WINDOW.md) for details.

## ⌨️ macOS Cursor Movement & Text Manipulation Features

The agent supports **powerful macOS keyboard shortcuts** for lightning-fast automation - 10-100x faster than clicking!

### 🎯 Text Navigation (Jump Instantly - No Clicking!)

**Line Navigation:**
```python
"hotkey:command,left"   # Jump to beginning of line
"hotkey:command,right"  # Jump to end of line
```

**Word Navigation:**
```python
"hotkey:option,left"    # Jump one word left
"hotkey:option,right"   # Jump one word right
```

**Document Navigation:**
```python
"hotkey:command,up"     # Jump to top of document
"hotkey:command,down"   # Jump to bottom of document
```

### ✂️ Text Selection (Add Shift to Any Movement)

```python
"hotkey:command,shift,right"  # Select to end of line
"hotkey:option,shift,right"   # Select next word
"hotkey:command,shift,down"   # Select to end of document
"hotkey:command,a"            # Select all (fastest!)
```

### 🚀 Text Manipulation (Human Speed!)

**Replace All Text (25x faster!):**
```python
# ❌ SLOW: 50 backspaces + type (51 actions)
# ✅ FAST: 2 actions!
["hotkey:command,a", "type:new text"]
```

**Delete Operations:**
```python
"hotkey:option,backspace"    # Delete word backwards (INSTANT!)
"hotkey:command,backspace"   # Delete to beginning of line
"hotkey:option,delete"       # Delete word forwards
```

**Clipboard Operations:**
```python
"hotkey:command,c"  # Copy
"hotkey:command,x"  # Cut
"hotkey:command,v"  # Paste
```

**Undo/Redo:**
```python
"hotkey:command,z"        # Undo
"hotkey:command,shift,z"  # Redo
```

### 🪟 Window Management

```python
"hotkey:command,tab"          # Switch apps
"hotkey:command,shift,tab"    # Switch apps backwards
"hotkey:command,grave"        # Switch windows of same app (Cmd+`)
"hotkey:control,left"         # Previous space/desktop
"hotkey:control,right"        # Next space/desktop
"hotkey:command,m"            # Minimize
"hotkey:command,h"            # Hide app
```

### 🌐 Browser Shortcuts

```python
"hotkey:command,f"       # Find
"hotkey:command,l"       # Focus address bar (auto-selects URL!)
"hotkey:command,r"       # Reload
"hotkey:command,plus"    # Zoom in (Cmd+=)
"hotkey:command,minus"   # Zoom out
"hotkey:command,0"       # Reset zoom
"hotkey:command,leftbracket"   # Back
"hotkey:command,rightbracket"  # Forward
```

### 💡 Real-World Examples

**Example 1: Edit URL (3 actions instead of 10+)**
```python
# ❌ SLOW: Click address bar → Triple-click → Type
# ✅ FAST: Cmd+L auto-selects everything!
["hotkey:command,l", "type:https://youtube.com", "key:return"]
```

**Example 2: Replace Text in Field**
```python
# ❌ SLOW: Click, select all, type
# ✅ FAST: Select all + type
["hotkey:command,a", "type:completely new text"]
```

**Example 3: Copy Entire Document**
```python
# ❌ SLOW: Click top, drag to bottom, copy
# ✅ FAST: 2 commands!
["hotkey:command,a", "hotkey:command,c"]
```

**Example 4: Fix Last Word**
```python
# ❌ SLOW: Click, select, delete, retype
# ✅ FAST: Delete word + type!
["hotkey:option,backspace", "type:correct_word"]
```

**Example 5: Go to End and Append**
```python
["hotkey:command,right", "type: additional text"]
```

### 🎓 Efficiency Patterns

| Task | Slow Method | Fast Method | Speed Gain |
|------|-------------|-------------|------------|
| Replace 50 chars | 50 backspaces + type | Cmd+A + type | **25x faster** |
| Delete word | 10 backspaces | Opt+Backspace | **10x faster** |
| Go to end | Click position | Cmd+Right | **Instant** |
| Select all | Click & drag | Cmd+A | **20x faster** |

### ⚡ Pro Tips

1. **Always prefer Cmd+A over clicking to select**
2. **Use Opt+Backspace to delete words, not character by character**
3. **Cmd+L in browsers auto-selects the entire URL**
4. **Jump with Cmd/Opt+arrows instead of clicking**
5. **Add Shift to any movement to select while moving**

### View System Statistics
```bash
python -m src.utils.prompt_stats
```

### Run Examples
```bash
python examples/prompt_system_example.py
```

## 📁 Important Files

| File | Purpose |
|------|---------|
| `prompts/planner_prompt.md` | Planner system prompt |
| `prompts/executor_prompt.md` | Executor system prompt |
| `prompts/supervisor_prompt.md` | Supervisor system prompt |
| `data/feedback_log.json` | Execution feedback data |
| `data/prompt_evolution_log.json` | Evolution history |
| `src/utils/prompt_config.py` | Configuration settings |

## 🔧 Configuration

Edit `src/utils/prompt_config.py`:

```python
# Evolution triggers
"min_failures_for_evolution": 5      # Min failures to evolve
"failure_rate_threshold": 0.2        # 20% failure rate = evolve
"failure_rate_window": 100           # Look at last 100 executions

# Enable/disable per component
COMPONENT_CONFIG = {
    "planner": {"enabled": True},
    "executor": {"enabled": True},
    "supervisor": {"enabled": True}
}
```

## 📊 Monitoring Commands

```python
# Get overall statistics
from src.utils.prompt_evolution import prompt_evolution
stats = prompt_evolution.get_statistics()

# Get success rate
rate = prompt_evolution.get_success_rate("executor")

# Get recent learnings
learnings = prompt_evolution.get_recent_learnings("planner", count=5)

# View prompt info
from src.utils.prompt_loader import prompt_loader
info = prompt_loader.get_prompt_info("executor")
```

## 🎯 Common Tasks

### Manually Edit a Prompt
```bash
vim prompts/planner_prompt.md
```
Changes are picked up automatically on next execution.

### Force Reload Prompts
```python
from src.utils.prompt_loader import reload_prompts
reload_prompts()
```

### Record Custom Feedback
```python
from src.utils.prompt_evolution import prompt_evolution

prompt_evolution.record_feedback(
    component="executor",
    task="click button",
    success=False,
    error_type="element_not_found",
    error_details="Button not found in tree"
)
```

### Check for Prompt Updates
```python
from src.utils.prompt_loader import prompt_loader
updates = prompt_loader.check_for_updates()
print(updates)  # {'planner': False, 'executor': True, ...}
```

## 🔍 Troubleshooting

### No evolution happening?
- ✓ Check if enough executions (min 10)
- ✓ Check failure rate (need >20%)
- ✓ Verify evolution enabled in config

### Too many evolutions?
- ✓ Increase `failure_rate_threshold`
- ✓ Increase `min_failures_for_evolution`
- ✓ Add `evolution_cooldown` period

### Prompts not loading?
```python
from src.utils.prompt_loader import prompt_loader
info = prompt_loader.get_all_prompts_info()
```

## 📈 Success Indicators

| Metric | Excellent | Good | Needs Work |
|--------|-----------|------|------------|
| Success Rate | >90% | 70-90% | <70% |
| Evolutions | 3-10 | 10-20 | >20 |
| Feedback Entries | 100+ | 50-100 | <50 |

## 🎓 Learning Patterns

The system automatically learns from:

1. **Element Not Found** → Better selectors, retry logic
2. **Timing Issues** → Longer waits, adaptive timing
3. **Format Errors** → Clearer specifications
4. **Validation Failures** → Better criteria

## 💡 Best Practices

1. ✅ Run diverse tasks (50-100 executions)
2. ✅ Monitor stats regularly
3. ✅ Review evolution logs weekly
4. ✅ Let system learn before manual intervention
5. ✅ Keep prompts version controlled

## 📚 Documentation

- **Full Docs**: [PROMPT_SYSTEM.md](PROMPT_SYSTEM.md)
- **Implementation**: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
- **Examples**: [examples/prompt_system_example.py](examples/prompt_system_example.py)

## 🆘 Support

Check these files for details:
1. `PROMPT_SYSTEM.md` - Complete documentation
2. `IMPLEMENTATION_SUMMARY.md` - What was built
3. `data/prompt_evolution_log.json` - What the system learned
4. `data/feedback_log.json` - Execution history

## 🎉 Quick Wins

```bash
# 1. Run a task
python -m src.main --task "open safari"

# 2. Check stats
python -m src.utils.prompt_stats

# 3. See examples
python examples/prompt_system_example.py

# 4. Review prompts
cat prompts/planner_prompt.md
```

That's it! The system learns and improves automatically. 🚀
