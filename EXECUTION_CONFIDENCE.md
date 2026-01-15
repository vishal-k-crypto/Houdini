# Execution Confidence Model

A sophisticated confidence estimation system that rates actions before execution and decides whether to proceed, defer, or retry based on calibrated confidence scores.

## Overview

The Execution Confidence Model provides:

1. **Action Rating (0-10 scale)** - Each action gets a confidence score based on:
   - Historical success rate (Thompson Sampling)
   - Context fit (app state, screen visibility)
   - Action complexity (simple vs complex operations)
   - Element certainty (target found, match confidence)
   - Temporal patterns (recent performance)

2. **Multi-Level Confidence Classification**:
   | Level | Score Range | Meaning |
   |-------|-------------|---------|
   | CRITICAL | 9-10 | Execute immediately, very high confidence |
   | HIGH | 7-8.9 | Execute with light verification |
   | MODERATE | 5-6.9 | Execute with verification checkpoint |
   | LOW | 3-4.9 | Requires confirmation or alternative |
   | VERY_LOW | 1-2.9 | Should not execute, needs retry or human input |
   | UNCERTAIN | 0-0.9 | Cannot assess, need more information |

3. **Smart Decision Making**:
   - `EXECUTE` - Proceed immediately
   - `EXECUTE_VERIFY` - Proceed with post-verification
   - `EXECUTE_CHECKPOINT` - Proceed with rollback capability
   - `DEFER_CONFIRM` - Ask for confirmation
   - `RETRY_CONTEXT` - Gather more context first
   - `ALTERNATIVE` - Try alternative approach
   - `ABORT` - Do not execute

4. **Calibrated Probabilities** - Uses Platt Scaling and Isotonic Regression to ensure when the model says "70% confident", actions actually succeed ~70% of the time.

5. **Learning from Outcomes** - Records success/failure to continuously improve predictions.

## ML Frameworks & Techniques Applied

This model integrates techniques from multiple open-source ML frameworks:

### 1. Uncertainty Calibration (uncertainty-calibration, uncertainty-toolbox)
- **Platt Scaling**: Logistic regression to map raw confidence → calibrated probability
- **Isotonic Regression**: Non-parametric monotonic calibration for better accuracy
- **Temperature Scaling**: Simple but effective calibration via learned temperature parameter
- **ECE (Expected Calibration Error)**: Measures how well calibrated the predictions are

### 2. Multi-Armed Bandits (MABWiser)
- **Thompson Sampling**: Bayesian approach with Beta distributions per action type
- **UCB (Upper Confidence Bound)**: Alternative exploration strategy balancing uncertainty

### 3. Conformal Prediction (MAPIE/crepes)
- **Prediction Intervals**: Returns [lower, upper] bounds with coverage guarantees
- **Prediction Sets**: Returns whether prediction is reliable with target coverage (90%)
- **Non-conformity Scoring**: Tracks residuals between predicted and actual outcomes

### 4. Reinforcement Learning (Q-Learning)
- **TD(λ) Learning**: Temporal difference with eligibility traces
- **State-Action Values**: Learns Q(s, a) for context-action pairs
- **Epsilon-Greedy + UCB**: Exploration strategies for action selection

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     ExecutionConfidenceModel                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌───────────────────┐        ┌───────────────────────────────────┐ │
│  │ ConfidenceCalib   │        │     ThompsonSamplingSelector      │ │
│  │     rator         │        │                                   │ │
│  ├───────────────────┤        ├───────────────────────────────────┤ │
│  │ • Platt Scaling   │        │ • Beta distributions per action   │ │
│  │ • Temperature     │        │ • Exploration/Exploitation        │ │
│  │ • Isotonic Reg    │        │ • UCB alternative                 │ │
│  │ • ECE Tracking    │        │ • Expected success calculation    │ │
│  └───────────────────┘        └───────────────────────────────────┘ │
│                                                                      │
│  ┌───────────────────┐        ┌───────────────────────────────────┐ │
│  │ ConformalPredictor│        │     QLearningActionEstimator      │ │
│  │ (MAPIE-inspired)  │        │                                   │ │
│  ├───────────────────┤        ├───────────────────────────────────┤ │
│  │ • Pred intervals  │        │ • TD(λ) with eligibility traces   │ │
│  │ • Coverage 90%    │        │ • State-action Q values           │ │
│  │ • Non-conformity  │        │ • Epsilon-greedy + UCB selection  │ │
│  │ • Pred reliability│        │ • Context feature extraction      │ │
│  └───────────────────┘        └───────────────────────────────────┘ │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │              Confidence Rating Engine (Ensemble)                 │ │
│  ├─────────────────────────────────────────────────────────────────┤ │
│  │ Inputs:                        Outputs:                          │ │
│  │ • action_type                  • score (0-10)                    │ │
│  │ • action_params                • level (enum)                    │ │
│  │ • context                      • decision (enum)                 │ │
│  │ • element_info                 • retry_strategy                  │ │
│  │                                • alternatives                    │ │
│  │                                • prediction_interval             │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │              Retry Strategy Generator                            │ │
│  ├─────────────────────────────────────────────────────────────────┤ │
│  │ • Max retries by confidence level                                │ │
│  │ • Wait time escalation                                           │ │
│  │ • Strategy modifications per attempt                             │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Basic Usage

```python
from src.utils.execution_confidence import (
    rate_action,
    should_execute_action,
    record_action_outcome,
)

# Rate an action before execution
rating = rate_action(
    action_type="click",
    action_params={"target": "Submit button"},
    context={"current_app": "Safari", "screen_active": True},
    element_info={"found": True, "confidence": 0.9, "num_matches": 1},
)

print(f"Confidence: {rating.score:.1f}/10 ({rating.level.value})")
print(f"Decision: {rating.decision.value}")

# Quick check with minimum threshold
should_exec, rating = should_execute_action(
    action_type="click",
    action_params={"target": "OK"},
    min_confidence=5.0,  # Require at least 5/10
)

if should_exec:
    # Execute the action...
    success = True  # Result of execution
    
    # Record outcome for learning
    record_action_outcome(
        action_type="click",
        action_params={"target": "OK"},
        rating=rating,
        success=success,
        execution_time=0.1,
    )
```

### Integration with Executor

```python
from src.utils.execution_confidence import (
    ExecutionConfidenceModel,
    ActionDecision,
)

class ConfidenceAwareExecutor:
    def __init__(self):
        self.confidence_model = ExecutionConfidenceModel()
    
    def execute_action(self, action_type: str, params: dict, context: dict):
        # Rate the action
        rating = self.confidence_model.rate_action(
            action_type, params, context, self.get_element_info(params)
        )
        
        # Handle based on decision
        if rating.decision == ActionDecision.EXECUTE:
            return self._execute_immediately(action_type, params)
            
        elif rating.decision == ActionDecision.EXECUTE_VERIFY:
            result = self._execute_immediately(action_type, params)
            self._verify_result(result)
            return result
            
        elif rating.decision == ActionDecision.EXECUTE_CHECKPOINT:
            checkpoint = self._create_checkpoint()
            try:
                return self._execute_immediately(action_type, params)
            except Exception:
                self._rollback(checkpoint)
                return self._try_alternatives(rating.alternative_actions)
                
        elif rating.decision == ActionDecision.ALTERNATIVE:
            return self._try_alternatives(rating.alternative_actions)
            
        elif rating.decision == ActionDecision.DEFER_CONFIRM:
            if self._get_user_confirmation(rating):
                return self._execute_immediately(action_type, params)
            return None
            
        elif rating.decision == ActionDecision.RETRY_CONTEXT:
            self._gather_more_context()
            return self.execute_action(action_type, params, self.context)
            
        else:  # ABORT
            raise ConfidenceTooLowError(rating.reasoning)
```

### Retry Handling

```python
def execute_with_retry(self, action_type, params, context):
    rating = self.confidence_model.rate_action(action_type, params, context, None)
    
    attempt = 0
    while True:
        try:
            result = self._execute(action_type, params)
            self.confidence_model.record_outcome(
                action_type, params, rating, success=True, execution_time=0.1
            )
            return result
            
        except ExecutionError as e:
            retry = self.confidence_model.get_retry_strategy(rating, attempt)
            
            if not retry["should_retry"]:
                self.confidence_model.record_outcome(
                    action_type, params, rating, success=False, 
                    execution_time=0.5, error_type=str(e)
                )
                raise
            
            # Apply retry strategy
            time.sleep(retry["wait_time"])
            
            if retry["modifications"].get("use_alternative"):
                params = self._apply_alternative(
                    params, retry["modifications"]["use_alternative"]
                )
            
            attempt += 1
```

## Component Scoring

### Historical Confidence (30%)
Uses Thompson Sampling to balance:
- **Exploitation**: Use actions that have worked well
- **Exploration**: Occasionally try uncertain actions to learn

```python
# Behind the scenes, the model maintains Beta distributions:
# Beta(successes + 1, failures + 1) for each action type
```

### Context Fit (25%)
Evaluates how well the action matches the current state:
- Current app matches expected app
- Screen is active
- No blocking dialogs
- Element is visible (for click/type)

### Action Complexity (15%)
Penalizes complex actions that are more likely to fail:
- Simple: `wait` (0.05), `hotkey` (0.15)
- Medium: `click` (0.2), `scroll` (0.2)
- Complex: `drag` (0.5), `code` (0.7)

### Element Certainty (20%)
For actions targeting UI elements:
- Element found: +0.3
- Multiple matches (ambiguous): -0.1 per extra match
- Match confidence from element finder

### Temporal Confidence (10%)
Recent success rate for this action type, with exponential decay favoring recent outcomes.

## Calibration

The model uses calibration techniques to ensure accurate probability estimates:

### Platt Scaling
Fits a sigmoid function to map raw scores to calibrated probabilities:
```
P(success) = 1 / (1 + exp(A * raw + B))
```

### Temperature Scaling
Single parameter calibration for sharpening/smoothing:
```
scaled_logit = logit / temperature
```

### Isotonic Regression
Non-parametric calibration using monotonic piecewise linear mapping.

### Conformal Prediction (MAPIE-inspired)
Provides prediction intervals with coverage guarantees:
```python
# Get prediction interval with 90% coverage guarantee
interval = model.get_prediction_interval(rating)
# Returns: {
#     "score": 7.5,
#     "interval": (6.2, 8.8),  # 90% of true outcomes fall here
#     "is_reliable": True,
#     "coverage_guarantee": 0.9
# }
```

### Q-Learning with TD(λ)
Learns state-action values with eligibility traces:
```
Q(s,a) ← Q(s,a) + α * [reward + γ*max_a' Q(s',a') - Q(s,a)] * e(s,a)
e(s,a) ← γ * λ * e(s,a) + 1  (eligibility trace)
```

### Expected Calibration Error (ECE)
Measures how well-calibrated the model is:
```
ECE = Σ |avg_confidence - avg_accuracy| * bin_size
```

## Confidence Levels & Retry Strategies

| Level | Max Retries | Retry Strategy |
|-------|-------------|----------------|
| CRITICAL | 1 | Simple retry with short wait |
| HIGH | 2 | Simple retry with short wait |
| MODERATE | 3 | Retry → Verification → Alternative |
| LOW | 2 | Gather context → Alternative |
| VERY_LOW | 1 | Screenshot + analyze |
| UNCERTAIN | 0 | No retry, request human guidance |

## Advanced Usage

### Using Prediction Intervals (Conformal Prediction)

```python
from src.utils.execution_confidence import ExecutionConfidenceModel

model = ExecutionConfidenceModel()

# Rate action and get prediction interval
rating = model.rate_action("click", {"target": "button"})
interval = model.get_prediction_interval(rating)

if interval["is_reliable"]:
    print(f"Score: {interval['score']:.1f}")
    print(f"90% confidence interval: {interval['interval']}")
else:
    print("Prediction uncertain - consider alternative approach")
```

### Selecting Best Action with RL

```python
# Select from multiple possible actions using different methods
possible_actions = [
    {"type": "click", "params": {"target": "button"}},
    {"type": "type", "params": {"text": "hello"}},
    {"type": "scroll", "params": {"direction": "down"}},
]

# Thompson Sampling (Bayesian exploration)
best, rating = model.select_best_action(possible_actions, method="thompson")

# UCB (Upper Confidence Bound)
best, rating = model.select_best_action(possible_actions, method="ucb")

# Q-Learning (learned state-action values)
best, rating = model.select_best_action(possible_actions, context, method="q_learning")
```

### Getting Comprehensive Stats

```python
stats = model.get_stats()
print(f"Calibration ECE: {stats['calibration']['ece']:.3f}")
print(f"Conformal coverage: {stats['conformal']['empirical_coverage']:.2%}")
print(f"Q-Learning actions explored: {stats['q_learning']['actions_explored']}")
```

## Data Storage

The model persists its learning in the `data/` directory:

- `confidence_calibration.json` - Calibration parameters and history
- `thompson_sampling.json` - Beta distribution parameters per action
- `execution_history.json` - Full execution history (last 1000 actions)

## Inspired By

This implementation combines concepts from several open-source ML frameworks:

1. **[uncertainty-toolbox](https://github.com/uncertainty-toolbox/uncertainty-toolbox)** - Calibration metrics (ECE, calibration error)
2. **[uncertainty-calibration](https://github.com/AnanyaKumar/calibration)** - Platt scaling, isotonic regression
3. **[MABWiser](https://github.com/fidelity/mabwiser)** - Thompson Sampling, UCB for multi-armed bandits
4. **[MAPIE](https://github.com/scikit-learn-contrib/MAPIE)** - Conformal prediction intervals with coverage guarantees
5. **[crepes](https://github.com/henrikbostrom/crepes)** - Conformal prediction for regression tasks
4. **[MAPIE](https://github.com/scikit-learn-contrib/MAPIE)** - Conformal prediction concepts

## Example Output

```
📊 Confidence Rating:
   Score: 6.1/10
   Level: MODERATE
   Calibrated: True

📈 Component Scores:
   Historical:  █████      50%
   Context Fit: ██████     60%
   Simplicity:  ████████   80%
   Element:     █████████  95%

🎯 Decision: execute_checkpoint
   ⚠️ Execute with checkpoint (can rollback)
   📋 Fallback alternatives: ['click_by_coordinates', 'click_by_accessibility']

💭 Reasoning: Confidence: 6.1/10 (moderate). Strongest signal: Element certainty (95%)
```

## Running Tests

```bash
cd /path/to/houdini-agent
source .venv/bin/activate
python test_execution_confidence.py
```

## See Also

- [examples/confidence_model_example.py](examples/confidence_model_example.py) - Full usage examples
- [PROBABILITY_MODEL.md](PROBABILITY_MODEL.md) - Related task probability model
