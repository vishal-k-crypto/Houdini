"""
Probability Model for Task Intent & Execution Uncertainty

This model adds flexibility to the executor by handling:
1. Incomplete task specifications (80-90% info provided)
2. Tasks on a spectrum between macro and micro level
3. Predicting user intent when task is ambiguous

Uses a hybrid approach combining:
- Bayesian Networks (pgmpy) for probabilistic reasoning
- Fuzzy Logic (scikit-fuzzy) for handling the macro-micro spectrum  
- Custom uncertainty quantification for intent prediction

The model enables the executor to:
- Estimate how complete a task specification is
- Predict missing information
- Adjust execution strategy based on uncertainty
- Learn from task history and feedback
"""

import re
import json
import math
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import numpy as np

# Conditional imports - use lightweight fallbacks if heavy deps not available
try:
    import skfuzzy as fuzz
    from skfuzzy import control as ctrl
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False

try:
    # Use DiscreteBayesianNetwork (BayesianNetwork is deprecated in pgmpy 1.0+)
    try:
        from pgmpy.models import DiscreteBayesianNetwork
        BayesianNetworkClass = DiscreteBayesianNetwork
    except ImportError:
        from pgmpy.models import BayesianNetwork
        BayesianNetworkClass = BayesianNetwork
    from pgmpy.factors.discrete import TabularCPD
    from pgmpy.inference import VariableElimination
    PGMPY_AVAILABLE = True
except ImportError:
    PGMPY_AVAILABLE = False
    BayesianNetworkClass = None

from .logging import logger


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class TaskCompleteness:
    """Analysis of how complete a task specification is."""
    overall_score: float  # 0.0 to 1.0
    has_target: bool      # Does task specify what to target?
    has_action: bool      # Does task specify what action to take?
    has_location: bool    # Does task specify where (app/context)?
    has_criteria: bool    # Does task specify success criteria?
    missing_info: List[str] = field(default_factory=list)
    predicted_info: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0  # Confidence in predictions


@dataclass
class MacroMicroPosition:
    """Position of a task on the macro-micro spectrum."""
    position: float       # 0.0 = full macro, 1.0 = full micro
    macro_confidence: float
    micro_confidence: float
    execution_strategy: str  # "macro_plan", "micro_direct", "hybrid"
    decomposition_needed: bool


@dataclass  
class IntentPrediction:
    """Prediction of user's true intent."""
    primary_intent: str
    confidence: float
    alternative_intents: List[Tuple[str, float]]  # (intent, probability)
    context_clues: List[str]
    ambiguity_score: float  # 0.0 = clear, 1.0 = highly ambiguous


@dataclass
class ExecutionFlexibility:
    """Combined flexibility model for execution."""
    task_completeness: TaskCompleteness
    macro_micro: MacroMicroPosition
    intent: IntentPrediction
    
    # Derived fields
    overall_uncertainty: float = 0.0
    recommended_approach: str = "standard"
    fallback_strategies: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        # Calculate overall uncertainty
        self.overall_uncertainty = self._calculate_uncertainty()
        self.recommended_approach = self._determine_approach()
        self.fallback_strategies = self._generate_fallbacks()
    
    def _calculate_uncertainty(self) -> float:
        """Combined uncertainty metric."""
        completeness_uncertainty = 1.0 - self.task_completeness.overall_score
        intent_uncertainty = self.intent.ambiguity_score
        
        # Weighted combination
        return (0.4 * completeness_uncertainty + 
                0.4 * intent_uncertainty + 
                0.2 * (1.0 - self.task_completeness.confidence))
    
    def _determine_approach(self) -> str:
        """Determine best execution approach."""
        if self.overall_uncertainty > 0.5:
            return "conservative_with_verification"
        elif self.macro_micro.position < 0.3:
            return "macro_planning"
        elif self.macro_micro.position > 0.7:
            return "direct_micro_execution"
        else:
            return "hybrid_adaptive"
    
    def _generate_fallbacks(self) -> List[str]:
        """Generate fallback strategies based on uncertainty."""
        fallbacks = []
        
        if self.task_completeness.overall_score < 0.8:
            fallbacks.append("infer_from_context")
        
        if self.intent.ambiguity_score > 0.3:
            fallbacks.append("multi_intent_exploration")
        
        if self.macro_micro.decomposition_needed:
            fallbacks.append("step_decomposition")
        
        fallbacks.append("supervisor_guidance")  # Always available
        return fallbacks


# ============================================================
# FUZZY LOGIC SYSTEM (Macro-Micro Spectrum)
# ============================================================

class FuzzyMacroMicroAnalyzer:
    """
    Uses fuzzy logic to determine where a task falls on the
    macro-micro spectrum.
    
    Inputs (fuzzy):
    - specificity: How specific is the task description?
    - action_granularity: How granular are the actions mentioned?
    - context_dependency: How much does it depend on current state?
    
    Output (fuzzy):
    - execution_level: macro / hybrid / micro
    """
    
    def __init__(self):
        self._initialized = False
        self._init_fuzzy_system()
    
    def _init_fuzzy_system(self):
        """Initialize fuzzy inference system."""
        if not FUZZY_AVAILABLE:
            logger.warning("scikit-fuzzy not available, using fallback logic")
            return
        
        try:
            # Input variables
            self.specificity = ctrl.Antecedent(np.arange(0, 1.01, 0.01), 'specificity')
            self.granularity = ctrl.Antecedent(np.arange(0, 1.01, 0.01), 'granularity')
            self.context_dep = ctrl.Antecedent(np.arange(0, 1.01, 0.01), 'context_dependency')
            
            # Output variable
            self.exec_level = ctrl.Consequent(np.arange(0, 1.01, 0.01), 'execution_level')
            
            # Membership functions for specificity
            self.specificity['vague'] = fuzz.trimf(self.specificity.universe, [0, 0, 0.4])
            self.specificity['moderate'] = fuzz.trimf(self.specificity.universe, [0.2, 0.5, 0.8])
            self.specificity['precise'] = fuzz.trimf(self.specificity.universe, [0.6, 1, 1])
            
            # Membership functions for granularity
            self.granularity['high_level'] = fuzz.trimf(self.granularity.universe, [0, 0, 0.4])
            self.granularity['medium'] = fuzz.trimf(self.granularity.universe, [0.2, 0.5, 0.8])
            self.granularity['detailed'] = fuzz.trimf(self.granularity.universe, [0.6, 1, 1])
            
            # Membership functions for context dependency
            self.context_dep['low'] = fuzz.trimf(self.context_dep.universe, [0, 0, 0.4])
            self.context_dep['medium'] = fuzz.trimf(self.context_dep.universe, [0.2, 0.5, 0.8])
            self.context_dep['high'] = fuzz.trimf(self.context_dep.universe, [0.6, 1, 1])
            
            # Membership functions for execution level
            self.exec_level['macro'] = fuzz.trimf(self.exec_level.universe, [0, 0, 0.4])
            self.exec_level['hybrid'] = fuzz.trimf(self.exec_level.universe, [0.2, 0.5, 0.8])
            self.exec_level['micro'] = fuzz.trimf(self.exec_level.universe, [0.6, 1, 1])
            
            # Fuzzy rules
            rules = [
                # Vague + high-level → macro
                ctrl.Rule(self.specificity['vague'] & self.granularity['high_level'], 
                         self.exec_level['macro']),
                # Precise + detailed → micro
                ctrl.Rule(self.specificity['precise'] & self.granularity['detailed'],
                         self.exec_level['micro']),
                # Moderate combinations → hybrid
                ctrl.Rule(self.specificity['moderate'], self.exec_level['hybrid']),
                ctrl.Rule(self.granularity['medium'], self.exec_level['hybrid']),
                # High context dependency → favor macro
                ctrl.Rule(self.context_dep['high'], self.exec_level['macro']),
                # Low context dependency + precise → micro
                ctrl.Rule(self.context_dep['low'] & self.specificity['precise'],
                         self.exec_level['micro']),
            ]
            
            # Create control system
            self.ctrl_system = ctrl.ControlSystem(rules)
            self.simulator = ctrl.ControlSystemSimulation(self.ctrl_system)
            self._initialized = True
            
        except Exception as e:
            logger.warning(f"Fuzzy system init failed: {e}")
            self._initialized = False
    
    def analyze(self, task: str, context: Optional[Dict] = None) -> MacroMicroPosition:
        """
        Analyze a task's position on the macro-micro spectrum.
        
        Args:
            task: The task description
            context: Optional context (current app, history, etc.)
        
        Returns:
            MacroMicroPosition with spectrum position and strategy
        """
        # Extract features from task
        specificity = self._measure_specificity(task)
        granularity = self._measure_granularity(task)
        context_dep = self._measure_context_dependency(task, context)
        
        if self._initialized and FUZZY_AVAILABLE:
            return self._fuzzy_analyze(specificity, granularity, context_dep)
        else:
            return self._fallback_analyze(specificity, granularity, context_dep)
    
    def _measure_specificity(self, task: str) -> float:
        """Measure how specific a task description is."""
        score = 0.0
        task_lower = task.lower()
        
        # Check for specific targets
        if re.search(r'(button|link|field|input|menu|icon|tab)', task_lower):
            score += 0.2
        
        # Check for specific values/names
        if re.search(r'["\']([^"\']+)["\']', task):  # Quoted strings
            score += 0.2
        
        # Check for specific numbers/positions
        if re.search(r'\b(first|second|third|1st|2nd|3rd|\d+)\b', task_lower):
            score += 0.15
        
        # Check for specific apps/URLs
        if re.search(r'(whatsapp|safari|chrome|gmail|youtube|\.com|\.org)', task_lower):
            score += 0.2
        
        # Check for specific actions
        if re.search(r'(click|type|press|scroll|drag|right-click|double-click)', task_lower):
            score += 0.25
        
        return min(1.0, score)
    
    def _measure_granularity(self, task: str) -> float:
        """Measure the granularity of actions mentioned."""
        score = 0.0
        task_lower = task.lower()
        
        # Micro-level indicators (detailed actions)
        micro_patterns = [
            r'(press|hit|tap)\s+(enter|return|tab|escape|space)',
            r'(command|cmd|ctrl|alt|shift)\s*\+',
            r'hotkey|shortcut|keyboard',
            r'click\s+at\s+\(?\d+',
            r'type\s*["\']',
            r'scroll\s+(up|down|left|right)',
            r'wait\s+\d+',
        ]
        
        # Macro-level indicators (high-level goals)
        macro_patterns = [
            r'(open|launch|start)\s+\w+',
            r'(search|find|look)\s+for',
            r'(send|message|email)\s+\w+',
            r'(download|upload|save)',
            r'(go to|navigate to|visit)',
        ]
        
        micro_matches = sum(1 for p in micro_patterns if re.search(p, task_lower))
        macro_matches = sum(1 for p in macro_patterns if re.search(p, task_lower))
        
        total_matches = micro_matches + macro_matches
        if total_matches == 0:
            return 0.5  # Unknown
        
        # Higher = more micro
        return micro_matches / total_matches
    
    def _measure_context_dependency(self, task: str, context: Optional[Dict]) -> float:
        """Measure how much the task depends on current context."""
        score = 0.3  # Base score
        task_lower = task.lower()
        
        # Context-dependent phrases
        if re.search(r'(current|this|that|here|there|it|them)', task_lower):
            score += 0.2
        
        # Screen-dependent actions
        if re.search(r'(visible|showing|displayed|on screen|see)', task_lower):
            score += 0.2
        
        # Relative positioning
        if re.search(r'(next to|above|below|beside|near|adjacent)', task_lower):
            score += 0.15
        
        # App/window context
        if context and context.get('current_app'):
            if not re.search(r'(open|launch|start)\s+\w+', task_lower):
                score += 0.15  # Task assumes current app
        
        return min(1.0, score)
    
    def _fuzzy_analyze(self, specificity: float, granularity: float, 
                       context_dep: float) -> MacroMicroPosition:
        """Use fuzzy inference for analysis."""
        try:
            self.simulator.input['specificity'] = specificity
            self.simulator.input['granularity'] = granularity
            self.simulator.input['context_dependency'] = context_dep
            
            self.simulator.compute()
            
            position = self.simulator.output['execution_level']
            
            # Calculate confidences
            macro_conf = 1.0 - position
            micro_conf = position
            
            return MacroMicroPosition(
                position=position,
                macro_confidence=macro_conf,
                micro_confidence=micro_conf,
                execution_strategy=self._determine_strategy(position),
                decomposition_needed=position < 0.4 and specificity < 0.5
            )
        except Exception as e:
            logger.warning(f"Fuzzy compute failed: {e}")
            return self._fallback_analyze(specificity, granularity, context_dep)
    
    def _fallback_analyze(self, specificity: float, granularity: float,
                          context_dep: float) -> MacroMicroPosition:
        """Fallback analysis without fuzzy logic."""
        # Simple weighted average
        position = (0.4 * granularity + 0.35 * specificity + 0.25 * (1 - context_dep))
        
        return MacroMicroPosition(
            position=position,
            macro_confidence=1.0 - position,
            micro_confidence=position,
            execution_strategy=self._determine_strategy(position),
            decomposition_needed=position < 0.4 and specificity < 0.5
        )
    
    def _determine_strategy(self, position: float) -> str:
        """Determine execution strategy from position."""
        if position < 0.35:
            return "macro_plan"
        elif position > 0.65:
            return "micro_direct"
        else:
            return "hybrid"


# ============================================================
# BAYESIAN NETWORK (Task Completeness & Intent)
# ============================================================

class BayesianTaskAnalyzer:
    """
    Uses Bayesian inference to model:
    1. Task completeness (how much info is provided)
    2. Missing information prediction
    3. Intent disambiguation
    
    The network models relationships between:
    - Task components (target, action, location, criteria)
    - Context (app, history, user patterns)
    - Intent (what user actually wants)
    """
    
    def __init__(self, history_path: Optional[Path] = None):
        self.history_path = history_path or Path("data/task_history.json")
        self.patterns_path = Path("data/patterns.json")
        self._initialized = False
        self._init_bayesian_network()
        
        # Prior probabilities learned from history
        self.priors = {
            'has_target': 0.8,
            'has_action': 0.9,
            'has_location': 0.6,
            'has_criteria': 0.3,
        }
        
        # Load and learn from history
        self._learn_from_history()
    
    def _init_bayesian_network(self):
        """Initialize the Bayesian Network structure."""
        if not PGMPY_AVAILABLE:
            logger.warning("pgmpy not available, using simplified Bayesian reasoning")
            return
        
        try:
            # Define network structure
            # Task components influence completeness and intent
            self.model = BayesianNetworkClass([
                ('has_target', 'task_complete'),
                ('has_action', 'task_complete'),
                ('has_location', 'task_complete'),
                ('has_criteria', 'task_complete'),
                ('task_complete', 'execution_success'),
                ('intent_clear', 'execution_success'),
                ('context_available', 'intent_clear'),
            ])
            
            # Define CPDs (Conditional Probability Distributions)
            # These will be updated from history
            
            cpd_target = TabularCPD('has_target', 2, [[0.2], [0.8]])  # P(has_target)
            cpd_action = TabularCPD('has_action', 2, [[0.1], [0.9]])  # P(has_action)
            cpd_location = TabularCPD('has_location', 2, [[0.4], [0.6]])
            cpd_criteria = TabularCPD('has_criteria', 2, [[0.7], [0.3]])
            
            # P(task_complete | components)
            # This is a complex CPD showing how completeness depends on components
            cpd_complete = TabularCPD(
                'task_complete', 2,
                [
                    # P(incomplete | target, action, location, criteria)
                    [0.95, 0.7, 0.8, 0.5, 0.85, 0.6, 0.7, 0.4,
                     0.9, 0.6, 0.7, 0.4, 0.8, 0.5, 0.6, 0.2],
                    # P(complete | target, action, location, criteria)
                    [0.05, 0.3, 0.2, 0.5, 0.15, 0.4, 0.3, 0.6,
                     0.1, 0.4, 0.3, 0.6, 0.2, 0.5, 0.4, 0.8],
                ],
                evidence=['has_target', 'has_action', 'has_location', 'has_criteria'],
                evidence_card=[2, 2, 2, 2]
            )
            
            cpd_context = TabularCPD('context_available', 2, [[0.3], [0.7]])
            
            # P(intent_clear | context)
            cpd_intent = TabularCPD(
                'intent_clear', 2,
                [[0.6, 0.2], [0.4, 0.8]],
                evidence=['context_available'],
                evidence_card=[2]
            )
            
            # P(success | complete, intent)
            cpd_success = TabularCPD(
                'execution_success', 2,
                [[0.8, 0.5, 0.6, 0.1], [0.2, 0.5, 0.4, 0.9]],
                evidence=['task_complete', 'intent_clear'],
                evidence_card=[2, 2]
            )
            
            self.model.add_cpds(
                cpd_target, cpd_action, cpd_location, cpd_criteria,
                cpd_complete, cpd_context, cpd_intent, cpd_success
            )
            
            self.model.check_model()
            self.inference = VariableElimination(self.model)
            self._initialized = True
            
        except Exception as e:
            logger.warning(f"Bayesian network init failed: {e}")
            self._initialized = False
    
    def _learn_from_history(self):
        """Learn priors from task history."""
        try:
            if self.patterns_path.exists():
                with open(self.patterns_path) as f:
                    patterns = json.load(f)
                
                if 'patterns' in patterns:
                    total = len(patterns['patterns'])
                    if total > 0:
                        # Analyze patterns to update priors
                        has_target_count = 0
                        has_action_count = 0
                        
                        for p in patterns['patterns']:
                            task = p.get('task_template', '').lower()
                            if re.search(r'(button|link|video|result|message)', task):
                                has_target_count += 1
                            if re.search(r'(click|type|open|send|play)', task):
                                has_action_count += 1
                        
                        self.priors['has_target'] = has_target_count / total
                        self.priors['has_action'] = has_action_count / total
                        
                        logger.debug(f"Learned priors from {total} patterns")
        except Exception as e:
            logger.debug(f"Could not learn from history: {e}")
    
    def analyze_completeness(self, task: str, context: Optional[Dict] = None) -> TaskCompleteness:
        """
        Analyze how complete a task specification is.
        
        Returns:
            TaskCompleteness with scores and predicted missing info
        """
        # Extract features
        has_target = self._detect_target(task)
        has_action = self._detect_action(task)
        has_location = self._detect_location(task)
        has_criteria = self._detect_criteria(task)
        
        missing = []
        if not has_target:
            missing.append("target element")
        if not has_action:
            missing.append("action to perform")
        if not has_location:
            missing.append("application/context")
        if not has_criteria:
            missing.append("success criteria")
        
        # Calculate overall score
        weights = {'target': 0.35, 'action': 0.35, 'location': 0.2, 'criteria': 0.1}
        score = (
            weights['target'] * (1.0 if has_target else 0.0) +
            weights['action'] * (1.0 if has_action else 0.0) +
            weights['location'] * (1.0 if has_location else 0.0) +
            weights['criteria'] * (1.0 if has_criteria else 0.0)
        )
        
        # Predict missing information
        predictions, confidence = self._predict_missing(task, missing, context)
        
        return TaskCompleteness(
            overall_score=score,
            has_target=has_target,
            has_action=has_action,
            has_location=has_location,
            has_criteria=has_criteria,
            missing_info=missing,
            predicted_info=predictions,
            confidence=confidence
        )
    
    def _detect_target(self, task: str) -> bool:
        """Detect if task specifies a target."""
        patterns = [
            r'(button|link|field|input|menu|icon|tab|video|result|message|contact)',
            r'(first|second|third|latest|newest|top|bottom)',
            r'["\']([^"\']+)["\']',  # Quoted text
            r'(called|named|titled|labeled)\s+\w+',
        ]
        return any(re.search(p, task.lower()) for p in patterns)
    
    def _detect_action(self, task: str) -> bool:
        """Detect if task specifies an action."""
        patterns = [
            r'(click|tap|press|hit|type|enter|write|input)',
            r'(open|launch|start|close|quit|exit)',
            r'(scroll|swipe|drag|drop|move)',
            r'(search|find|look for|navigate|go to|visit)',
            r'(send|submit|post|share|download|upload)',
            r'(play|pause|stop|watch|listen)',
        ]
        return any(re.search(p, task.lower()) for p in patterns)
    
    def _detect_location(self, task: str) -> bool:
        """Detect if task specifies location/context."""
        patterns = [
            r'(in|on|using|via|through)\s+(safari|chrome|whatsapp|youtube|gmail|finder)',
            r'(\.com|\.org|\.io|\.ai|\.net)',
            r'(browser|terminal|desktop|folder)',
            r'(app|application|website|page)',
        ]
        return any(re.search(p, task.lower()) for p in patterns)
    
    def _detect_criteria(self, task: str) -> bool:
        """Detect if task specifies success criteria."""
        patterns = [
            r'(until|when|after|before)',
            r'(verify|confirm|check|make sure)',
            r'(should|must|needs to)',
            r'(successfully|completely|correctly)',
        ]
        return any(re.search(p, task.lower()) for p in patterns)
    
    def _predict_missing(self, task: str, missing: List[str], 
                         context: Optional[Dict]) -> Tuple[Dict, float]:
        """Predict missing information from context and patterns."""
        predictions = {}
        confidence = 0.0
        
        task_lower = task.lower()
        
        # Predict location if missing
        if "application/context" in missing:
            if re.search(r'(video|youtube|watch|play)', task_lower):
                predictions['location'] = 'Safari/YouTube'
                confidence += 0.3
            elif re.search(r'(message|send|whatsapp|contact)', task_lower):
                predictions['location'] = 'WhatsApp'
                confidence += 0.3
            elif re.search(r'(search|google|browse)', task_lower):
                predictions['location'] = 'Safari'
                confidence += 0.25
            elif context and context.get('current_app'):
                predictions['location'] = context['current_app']
                confidence += 0.2
        
        # Predict action if missing
        if "action to perform" in missing:
            if re.search(r'(result|link|video|button)', task_lower):
                predictions['action'] = 'click'
                confidence += 0.25
            elif re.search(r'(message|text|content)', task_lower):
                predictions['action'] = 'type'
                confidence += 0.2
        
        # Normalize confidence
        if predictions:
            confidence = min(0.8, confidence)
        
        return predictions, confidence


# ============================================================
# INTENT PREDICTION ENGINE
# ============================================================

class IntentPredictor:
    """
    Predicts user's true intent from partial/ambiguous descriptions.
    Uses pattern matching + learned associations.
    """
    
    # Intent categories and their indicators
    INTENT_PATTERNS = {
        'navigation': [
            r'(go to|navigate|visit|open|launch)',
            r'(search|find|look for)',
        ],
        'interaction': [
            r'(click|tap|press|select)',
            r'(fill|type|enter|write)',
            r'(scroll|swipe|drag)',
        ],
        'communication': [
            r'(send|message|email|text)',
            r'(call|contact|reach)',
            r'(reply|respond)',
        ],
        'media': [
            r'(play|watch|listen|view)',
            r'(pause|stop|skip)',
            r'(download|save)',
        ],
        'file_management': [
            r'(create|make|new)\s+(file|folder|document)',
            r'(delete|remove|trash)',
            r'(copy|move|rename)',
        ],
    }
    
    def __init__(self):
        self.history: List[Dict] = []
    
    def predict(self, task: str, context: Optional[Dict] = None) -> IntentPrediction:
        """Predict user intent from task description."""
        task_lower = task.lower()
        
        # Score each intent category
        intent_scores = {}
        for intent, patterns in self.INTENT_PATTERNS.items():
            score = 0
            for pattern in patterns:
                if re.search(pattern, task_lower):
                    score += 1
            intent_scores[intent] = score / len(patterns)
        
        # Find primary and alternatives
        sorted_intents = sorted(intent_scores.items(), key=lambda x: -x[1])
        
        if sorted_intents[0][1] == 0:
            # No matches - try inference
            primary = self._infer_intent(task, context)
            confidence = 0.3
            ambiguity = 0.8
        else:
            primary = sorted_intents[0][0]
            confidence = sorted_intents[0][1]
            
            # Check ambiguity (similar scores for top intents)
            if len(sorted_intents) > 1:
                score_diff = sorted_intents[0][1] - sorted_intents[1][1]
                ambiguity = 1.0 - min(1.0, score_diff * 2)
            else:
                ambiguity = 0.2
        
        # Collect alternatives
        alternatives = [
            (intent, score) 
            for intent, score in sorted_intents[1:4] 
            if score > 0
        ]
        
        # Extract context clues
        clues = self._extract_clues(task)
        
        return IntentPrediction(
            primary_intent=primary,
            confidence=confidence,
            alternative_intents=alternatives,
            context_clues=clues,
            ambiguity_score=ambiguity
        )
    
    def _infer_intent(self, task: str, context: Optional[Dict]) -> str:
        """Infer intent when no patterns match."""
        task_lower = task.lower()
        
        # Object-based inference
        if re.search(r'(video|youtube|movie|show)', task_lower):
            return 'media'
        elif re.search(r'(message|whatsapp|text|chat)', task_lower):
            return 'communication'
        elif re.search(r'(file|folder|document)', task_lower):
            return 'file_management'
        elif re.search(r'(website|page|\.com)', task_lower):
            return 'navigation'
        
        # Default
        return 'interaction'
    
    def _extract_clues(self, task: str) -> List[str]:
        """Extract context clues from task."""
        clues = []
        task_lower = task.lower()
        
        # App mentions
        apps = re.findall(r'(safari|chrome|whatsapp|youtube|finder|terminal|gmail)', task_lower)
        clues.extend([f"app:{app}" for app in apps])
        
        # Targets
        targets = re.findall(r'(first|latest|newest|second|third)', task_lower)
        clues.extend([f"position:{t}" for t in targets])
        
        # Quoted text
        quoted = re.findall(r'["\']([^"\']+)["\']', task)
        clues.extend([f"text:{q}" for q in quoted])
        
        return clues


# ============================================================
# ELEMENT AFFORDANCE SCORER (Practical World Awareness)
# ============================================================

@dataclass
class ElementAffordanceScore:
    """Score representing how well an element matches intent given its affordances."""
    probability: float          # 0.0 - 1.0
    is_target: bool             # Is it a likely target?
    reason: str                 # Why it was scored this way
    match_quality: str          # "high", "medium", "low", "negative"

class ElementAffordanceScorer:
    """
    Scores UI elements based on their "Practical Affordance".
    Distinguishes between "Text that matches" (e.g. Header) and 
    "Things that do the job" (e.g. Buttons).
    """
    
    def score_element(self, element: Any, intent: Dict, screen_height: int) -> ElementAffordanceScore:
        """
        Score a single element.
        element: AccessibilityElement object
        intent: Dict from vision_executor._parse_intent
        """
        score = 0.5  # Base score
        reasons = []
        
        # 1. Role Affordance (Is it clickable?)
        # ------------------------------------
        interactive_roles = ['button', 'link', 'menuItem', 'checkBox', 'radioButton', 'switch']
        static_roles = ['staticText', 'text', 'heading', 'group', 'image']
        
        if element.role in interactive_roles:
            score += 0.2
            reasons.append("interactive_role")
        elif element.role in static_roles:
            score -= 0.1
            reasons.append("static_role")
            
        # 2. Position Heuristics (Is it a header/footer?)
        # ---------------------------------------------
        # Top 10% is usually header
        is_top_header = element.y < (screen_height * 0.10)
        # Bottom 10% is usually footer/status
        is_bottom_footer = element.y > (screen_height * 0.90)
        
        if is_top_header:
            score -= 0.3
            reasons.append("top_header_penalty")
        
        # 3. Content Specificity (Is it generic?)
        # -------------------------------------
        text = (element.title or "") + " " + (element.value or "")
        text = text.strip().lower()
        
        # Keywords check
        intent_keywords = [k.lower() for k in intent.get("keywords", [])]
        keyword_match = any(k in text for k in intent_keywords)
        
        if keyword_match:
            score += 0.3
            reasons.append("keyword_match")
            
            # Exact match generic penalty (e.g. just "1080p" vs "Download 1080p")
            if len(text.split()) < 2 and element.role not in interactive_roles:
                 score -= 0.2
                 reasons.append("generic_text_penalty")
        
        # 4. Intent Alignment
        # -----------------
        target_type = intent.get("target_type", "unknown")
        if target_type == "video" and (element.width > 200 or "duration" in text):
             score += 0.2
             reasons.append("video_like")
        
        # Clamp score
        score = max(0.0, min(1.0, score))
        
        quality = "low"
        if score > 0.8: quality = "high"
        elif score > 0.5: quality = "medium"
        
        return ElementAffordanceScore(
            probability=score,
            is_target=score > 0.6,
            reason=", ".join(reasons),
            match_quality=quality
        )


# ============================================================
# UNIFIED PROBABILITY MODEL
# ============================================================

class TaskProbabilityModel:
    """
    Unified probability model combining all analyzers.
    
    This is the main entry point for the executor to use.
    It provides a comprehensive analysis of task uncertainty
    and recommended execution strategies.
    """
    
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path("data")
        
        # Initialize components
        self.fuzzy_analyzer = FuzzyMacroMicroAnalyzer()
        self.bayesian_analyzer = BayesianTaskAnalyzer(
            history_path=self.data_dir / "task_history.json"
        )
        self.intent_predictor = IntentPredictor()
        self.affordance_scorer = ElementAffordanceScorer()
        
        # Feedback learning
        self.feedback_path = self.data_dir / "probability_feedback.json"
        self.feedback: List[Dict] = self._load_feedback()
    
    def analyze(self, task: str, context: Optional[Dict] = None) -> ExecutionFlexibility:
        """
        Comprehensive task analysis for flexible execution.
        
        Args:
            task: The task description from user
            context: Optional context (current app, screen, history)
        
        Returns:
            ExecutionFlexibility with all analysis and recommendations
        """
        logger.debug(f"Analyzing task flexibility: {task}")
        
        # Run all analyzers
        completeness = self.bayesian_analyzer.analyze_completeness(task, context)
        macro_micro = self.fuzzy_analyzer.analyze(task, context)
        intent = self.intent_predictor.predict(task, context)
        
        # Create combined result
        flexibility = ExecutionFlexibility(
            task_completeness=completeness,
            macro_micro=macro_micro,
            intent=intent
        )
        
        logger.debug(f"  Completeness: {completeness.overall_score:.0%}")
        logger.debug(f"  Macro-Micro: {macro_micro.position:.2f} ({macro_micro.execution_strategy})")
        logger.debug(f"  Intent: {intent.primary_intent} ({intent.confidence:.0%})")
        logger.debug(f"  Overall uncertainty: {flexibility.overall_uncertainty:.0%}")
        
        return flexibility
    
    def get_execution_params(self, task: str, context: Optional[Dict] = None) -> Dict:
        """
        Get execution parameters based on probability analysis.
        
        Returns a dict that can be passed to executor with:
        - min_match_probability: threshold for element matching
        - verification_strictness: how strict to verify actions
        - fallback_chain: ordered list of fallback strategies
        - exploration_enabled: whether to try alternatives
        """
        flexibility = self.analyze(task, context)
        
        # Calculate dynamic thresholds based on uncertainty
        uncertainty = flexibility.overall_uncertainty
        completeness = flexibility.task_completeness.overall_score
        
        # Higher uncertainty → lower match probability threshold (more forgiving)
        # But also need more verification
        if uncertainty > 0.6:
            min_match = 0.4
            verification = "strict"
            exploration = True
        elif uncertainty > 0.3:
            min_match = 0.55
            verification = "moderate"
            exploration = True
        else:
            min_match = 0.7
            verification = "light"
            exploration = False
        
        return {
            'min_match_probability': min_match,
            'verification_strictness': verification,
            'fallback_chain': flexibility.fallback_strategies,
            'exploration_enabled': exploration,
            'execution_strategy': flexibility.macro_micro.execution_strategy,
            'predicted_info': flexibility.task_completeness.predicted_info,
            'primary_intent': flexibility.intent.primary_intent,
            'confidence': 1.0 - uncertainty,
        }
    
    def record_feedback(self, task: str, success: bool, 
                        actual_intent: Optional[str] = None,
                        correction: Optional[str] = None):
        """Record feedback to improve future predictions."""
        feedback_entry = {
            'timestamp': datetime.now().isoformat(),
            'task': task,
            'success': success,
            'actual_intent': actual_intent,
            'correction': correction,
        }
        
        self.feedback.append(feedback_entry)
        self._save_feedback()
        
        logger.debug(f"Recorded probability feedback: {success}")
    
    def _load_feedback(self) -> List[Dict]:
        """Load feedback history."""
        try:
            if self.feedback_path.exists():
                with open(self.feedback_path) as f:
                    return json.load(f)
        except Exception as e:
            logger.debug(f"Could not load feedback: {e}")
        return []
    
    def _save_feedback(self):
        """Save feedback history."""
        try:
            self.feedback_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.feedback_path, 'w') as f:
                json.dump(self.feedback[-1000:], f, indent=2)  # Keep last 1000
        except Exception as e:
            logger.debug(f"Could not save feedback: {e}")


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

_model: Optional[TaskProbabilityModel] = None

def get_probability_model() -> TaskProbabilityModel:
    """Get or create the singleton probability model."""
    global _model
    if _model is None:
        _model = TaskProbabilityModel()
    return _model


def analyze_task_flexibility(task: str, context: Optional[Dict] = None) -> ExecutionFlexibility:
    """Quick access to task flexibility analysis."""
    return get_probability_model().analyze(task, context)


def get_flexible_execution_params(task: str, context: Optional[Dict] = None) -> Dict:
    """Get execution parameters with flexibility adjustments."""
    return get_probability_model().get_execution_params(task, context)
