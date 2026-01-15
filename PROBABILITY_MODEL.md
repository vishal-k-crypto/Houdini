# Probability Model for Task Flexibility

The Probability Model adds intelligence to the Houdini executor by handling:
- **Incomplete task specifications** (user provides 80-90% of the info)
- **Macro-micro spectrum tasks** (not fully detailed, but not just a goal)
- **Ambiguous intent** (when the user's intent isn't crystal clear)

## Overview

The system combines three proven approaches:

### 1. Fuzzy Logic (scikit-fuzzy)
Handles the macro-micro spectrum using fuzzy membership functions:
- **Input**: Task specificity, action granularity, context dependency
- **Output**: Execution level (macro/hybrid/micro) with smooth transitions

### 2. Bayesian Networks (pgmpy)
Models probabilistic relationships between task components:
- Task completeness depends on: target, action, location, criteria
- Intent clarity depends on: context availability
- Execution success depends on: completeness + intent clarity

### 3. Pattern-Based Intent Prediction
Uses learned patterns and heuristics to predict:
- Primary intent (navigation, interaction, communication, media, file_management)
- Alternative intents with probabilities
- Ambiguity score

## Architecture

```
User Task
    │
    ▼
┌─────────────────────────────────────┐
│      TaskProbabilityModel           │
│  ┌─────────────────────────────┐    │
│  │ FuzzyMacroMicroAnalyzer     │───▶ MacroMicroPosition
│  │ (scikit-fuzzy)              │    │
│  └─────────────────────────────┘    │
│  ┌─────────────────────────────┐    │
│  │ BayesianTaskAnalyzer        │───▶ TaskCompleteness
│  │ (pgmpy)                     │    │
│  └─────────────────────────────┘    │
│  ┌─────────────────────────────┐    │
│  │ IntentPredictor             │───▶ IntentPrediction
│  │ (pattern matching)          │    │
│  └─────────────────────────────┘    │
└─────────────────────────────────────┘
    │
    ▼
ExecutionFlexibility
    │
    ▼
┌─────────────────────────────────────┐
│ Dynamic Execution Parameters        │
│ - min_match_probability             │
│ - verification_strictness           │
│ - fallback_chain                    │
│ - exploration_enabled               │
└─────────────────────────────────────┘
```

## Usage

### Basic Analysis

```python
from src.utils.probability_model import analyze_task_flexibility

task = "send a message to kushal"
flexibility = analyze_task_flexibility(task)

print(f"Completeness: {flexibility.task_completeness.overall_score:.0%}")
print(f"Intent: {flexibility.intent.primary_intent}")
print(f"Uncertainty: {flexibility.overall_uncertainty:.0%}")
```

### Get Execution Parameters

```python
from src.utils.probability_model import get_flexible_execution_params

params = get_flexible_execution_params("click the button")
print(f"Min match threshold: {params['min_match_probability']:.0%}")
print(f"Verification: {params['verification_strictness']}")
```

### Full Model Access

```python
from src.utils.probability_model import TaskProbabilityModel

model = TaskProbabilityModel()
flexibility = model.analyze("search for AI news")

# Record feedback for learning
model.record_feedback("search for AI news", success=True, actual_intent="navigation")
```

## Key Concepts

### Task Completeness (0.0 - 1.0)

Measures how much information the user provided:
- **has_target**: Does the task specify what to click/interact with?
- **has_action**: Does it specify the action (click, type, scroll)?
- **has_location**: Does it specify the app/context?
- **has_criteria**: Does it specify how to verify success?

**Examples**:
- "open the latest MrBeast video on YouTube" → 85% complete
- "click something" → 30% complete
- "search" → 20% complete

### Macro-Micro Position (0.0 - 1.0)

Where the task falls on the spectrum:
- **0.0** = Pure macro (high-level goal, needs planning)
- **0.5** = Hybrid (mix of goal and specific actions)
- **1.0** = Pure micro (specific actions, direct execution)

**Examples**:
- "search for AI news" → 0.2 (macro)
- "click the first search result" → 0.6 (hybrid)
- "press cmd+space, type Safari, press enter" → 0.9 (micro)

### Intent Ambiguity (0.0 - 1.0)

How clear the user's intent is:
- **0.0** = Crystal clear intent
- **0.5** = Some ambiguity
- **1.0** = Very ambiguous

### Execution Strategy

Based on analysis, the model recommends:
- **macro_plan**: Full planning needed, break into steps
- **micro_direct**: Direct execution, skip planning
- **hybrid**: Mix of planning and direct execution

### Dynamic Match Probability

The model adjusts element matching thresholds:
- **High uncertainty** → Lower threshold (0.4) + strict verification
- **Moderate uncertainty** → Medium threshold (0.55) + exploration
- **Low uncertainty** → Higher threshold (0.7) + light verification

## Integration

The probability model is integrated into:

### 1. Vision Executor (`vision_executor.py`)
```python
# Gets flexible execution params
exec_params = get_flexible_execution_params(action_description, context)
min_match_prob = exec_params.get('min_match_probability', 0.5)

# Uses dynamic threshold for coordinate prediction
result = _fast_coordinate_fallback(action_description, min_match_prob)
```

### 2. Adaptive Coordinator (`adaptive_coordinator.py`)
```python
# Analyzes task before planning
self._analyze_task_flexibility(task)

# Uses analysis in macro planning
if self.state.task_flexibility:
    # Include predicted info in planner prompt
    # Adjust planning granularity
    # Add verification steps if uncertain
```

## Installation

The probability model uses these packages:

```bash
pip install scikit-fuzzy pgmpy networkx
```

These are optional - the model gracefully falls back to simpler logic if unavailable.

## Testing

Run the test suite:

```bash
python test_probability_model.py
```

## Configuration

### Adjusting Thresholds

In `probability_model.py`, you can adjust:

```python
# Task completeness weights
weights = {'target': 0.35, 'action': 0.35, 'location': 0.2, 'criteria': 0.1}

# Uncertainty → match probability mapping
if uncertainty > 0.6:
    min_match = 0.4  # Lower threshold
elif uncertainty > 0.3:
    min_match = 0.55  # Medium threshold
else:
    min_match = 0.7  # Higher threshold
```

### Learning from History

The model learns from:
- `data/patterns.json` - Successful task patterns
- `data/task_history.json` - Past tasks
- `data/probability_feedback.json` - Explicit feedback

## Fallback Behavior

If dependencies aren't available:
1. **No scikit-fuzzy**: Uses weighted average for macro-micro
2. **No pgmpy**: Uses rule-based completeness scoring
3. **Both missing**: Full functionality via pure Python logic

The system never fails - it gracefully degrades.
