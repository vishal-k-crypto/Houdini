# Quick Reference - Prompt Evolution System

## 🚀 Quick Start

### Run a Task (Evolution Happens Automatically)
```bash
python -m src.main --task "your task here"
```

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
