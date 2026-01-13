# Internal Prompting System with Evolution

## Overview

This system provides intelligent, self-evolving prompts for the Houdini Agent's three core components:
- **Planner**: Task decomposition and action planning
- **Executor**: Action execution (blind and vision-based)
- **Supervisor**: Validation and quality control

Each component has a dedicated prompt file that defines its behavior, guidelines, and best practices. These prompts automatically evolve based on execution failures and learned patterns, similar to how modern AI chat models have internal system prompts.

## Architecture

```
houdini-agent/
├── prompts/                      # Internal prompt files
│   ├── planner_prompt.md         # Planner system prompt
│   ├── executor_prompt.md        # Executor system prompt
│   └── supervisor_prompt.md      # Supervisor system prompt
├── src/
│   └── utils/
│       ├── prompt_loader.py      # Centralized prompt loading
│       ├── prompt_evolution.py   # Automatic prompt evolution
│       └── prompt_stats.py       # Statistics and monitoring
└── data/
    ├── feedback_log.json         # Execution feedback
    └── prompt_evolution_log.json # Evolution history
```

## Key Features

### 1. **Centralized Prompt Management**
- All prompts stored in dedicated markdown files
- Single source of truth for component behavior
- Easy to review and manually edit if needed
- Automatic caching for performance

### 2. **Automatic Evolution**
The system learns from failures and automatically improves prompts:

```python
# Failure patterns detected automatically
- Frequent element_not_found → Add retry logic guidance
- Timing issues → Increase default wait times
- Action format errors → Clarify action specifications
```

**Evolution Triggers:**
- Failure rate > 20% (over last 100 executions)
- 5+ failures of same type
- Supervisor validation failures

### 3. **Feedback Loop**
Every execution is tracked:
```python
prompt_evolution.record_feedback(
    component="planner",
    task="search for python tutorials",
    success=True,
    execution_time=2.3,
    actions_taken=[...]
)
```

### 4. **Version Tracking**
- Each prompt evolution is logged with timestamp
- Full history of what changed and why
- Rollback capability (manual restoration)

## Usage

### Basic Usage (Automatic)

The prompt system is integrated automatically. Just run tasks normally:

```bash
python -m src.main --task "search for python tutorials"
```

The system will:
1. Load the latest evolved prompts
2. Execute the task
3. Record feedback
4. Automatically evolve prompts if needed

### View Statistics

Monitor system performance and evolution:

```bash
python -m src.utils.prompt_stats
```

This shows:
- Overall success rates
- Component-specific statistics
- Recent prompt evolutions
- Recent execution feedback
- Recommendations

### Manual Prompt Editing

You can manually edit prompts at any time:

```bash
# Edit any component's prompt
vim prompts/planner_prompt.md
vim prompts/executor_prompt.md
vim prompts/supervisor_prompt.md
```

Changes are automatically picked up on next execution.

### Force Prompt Reload

If you've manually edited prompts:

```python
from src.utils.prompt_loader import reload_prompts
reload_prompts()
```

## Prompt Structure

Each prompt file contains:

### 1. Role Definition
```markdown
## Role
You are the **Planner Agent** - an intelligent task decomposition system...
```

### 2. Core Responsibilities
Clear list of what the component does

### 3. Guidelines and Rules
Specific instructions for behavior:
- Action classification rules
- Optimization strategies
- Error handling principles
- Platform-specific knowledge

### 4. Output Formats
Exact JSON structures expected

### 5. Evolution Notes (Auto-Generated)
```markdown
## Evolution Update - 2026-01-13 15:30

**Observation**: High rate of element not found errors.
**Improvement**:
- Retry element lookup with broader search criteria
- Wait for page/UI stabilization before searching
```

## Evolution Process

### 1. Feedback Collection
```python
# Automatic in executor
prompt_evolution.record_feedback(
    component="executor",
    task="click login button",
    success=False,
    error_type="element_not_found",
    error_details="Button 'login' not found in accessibility tree"
)
```

### 2. Pattern Analysis
When failure rate exceeds threshold:
```python
analysis = {
    "total_failures": 8,
    "error_types": {"element_not_found": 5, "timeout": 3},
    "patterns": ["frequent_element_not_found", "timing_issues"]
}
```

### 3. Improvement Generation
```python
improvement = """
## Evolution Update - 2026-01-13 15:30
**Observation**: High rate of element not found errors.
**Improvement**:
- Retry with broader search criteria
- Add explicit wait times
"""
```

### 4. Prompt Update
Improvement is appended to the prompt file automatically.

### 5. Verification
Monitor statistics to verify improvements work:
```bash
python -m src.utils.prompt_stats
```

## Learning Categories

### Planner Learnings
- Better action batching strategies
- Improved timing estimates
- More accurate action formats
- Task pattern recognition

### Executor Learnings
- Optimal wait times
- Better element selectors
- Retry strategies
- Error recovery patterns

### Supervisor Learnings
- More accurate validation criteria
- Better failure detection
- Improved suggestion quality
- Context-aware validation

## API Reference

### PromptLoader

```python
from src.utils.prompt_loader import prompt_loader

# Load a component's prompt
prompt = prompt_loader.load_prompt("planner")

# Get prompt information
info = prompt_loader.get_prompt_info("executor")

# Reload all prompts
prompt_loader.reload_all()

# Check for updates
updates = prompt_loader.check_for_updates()
```

### PromptEvolution

```python
from src.utils.prompt_evolution import prompt_evolution

# Record feedback
prompt_evolution.record_feedback(
    component="planner",
    task="search python",
    success=True,
    execution_time=1.5,
    actions_taken=["open safari", "search"]
)

# Get statistics
stats = prompt_evolution.get_statistics()

# Get success rate
rate = prompt_evolution.get_success_rate("executor", window=100)

# Get recent learnings
learnings = prompt_evolution.get_recent_learnings("planner", count=5)

# Manually trigger evolution (usually automatic)
prompt_evolution.evolve_prompt("executor", recent_failures)
```

## Best Practices

### 1. Let It Learn
- Don't manually intervene too early
- Let the system collect feedback (50+ executions)
- Review evolution logs regularly

### 2. Monitor Regularly
```bash
# Check stats after significant testing
python -m src.utils.prompt_stats
```

### 3. Review Evolutions
Check [data/prompt_evolution_log.json](../data/prompt_evolution_log.json) to see what the system learned.

### 4. Manual Refinement
If automated evolution isn't working:
- Edit prompt files directly
- Add specific examples
- Clarify ambiguous guidelines
- Remove outdated evolution notes

### 5. Test After Changes
Run diverse tasks after manual edits:
```bash
python -m src.main --task "open safari"
python -m src.main --task "search for AI news"
python -m src.main --task "click first result"
```

## Troubleshooting

### Prompts Not Loading
```python
from src.utils.prompt_loader import prompt_loader
info = prompt_loader.get_all_prompts_info()
print(info)
```

### No Evolution Happening
- Check failure rate (needs >20%)
- Verify feedback is being recorded
- Check `data/feedback_log.json`

### Too Many Evolutions
- System might be unstable
- Review `data/prompt_evolution_log.json`
- Consider resetting prompts to baseline

### Reset a Prompt
1. Backup current version: `cp prompts/planner_prompt.md prompts/planner_prompt.backup`
2. Remove evolution sections manually
3. Or restore from git: `git checkout prompts/planner_prompt.md`

## Data Files

### feedback_log.json
Records every execution:
```json
{
  "timestamp": "2026-01-13T15:30:00",
  "component": "executor",
  "task": "click button",
  "success": false,
  "error_type": "element_not_found",
  "execution_time": 2.3
}
```

### prompt_evolution_log.json
Tracks prompt changes:
```json
{
  "timestamp": "2026-01-13T15:30:00",
  "component": "executor",
  "analysis": {...},
  "improvement": "...",
  "failure_count": 8
}
```

## Future Enhancements

Potential improvements:
- [ ] A/B testing of prompt variations
- [ ] Success pattern learning (not just failures)
- [ ] Cross-component learning
- [ ] User preference learning
- [ ] Automated prompt compression (remove outdated rules)
- [ ] Multi-model prompt optimization

## Contributing

When adding features:
1. Update relevant prompt files with new capabilities
2. Add feedback recording for new failure modes
3. Document new error types in prompt evolution system
4. Test evolution triggers with new patterns

## License

Part of the Houdini Agent project.
