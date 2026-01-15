# LangGraph Migration Guide

This document explains the migration from custom loop coordinators to LangGraph-based execution.

## Why LangGraph?

The previous architecture used manual state management in `LoopCoordinator` and `AdaptiveLoopCoordinator`. LangGraph provides significant advantages:

| Feature | Custom Loops | LangGraph |
|---------|-------------|-----------|
| State Management | Manual tracking | Automatic |
| Crash Recovery | None | Built-in checkpointing |
| Resume Execution | Not supported | Native support |
| Human-in-the-Loop | Manual implementation | Built-in hooks |
| Visualization | None | Graph visualization |
| Debugging | Print statements | State inspection at any node |

## Architecture Comparison

### Before: Custom Loop Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  AdaptiveLoopCoordinator                │
│  ┌─────────────────────────────────────────────────┐   │
│  │            Manual While Loop                     │   │
│  │  while running and iteration < max:              │   │
│  │    if phase == PLANNING:                         │   │
│  │      generate_macro_plan()                       │   │
│  │    elif phase == EXECUTING:                      │   │
│  │      execute_macro_step()                        │   │
│  │    elif phase == SUPERVISOR_GUIDE:               │   │
│  │      supervisor_guide_executor()                 │   │
│  │    elif phase == VERIFYING:                      │   │
│  │      supervisor_verify_completion()              │   │
│  │    elif phase == EVOLVING:                       │   │
│  │      supervisor_evolve_task()                    │   │
│  │    ...                                           │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  State: AdaptiveState (dataclass)                      │
│  - Manual phase tracking                               │
│  - Manual iteration counting                           │
│  - No persistence                                      │
└─────────────────────────────────────────────────────────┘
```

### After: LangGraph Architecture

```
    ┌─────────────┐
    │  __start__  │
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │   analyze   │  (probability model + initial setup)
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │   planner   │  (macro planning)
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐◄─────────────────────┐
    │  executor   │  (micro actions)     │
    └──────┬──────┘                      │
           │                             │
           ▼                             │
    ┌─────────────┐   needs_supervisor   │
    │  router     │──────────────────────┤
    └──────┬──────┘                      │
           │ step_complete               │
           ▼                             │
    ┌─────────────┐                      │
    │  verifier   │                      │
    └──────┬──────┘                      │
           │                             │
           ▼                             │
    ┌─────────────┐   incomplete         │
    │  evolver    │──────────────────────┘
    └──────┬──────┘
           │ complete
           ▼
    ┌─────────────┐
    │  __end__    │
    └─────────────┘

Benefits:
- State is TypedDict, flows automatically between nodes
- Checkpointing saves state to SQLite/memory
- Can resume from any checkpoint
- Clear conditional routing with named edges
```

## File Changes

### New Files

| File | Description |
|------|-------------|
| `src/loop/langgraph_state.py` | TypedDict state schema with annotations |
| `src/loop/langgraph_coordinator.py` | LangGraph-based coordinator |

### Modified Files

| File | Changes |
|------|---------|
| `requirements.txt` | Added `langgraph>=0.2.0`, `langchain-core>=0.3.0` |
| `src/loop/__init__.py` | Exports LangGraph components |
| `src/main.py` | Added `--langgraph` flag and related options |
| `commands.sh` | Added LangGraph usage examples |

## Usage

### Basic Usage

```bash
# Use LangGraph architecture
python -m src.main --task "search for AI news" --langgraph
```

### With Checkpointing (Crash Recovery)

```bash
# Enable persistent checkpoints
python -m src.main --task "complex multi-step task" \
    --langgraph \
    --checkpoint-path data/checkpoints.db
```

### Resume from Checkpoint

If execution was interrupted, resume with the thread ID:

```bash
# Resume a previous execution
python -m src.main --task "same task" \
    --langgraph \
    --checkpoint-path data/checkpoints.db \
    --resume-thread abc12345
```

### Human-in-the-Loop

```bash
# Enable human approval points
python -m src.main --task "send email to boss" \
    --langgraph \
    --human-approval
```

## State Schema

The new `HoudiniAgentState` TypedDict includes:

```python
class HoudiniAgentState(TypedDict):
    # Task info
    task_id: str
    task: str
    phase: str  # AgentPhase enum value
    
    # Planning
    macro_steps: List[MacroStep]
    current_macro_step_idx: int
    
    # Execution
    pending_actions: List[MicroAction]
    executed_actions: Annotated[List[ActionRecord], operator.add]
    
    # Screen context
    current_screen: Optional[ScreenContext]
    screen_history: Annotated[List[ScreenContext], operator.add]
    
    # Supervisor
    needs_supervisor: bool
    interventions: Annotated[List[SupervisorIntervention], operator.add]
    
    # Verification & Evolution
    verification_complete: bool
    evolution_count: int
    
    # Human-in-the-loop
    awaiting_human_input: bool
    human_input_response: Optional[str]
    
    # Control
    iteration: int
    max_iterations: int
    should_abort: bool
```

### Key Features:

1. **Annotated Lists**: Use `operator.add` to accumulate values across nodes
2. **Optional Fields**: Allow graceful handling of missing data
3. **Phase Tracking**: Clear enum-based phase management
4. **Human Input**: Built-in fields for human-in-the-loop

## Node Implementations

Each node receives the full state and returns updates:

```python
def _planner_node(self, state: HoudiniAgentState) -> Dict[str, Any]:
    """Macro planning node."""
    # Generate plan
    response = self.client.generate_json(prompt)
    
    # Return only the fields that changed
    return {
        "macro_steps": response["macro_steps"],
        "expected_outcome": response["expected_outcome"],
        "phase": AgentPhase.EXECUTING.value,
    }
```

## Conditional Routing

Routing is declarative with named edges:

```python
# After executor, route based on state
graph.add_conditional_edges(
    "executor",
    self._route_after_executor,
    {
        "supervisor": "supervisor",
        "verifier": "verifier",
        "executor": "executor",  # Loop back
        "end": END,
    }
)

def _route_after_executor(self, state) -> Literal["supervisor", "verifier", "executor", "end"]:
    if state.get("needs_supervisor"):
        return "supervisor"
    if state.get("phase") == AgentPhase.VERIFYING.value:
        return "verifier"
    return "executor"
```

## Checkpointing

LangGraph automatically saves state at each node:

```python
# Memory-only (default)
checkpointer = MemorySaver()

# Persistent SQLite
checkpointer = SqliteSaver.from_conn_string("data/checkpoints.db")

# Compile with checkpointer
app = graph.compile(checkpointer=checkpointer)
```

## API Reference

### LangGraphCoordinator

```python
coordinator = LangGraphCoordinator(
    client=client,                    # OllamaClient instance
    enable_thinking_window=True,      # Show thinking window
    max_iterations=100,               # Maximum iterations
    max_evolutions=3,                 # Maximum task evolutions
    checkpoint_path="data/cp.db",     # SQLite path (optional)
    enable_human_approval=False,      # Human-in-the-loop
)

# Execute task
result = coordinator.execute(task, thread_id=None)

# Resume from checkpoint
result = coordinator.resume(thread_id, human_input=None)

# Get current state
state = coordinator.get_state(thread_id)
```

### Convenience Function

```python
from src.loop import run_with_langgraph

result = run_with_langgraph(
    task="search for AI news",
    model="qwen2.5-coder:32b",
    checkpoint_path="data/checkpoints.db",
)
```

## Migration Checklist

- [x] Install LangGraph: `pip install langgraph langchain-core`
- [x] Created `langgraph_state.py` with TypedDict schema
- [x] Created `langgraph_coordinator.py` with graph-based execution
- [x] Updated `__init__.py` exports
- [x] Added CLI flags in `main.py`
- [x] Updated `commands.sh` documentation
- [ ] Test with various tasks
- [ ] Benchmark performance vs adaptive coordinator
- [ ] Add more human-in-the-loop checkpoints if needed

## Backward Compatibility

The old architectures are still available:

```bash
# Adaptive (default)
python -m src.main --task "your task"

# Legacy
python -m src.main --task "your task" --legacy

# LangGraph (new)
python -m src.main --task "your task" --langgraph
```

## Future Improvements

1. **Async Execution**: LangGraph supports async nodes for parallel processing
2. **Streaming**: Stream intermediate results to UI
3. **Sub-graphs**: Compose complex workflows from smaller graphs
4. **Time Travel**: Inspect and replay execution from any checkpoint
5. **Tool Integration**: Better integration with LangChain tools
