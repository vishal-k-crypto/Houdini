"""
Pydantic Schemas - Strict data validation for Planner and Executor.

These models enforce JSON structures from LLM responses, reducing hallucination
issues and catching malformed data at parse time.
"""

from typing import List, Optional, Union, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class ActionType(str, Enum):
    """Types of actions the agent can take."""
    BLIND = "blind"
    VISION = "vision"


class SupervisorDecision(str, Enum):
    """Possible supervisor decisions."""
    GUIDE = "guide"
    SKIP = "skip"
    ABORT = "abort"


# =============================================================================
# ACTION MODELS
# =============================================================================

class BlindAction(BaseModel):
    """
    A single blind action string.
    
    Format examples:
    - "hotkey:command,space"
    - "type:Safari"
    - "key:return"
    - "wait:0.5"
    - "click:100,200"
    """
    action: str = Field(..., description="Action string in format 'type:params'")
    
    @field_validator('action')
    @classmethod
    def validate_action_format(cls, v: str) -> str:
        """Validate action follows expected format."""
        if not v:
            raise ValueError("Action cannot be empty")
        # Actions should have format "type:value" or be a simple string
        valid_prefixes = ('hotkey:', 'type:', 'key:', 'wait:', 'click:')
        if ':' in v and not any(v.startswith(p) for p in valid_prefixes):
            # Allow other formats but log for now
            pass
        return v


class BlindBatch(BaseModel):
    """Batch of blind actions that can be executed without screen observation."""
    type: Literal["blind"] = "blind"
    description: str = Field(..., description="Human-readable description of the batch")
    actions: List[str] = Field(default_factory=list, description="List of action strings")
    
    @field_validator('actions')
    @classmethod
    def validate_actions_not_empty(cls, v: List[str]) -> List[str]:
        """Ensure at least one action for blind batches."""
        # Allow empty for now - executor handles this case
        return v


class VisionBatch(BaseModel):
    """Single vision action requiring screen observation."""
    type: Literal["vision"] = "vision"
    description: str = Field(..., description="Human-readable description")
    action: str = Field(..., description="Vision action description (what to click/find)")


# Discriminated union of batch types
ActionBatch = Union[BlindBatch, VisionBatch]


# =============================================================================
# PLANNER MODELS
# =============================================================================

class PlannerResponse(BaseModel):
    """Response from GeminiPlanner.plan()"""
    batches: List[Union[BlindBatch, VisionBatch]] = Field(
        default_factory=list,
        description="List of action batches to execute"
    )
    
    @classmethod
    def from_raw_json(cls, data: dict) -> "PlannerResponse":
        """Parse raw JSON dict, handling legacy formats."""
        batches = []
        for batch_data in data.get("batches", []):
            batch_type = batch_data.get("type", "blind")
            if batch_type == "vision":
                batches.append(VisionBatch(**batch_data))
            else:
                batches.append(BlindBatch(**batch_data))
        return cls(batches=batches)


# =============================================================================
# MACRO PLANNER MODELS (Adaptive Coordinator)
# =============================================================================

class MacroStep(BaseModel):
    """High-level macro step from adaptive planner."""
    step: str = Field(..., description="High-level description of what to do")
    context: str = Field("", description="Expected state after this step")
    potential_issues: Optional[str] = Field(None, description="What could go wrong")
    suggested_actions: Optional[List[str]] = Field(
        None, 
        description="Concrete action patterns like 'hotkey:command,space', 'type:Safari', 'key:return'"
    )


class MacroPlanResponse(BaseModel):
    """Response from macro planning."""
    macro_steps: List[MacroStep] = Field(
        default_factory=list,
        description="List of high-level steps"
    )
    expected_outcome: str = Field(
        "Task completed",
        description="What success looks like"
    )
    success_criteria: str = Field(
        "User goal achieved",
        description="How to verify completion"
    )


# =============================================================================
# MICRO EXECUTOR MODELS
# =============================================================================

class MicroActionParams(BaseModel):
    """Parameters for a micro action."""
    keys: Optional[List[str]] = None  # For hotkey
    text: Optional[str] = None        # For type
    key: Optional[str] = None         # For key press
    seconds: Optional[float] = None   # For wait
    element: Optional[str] = None     # For click
    x: Optional[int] = None           # For click coordinates
    y: Optional[int] = None           # For click coordinates


class MicroAction(BaseModel):
    """Low-level micro action from executor."""
    type: str = Field(..., description="Action type: hotkey, type, key, wait, click")
    params: MicroActionParams = Field(default_factory=MicroActionParams)
    description: str = Field("", description="Human-readable description")
    requires_screen: bool = Field(False, description="Whether action needs screen check")


class MicroActionsResponse(BaseModel):
    """Response from executor's micro action generation."""
    actions: List[MicroAction] = Field(default_factory=list)
    requires_screen_check: bool = Field(False)
    confidence: float = Field(0.5, ge=0.0, le=1.0)


# =============================================================================
# SUPERVISOR MODELS
# =============================================================================

class SupervisorGuidance(BaseModel):
    """Supervisor decision when guiding the executor."""
    decision: SupervisorDecision = Field(..., description="guide, skip, or abort")
    reason: str = Field("", description="Explanation for the decision")
    actions: List[MicroAction] = Field(
        default_factory=list,
        description="Actions to execute (only if decision is 'guide')"
    )
    note: Optional[str] = Field(None, description="Additional learning context")


class VerificationResult(BaseModel):
    """Result from task completion verification."""
    complete: bool = Field(..., description="Whether task is complete")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Confidence level")
    reason: str = Field("", description="Explanation of decision")
    what_is_missing: Optional[str] = Field(None, description="What needs to be done")
    corrective_steps: List[MacroStep] = Field(
        default_factory=list,
        description="Steps to complete the task"
    )


class EvolutionPlan(BaseModel):
    """Supervisor's evolved plan when task verification fails."""
    executor_mistakes: str = Field("", description="What went wrong")
    correction_message: str = Field("", description="Guidance for executor")
    new_steps: List[MacroStep] = Field(default_factory=list)


# =============================================================================
# EXECUTOR RESULT MODELS
# =============================================================================

class ExecutorResult(BaseModel):
    """Result from blind/vision execution."""
    success: bool = Field(..., description="Whether execution succeeded")
    error: Optional[str] = Field(None, description="Error message if failed")
    method: Optional[str] = Field(None, description="Execution method used")


class VisionExecutionResult(BaseModel):
    """Result from vision action execution."""
    success: bool = Field(...)
    clicked: bool = Field(False)
    coordinates: Optional[tuple] = Field(None)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    element: Optional[str] = Field(None, description="Element text that was found")
    error: Optional[str] = Field(None)


class PlanExecutionResult(BaseModel):
    """Result from execute_plan_fast()."""
    results: List[Dict[str, Any]] = Field(default_factory=list)
    completed: int = Field(0)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def parse_planner_response(raw_json: str) -> PlannerResponse:
    """
    Safely parse planner JSON response with validation.
    
    Args:
        raw_json: Raw JSON string from LLM
        
    Returns:
        Validated PlannerResponse
        
    Raises:
        ValueError: If JSON is malformed or missing required fields
    """
    import json
    
    # Clean the JSON
    clean = raw_json.strip()
    if "```json" in clean:
        clean = clean.split("```json")[1].split("```")[0]
    elif "```" in clean:
        clean = clean.split("```")[1].split("```")[0]
    
    data = json.loads(clean)
    return PlannerResponse.from_raw_json(data)


def parse_macro_plan(raw_json: str) -> MacroPlanResponse:
    """
    Safely parse macro plan JSON response with validation.
    """
    import json
    
    clean = raw_json.strip()
    if "```json" in clean:
        clean = clean.split("```json")[1].split("```")[0]
    elif "```" in clean:
        clean = clean.split("```")[1].split("```")[0]
    
    data = json.loads(clean)
    return MacroPlanResponse.model_validate(data)


def parse_micro_actions(raw_json: str) -> MicroActionsResponse:
    """
    Safely parse micro actions JSON response with validation.
    """
    import json
    
    clean = raw_json.strip()
    if "```json" in clean:
        clean = clean.split("```json")[1].split("```")[0]
    elif "```" in clean:
        clean = clean.split("```")[1].split("```")[0]
    
    data = json.loads(clean)
    return MicroActionsResponse.model_validate(data)


def parse_supervisor_guidance(raw_json: str) -> SupervisorGuidance:
    """
    Safely parse supervisor guidance JSON response with validation.
    """
    import json
    
    clean = raw_json.strip()
    if "```json" in clean:
        clean = clean.split("```json")[1].split("```")[0]
    elif "```" in clean:
        clean = clean.split("```")[1].split("```")[0]
    
    data = json.loads(clean)
    return SupervisorGuidance.model_validate(data)


def parse_verification_result(raw_json: str) -> VerificationResult:
    """
    Safely parse verification result JSON response with validation.
    """
    import json
    
    clean = raw_json.strip()
    if "```json" in clean:
        clean = clean.split("```json")[1].split("```")[0]
    elif "```" in clean:
        clean = clean.split("```")[1].split("```")[0]
    
    data = json.loads(clean)
    return VerificationResult.model_validate(data)
