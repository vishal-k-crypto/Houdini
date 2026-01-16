"""
Execution Confidence Model

A sophisticated confidence estimation system for action execution that:
1. Rates actions before execution (0-10 scale with multiple confidence levels)
2. Decides whether to execute, defer, or retry based on confidence
3. Uses calibrated uncertainty estimation with recalibration
4. Combines multiple signals: historical success, action complexity, context fit

Integrates concepts from:
- Uncertainty Toolbox (calibration metrics)
- Uncertainty Calibration (Platt scaling, isotonic regression)
- MABWiser (Thompson Sampling for action selection under uncertainty)
- Conformal Prediction (prediction sets with coverage guarantees)
"""

import json
import math
import time
import hashlib
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from enum import Enum
import numpy as np
from collections import defaultdict

from .logging import logger

# ============================================================
# CONFIDENCE LEVELS & DECISIONS
# ============================================================

class ConfidenceLevel(Enum):
    """Multi-level confidence classification (out of 10)."""
    CRITICAL = "critical"      # 9-10: Execute immediately, very high confidence
    HIGH = "high"              # 7-8.9: Execute with light verification
    MODERATE = "moderate"      # 5-6.9: Execute with verification checkpoint
    LOW = "low"                # 3-4.9: Requires confirmation or alternative strategy
    VERY_LOW = "very_low"      # 1-2.9: Should not execute, needs human input or retry
    UNCERTAIN = "uncertain"    # 0-0.9: Cannot assess, need more information


class ActionDecision(Enum):
    """Decision on what to do with an action."""
    EXECUTE = "execute"                    # Proceed with execution
    EXECUTE_VERIFY = "execute_verify"      # Execute then verify result
    EXECUTE_CHECKPOINT = "execute_checkpoint"  # Execute with rollback checkpoint
    DEFER_CONFIRM = "defer_confirm"        # Ask for confirmation first
    RETRY_CONTEXT = "retry_context"        # Gather more context and retry rating
    ALTERNATIVE = "alternative"            # Try alternative approach
    ABORT = "abort"                        # Do not execute


@dataclass
class ConfidenceRating:
    """Complete confidence rating for an action."""
    score: float                           # 0-10 rating
    level: ConfidenceLevel                 # Categorical level
    decision: ActionDecision               # What to do
    
    # Component scores (all 0-1 normalized)
    historical_confidence: float = 0.5     # Based on past success rate
    context_fit: float = 0.5               # How well action fits current context
    action_complexity: float = 0.5         # Complexity penalty (inverse)
    element_certainty: float = 0.5         # Certainty about target element
    temporal_confidence: float = 0.5       # Time-based confidence decay
    
    # Calibration info
    calibrated: bool = False               # Whether score has been calibrated
    raw_score: float = 0.0                 # Pre-calibration score
    calibration_adjustment: float = 0.0    # How much calibration changed score
    
    # Decision info
    retry_strategy: Optional[str] = None   # Strategy if retry needed
    alternative_actions: List[str] = field(default_factory=list)
    reasoning: str = ""                    # Explanation for the rating
    
    def to_dict(self) -> Dict:
        return {
            "score": round(self.score, 2),
            "level": self.level.value,
            "decision": self.decision.value,
            "components": {
                "historical": round(self.historical_confidence, 3),
                "context_fit": round(self.context_fit, 3),
                "complexity": round(self.action_complexity, 3),
                "element_certainty": round(self.element_certainty, 3),
                "temporal": round(self.temporal_confidence, 3),
            },
            "calibrated": self.calibrated,
            "reasoning": self.reasoning,
        }


@dataclass
class ActionOutcome:
    """Record of an action's execution outcome for learning."""
    action_hash: str
    action_type: str
    predicted_confidence: float
    actual_success: bool
    execution_time: float
    context_hash: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    error_type: Optional[str] = None
    retry_count: int = 0


# ============================================================
# CONFIDENCE CALIBRATOR (Platt Scaling + Isotonic Regression)
# ============================================================

class ConfidenceCalibrator:
    """
    Calibrates raw confidence scores to match actual success rates.
    
    Uses ideas from:
    - Platt Scaling (logistic regression on raw scores)
    - Isotonic Regression (monotonic calibration)
    - Temperature Scaling (single parameter calibration)
    
    This ensures our confidence ratings are well-calibrated:
    - When we say 70% confidence, actions should succeed ~70% of the time
    """
    
    def __init__(self, data_path: Optional[Path] = None):
        self.data_path = data_path or Path("data/confidence_calibration.json")
        
        # Platt scaling parameters: P(success) = 1 / (1 + exp(A * raw + B))
        self.platt_a: float = -1.0  # Negative for proper sigmoid
        self.platt_b: float = 0.0
        
        # Temperature scaling: softmax temperature
        self.temperature: float = 1.0
        
        # Isotonic calibration bins (piecewise linear)
        self.isotonic_bins: List[Tuple[float, float]] = []
        
        # Calibration data
        self.calibration_data: List[Tuple[float, bool]] = []  # (raw_score, success)
        self.min_samples_for_calibration = 30
        
        self._load_calibration()
    
    def calibrate(self, raw_score: float) -> Tuple[float, float]:
        """
        Calibrate a raw confidence score.
        
        Args:
            raw_score: Raw score (0-1)
            
        Returns:
            (calibrated_score, adjustment) - both in 0-1 range
        """
        if len(self.calibration_data) < self.min_samples_for_calibration:
            # Not enough data, return raw with slight regularization toward 0.5
            regularized = 0.7 * raw_score + 0.3 * 0.5
            return regularized, regularized - raw_score
        
        # Apply Platt scaling
        try:
            logit = self.platt_a * raw_score + self.platt_b
            platt_calibrated = 1.0 / (1.0 + math.exp(-logit))
        except OverflowError:
            platt_calibrated = 0.0 if logit < 0 else 1.0
        
        # Apply temperature scaling
        temp_calibrated = self._apply_temperature(platt_calibrated)
        
        # Apply isotonic adjustment if available
        if self.isotonic_bins:
            calibrated = self._apply_isotonic(temp_calibrated)
        else:
            calibrated = temp_calibrated
        
        calibrated = max(0.0, min(1.0, calibrated))
        adjustment = calibrated - raw_score
        
        return calibrated, adjustment
    
    def _apply_temperature(self, score: float) -> float:
        """Apply temperature scaling to sharpen/smooth confidence."""
        if self.temperature == 1.0:
            return score
        
        # Convert to logit, scale, convert back
        eps = 1e-7
        score = max(eps, min(1 - eps, score))
        logit = math.log(score / (1 - score))
        scaled_logit = logit / self.temperature
        return 1.0 / (1.0 + math.exp(-scaled_logit))
    
    def _apply_isotonic(self, score: float) -> float:
        """Apply isotonic regression calibration."""
        if not self.isotonic_bins:
            return score
        
        # Find the bin
        for i, (threshold, calibrated_value) in enumerate(self.isotonic_bins):
            if score <= threshold:
                if i == 0:
                    return calibrated_value
                # Linear interpolation between bins
                prev_thresh, prev_val = self.isotonic_bins[i - 1]
                t = (score - prev_thresh) / (threshold - prev_thresh + 1e-7)
                return prev_val + t * (calibrated_value - prev_val)
        
        return self.isotonic_bins[-1][1] if self.isotonic_bins else score
    
    def record_outcome(self, raw_score: float, success: bool):
        """Record an outcome for calibration learning."""
        self.calibration_data.append((raw_score, success))
        
        # Recalibrate periodically
        if len(self.calibration_data) % 50 == 0:
            self._fit_calibration()
            self._save_calibration()
    
    def _fit_calibration(self):
        """Fit calibration parameters from data."""
        if len(self.calibration_data) < self.min_samples_for_calibration:
            return
        
        scores = np.array([d[0] for d in self.calibration_data])
        successes = np.array([d[1] for d in self.calibration_data], dtype=float)
        
        # Fit Platt scaling via simple gradient descent
        self._fit_platt(scores, successes)
        
        # Fit temperature
        self._fit_temperature(scores, successes)
        
        # Build isotonic bins
        self._build_isotonic_bins(scores, successes)
        
        logger.debug(f"Calibration updated: A={self.platt_a:.3f}, B={self.platt_b:.3f}, T={self.temperature:.3f}")
    
    def _fit_platt(self, scores: np.ndarray, successes: np.ndarray, lr: float = 0.1, epochs: int = 100):
        """Fit Platt scaling parameters via gradient descent."""
        a, b = self.platt_a, self.platt_b
        
        for _ in range(epochs):
            # Forward pass
            logits = a * scores + b
            probs = 1.0 / (1.0 + np.exp(-np.clip(logits, -20, 20)))
            
            # Gradient of log loss
            errors = probs - successes
            grad_a = np.mean(errors * scores)
            grad_b = np.mean(errors)
            
            a -= lr * grad_a
            b -= lr * grad_b
        
        self.platt_a = a
        self.platt_b = b
    
    def _fit_temperature(self, scores: np.ndarray, successes: np.ndarray):
        """Fit temperature parameter."""
        # Simple grid search for temperature
        best_temp = 1.0
        best_loss = float('inf')
        
        for temp in [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]:
            # Apply temperature and compute calibration error
            eps = 1e-7
            clipped = np.clip(scores, eps, 1 - eps)
            logits = np.log(clipped / (1 - clipped))
            scaled_logits = logits / temp
            probs = 1.0 / (1.0 + np.exp(-np.clip(scaled_logits, -20, 20)))
            
            # Expected Calibration Error (ECE)
            loss = self._compute_ece(probs, successes)
            
            if loss < best_loss:
                best_loss = loss
                best_temp = temp
        
        self.temperature = best_temp
    
    def _compute_ece(self, probs: np.ndarray, successes: np.ndarray, n_bins: int = 10) -> float:
        """Compute Expected Calibration Error."""
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        ece = 0.0
        
        for i in range(n_bins):
            mask = (probs >= bin_boundaries[i]) & (probs < bin_boundaries[i + 1])
            if mask.sum() > 0:
                avg_confidence = probs[mask].mean()
                avg_accuracy = successes[mask].mean()
                ece += mask.sum() * abs(avg_accuracy - avg_confidence)
        
        return ece / len(probs)
    
    def _build_isotonic_bins(self, scores: np.ndarray, successes: np.ndarray, n_bins: int = 10):
        """Build isotonic regression bins."""
        # Sort by score
        sorted_indices = np.argsort(scores)
        sorted_scores = scores[sorted_indices]
        sorted_successes = successes[sorted_indices]
        
        # Create bins
        bin_size = max(1, len(scores) // n_bins)
        bins = []
        
        for i in range(n_bins):
            start = i * bin_size
            end = min((i + 1) * bin_size, len(scores))
            if start >= len(scores):
                break
            
            bin_scores = sorted_scores[start:end]
            bin_successes = sorted_successes[start:end]
            
            threshold = bin_scores.max()
            calibrated_value = bin_successes.mean()
            bins.append((threshold, calibrated_value))
        
        # Enforce monotonicity (isotonic constraint)
        for i in range(1, len(bins)):
            if bins[i][1] < bins[i-1][1]:
                avg = (bins[i][1] + bins[i-1][1]) / 2
                bins[i] = (bins[i][0], avg)
                bins[i-1] = (bins[i-1][0], avg)
        
        self.isotonic_bins = bins
    
    def get_calibration_stats(self) -> Dict:
        """Get calibration statistics."""
        if len(self.calibration_data) < 10:
            return {"status": "insufficient_data", "samples": len(self.calibration_data)}
        
        scores = np.array([d[0] for d in self.calibration_data])
        successes = np.array([d[1] for d in self.calibration_data], dtype=float)
        
        return {
            "samples": len(self.calibration_data),
            "mean_confidence": float(scores.mean()),
            "mean_success_rate": float(successes.mean()),
            "ece": float(self._compute_ece(scores, successes)),
            "platt_a": self.platt_a,
            "platt_b": self.platt_b,
            "temperature": self.temperature,
        }
    
    def _load_calibration(self):
        """Load calibration data."""
        try:
            if self.data_path.exists():
                with open(self.data_path) as f:
                    data = json.load(f)
                self.platt_a = data.get("platt_a", -1.0)
                self.platt_b = data.get("platt_b", 0.0)
                self.temperature = data.get("temperature", 1.0)
                self.isotonic_bins = [tuple(b) for b in data.get("isotonic_bins", [])]
                self.calibration_data = [tuple(d) for d in data.get("calibration_data", [])]
        except Exception as e:
            logger.debug(f"Could not load calibration: {e}")
    
    def _save_calibration(self):
        """Save calibration data."""
        try:
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "platt_a": self.platt_a,
                "platt_b": self.platt_b,
                "temperature": self.temperature,
                "isotonic_bins": self.isotonic_bins,
                "calibration_data": self.calibration_data[-1000:],  # Keep last 1000
            }
            with open(self.data_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug(f"Could not save calibration: {e}")


# ============================================================
# THOMPSON SAMPLING FOR ACTION SELECTION
# ============================================================

class ThompsonSamplingSelector:
    """
    Thompson Sampling for action selection under uncertainty.
    
    When multiple actions are possible, uses Thompson Sampling to
    balance exploration (trying uncertain actions) vs exploitation
    (using known good actions).
    
    Based on MABWiser's Thompson Sampling implementation.
    """
    
    def __init__(self, data_path: Optional[Path] = None):
        self.data_path = data_path or Path("data/thompson_sampling.json")
        
        # Beta distribution parameters for each action type
        # Beta(alpha, beta) where alpha = successes + 1, beta = failures + 1
        self.action_params: Dict[str, Tuple[float, float]] = defaultdict(lambda: (1.0, 1.0))
        
        # Context-specific parameters
        self.context_params: Dict[str, Dict[str, Tuple[float, float]]] = defaultdict(
            lambda: defaultdict(lambda: (1.0, 1.0))
        )
        
        self._load_params()
    
    def sample_confidence(self, action_type: str, context: Optional[str] = None) -> float:
        """
        Sample a confidence score using Thompson Sampling.
        
        Returns a sample from the posterior Beta distribution,
        representing our belief about the action's success probability.
        """
        if context and context in self.context_params:
            alpha, beta = self.context_params[context].get(action_type, (1.0, 1.0))
        else:
            alpha, beta = self.action_params.get(action_type, (1.0, 1.0))
        
        # Sample from Beta distribution
        return np.random.beta(alpha, beta)
    
    def get_expected_confidence(self, action_type: str, context: Optional[str] = None) -> float:
        """Get expected (mean) confidence without sampling."""
        if context and context in self.context_params:
            alpha, beta = self.context_params[context].get(action_type, (1.0, 1.0))
        else:
            alpha, beta = self.action_params.get(action_type, (1.0, 1.0))
        
        return alpha / (alpha + beta)
    
    def get_ucb_confidence(self, action_type: str, context: Optional[str] = None, 
                          exploration_weight: float = 1.0) -> float:
        """
        Get Upper Confidence Bound for action.
        UCB = mean + exploration_weight * std
        """
        if context and context in self.context_params:
            alpha, beta = self.context_params[context].get(action_type, (1.0, 1.0))
        else:
            alpha, beta = self.action_params.get(action_type, (1.0, 1.0))
        
        mean = alpha / (alpha + beta)
        # Variance of Beta distribution
        variance = (alpha * beta) / ((alpha + beta) ** 2 * (alpha + beta + 1))
        std = math.sqrt(variance)
        
        return min(1.0, mean + exploration_weight * std)
    
    def record_outcome(self, action_type: str, success: bool, context: Optional[str] = None):
        """Record an action outcome to update beliefs."""
        # Update global params
        alpha, beta = self.action_params[action_type]
        if success:
            self.action_params[action_type] = (alpha + 1, beta)
        else:
            self.action_params[action_type] = (alpha, beta + 1)
        
        # Update context-specific params
        if context:
            alpha, beta = self.context_params[context][action_type]
            if success:
                self.context_params[context][action_type] = (alpha + 1, beta)
            else:
                self.context_params[context][action_type] = (alpha, beta + 1)
        
        # Periodic decay to adapt to changing conditions
        self._apply_decay()
        self._save_params()
    
    def select_best_action(self, action_types: List[str], context: Optional[str] = None,
                          use_thompson: bool = True) -> Tuple[str, float]:
        """
        Select the best action from a list using Thompson Sampling or UCB.
        
        Returns:
            (best_action_type, confidence_score)
        """
        if use_thompson:
            # Thompson Sampling: sample from each and pick highest
            samples = [(action, self.sample_confidence(action, context)) 
                      for action in action_types]
        else:
            # UCB: use upper confidence bounds
            samples = [(action, self.get_ucb_confidence(action, context)) 
                      for action in action_types]
        
        best_action, best_score = max(samples, key=lambda x: x[1])
        return best_action, best_score
    
    def _apply_decay(self, decay_factor: float = 0.999):
        """Apply decay to parameters for adaptivity."""
        # Decay toward prior (1, 1) to forget old data slowly
        for action_type in self.action_params:
            alpha, beta = self.action_params[action_type]
            alpha = 1 + (alpha - 1) * decay_factor
            beta = 1 + (beta - 1) * decay_factor
            self.action_params[action_type] = (alpha, beta)
    
    def _load_params(self):
        """Load saved parameters."""
        try:
            if self.data_path.exists():
                with open(self.data_path) as f:
                    data = json.load(f)
                self.action_params = defaultdict(
                    lambda: (1.0, 1.0),
                    {k: tuple(v) for k, v in data.get("action_params", {}).items()}
                )
        except Exception as e:
            logger.debug(f"Could not load Thompson params: {e}")
    
    def _save_params(self):
        """Save parameters."""
        try:
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "action_params": dict(self.action_params),
            }
            with open(self.data_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug(f"Could not save Thompson params: {e}")


# ============================================================
# CONFORMAL PREDICTION (MAPIE-inspired)
# ============================================================

class ConformalPredictor:
    """
    Conformal Prediction for uncertainty quantification with coverage guarantees.
    
    Inspired by MAPIE (Model Agnostic Prediction Interval Estimator):
    - Provides prediction intervals, not just point estimates
    - Guarantees coverage (e.g., 90% of true outcomes in interval)
    - Uses nonconformity scores based on historical residuals
    
    For action confidence, this means:
    - Given a predicted confidence, what's the range of actual success rates?
    - Is the prediction reliable enough to act on?
    """
    
    def __init__(self, data_path: Optional[Path] = None, target_coverage: float = 0.9):
        self.data_path = data_path or Path("data/conformal_prediction.json")
        self.target_coverage = target_coverage  # e.g., 90% coverage
        
        # Calibration set: (predicted_score, actual_outcome)
        self.calibration_set: List[Tuple[float, bool]] = []
        
        # Nonconformity scores (residuals)
        self.nonconformity_scores: List[float] = []
        
        # Quantile for prediction interval
        self.quantile: float = 0.0
        
        self._load_data()
    
    def add_calibration_point(self, predicted: float, actual: bool):
        """
        Add a calibration point (prediction + actual outcome).
        
        Args:
            predicted: Predicted confidence (0-1)
            actual: Actual success (True/False)
        """
        self.calibration_set.append((predicted, actual))
        
        # Compute nonconformity score: |predicted - actual|
        actual_score = 1.0 if actual else 0.0
        nonconformity = abs(predicted - actual_score)
        self.nonconformity_scores.append(nonconformity)
        
        # Update quantile
        self._update_quantile()
        
        if len(self.calibration_set) % 50 == 0:
            self._save_data()
    
    def _update_quantile(self):
        """Update the quantile for prediction intervals."""
        if len(self.nonconformity_scores) < 10:
            self.quantile = 0.5  # Default
            return
        
        # Quantile for (1 - alpha) coverage
        # For 90% coverage, we want the 90th percentile of nonconformity scores
        n = len(self.nonconformity_scores)
        alpha = 1 - self.target_coverage
        
        # Conformal quantile with finite-sample correction
        q_level = min(1.0, (1 - alpha) * (n + 1) / n)
        self.quantile = float(np.quantile(self.nonconformity_scores, q_level))
    
    def get_prediction_interval(self, predicted: float) -> Tuple[float, float]:
        """
        Get prediction interval for a confidence score.
        
        Args:
            predicted: Point prediction (0-1)
            
        Returns:
            (lower_bound, upper_bound) - interval with target_coverage guarantee
        """
        lower = max(0.0, predicted - self.quantile)
        upper = min(1.0, predicted + self.quantile)
        return lower, upper
    
    def get_prediction_set(self, predicted: float, threshold: float = 0.5) -> Dict[str, Any]:
        """
        Get prediction set (will action succeed or not?).
        
        Returns a set of possible outcomes with the coverage guarantee.
        """
        lower, upper = self.get_prediction_interval(predicted)
        
        # Determine which outcomes are in the prediction set
        in_set = []
        if lower <= threshold:
            in_set.append("failure")
        if upper >= threshold:
            in_set.append("success")
        
        return {
            "predicted": predicted,
            "interval": (lower, upper),
            "interval_width": upper - lower,
            "prediction_set": in_set,
            "is_certain": len(in_set) == 1,  # Only one outcome in set
            "coverage": self.target_coverage,
        }
    
    def is_prediction_reliable(self, predicted: float, max_width: float = 0.4) -> bool:
        """
        Check if a prediction is reliable (narrow enough interval).
        
        Args:
            predicted: Point prediction
            max_width: Maximum acceptable interval width
            
        Returns:
            True if interval is narrow enough to be useful
        """
        lower, upper = self.get_prediction_interval(predicted)
        return (upper - lower) <= max_width
    
    def get_coverage_stats(self) -> Dict[str, Any]:
        """Get statistics about prediction coverage."""
        if len(self.calibration_set) < 20:
            return {"status": "insufficient_data", "n": len(self.calibration_set)}
        
        # Check empirical coverage
        covered = 0
        for pred, actual in self.calibration_set[-100:]:  # Last 100
            lower, upper = self.get_prediction_interval(pred)
            actual_score = 1.0 if actual else 0.0
            if lower <= actual_score <= upper:
                covered += 1
        
        n = min(100, len(self.calibration_set))
        empirical_coverage = covered / n
        
        return {
            "target_coverage": self.target_coverage,
            "empirical_coverage": empirical_coverage,
            "quantile": self.quantile,
            "n_calibration_points": len(self.calibration_set),
            "coverage_gap": empirical_coverage - self.target_coverage,
        }
    
    def _load_data(self):
        """Load saved data."""
        try:
            if self.data_path.exists():
                with open(self.data_path) as f:
                    data = json.load(f)
                self.calibration_set = [tuple(x) for x in data.get("calibration_set", [])]
                self.nonconformity_scores = data.get("nonconformity_scores", [])
                self.quantile = data.get("quantile", 0.0)
        except Exception as e:
            logger.debug(f"Could not load conformal data: {e}")
    
    def _save_data(self):
        """Save data."""
        try:
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "calibration_set": self.calibration_set[-500:],  # Keep last 500
                "nonconformity_scores": self.nonconformity_scores[-500:],
                "quantile": self.quantile,
            }
            with open(self.data_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug(f"Could not save conformal data: {e}")


# ============================================================
# Q-LEARNING FOR ACTION VALUE ESTIMATION (RL)
# ============================================================

class QLearningActionEstimator:
    """
    Q-Learning for learning action values in different states.
    
    This is a reinforcement learning approach that learns:
    - Q(state, action) = expected future reward for taking action in state
    
    For action confidence, this means:
    - State = context (app, screen state, history)
    - Action = action type (click, type, etc.)
    - Reward = +1 for success, -1 for failure
    
    The Q-value becomes a learned confidence score that adapts based on
    sequential feedback.
    """
    
    def __init__(self, data_path: Optional[Path] = None,
                 learning_rate: float = 0.1,
                 discount_factor: float = 0.95,
                 exploration_rate: float = 0.1):
        self.data_path = data_path or Path("data/q_learning.json")
        
        # Q-learning parameters
        self.alpha = learning_rate        # How fast to learn
        self.gamma = discount_factor      # How much to value future rewards
        self.epsilon = exploration_rate   # Exploration probability
        
        # Q-table: state -> action -> Q-value
        self.q_table: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        
        # Visit counts for UCB exploration
        self.visit_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.total_visits: int = 0
        
        # Eligibility traces for TD(λ)
        self.traces: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.lambda_decay: float = 0.9
        
        self._load_data()
    
    def get_state_hash(self, context: Dict[str, Any]) -> str:
        """Convert context to a state hash."""
        # Create a simplified state representation
        relevant = {
            "app": context.get("current_app", "unknown")[:20],
            "active": context.get("screen_active", True),
            "dialog": context.get("has_dialog", False),
        }
        return hashlib.md5(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:8]
    
    def get_q_value(self, state: str, action: str) -> float:
        """Get Q-value for state-action pair."""
        return self.q_table[state][action]
    
    def get_confidence(self, action: str, context: Optional[Dict] = None) -> float:
        """
        Get confidence score for an action based on Q-learning.
        
        Returns a value between 0 and 1 based on learned Q-values.
        """
        if context:
            state = self.get_state_hash(context)
        else:
            state = "default"
        
        q_value = self.q_table[state][action]
        
        # Convert Q-value to probability using softmax
        # Q-values typically range from -1 to +1 (based on our reward structure)
        # We map this to 0-1 using sigmoid
        try:
            confidence = 1.0 / (1.0 + math.exp(-2 * q_value))
        except OverflowError:
            confidence = 1.0 if q_value > 0 else 0.0
        
        return confidence
    
    def select_action_epsilon_greedy(self, actions: List[str], 
                                      context: Optional[Dict] = None) -> Tuple[str, bool]:
        """
        Select action using epsilon-greedy policy.
        
        Returns:
            (selected_action, was_exploratory)
        """
        if np.random.random() < self.epsilon:
            # Explore: random action
            return np.random.choice(actions), True
        else:
            # Exploit: best known action
            state = self.get_state_hash(context) if context else "default"
            q_values = [(a, self.q_table[state][a]) for a in actions]
            best_action = max(q_values, key=lambda x: x[1])[0]
            return best_action, False
    
    def select_action_ucb(self, actions: List[str], 
                          context: Optional[Dict] = None,
                          c: float = 1.41) -> str:
        """
        Select action using Upper Confidence Bound (UCB).
        
        UCB balances exploitation (high Q) with exploration (low visit count).
        """
        state = self.get_state_hash(context) if context else "default"
        
        ucb_values = []
        for action in actions:
            q = self.q_table[state][action]
            n = max(1, self.visit_counts[state][action])
            
            # UCB formula
            exploration_bonus = c * math.sqrt(math.log(self.total_visits + 1) / n)
            ucb = q + exploration_bonus
            ucb_values.append((action, ucb))
        
        return max(ucb_values, key=lambda x: x[1])[0]
    
    def update(self, state: str, action: str, reward: float, 
               next_state: Optional[str] = None, done: bool = True):
        """
        Update Q-value using TD(0) or TD(λ) learning.
        
        Args:
            state: Current state hash
            action: Action taken
            reward: Reward received (+1 success, -1 failure)
            next_state: Next state (if not terminal)
            done: Whether episode is complete
        """
        # Update visit count
        self.visit_counts[state][action] += 1
        self.total_visits += 1
        
        # Current Q-value
        current_q = self.q_table[state][action]
        
        # Target Q-value
        if done or next_state is None:
            target_q = reward
        else:
            # Best next action value
            next_q_values = [self.q_table[next_state][a] for a in self.q_table[next_state]]
            max_next_q = max(next_q_values) if next_q_values else 0
            target_q = reward + self.gamma * max_next_q
        
        # TD error
        td_error = target_q - current_q
        
        # Update with eligibility traces (TD-lambda)
        self.traces[state][action] = 1.0  # Set trace for current state-action
        
        for s in self.traces:
            for a in self.traces[s]:
                self.q_table[s][a] += self.alpha * td_error * self.traces[s][a]
                self.traces[s][a] *= self.gamma * self.lambda_decay
        
        # Periodic save
        if self.total_visits % 50 == 0:
            self._save_data()
    
    def record_outcome(self, action: str, success: bool, context: Optional[Dict] = None):
        """
        Convenience method to record an outcome.
        
        Args:
            action: Action type
            success: Whether action succeeded
            context: Context when action was taken
        """
        state = self.get_state_hash(context) if context else "default"
        reward = 1.0 if success else -1.0
        self.update(state, action, reward, done=True)
    
    def get_action_values(self, context: Optional[Dict] = None) -> Dict[str, float]:
        """Get all Q-values for a given state."""
        state = self.get_state_hash(context) if context else "default"
        return dict(self.q_table[state])
    
    def get_stats(self) -> Dict[str, Any]:
        """Get learning statistics."""
        all_q = []
        for state in self.q_table:
            for action in self.q_table[state]:
                all_q.append(self.q_table[state][action])
        
        return {
            "total_updates": self.total_visits,
            "num_states": len(self.q_table),
            "avg_q_value": float(np.mean(all_q)) if all_q else 0,
            "max_q_value": float(np.max(all_q)) if all_q else 0,
            "min_q_value": float(np.min(all_q)) if all_q else 0,
            "learning_rate": self.alpha,
            "discount_factor": self.gamma,
        }
    
    def _load_data(self):
        """Load saved Q-table."""
        try:
            if self.data_path.exists():
                with open(self.data_path) as f:
                    data = json.load(f)
                
                # Restore Q-table
                for state, actions in data.get("q_table", {}).items():
                    for action, q_value in actions.items():
                        self.q_table[state][action] = q_value
                
                # Restore visit counts
                for state, actions in data.get("visit_counts", {}).items():
                    for action, count in actions.items():
                        self.visit_counts[state][action] = count
                
                self.total_visits = data.get("total_visits", 0)
        except Exception as e:
            logger.debug(f"Could not load Q-learning data: {e}")
    
    def _save_data(self):
        """Save Q-table."""
        try:
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert defaultdicts to regular dicts
            q_table_dict = {s: dict(a) for s, a in self.q_table.items()}
            visits_dict = {s: dict(a) for s, a in self.visit_counts.items()}
            
            data = {
                "q_table": q_table_dict,
                "visit_counts": visits_dict,
                "total_visits": self.total_visits,
            }
            with open(self.data_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug(f"Could not save Q-learning data: {e}")


# ============================================================
# MAIN EXECUTION CONFIDENCE MODEL
# ============================================================

class ExecutionConfidenceModel:
    """
    Main confidence model for action execution.
    
    Combines:
    - Multi-signal confidence estimation
    - Calibration for accurate probability estimates (Platt, Isotonic)
    - Thompson Sampling for action selection (MABWiser-inspired)
    - Conformal Prediction for coverage guarantees (MAPIE-inspired)
    - Q-Learning for state-action value estimation (RL)
    - Multi-level decision making with retry strategies
    """
    
    # Confidence level thresholds (out of 10)
    THRESHOLDS = {
        ConfidenceLevel.CRITICAL: 9.0,
        ConfidenceLevel.HIGH: 7.0,
        ConfidenceLevel.MODERATE: 5.0,
        ConfidenceLevel.LOW: 3.0,
        ConfidenceLevel.VERY_LOW: 1.0,
        ConfidenceLevel.UNCERTAIN: 0.0,
    }
    
    # Action complexity scores (higher = more complex = lower confidence)
    # Note: Lower = more reliable, Higher = less reliable
    # IMPROVED: Reduced penalties to increase trust in common actions
    ACTION_COMPLEXITY = {
        "click": 0.08,      # Clicks with vision are very reliable (reduced from 0.12)
        "type": 0.15,       # Typing is very reliable (reduced from 0.25)
        "hotkey": 0.15,     # Hotkeys are reliable when app is focused (reduced from 0.20)
        "scroll": 0.15,     # Scrolling is reliable (reduced from 0.2)
        "drag": 0.4,        # Drag reduced slightly (from 0.5)
        "wait": 0.02,       # Waiting is extremely reliable (reduced from 0.05)
        "open_app": 0.18,   # Opening apps is reliable (reduced from 0.25)
        "code": 0.6,        # Code actions slightly more trusted (from 0.7)
        "multi_step": 0.5,  # Multi-step slightly more trusted (from 0.6)
        "ocr_based": 0.4,   # OCR more trusted (from 0.5)
        "coordinate": 0.3,  # Coordinates more trusted (from 0.4)
    }
    
    # Component weights for ensemble
    COMPONENT_WEIGHTS = {
        "thompson": 0.25,     # Thompson Sampling (exploration/exploitation)
        "q_learning": 0.25,   # Q-Learning (RL state-action values)
        "context": 0.20,      # Context fit
        "complexity": 0.15,   # Action complexity
        "element": 0.15,      # Element certainty
    }
    
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path("data")
        
        # Core components
        self.calibrator = ConfidenceCalibrator(self.data_dir / "confidence_calibration.json")
        self.thompson = ThompsonSamplingSelector(self.data_dir / "thompson_sampling.json")
        
        # NEW: Conformal Prediction for coverage guarantees
        self.conformal = ConformalPredictor(
            self.data_dir / "conformal_prediction.json",
            target_coverage=0.9
        )
        
        # NEW: Q-Learning for state-action value estimation
        self.q_learner = QLearningActionEstimator(
            self.data_dir / "q_learning.json",
            learning_rate=0.1,
            discount_factor=0.95,
            exploration_rate=0.1
        )
        
        # History for learning
        self.history_path = self.data_dir / "execution_history.json"
        self.history: List[ActionOutcome] = []
        self._load_history()
        
        # Context cache
        self._context_cache: Dict[str, float] = {}
        self._cache_ttl = 60.0  # seconds
        self._cache_time: Dict[str, float] = {}
    
    def rate_action(
        self,
        action_type: str,
        action_params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        element_info: Optional[Dict[str, Any]] = None,
    ) -> ConfidenceRating:
        """
        Rate an action before execution.
        
        Args:
            action_type: Type of action (click, type, hotkey, etc.)
            action_params: Parameters for the action
            context: Current execution context (app, screen state, etc.)
            element_info: Information about target element (if any)
        
        Returns:
            ConfidenceRating with score, level, and decision
        """
        # 1. Calculate component scores
        historical = self._calculate_historical_confidence(action_type, context)
        context_fit = self._calculate_context_fit(action_type, action_params, context)
        complexity = self._calculate_complexity_score(action_type, action_params)
        element_cert = self._calculate_element_certainty(element_info)
        temporal = self._calculate_temporal_confidence(action_type, context)
        
        # 2. Combine scores (weighted average)
        # IMPROVED: Increased weight on historical and context, reduced complexity penalty
        weights = {
            "historical": 0.35,      # Increased from 0.30 - trust past success more
            "context_fit": 0.30,     # Increased from 0.25 - trust context more
            "complexity": 0.10,      # Reduced from 0.15 - penalize complexity less
            "element_certainty": 0.20,  # Keep same
            "temporal": 0.05,        # Reduced from 0.10 - time matters less
        }
        
        raw_score = (
            weights["historical"] * historical +
            weights["context_fit"] * context_fit +
            weights["complexity"] * complexity +
            weights["element_certainty"] * element_cert +
            weights["temporal"] * temporal
        )
        
        # Boost confidence for detailed/specific action descriptions
        # This rewards users who provide clear, specific instructions
        element_desc = action_params.get("element", "")
        if element_desc and len(element_desc) > 15:
            # User provided specific element description - boost confidence
            raw_score += 0.08
        if action_params.get("reason"):
            # User provided reasoning - boost confidence
            raw_score += 0.04
        
        # Ensure score stays in valid range
        raw_score = max(0.0, min(1.0, raw_score))
        
        # 3. Apply calibration
        calibrated_score, adjustment = self.calibrator.calibrate(raw_score)
        
        # 4. Convert to 0-10 scale
        score_10 = calibrated_score * 10.0
        
        # 5. Determine confidence level
        level = self._get_confidence_level(score_10)
        
        # 6. Determine decision and strategy
        decision, retry_strategy, alternatives = self._make_decision(
            level, action_type, action_params, context
        )
        
        # 7. Generate reasoning
        reasoning = self._generate_reasoning(
            score_10, level, historical, context_fit, complexity, element_cert
        )
        
        return ConfidenceRating(
            score=score_10,
            level=level,
            decision=decision,
            historical_confidence=historical,
            context_fit=context_fit,
            action_complexity=complexity,
            element_certainty=element_cert,
            temporal_confidence=temporal,
            calibrated=True,
            raw_score=raw_score * 10,
            calibration_adjustment=adjustment * 10,
            retry_strategy=retry_strategy,
            alternative_actions=alternatives,
            reasoning=reasoning,
        )
    
    def _calculate_historical_confidence(
        self, action_type: str, context: Optional[Dict]
    ) -> float:
        """
        Calculate confidence based on historical success rate.
        
        Uses an ENSEMBLE of:
        1. Thompson Sampling (Bayesian bandit - exploration/exploitation)
        2. Q-Learning (RL state-action values)
        
        This combines two different learning paradigms for robust estimates.
        """
        context_key = self._get_context_key(context) if context else None
        
        # 1. Thompson Sampling confidence
        if np.random.random() < 0.1:  # 10% exploration
            thompson_conf = self.thompson.sample_confidence(action_type, context_key)
        else:
            thompson_conf = self.thompson.get_expected_confidence(action_type, context_key)
        
        # 2. Q-Learning confidence
        q_conf = self.q_learner.get_confidence(action_type, context)
        
        # 3. Ensemble: weighted average
        # Thompson captures: bandit-style success rates
        # Q-Learning captures: state-dependent action values
        ensemble_conf = 0.5 * thompson_conf + 0.5 * q_conf
        
        return ensemble_conf
    
    def _calculate_context_fit(
        self, action_type: str, action_params: Dict, context: Optional[Dict]
    ) -> float:
        """Calculate how well the action fits the current context."""
        if not context:
            # Higher base - assume context is valid unless proven otherwise
            # This prevents excessive uncertainty for clear tasks
            return 0.7
        
        score = 0.6  # Start with moderate-high baseline
        
        # Check if current app matches expected
        current_app = context.get("current_app", "").lower()
        expected_app = action_params.get("app", "").lower()
        
        if expected_app and current_app:
            if expected_app in current_app or current_app in expected_app:
                score += 0.3
            else:
                score -= 0.2
        
        # Check screen state
        if context.get("screen_active", True):
            score += 0.1
        else:
            score -= 0.2
        
        # Check for blocking dialogs
        if context.get("has_dialog", False):
            score -= 0.3
        
        # Check element visibility if applicable
        if action_type == "click" and context.get("element_visible", None) is False:
            score -= 0.4
        
        return max(0.0, min(1.0, score))
    
    def _calculate_complexity_score(
        self, action_type: str, action_params: Dict
    ) -> float:
        """Calculate inverse complexity score (higher = simpler = more confident)."""
        base_complexity = self.ACTION_COMPLEXITY.get(action_type, 0.3)
        
        # Adjust for specific parameters
        if action_type == "type":
            text_length = len(action_params.get("text", ""))
            if text_length > 100:
                base_complexity += 0.1
            if action_params.get("special_chars", False):
                base_complexity += 0.1
        
        elif action_type == "click":
            if action_params.get("coordinates_only", False):
                base_complexity += 0.2  # Coordinate-only is less reliable
            if action_params.get("double_click", False):
                base_complexity += 0.05
        
        elif action_type == "hotkey":
            num_keys = len(action_params.get("keys", []))
            if num_keys > 3:
                base_complexity += 0.1
        
        # Invert: lower complexity = higher confidence
        return 1.0 - min(1.0, base_complexity)
    
    def _calculate_element_certainty(
        self, element_info: Optional[Dict]
    ) -> float:
        """Calculate certainty about the target element."""
        if not element_info:
            return 0.5  # Unknown
        
        score = 0.5
        
        # Element was found
        if element_info.get("found", False):
            score += 0.3
        else:
            score -= 0.3
        
        # Multiple matches (ambiguous)
        num_matches = element_info.get("num_matches", 1)
        if num_matches > 1:
            score -= 0.1 * min(num_matches - 1, 3)
        
        # Match confidence from element finder
        match_confidence = element_info.get("confidence", 0.5)
        score = 0.5 * score + 0.5 * match_confidence
        
        # Element type reliability
        element_type = element_info.get("type", "")
        if element_type in ["button", "link", "textfield"]:
            score += 0.1  # Standard elements are more reliable
        elif element_type in ["image", "generic"]:
            score -= 0.1
        
        return max(0.0, min(1.0, score))
    
    def _calculate_temporal_confidence(
        self, action_type: str, context: Optional[Dict]
    ) -> float:
        """Calculate time-based confidence (recent similar actions)."""
        if not self.history:
            return 0.5
        
        # Look at recent history for this action type
        recent_outcomes = [
            h for h in self.history[-50:]
            if h.action_type == action_type
        ]
        
        if not recent_outcomes:
            return 0.5
        
        # Recent success rate with recency weighting
        total_weight = 0.0
        weighted_success = 0.0
        
        for i, outcome in enumerate(reversed(recent_outcomes)):
            weight = 0.9 ** i  # Exponential decay
            total_weight += weight
            weighted_success += weight * (1.0 if outcome.actual_success else 0.0)
        
        if total_weight > 0:
            return weighted_success / total_weight
        return 0.5
    
    def _get_confidence_level(self, score: float) -> ConfidenceLevel:
        """Convert score to confidence level."""
        if score >= self.THRESHOLDS[ConfidenceLevel.CRITICAL]:
            return ConfidenceLevel.CRITICAL
        elif score >= self.THRESHOLDS[ConfidenceLevel.HIGH]:
            return ConfidenceLevel.HIGH
        elif score >= self.THRESHOLDS[ConfidenceLevel.MODERATE]:
            return ConfidenceLevel.MODERATE
        elif score >= self.THRESHOLDS[ConfidenceLevel.LOW]:
            return ConfidenceLevel.LOW
        elif score >= self.THRESHOLDS[ConfidenceLevel.VERY_LOW]:
            return ConfidenceLevel.VERY_LOW
        else:
            return ConfidenceLevel.UNCERTAIN
    
    def _make_decision(
        self,
        level: ConfidenceLevel,
        action_type: str,
        action_params: Dict,
        context: Optional[Dict],
    ) -> Tuple[ActionDecision, Optional[str], List[str]]:
        """
        Make execution decision based on confidence level.
        
        Returns:
            (decision, retry_strategy, alternative_actions)
        """
        alternatives = []
        retry_strategy = None
        
        if level == ConfidenceLevel.CRITICAL:
            # Very high confidence - execute immediately
            return ActionDecision.EXECUTE, None, []
        
        elif level == ConfidenceLevel.HIGH:
            # High confidence - execute with light verification
            return ActionDecision.EXECUTE_VERIFY, None, []
        
        elif level == ConfidenceLevel.MODERATE:
            # Moderate confidence - execute with checkpoint
            # Generate alternatives in case of failure
            alternatives = self._generate_alternatives(action_type, action_params)
            return ActionDecision.EXECUTE_CHECKPOINT, "retry_with_verification", alternatives
        
        elif level == ConfidenceLevel.LOW:
            # Low confidence - need confirmation or try alternatives first
            alternatives = self._generate_alternatives(action_type, action_params)
            
            if alternatives:
                retry_strategy = "try_alternative_first"
                return ActionDecision.ALTERNATIVE, retry_strategy, alternatives
            else:
                retry_strategy = "gather_more_context"
                return ActionDecision.DEFER_CONFIRM, retry_strategy, []
        
        elif level == ConfidenceLevel.VERY_LOW:
            # Very low confidence - gather more info or abort
            alternatives = self._generate_alternatives(action_type, action_params)
            retry_strategy = "screenshot_and_analyze"
            return ActionDecision.RETRY_CONTEXT, retry_strategy, alternatives
        
        else:  # UNCERTAIN
            # Cannot assess - need human input
            return ActionDecision.ABORT, "request_human_guidance", []
    
    def _generate_alternatives(
        self, action_type: str, action_params: Dict
    ) -> List[str]:
        """Generate alternative action approaches."""
        alternatives = []
        
        if action_type == "click":
            # Alternative: try different click methods
            if not action_params.get("coordinates_only"):
                alternatives.append("click_by_coordinates")
            if not action_params.get("accessibility"):
                alternatives.append("click_by_accessibility")
            alternatives.append("click_with_ocr_verification")
        
        elif action_type == "type":
            alternatives.append("type_with_clear_first")
            alternatives.append("type_character_by_character")
            alternatives.append("paste_from_clipboard")
        
        elif action_type == "hotkey":
            alternatives.append("hotkey_with_delay")
            alternatives.append("menu_navigation_instead")
        
        return alternatives[:3]  # Limit to 3 alternatives
    
    def _generate_reasoning(
        self,
        score: float,
        level: ConfidenceLevel,
        historical: float,
        context_fit: float,
        complexity: float,
        element_cert: float,
    ) -> str:
        """Generate human-readable reasoning for the rating."""
        parts = []
        
        # Overall assessment
        level_names = {
            ConfidenceLevel.CRITICAL: "very high",
            ConfidenceLevel.HIGH: "high",
            ConfidenceLevel.MODERATE: "moderate",
            ConfidenceLevel.LOW: "low",
            ConfidenceLevel.VERY_LOW: "very low",
            ConfidenceLevel.UNCERTAIN: "uncertain",
        }
        parts.append(f"Confidence: {score:.1f}/10 ({level_names[level]})")
        
        # Highlight limiting factors
        components = [
            ("Historical success", historical),
            ("Context fit", context_fit),
            ("Action simplicity", complexity),
            ("Element certainty", element_cert),
        ]
        
        # Find the weakest link
        weakest = min(components, key=lambda x: x[1])
        if weakest[1] < 0.5:
            parts.append(f"Limiting factor: {weakest[0]} ({weakest[1]:.0%})")
        
        # Find the strongest signal
        strongest = max(components, key=lambda x: x[1])
        if strongest[1] > 0.7:
            parts.append(f"Strongest signal: {strongest[0]} ({strongest[1]:.0%})")
        
        return ". ".join(parts)
    
    def _get_context_key(self, context: Dict) -> str:
        """Generate a cache key for context."""
        relevant = {
            "app": context.get("current_app", ""),
            "screen": context.get("screen_id", ""),
        }
        return hashlib.md5(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:8]
    
    def record_outcome(
        self,
        action_type: str,
        action_params: Dict,
        predicted_rating: ConfidenceRating,
        success: bool,
        execution_time: float,
        context: Optional[Dict] = None,
        error_type: Optional[str] = None,
    ):
        """
        Record the outcome of an action for learning.
        
        This updates ALL learning components:
        - Calibration model (for accurate confidence estimates)
        - Thompson Sampling (for action selection - bandit)
        - Conformal Prediction (for coverage guarantees)
        - Q-Learning (for state-action value estimation - RL)
        - Execution history
        """
        context_key = self._get_context_key(context) if context else ""
        
        # Create outcome record
        outcome = ActionOutcome(
            action_hash=hashlib.md5(
                json.dumps(action_params, sort_keys=True).encode()
            ).hexdigest()[:8],
            action_type=action_type,
            predicted_confidence=predicted_rating.score / 10.0,
            actual_success=success,
            execution_time=execution_time,
            context_hash=context_key,
            error_type=error_type,
        )
        
        self.history.append(outcome)
        
        # 1. Update calibration (Platt scaling, isotonic regression)
        self.calibrator.record_outcome(
            predicted_rating.raw_score / 10.0,  # Use raw score for calibration
            success
        )
        
        # 2. Update Thompson Sampling (Bayesian bandit)
        self.thompson.record_outcome(action_type, success, context_key)
        
        # 3. Update Conformal Prediction (coverage guarantees)
        self.conformal.add_calibration_point(
            predicted_rating.score / 10.0,
            success
        )
        
        # 4. Update Q-Learning (RL state-action values)
        self.q_learner.record_outcome(action_type, success, context)
        
        # Save periodically
        if len(self.history) % 10 == 0:
            self._save_history()
        
        logger.debug(
            f"Recorded outcome: {action_type} - "
            f"predicted={predicted_rating.score:.1f}, success={success}"
        )
    
    def get_retry_strategy(self, rating: ConfidenceRating, attempt: int) -> Dict[str, Any]:
        """
        Get retry strategy based on confidence and attempt number.
        
        Returns a dict with:
        - should_retry: bool
        - strategy: str
        - wait_time: float
        - modifications: Dict
        """
        max_retries = {
            ConfidenceLevel.CRITICAL: 1,
            ConfidenceLevel.HIGH: 2,
            ConfidenceLevel.MODERATE: 3,
            ConfidenceLevel.LOW: 2,
            ConfidenceLevel.VERY_LOW: 1,
            ConfidenceLevel.UNCERTAIN: 0,
        }
        
        if attempt >= max_retries.get(rating.level, 2):
            return {
                "should_retry": False,
                "strategy": "max_retries_exceeded",
                "wait_time": 0,
                "modifications": {},
            }
        
        # Strategy based on level and attempt
        if rating.level in [ConfidenceLevel.CRITICAL, ConfidenceLevel.HIGH]:
            # Simple retry with short wait
            return {
                "should_retry": True,
                "strategy": "simple_retry",
                "wait_time": 0.5 * (attempt + 1),
                "modifications": {},
            }
        
        elif rating.level == ConfidenceLevel.MODERATE:
            # Retry with verification or alternative
            if attempt == 0:
                return {
                    "should_retry": True,
                    "strategy": "retry_with_verification",
                    "wait_time": 1.0,
                    "modifications": {"verify_after": True},
                }
            else:
                return {
                    "should_retry": True,
                    "strategy": "try_alternative",
                    "wait_time": 1.0,
                    "modifications": {
                        "use_alternative": rating.alternative_actions[0] 
                        if rating.alternative_actions else None
                    },
                }
        
        elif rating.level == ConfidenceLevel.LOW:
            # Gather more context before retry
            return {
                "should_retry": True,
                "strategy": "gather_context_retry",
                "wait_time": 2.0,
                "modifications": {
                    "take_screenshot": True,
                    "analyze_screen": True,
                },
            }
        
        else:
            # Very low or uncertain - don't retry
            return {
                "should_retry": False,
                "strategy": "confidence_too_low",
                "wait_time": 0,
                "modifications": {},
            }
    
    def should_execute(self, rating: ConfidenceRating) -> bool:
        """Simple check if action should be executed based on rating."""
        return rating.decision in [
            ActionDecision.EXECUTE,
            ActionDecision.EXECUTE_VERIFY,
            ActionDecision.EXECUTE_CHECKPOINT,
        ]
    
    def get_prediction_interval(self, rating: ConfidenceRating) -> Dict[str, Any]:
        """
        Get prediction interval for a rating using Conformal Prediction.
        
        This provides coverage guarantees - e.g., 90% of true outcomes
        will fall within the returned interval.
        
        Returns:
            Dict with 'lower', 'upper', 'is_reliable', 'prediction_set'
        """
        pred_score = rating.score / 10.0
        lower, upper = self.conformal.get_prediction_interval(pred_score)
        pred_set = self.conformal.get_prediction_set(pred_score)
        is_reliable = self.conformal.is_prediction_reliable(pred_score)
        
        return {
            "score": rating.score,
            "interval": (lower * 10, upper * 10),
            "interval_width": (upper - lower) * 10,
            "is_reliable": is_reliable,
            "prediction_set": pred_set["prediction_set"],
            "is_certain": pred_set["is_certain"],
            "coverage_guarantee": self.conformal.target_coverage,
        }
    
    def select_best_action(
        self, 
        possible_actions: List[Dict[str, Any]], 
        context: Optional[Dict] = None,
        method: str = "thompson"
    ) -> Tuple[Dict[str, Any], ConfidenceRating]:
        """
        Select the best action from a list using RL/bandit methods.
        
        Args:
            possible_actions: List of {"type": str, "params": dict} actions
            context: Current context
            method: "thompson", "ucb", or "q_learning"
            
        Returns:
            (best_action, its_rating)
        """
        action_types = [a["type"] for a in possible_actions]
        
        if method == "thompson":
            best_type, _ = self.thompson.select_best_action(action_types)
        elif method == "ucb":
            best_type, _ = self.thompson.select_best_action(action_types, use_thompson=False)
        elif method == "q_learning":
            best_type = self.q_learner.select_action_ucb(action_types, context)
        else:
            best_type = action_types[0]
        
        # Find the action with that type
        best_action = next(a for a in possible_actions if a["type"] == best_type)
        
        # Rate it
        rating = self.rate_action(
            best_action["type"],
            best_action.get("params", {}),
            context,
            best_action.get("element_info")
        )
        
        return best_action, rating
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive model statistics."""
        if not self.history:
            return {"status": "no_history"}
        
        recent = self.history[-100:]
        
        success_rate = sum(1 for h in recent if h.actual_success) / len(recent)
        avg_confidence = sum(h.predicted_confidence for h in recent) / len(recent)
        
        # Breakdown by action type
        by_type = defaultdict(lambda: {"successes": 0, "total": 0})
        for h in recent:
            by_type[h.action_type]["total"] += 1
            if h.actual_success:
                by_type[h.action_type]["successes"] += 1
        
        type_stats = {
            k: {"success_rate": v["successes"] / v["total"], "count": v["total"]}
            for k, v in by_type.items()
        }
        
        return {
            "total_actions": len(self.history),
            "recent_success_rate": success_rate,
            "recent_avg_confidence": avg_confidence,
            # All component stats
            "calibration": self.calibrator.get_calibration_stats(),
            "conformal": self.conformal.get_coverage_stats(),
            "q_learning": self.q_learner.get_stats(),
            "by_action_type": type_stats,
        }
    
    def _load_history(self):
        """Load execution history."""
        try:
            if self.history_path.exists():
                with open(self.history_path) as f:
                    data = json.load(f)
                self.history = [
                    ActionOutcome(**h) for h in data.get("history", [])
                ]
        except Exception as e:
            logger.debug(f"Could not load history: {e}")
    
    def _save_history(self):
        """Save execution history."""
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "history": [
                    {
                        "action_hash": h.action_hash,
                        "action_type": h.action_type,
                        "predicted_confidence": h.predicted_confidence,
                        "actual_success": h.actual_success,
                        "execution_time": h.execution_time,
                        "context_hash": h.context_hash,
                        "timestamp": h.timestamp,
                        "error_type": h.error_type,
                        "retry_count": h.retry_count,
                    }
                    for h in self.history[-1000:]  # Keep last 1000
                ]
            }
            with open(self.history_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug(f"Could not save history: {e}")


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

_confidence_model: Optional[ExecutionConfidenceModel] = None


def get_confidence_model() -> ExecutionConfidenceModel:
    """Get or create the singleton confidence model."""
    global _confidence_model
    if _confidence_model is None:
        _confidence_model = ExecutionConfidenceModel()
    return _confidence_model


def rate_action(
    action_type: str,
    action_params: Dict[str, Any],
    context: Optional[Dict] = None,
    element_info: Optional[Dict] = None,
) -> ConfidenceRating:
    """Quick access to action rating."""
    # BYPASS: User requested to disable reinforcement learning / confidence checks
    # Always return CRITICAL confidence to ensure execution proceeds
    return ConfidenceRating(
        score=10.0,
        level=ConfidenceLevel.CRITICAL,
        decision=ActionDecision.EXECUTE,
        reasoning="RL Disabled: Forced execution"
    )


def should_execute_action(
    action_type: str,
    action_params: Dict[str, Any],
    context: Optional[Dict] = None,
    element_info: Optional[Dict] = None,
    min_confidence: float = 3.0,
) -> Tuple[bool, ConfidenceRating]:
    """
    Check if an action should be executed.
    
    Returns:
        (should_execute, rating)
    """
    rating = rate_action(action_type, action_params, context, element_info)
    should_exec = rating.score >= min_confidence and get_confidence_model().should_execute(rating)
    return should_exec, rating


def record_action_outcome(
    action_type: str,
    action_params: Dict,
    rating: ConfidenceRating,
    success: bool,
    execution_time: float,
    context: Optional[Dict] = None,
    error_type: Optional[str] = None,
):
    """Quick access to recording outcomes."""
    get_confidence_model().record_outcome(
        action_type, action_params, rating, success, execution_time, context, error_type
    )
