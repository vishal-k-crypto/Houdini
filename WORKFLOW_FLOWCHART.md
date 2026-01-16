# Houdini Agent Workflow Flowchart

## Complete System Flow

```mermaid
flowchart TD
    Start([User Task Input]) --> Init[Initialize System]
    Init --> ArchSelect{Architecture Mode?}
    
    ArchSelect -->|Adaptive Default| Adaptive[Adaptive Architecture]
    ArchSelect -->|LangGraph| LangGraph[LangGraph Architecture]
    ArchSelect -->|Legacy| Legacy[Legacy Architecture]
    
    %% Adaptive Architecture Path
    Adaptive --> MacroPlanner[Macro Planner<br/>Strategic Planning]
    MacroPlanner --> MacroPlan[Generate High-Level Steps<br/>Example: Open App → Navigate → Action]
    MacroPlan --> MicroExec[Micro Executor<br/>Tactical Execution]
    
    MicroExec --> ScreenAnalysis[Analyze Screen State<br/>- App/Window Detection<br/>- UI Elements<br/>- Context Understanding]
    ScreenAnalysis --> GenActions[Generate Micro Actions<br/>- hotkey, type, click<br/>- wait, move]
    
    GenActions --> ExecuteAction[Execute Action]
    ExecuteAction --> Unexpected{Unexpected<br/>Situation?}
    
    Unexpected -->|Yes - Dialog/Error| Supervisor[Adaptive Supervisor<br/>Real-Time Oversight]
    Unexpected -->|No| StepComplete{Step<br/>Complete?}
    
    Supervisor --> GuidanceType{Guidance Type}
    GuidanceType --> HandleRandom[Handle Randomness<br/>Close Dialog, Retry]
    GuidanceType --> GuideStuck[Guide When Stuck<br/>Alternative Approach]
    GuidanceType --> EvolveTask[Evolve Task Plan<br/>Add New Steps]
    
    HandleRandom --> MicroExec
    GuideStuck --> MicroExec
    EvolveTask --> MacroPlan
    
    StepComplete -->|No| MicroExec
    StepComplete -->|Yes| AllStepsComplete{All Macro<br/>Steps Done?}
    
    AllStepsComplete -->|No| MicroExec
    AllStepsComplete -->|Yes| Verify[Supervisor Verification<br/>Check Actual Completion]
    
    Verify --> VerifyResult{Task<br/>Complete?}
    VerifyResult -->|No - Incomplete| EvolveTask
    VerifyResult -->|Yes| RecordContext[Record to Context Memory<br/>Store Success Patterns]
    
    %% LangGraph Architecture Path
    LangGraph --> StateInit[Initialize State Machine]
    StateInit --> Checkpoint1[Load/Create Checkpoint]
    Checkpoint1 --> LGMacro[Macro Planning Node]
    LGMacro --> Checkpoint2[Save State]
    Checkpoint2 --> LGMicro[Micro Execution Node]
    LGMicro --> Checkpoint3[Save State]
    Checkpoint3 --> LGSuper[Supervisor Node]
    LGSuper --> LGVerify{Complete?}
    LGVerify -->|No| LGMicro
    LGVerify -->|Yes| LGContext[Record Context]
    LGContext --> LGEnd([Task Complete])
    
    %% Legacy Architecture Path
    Legacy --> LegacyPlan[Traditional Planner]
    LegacyPlan --> LegacyExec[Executor]
    LegacyExec --> LegacySuper[Supervisor]
    LegacySuper --> LegacyVerify{Complete?}
    LegacyVerify -->|No| LegacyExec
    LegacyVerify -->|Yes| LegacyContext[Record Context]
    LegacyContext --> LegacyEnd([Task Complete])
    
    %% Adaptive Architecture Continuation
    RecordContext --> ReplayRecord[Record Replay Session<br/>Cursor, Actions, Screenshots]
    ReplayRecord --> End([Task Complete])
    
    %% Supporting Systems
    MacroPlanner -.->|Uses| ProbModel[Probability Model<br/>Dynamic Thresholds]
    MicroExec -.->|Uses| VisionSystem[Vision System<br/>Apple Vision + UI-TARS]
    ExecuteAction -.->|Uses| ConfidenceModel[Confidence Calibration<br/>Q-Learning, Thompson Sampling]
    Supervisor -.->|Learns from| PromptEvolution[Prompt Evolution<br/>Feedback-Driven Improvements]
    RecordContext -.->|Stores| ContextMemory[Context Memory DB<br/>File Locations, Patterns]
    
    style Start fill:#e1f5e1
    style End fill:#e1f5e1
    style LGEnd fill:#e1f5e1
    style LegacyEnd fill:#e1f5e1
    style Supervisor fill:#fff4e1
    style MacroPlanner fill:#e1f0ff
    style MicroExec fill:#ffe1f0
    style VisionSystem fill:#f0e1ff
    style ContextMemory fill:#e1ffe1
```

## Component Details

### 1. Macro Planner (Strategic Layer)
- **Input**: User task description
- **Processing**: 
  - Analyzes task complexity using Probability Model
  - Breaks down into high-level steps
  - Does NOT specify keyboard shortcuts
- **Output**: Sequential macro steps (e.g., "Open App", "Navigate to Section")

### 2. Micro Executor (Tactical Layer)
- **Input**: One macro step + current screen state
- **Processing**:
  - Captures screenshot
  - Analyzes UI using Vision System
  - Determines specific actions needed
  - Generates low-level commands
- **Output**: Executable actions (hotkey, type, click, wait)
- **Intelligence**: 
  - Knows when stuck
  - Requests supervisor help
  - Adapts to UI changes

### 3. Adaptive Supervisor (Oversight Layer)
- **Monitors**: Executor progress continuously
- **Handles**:
  - Unexpected dialogs/popups
  - Execution failures
  - Task completion verification
- **Powers**:
  - Can guide executor with alternative approaches
  - Can evolve the macro plan in real-time
  - Can add new steps dynamically
- **Learning**: Feeds back to Prompt Evolution system

### 4. Supporting Systems

#### Vision System
- **Apple Vision Framework**: Hardware-accelerated UI detection
- **UI-TARS MLX**: Semantic grounding for complex elements
- **Coordinate Handling**: Retina display support

#### Probability Model
- **Dynamic Thresholds**: Adjusts match probability based on task
- **Incomplete Specs**: Handles 80-90% info tasks
- **Confidence Scoring**: Q-Learning, Thompson Sampling, Conformal Prediction

#### Context Memory
- **Stores**: Successful file operations, patterns, locations
- **Recalls**: For future task execution
- **Database**: `data/context_memory/`

#### Prompt Evolution
- **Tracks**: Success/failure rates
- **Analyzes**: Error patterns
- **Evolves**: Prompt files automatically when failure rate > 20%

## Execution Modes Comparison

| Feature | Adaptive | LangGraph | Legacy |
|---------|----------|-----------|--------|
| Macro/Micro Separation | ✅ Yes | ✅ Yes | ❌ No |
| Real-Time Evolution | ✅ Yes | ✅ Yes | ⚠️ Limited |
| Checkpointing | ❌ No | ✅ Yes | ❌ No |
| Crash Recovery | ❌ No | ✅ Yes | ❌ No |
| Human-in-Loop | ⚠️ Manual | ✅ Built-in | ❌ No |
| Randomness Handling | ✅ Supervisor | ✅ Supervisor | ⚠️ Basic |
| State Management | 🔄 Dynamic | 🔄 LangGraph | 📝 Sequential |

## Replay & Debugging Flow

```mermaid
flowchart LR
    Execution[Task Execution] --> Record[Auto-Record Session]
    Record --> Save[Save to replay_sessions/]
    Save --> Replay[Time-Travel Replay Mode]
    
    Replay --> View[View:]
    View --> Cursor[Cursor Positions]
    View --> Think[AI Thinking Process]
    View --> Screens[Screenshots at Checkpoints]
    View --> Timing[Action Timing]
    
    style Record fill:#ffe1e1
    style Replay fill:#e1ffe1
```

## Permission Check Flow

```mermaid
flowchart TD
    Launch[Launch Agent] --> PermCheck{Permissions<br/>Granted?}
    
    PermCheck -->|Yes| Continue[Continue Execution]
    PermCheck -->|No| CheckAccess[Check Accessibility]
    
    CheckAccess --> AccessOK{Accessibility<br/>OK?}
    AccessOK -->|No| PromptAccess[Prompt: Grant Accessibility<br/>in System Settings]
    AccessOK -->|Yes| CheckScreen[Check Screen Recording]
    
    CheckScreen --> ScreenOK{Screen<br/>Recording OK?}
    ScreenOK -->|No| PromptScreen[Prompt: Grant Screen Recording<br/>in System Settings]
    ScreenOK -->|Yes| CheckCoords[Check Coordinate System]
    
    CheckCoords --> CoordsOK{Retina<br/>Handled?}
    CoordsOK -->|No| FixCoords[Fix Coordinate Scaling]
    CoordsOK -->|Yes| Continue
    
    PromptAccess --> Restart[Restart Terminal Required]
    PromptScreen --> Restart
    FixCoords --> Continue
    Restart --> Launch
    
    style PromptAccess fill:#ffe1e1
    style PromptScreen fill:#ffe1e1
    style Continue fill:#e1f5e1
```

## Quick Reference

### Starting a Task
```bash
python -m src.main --task "your task here"
```

### Architecture Selection
```bash
# Adaptive (default)
python -m src.main --task "task"

# LangGraph with checkpoints
python -m src.main --task "task" --langgraph --checkpoint-path data/checkpoints.db

# Legacy
python -m src.main --task "task" --legacy
```

### Replay Debugging
```bash
# Interactive replay mode
python -m src.main --replay

# List all sessions
python -m src.main --replay-list

# Replay specific session
python -m src.main --replay-session <task_id>
```

### Permission Testing
```bash
python test_permissions.py
```

## Key Innovation: Real-Time Task Evolution

Unlike traditional agents that fail when the plan doesn't match reality, Houdini can **evolve the task mid-execution**:

1. **Initial Plan**: [A] → [B] → [C]
2. **Supervisor Verifies**: Task incomplete after [C]
3. **Evolved Plan**: [A] → [B] → [C] → [D] → [E]
4. **Execution Continues**: Agent completes [D] and [E] automatically

This enables robust handling of:
- Multi-step workflows with dependencies
- Unexpected UI states
- Incomplete task specifications
- Dynamic web content
- Permission dialogs
- App-specific behaviors
